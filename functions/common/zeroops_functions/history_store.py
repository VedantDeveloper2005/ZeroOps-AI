"""PostgreSQL projection adapter for versioned workflow events."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import ssl
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import asyncpg

from .contracts import EventArtifactV1, WorkflowEventV1
from .security import redact


POSTGRES_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"
_SAFE_MESSAGE_AUTHORIZATION = re.compile(
    r"(?i)\b(authorization\s*[:=]\s*(?:bearer|basic)\s+)[^\s,;]+"
)
_SAFE_MESSAGE_ASSIGNMENT = re.compile(
    r"(?im)\b("
    r"(?:api[_-]?key|client[_-]?secret|connection[_-]?string|database[_-]?url|"
    r"password|private[_-]?key|refresh[_-]?token|secret|token)"
    r")(\s*[:=]\s*)([^\s,;]+)"
)
_SAFE_MESSAGE_URI_CREDENTIAL = re.compile(
    r"(?i)([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@"
)
_STORAGE_LOCATOR_KEYS = {
    "artifact_uri",
    "blob_name",
    "blob_path",
    "blob_uri",
    "blob_version_id",
    "container",
    "output_blob_name",
    "output_version_id",
    "plan_handle",
    "result_uri",
    "saved_plan",
    "storage_container",
    "storage_path",
    "version_id",
}
_TERMINAL_OPERATION_EVENTS = {
    "repository_analysis": {"repository.analysis.completed"},
    "terraform_generation": {"terraform.generation.completed"},
    "terraform_validation": {"terraform.validation.completed"},
    "terraform_plan": {"terraform.plan.completed"},
    "terraform_apply": {"terraform.apply.completed"},
    "postdeploy_verification": {"postdeploy.verification.completed"},
}
_END_TO_END_OPERATION_TYPES = {
    "deployment",
    "end_to_end",
    "infrastructure_pipeline",
    "provisioning",
}
_END_TO_END_TERMINAL_EVENTS = {
    "postdeploy.verification.completed",
    "terraform.apply.completed",
}


def _uuid(value: str, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a canonical UUID") from error


def _json_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _utc_timestamp(value: datetime) -> datetime:
    """Normalize legacy naive event timestamps without changing event identity."""

    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _safe_message(value: str | None) -> str | None:
    if value is None:
        return None
    message = str(value)[:1024]
    message = _SAFE_MESSAGE_AUTHORIZATION.sub(r"\1[REDACTED]", message)
    message = _SAFE_MESSAGE_URI_CREDENTIAL.sub(r"\1[REDACTED]@", message)
    return _SAFE_MESSAGE_ASSIGNMENT.sub(r"\1\2[REDACTED]", message)


def _without_storage_locators(value: Any) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, child in value.items():
            normalized_key = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
            if (
                normalized_key in _STORAGE_LOCATOR_KEYS
                or normalized_key.endswith("_blob_name")
                or normalized_key.endswith("_blob_path")
                or normalized_key.endswith("_version_id")
                or normalized_key.endswith("_artifact_uri")
                or normalized_key.endswith("_result_uri")
            ):
                continue
            safe[str(key)] = _without_storage_locators(child)
        return safe
    if isinstance(value, list):
        return [_without_storage_locators(item) for item in value]
    return value


def _safe_event_artifact(artifact: EventArtifactV1) -> dict[str, Any]:
    """Return artifact metadata safe for the user-visible event timeline."""

    return {
        "artifact_id": artifact.artifact_id,
        "kind": artifact.kind,
        "sha256": artifact.sha256,
        "size_bytes": artifact.size_bytes,
        "content_type": artifact.content_type,
        "access_scope": artifact.access_scope,
        "sanitization_status": artifact.sanitization_status,
    }


def _safe_event_data(event: WorkflowEventV1) -> dict[str, Any]:
    return {
        "schema_version": event.schema_version,
        "event_id": event.event_id,
        "stage": event.stage,
        "attempt": event.attempt,
        "status": event.status,
        "actor_id": event.actor_id,
        "artifacts": [_safe_event_artifact(artifact) for artifact in event.artifacts],
        "metadata": redact(_without_storage_locators(event.safe_metadata)),
        "error_code": event.error_code,
    }


def _event_fingerprint(event: WorkflowEventV1) -> str:
    payload = event.model_dump(mode="json")
    # Queue-handler retries rebuild deterministic events and may assign a fresh
    # delivery timestamp. The event identity binds semantic content, not the
    # retry's wall-clock timestamp.
    payload.pop("occurred_at", None)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _artifact_projection_complete(artifact: EventArtifactV1) -> bool:
    fields = {
        "sha256": artifact.sha256,
        "storage_container": artifact.storage_container,
        "storage_path": artifact.storage_path,
        "size_bytes": artifact.size_bytes,
        "content_type": artifact.content_type,
    }
    supplied = [value is not None for value in fields.values()]
    if not any(supplied):
        return False
    missing = [
        field_name
        for field_name, value in fields.items()
        if value is None or (isinstance(value, str) and not value.strip())
    ]
    if missing:
        raise ValueError(
            "Artifact projection metadata must be all-or-none; missing "
            + ", ".join(missing)
        )
    return True


def _operation_status(
    operation_type: str,
    event: WorkflowEventV1,
) -> tuple[str, bool]:
    if event.status == "failed":
        return "failed", True

    normalized_operation = operation_type.strip().lower().replace("-", "_")
    operation_terminal_events = _TERMINAL_OPERATION_EVENTS.get(
        normalized_operation,
        set(),
    )
    if normalized_operation in _END_TO_END_OPERATION_TYPES:
        operation_terminal_events = _END_TO_END_TERMINAL_EVENTS
    elif not operation_terminal_events:
        operation_terminal_events = {
            f"{normalized_operation.replace('_', '.')}.completed"
        }
    is_terminal_completion = (
        event.status in {"completed", "degraded"}
        and event.event_type in operation_terminal_events
    )
    if is_terminal_completion:
        return ("degraded" if event.status == "degraded" else "completed"), True
    if event.status == "degraded":
        return f"{event.stage.replace('-', '_')}_degraded", False
    return event.event_type.replace(".", "_"), False


def _prior_attempt(summary: Any) -> int:
    try:
        value = int(_json_mapping(summary).get("last_attempt", 0))
    except (TypeError, ValueError):
        return 0
    return value if value >= 0 else 0


def _is_terminal_status(value: Any) -> bool:
    normalized = str(value or "").lower()
    return (
        normalized in {"completed", "degraded", "failed", "cancelled"}
        or normalized.endswith("_completed")
        or normalized.endswith("_degraded")
        or normalized.endswith("_failed")
    )


def _attempt_is_already_terminal(
    current_status: Any,
    *,
    prior_attempt: int,
    incoming_attempt: int,
) -> bool:
    return incoming_attempt == prior_attempt and _is_terminal_status(current_status)


@dataclass(frozen=True)
class PostgresSettings:
    host: str
    port: int
    database: str
    entra_user: str
    ssl_mode: str = "verify-full"

    @classmethod
    def from_environment(cls) -> "PostgresSettings":
        return cls(
            host=os.environ["POSTGRES_HOST"],
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.environ["POSTGRES_DATABASE"],
            entra_user=os.environ["POSTGRES_ENTRA_USER"],
            ssl_mode=os.getenv("POSTGRES_SSL_MODE", "verify-full"),
        )


class PostgresHistoryProjector:
    def __init__(self, settings: PostgresSettings, credential: Any):
        self.settings = settings
        self.credential = credential

    async def _connect(self) -> asyncpg.Connection:
        token = await asyncio.to_thread(
            self.credential.get_token,
            POSTGRES_SCOPE,
        )
        ssl_context: ssl.SSLContext | str | None
        if self.settings.ssl_mode in {"require", "verify-ca", "verify-full"}:
            ssl_context = ssl.create_default_context()
            if self.settings.ssl_mode == "require":
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
        else:
            raise RuntimeError("PostgreSQL TLS cannot be disabled")
        return await asyncpg.connect(
            host=self.settings.host,
            port=self.settings.port,
            database=self.settings.database,
            user=self.settings.entra_user,
            password=token.token,
            ssl=ssl_context,
            command_timeout=30,
            server_settings={"application_name": "zeroops-history-projector"},
        )

    async def project(self, event: WorkflowEventV1) -> bool:
        """Project one event; return False when it was already processed."""

        tenant_id = _uuid(event.tenant_id, "tenant_id")
        run_id = _uuid(event.run_id, "run_id")
        project_id = _uuid(event.project_id, "project_id")
        event_data = _safe_event_data(event)
        safe_message = _safe_message(event.safe_message)
        fingerprint = _event_fingerprint(event)
        occurred_at = _utc_timestamp(event.occurred_at)
        connection = await self._connect()
        try:
            async with connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1))",
                    str(run_id),
                )
                run = await connection.fetchrow(
                    """
                    SELECT requested_by_user_id, project_id, operation_type,
                           status, summary
                    FROM operation_runs
                    WHERE id = $1 AND tenant_id = $2
                    FOR UPDATE
                    """,
                    run_id,
                    tenant_id,
                )
                if run is None:
                    raise ValueError("Workflow event references an unknown tenant operation")
                run_project_id = run["project_id"]
                if run_project_id != project_id:
                    raise ValueError("Workflow event project does not exactly match operation")

                duplicate = await connection.fetchrow(
                    """
                    SELECT operation_run_id, project_id, action, actor_type,
                           actor_id, details, event_data, event_fingerprint
                    FROM activity_events
                    WHERE tenant_id = $1 AND external_event_id = $2
                    """,
                    tenant_id,
                    event.event_id,
                )
                if duplicate:
                    self._assert_duplicate_matches(
                        duplicate,
                        event=event,
                        run_id=run_id,
                        project_id=project_id,
                        safe_message=safe_message,
                        event_data=event_data,
                        fingerprint=fingerprint,
                    )
                    return False

                user_id = run["requested_by_user_id"]
                sequence = await connection.fetchval(
                    """
                    SELECT COALESCE(MAX(sequence_number), 0) + 1
                    FROM activity_events
                    WHERE operation_run_id = $1
                    """,
                    run_id,
                )
                activity_event_id = uuid.uuid4()
                await connection.execute(
                    """
                    INSERT INTO activity_events (
                        id, tenant_id, operation_run_id, user_id, project_id,
                        action, details, actor_type, actor_id, event_data,
                        external_event_id, event_fingerprint, sequence_number,
                        created_at
                    )
                    VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb,
                        $11, $12, $13, $14::timestamptz AT TIME ZONE 'UTC'
                    )
                    """,
                    activity_event_id,
                    tenant_id,
                    run_id,
                    user_id,
                    project_id,
                    event.event_type,
                    safe_message,
                    event.actor_type,
                    event.actor_id,
                    json.dumps(event_data, separators=(",", ":")),
                    event.event_id,
                    fingerprint,
                    sequence,
                    occurred_at,
                )
                for artifact in event.artifacts:
                    await self._project_artifact(
                        connection,
                        event=event,
                        artifact=artifact,
                        tenant_id=tenant_id,
                        run_id=run_id,
                        project_id=project_id,
                        user_id=user_id,
                    )
                prior_attempt = _prior_attempt(run["summary"])
                stale_attempt = event.attempt < prior_attempt
                same_attempt_terminal_regression = _attempt_is_already_terminal(
                    run["status"],
                    prior_attempt=prior_attempt,
                    incoming_attempt=event.attempt,
                )
                if not stale_attempt and not same_attempt_terminal_regression:
                    await self._update_operation(
                        connection,
                        event,
                        tenant_id,
                        run_id,
                        operation_type=run["operation_type"],
                        activity_event_id=activity_event_id,
                        sequence=sequence,
                        reopen_terminal=(
                            event.status == "started" and event.attempt > prior_attempt
                        ),
                    )
            return True
        finally:
            await connection.close()

    @staticmethod
    def _assert_duplicate_matches(
        duplicate: asyncpg.Record,
        *,
        event: WorkflowEventV1,
        run_id: uuid.UUID,
        project_id: uuid.UUID,
        safe_message: str | None,
        event_data: dict[str, Any],
        fingerprint: str,
    ) -> None:
        immutable_values = {
            "operation_run_id": (duplicate["operation_run_id"], run_id),
            "project_id": (duplicate["project_id"], project_id),
            "action": (duplicate["action"], event.event_type),
            "actor_type": (duplicate["actor_type"], event.actor_type),
            "actor_id": (duplicate["actor_id"], event.actor_id),
        }
        if any(stored != incoming for stored, incoming in immutable_values.values()):
            raise ValueError("Workflow event ID is already bound to a different event")
        stored_fingerprint = duplicate["event_fingerprint"]
        if stored_fingerprint:
            if stored_fingerprint != fingerprint:
                raise ValueError("Workflow event ID was replayed with different content")
            return
        if duplicate["details"] != safe_message:
            raise ValueError("Workflow event ID was replayed with different content")
        if _json_mapping(duplicate["event_data"]) != event_data:
            raise ValueError("Workflow event ID was replayed with different content")

    @staticmethod
    async def _project_artifact(
        connection: asyncpg.Connection,
        *,
        event: WorkflowEventV1,
        artifact: EventArtifactV1,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID | None,
    ) -> None:
        if not _artifact_projection_complete(artifact):
            return
        artifact_id = _uuid(artifact.artifact_id, "artifact_id")
        display_name = re.sub(
            r"[\x00-\x1f\x7f\"'\\/:;]+",
            "-",
            artifact.storage_path.rsplit("/", 1)[-1],
        ).strip(" .-")[:160] or "artifact"
        metadata = redact(
            {
                "blob_version_id": artifact.blob_version_id,
                "workflow_event_id": event.event_id,
                "correlation_id": event.correlation_id,
            }
        )
        await connection.execute(
            """
            INSERT INTO artifacts (
                id, artifact_key, tenant_id, operation_run_id, project_id,
                created_by_user_id, kind, display_name, content_type,
                storage_container, storage_path, sha256_digest, size_bytes,
                version, access_scope, sanitization_status, metadata, created_at
            )
            VALUES (
                $1, $1, $2, $3, $4, $5, $6, $7, $8,
                $9, $10, $11, $12, 1, $13, $14, $15::jsonb,
                $16::timestamptz AT TIME ZONE 'UTC'
            )
            ON CONFLICT (id) DO NOTHING
            """,
            artifact_id,
            tenant_id,
            run_id,
            project_id,
            user_id,
            artifact.kind,
            display_name,
            artifact.content_type,
            artifact.storage_container,
            artifact.storage_path,
            artifact.sha256,
            artifact.size_bytes,
            artifact.access_scope,
            artifact.sanitization_status,
            json.dumps(metadata, separators=(",", ":")),
            _utc_timestamp(event.occurred_at),
        )
        existing = await connection.fetchrow(
            """
            SELECT artifact_key, tenant_id, operation_run_id, project_id,
                   created_by_user_id, kind, display_name, content_type,
                   storage_container, storage_path, sha256_digest, size_bytes,
                   version, access_scope, sanitization_status
            FROM artifacts
            WHERE id = $1
            """,
            artifact_id,
        )
        if existing is None:
            raise ValueError("Artifact projection did not produce a durable row")
        expected = (
            artifact_id,
            tenant_id,
            run_id,
            project_id,
            user_id,
            artifact.kind,
            display_name,
            artifact.content_type,
            artifact.storage_container,
            artifact.storage_path,
            artifact.sha256,
            artifact.size_bytes,
            1,
            artifact.access_scope,
            artifact.sanitization_status,
        )
        actual = (
            existing["artifact_key"],
            existing["tenant_id"],
            existing["operation_run_id"],
            existing["project_id"],
            existing["created_by_user_id"],
            existing["kind"],
            existing["display_name"],
            existing["content_type"],
            existing["storage_container"],
            existing["storage_path"],
            existing["sha256_digest"],
            existing["size_bytes"],
            existing["version"],
            existing["access_scope"],
            existing["sanitization_status"],
        )
        if actual != expected:
            raise ValueError("Artifact ID was replayed with different immutable metadata")

    @staticmethod
    async def _update_operation(
        connection: asyncpg.Connection,
        event: WorkflowEventV1,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        *,
        operation_type: str,
        activity_event_id: uuid.UUID,
        sequence: int,
        reopen_terminal: bool,
    ) -> None:
        metadata = _json_mapping(redact(event.safe_metadata))
        status_value, terminal = _operation_status(operation_type, event)
        occurred_at = _utc_timestamp(event.occurred_at)
        await connection.execute(
            """
            UPDATE operation_runs
            SET status = $3,
                summary = COALESCE(summary, '{}'::jsonb) || $4::jsonb,
                model_provider = COALESCE($5, model_provider),
                model_name = COALESCE($6, model_name),
                model_version = COALESCE($7, model_version),
                prompt_version = COALESCE($8, prompt_version),
                input_tokens = COALESCE($9, input_tokens),
                output_tokens = COALESCE($10, output_tokens),
                model_cost_microusd = COALESCE($11, model_cost_microusd),
                error_code = CASE
                    WHEN $12 IS NOT NULL THEN $12
                    WHEN $15 THEN NULL
                    ELSE error_code
                END,
                redacted_error = CASE
                    WHEN $13 IS NOT NULL THEN $13
                    WHEN $15 THEN NULL
                    ELSE redacted_error
                END,
                started_at = COALESCE(
                    started_at,
                    $14::timestamptz AT TIME ZONE 'UTC'
                ),
                completed_at = CASE
                    WHEN $15 THEN $14::timestamptz AT TIME ZONE 'UTC'
                    WHEN $16 THEN NULL
                    ELSE completed_at
                END,
                updated_at = GREATEST(
                    COALESCE(
                        updated_at,
                        $14::timestamptz AT TIME ZONE 'UTC'
                    ),
                    $14::timestamptz AT TIME ZONE 'UTC'
                )
            WHERE id = $1 AND tenant_id = $2
              AND NOT EXISTS (
                  SELECT 1
                  FROM activity_events AS newer
                  WHERE newer.operation_run_id = $1
                    AND newer.id <> $17
                    AND (
                        CASE
                            WHEN COALESCE(newer.event_data->>'attempt', '')
                                ~ '^[0-9]+$'
                            THEN (newer.event_data->>'attempt')::integer
                            ELSE 1
                        END > $18
                        OR (
                            CASE
                                WHEN COALESCE(newer.event_data->>'attempt', '')
                                    ~ '^[0-9]+$'
                                THEN (newer.event_data->>'attempt')::integer
                                ELSE 1
                            END = $18
                            AND (
                                newer.created_at >
                                    $14::timestamptz AT TIME ZONE 'UTC'
                                OR (
                                    newer.created_at =
                                        $14::timestamptz AT TIME ZONE 'UTC'
                                    AND COALESCE(newer.sequence_number, 0) > $19
                                )
                            )
                        )
                    )
              )
            """,
            run_id,
            tenant_id,
            status_value,
            json.dumps(
                {
                    "last_event_type": event.event_type,
                    "last_stage": event.stage,
                    "last_attempt": event.attempt,
                    "last_status": event.status,
                    "last_event_occurred_at": occurred_at.isoformat(),
                    "last_metadata": metadata,
                },
                separators=(",", ":"),
            ),
            _string_or_none(metadata.get("provider")),
            _string_or_none(metadata.get("model")),
            _string_or_none(metadata.get("model_version")),
            _string_or_none(metadata.get("prompt_version")),
            _nonnegative_int_or_none(
                metadata.get("input_tokens"),
                maximum=2_147_483_647,
            ),
            _nonnegative_int_or_none(
                metadata.get("output_tokens"),
                maximum=2_147_483_647,
            ),
            _nonnegative_int_or_none(
                metadata.get(
                    "model_cost_microusd",
                    metadata.get("cost_microusd"),
                ),
                maximum=9_223_372_036_854_775_807,
            ),
            event.error_code,
            _safe_message(event.safe_message),
            occurred_at,
            terminal,
            reopen_terminal,
            activity_event_id,
            event.attempt,
            sequence,
        )


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized[:200] or None


def _nonnegative_int_or_none(
    value: Any,
    *,
    maximum: int = 9_223_372_036_854_775_807,
) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if 0 <= result <= maximum else None
