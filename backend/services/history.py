"""Tenant-scoped operation history queries and write helpers."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy import and_, func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

try:
    from backend import models
    from backend.services.redaction import redact_sensitive_text, redact_sensitive_values
    from backend.services.tenancy import require_tenant_membership
except ImportError:
    import models
    from services.redaction import redact_sensitive_text, redact_sensitive_values
    from services.tenancy import require_tenant_membership


_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
_ACTOR_TYPES = {"agent", "api", "function", "system", "user", "vmss", "worker"}


@dataclass(frozen=True)
class OperationRunPage:
    items: list[tuple[models.OperationRun, int, int]]
    total: int


async def _advisory_run_lock(db: AsyncSession, lock_key: str) -> None:
    """Serialize history sequence/idempotency writes on PostgreSQL.

    SQLite remains lock-free for focused unit tests. The projector uses the
    same ``hashtext(run_id)`` lock key for operation event sequencing.
    """

    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": lock_key},
        )


def _event_fingerprint(
    *,
    operation_run_id: uuid.UUID,
    project_id: Optional[uuid.UUID],
    action: str,
    actor_type: str,
    actor_id: str,
    details: Optional[str],
    event_data: dict[str, Any],
) -> str:
    canonical = json.dumps(
        {
            "operation_run_id": str(operation_run_id),
            "project_id": str(project_id) if project_id else None,
            "action": action,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "details": details,
            "event_data": event_data,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _assert_operation_idempotency_match(
    existing: models.OperationRun,
    *,
    operation_type: str,
    project_id: Optional[uuid.UUID],
    parent_operation_run_id: Optional[uuid.UUID],
    source_revision: Optional[str],
    input_digest: Optional[str],
) -> None:
    immutable_values = {
        "operation_type": (existing.operation_type, operation_type),
        "project_id": (existing.project_id, project_id),
        "parent_operation_run_id": (
            existing.parent_operation_run_id,
            parent_operation_run_id,
        ),
        "source_revision": (existing.source_revision, source_revision),
        "input_digest": (existing.input_digest, input_digest),
    }
    mismatches = [
        field_name
        for field_name, (stored, requested) in immutable_values.items()
        if stored != requested
    ]
    if mismatches:
        raise ValueError(
            "idempotency_key is already bound to a different operation request "
            f"({', '.join(mismatches)})."
        )


def _assert_event_idempotency_match(
    existing: models.ActivityEvent,
    *,
    operation_run_id: uuid.UUID,
    project_id: Optional[uuid.UUID],
    action: str,
    actor_type: str,
    actor_id: str,
    details: Optional[str],
    event_data: dict[str, Any],
    event_fingerprint: str,
) -> None:
    immutable_values = {
        "operation_run_id": (existing.operation_run_id, operation_run_id),
        "project_id": (existing.project_id, project_id),
        "action": (existing.action, action),
        "actor_type": (existing.actor_type, actor_type),
        "actor_id": (existing.actor_id, actor_id),
    }
    if any(stored != requested for stored, requested in immutable_values.values()):
        raise ValueError("external_event_id is already bound to a different event.")
    if existing.event_fingerprint:
        if existing.event_fingerprint != event_fingerprint:
            raise ValueError("external_event_id was replayed with different event content.")
        return
    if existing.details != details or (existing.event_data or {}) != event_data:
        raise ValueError("external_event_id was replayed with different event content.")


async def _require_project_in_tenant(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> models.Project:
    """Validate project access through its owning user's active membership.

    Project rows predate the SaaS tenancy layer. This bridge keeps them isolated
    without confusing the customer's Entra tenant ID with a ZeroOps tenant.
    A future project-table migration can replace this membership join with a
    direct non-null ``projects.tenant_id`` key.
    """

    result = await db.execute(
        select(models.Project)
        .join(
            models.TenantMembership,
            models.TenantMembership.user_id == models.Project.user_id,
        )
        .where(
            and_(
                models.Project.id == project_id,
                models.TenantMembership.tenant_id == tenant_id,
                models.TenantMembership.status == "active",
            )
        )
    )
    project = result.scalars().first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


async def create_operation_run(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    requested_by_user_id: uuid.UUID,
    operation_type: str,
    project_id: Optional[uuid.UUID] = None,
    parent_operation_run_id: Optional[uuid.UUID] = None,
    source_revision: Optional[str] = None,
    input_digest: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    summary: Optional[dict[str, Any]] = None,
    model_provider: Optional[str] = None,
    model_name: Optional[str] = None,
    model_version: Optional[str] = None,
    prompt_version: Optional[str] = None,
) -> models.OperationRun:
    """Create a redacted history record without storing raw execution input."""

    normalized_operation_type = operation_type.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", normalized_operation_type):
        raise ValueError("operation_type must be a lowercase identifier of at most 64 characters.")
    await require_tenant_membership(
        db,
        user_id=requested_by_user_id,
        tenant_id=tenant_id,
    )
    if project_id is not None:
        await _require_project_in_tenant(db, project_id=project_id, tenant_id=tenant_id)
    if parent_operation_run_id is not None:
        parent_result = await db.execute(
            select(models.OperationRun.id).where(
                and_(
                    models.OperationRun.id == parent_operation_run_id,
                    models.OperationRun.tenant_id == tenant_id,
                )
            )
        )
        if parent_result.scalar_one_or_none() is None:
            raise ValueError("Parent operation run does not belong to the tenant.")
    if input_digest is not None and not _DIGEST_PATTERN.fullmatch(input_digest):
        raise ValueError("input_digest must be a lowercase SHA-256 value.")

    normalized_source_revision = (source_revision or "").strip()[:255] or None
    clean_summary = redact_sensitive_values(summary or {})
    normalized_model_provider = (model_provider or "").strip()[:100] or None
    normalized_model_name = (model_name or "").strip()[:200] or None
    normalized_model_version = (model_version or "").strip()[:100] or None
    normalized_prompt_version = (prompt_version or "").strip()[:100] or None
    normalized_idempotency_key = (idempotency_key or "").strip() or None
    if normalized_idempotency_key:
        if len(normalized_idempotency_key) > 128:
            raise ValueError("idempotency_key must not exceed 128 characters.")
        await _advisory_run_lock(
            db,
            f"operation:{tenant_id}:{normalized_idempotency_key}",
        )
        existing_result = await db.execute(
            select(models.OperationRun).where(
                and_(
                    models.OperationRun.tenant_id == tenant_id,
                    models.OperationRun.idempotency_key == normalized_idempotency_key,
                )
            )
        )
        existing = existing_result.scalars().first()
        if existing is not None:
            _assert_operation_idempotency_match(
                existing,
                operation_type=normalized_operation_type,
                project_id=project_id,
                parent_operation_run_id=parent_operation_run_id,
                source_revision=normalized_source_revision,
                input_digest=input_digest,
            )
            return existing

    run = models.OperationRun(
        tenant_id=tenant_id,
        project_id=project_id,
        requested_by_user_id=requested_by_user_id,
        parent_operation_run_id=parent_operation_run_id,
        operation_type=normalized_operation_type,
        status="queued",
        source_revision=normalized_source_revision,
        input_digest=input_digest,
        idempotency_key=normalized_idempotency_key,
        summary=clean_summary,
        model_provider=normalized_model_provider,
        model_name=normalized_model_name,
        model_version=normalized_model_version,
        prompt_version=normalized_prompt_version,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    try:
        async with db.begin_nested():
            db.add(run)
            await db.flush()
    except IntegrityError:
        if not normalized_idempotency_key:
            raise
        existing_result = await db.execute(
            select(models.OperationRun).where(
                and_(
                    models.OperationRun.tenant_id == tenant_id,
                    models.OperationRun.idempotency_key == normalized_idempotency_key,
                )
            )
        )
        existing = existing_result.scalars().first()
        if existing is None:
            raise
        _assert_operation_idempotency_match(
            existing,
            operation_type=normalized_operation_type,
            project_id=project_id,
            parent_operation_run_id=parent_operation_run_id,
            source_revision=normalized_source_revision,
            input_digest=input_digest,
        )
        return existing
    return run


async def append_activity_event(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    operation_run_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    action: str,
    project_id: Optional[uuid.UUID] = None,
    actor_type: str = "user",
    actor_id: Optional[str] = None,
    details: Optional[str] = None,
    event_data: Optional[dict[str, Any]] = None,
    external_event_id: Optional[str] = None,
) -> models.ActivityEvent:
    """Append a redacted event to a tenant-owned operation timeline."""

    normalized_action = action.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,99}", normalized_action):
        raise ValueError("action must be a lowercase event identifier of at most 100 characters.")
    normalized_actor_type = actor_type.strip().lower()
    if normalized_actor_type not in _ACTOR_TYPES:
        raise ValueError(
            "actor_type must be agent, api, function, system, user, vmss, or worker."
        )
    normalized_actor_id = (actor_id or str(actor_user_id)).strip()
    if not normalized_actor_id or len(normalized_actor_id) > 128:
        raise ValueError("actor_id must contain between 1 and 128 characters.")
    await require_tenant_membership(db, user_id=actor_user_id, tenant_id=tenant_id)
    normalized_external_event_id = (external_event_id or "").strip() or None
    if normalized_external_event_id:
        if len(normalized_external_event_id) > 128:
            raise ValueError("external_event_id must not exceed 128 characters.")

    await _advisory_run_lock(db, str(operation_run_id))

    run_result = await db.execute(
        select(models.OperationRun).where(
            and_(
                models.OperationRun.id == operation_run_id,
                models.OperationRun.tenant_id == tenant_id,
            )
        )
    )
    run = run_result.scalars().first()
    if run is None:
        raise ValueError("Operation run does not belong to the tenant.")
    if run.project_id is None and project_id is not None:
        raise ValueError("A projectless operation cannot accept a project-bound event.")
    if project_id is not None and run.project_id != project_id:
        raise ValueError("Event project does not match the operation run.")
    event_project_id = run.project_id
    clean_details = (
        redact_sensitive_text(details, maximum_length=10_000) if details else None
    )
    clean_event_data = redact_sensitive_values(event_data or {})
    fingerprint = _event_fingerprint(
        operation_run_id=operation_run_id,
        project_id=event_project_id,
        action=normalized_action,
        actor_type=normalized_actor_type,
        actor_id=normalized_actor_id,
        details=clean_details,
        event_data=clean_event_data,
    )
    if normalized_external_event_id:
        existing_result = await db.execute(
            select(models.ActivityEvent).where(
                and_(
                    models.ActivityEvent.tenant_id == tenant_id,
                    models.ActivityEvent.external_event_id == normalized_external_event_id,
                )
            )
        )
        existing = existing_result.scalars().first()
        if existing is not None:
            _assert_event_idempotency_match(
                existing,
                operation_run_id=operation_run_id,
                project_id=event_project_id,
                action=normalized_action,
                actor_type=normalized_actor_type,
                actor_id=normalized_actor_id,
                details=clean_details,
                event_data=clean_event_data,
                event_fingerprint=fingerprint,
            )
            return existing

    sequence_result = await db.execute(
        select(func.max(models.ActivityEvent.sequence_number)).where(
            models.ActivityEvent.operation_run_id == operation_run_id
        )
    )
    next_sequence = (sequence_result.scalar_one_or_none() or 0) + 1
    event = models.ActivityEvent(
        tenant_id=tenant_id,
        operation_run_id=operation_run_id,
        user_id=actor_user_id,
        project_id=event_project_id,
        action=normalized_action,
        details=clean_details,
        actor_type=normalized_actor_type,
        actor_id=normalized_actor_id,
        event_data=clean_event_data,
        external_event_id=normalized_external_event_id,
        event_fingerprint=fingerprint,
        sequence_number=next_sequence,
    )
    try:
        # The savepoint lets a concurrent Service Bus retry lose the unique-key
        # race without aborting the projector's surrounding transaction.
        async with db.begin_nested():
            db.add(event)
            await db.flush()
    except IntegrityError:
        if not normalized_external_event_id:
            raise
        duplicate_result = await db.execute(
            select(models.ActivityEvent).where(
                and_(
                    models.ActivityEvent.tenant_id == tenant_id,
                    models.ActivityEvent.external_event_id == normalized_external_event_id,
                )
            )
        )
        duplicate = duplicate_result.scalars().first()
        if duplicate is None:
            raise
        _assert_event_idempotency_match(
            duplicate,
            operation_run_id=operation_run_id,
            project_id=event_project_id,
            action=normalized_action,
            actor_type=normalized_actor_type,
            actor_id=normalized_actor_id,
            details=clean_details,
            event_data=clean_event_data,
            event_fingerprint=fingerprint,
        )
        return duplicate
    return event


async def update_operation_status(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    operation_run_id: uuid.UUID,
    status_value: str,
    summary: Optional[dict[str, Any]] = None,
    error_code: Optional[str] = None,
    error_detail: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    model_cost_microusd: Optional[int] = None,
) -> models.OperationRun:
    result = await db.execute(
        select(models.OperationRun).where(
            and_(
                models.OperationRun.id == operation_run_id,
                models.OperationRun.tenant_id == tenant_id,
            )
        )
    )
    run = result.scalars().first()
    if run is None:
        raise ValueError("Operation run does not belong to the tenant.")

    normalized_status = status_value.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", normalized_status):
        raise ValueError("status must be a lowercase identifier of at most 64 characters.")
    run.status = normalized_status
    if summary is not None:
        run.summary = redact_sensitive_values(summary)
    run.error_code = (error_code or "").strip()[:100] or None
    run.redacted_error = (
        redact_sensitive_text(error_detail, maximum_length=10_000) if error_detail else None
    )
    run.input_tokens = input_tokens if input_tokens is None or input_tokens >= 0 else None
    run.output_tokens = output_tokens if output_tokens is None or output_tokens >= 0 else None
    run.model_cost_microusd = (
        model_cost_microusd if model_cost_microusd is None or model_cost_microusd >= 0 else None
    )
    if run.started_at is None and normalized_status not in {"queued", "pending"}:
        run.started_at = datetime.utcnow()
    if normalized_status in _TERMINAL_STATUSES:
        run.completed_at = datetime.utcnow()
    run.updated_at = datetime.utcnow()
    await db.flush()
    return run


async def list_operation_runs(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    page: int,
    per_page: int,
    operation_type: Optional[str] = None,
    status_value: Optional[str] = None,
    project_id: Optional[uuid.UUID] = None,
) -> OperationRunPage:
    conditions = [models.OperationRun.tenant_id == tenant_id]
    if operation_type:
        conditions.append(models.OperationRun.operation_type == operation_type.strip().lower())
    if status_value:
        conditions.append(models.OperationRun.status == status_value.strip().lower())
    if project_id:
        conditions.append(models.OperationRun.project_id == project_id)

    total_result = await db.execute(
        select(func.count(models.OperationRun.id)).where(and_(*conditions))
    )
    total = int(total_result.scalar_one())
    run_result = await db.execute(
        select(models.OperationRun)
        .where(and_(*conditions))
        .order_by(models.OperationRun.created_at.desc(), models.OperationRun.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    runs = list(run_result.scalars().all())
    if not runs:
        return OperationRunPage(items=[], total=total)

    run_ids = [run.id for run in runs]
    artifact_result = await db.execute(
        select(models.Artifact.operation_run_id, func.count(models.Artifact.id))
        .where(
            and_(
                models.Artifact.tenant_id == tenant_id,
                models.Artifact.operation_run_id.in_(run_ids),
                models.Artifact.access_scope == "user",
                models.Artifact.sanitization_status == "sanitized",
            )
        )
        .group_by(models.Artifact.operation_run_id)
    )
    event_result = await db.execute(
        select(models.ActivityEvent.operation_run_id, func.count(models.ActivityEvent.id))
        .where(
            and_(
                models.ActivityEvent.tenant_id == tenant_id,
                models.ActivityEvent.operation_run_id.in_(run_ids),
            )
        )
        .group_by(models.ActivityEvent.operation_run_id)
    )
    artifact_counts = {run_id: int(count) for run_id, count in artifact_result.all()}
    event_counts = {run_id: int(count) for run_id, count in event_result.all()}
    return OperationRunPage(
        items=[
            (run, artifact_counts.get(run.id, 0), event_counts.get(run.id, 0))
            for run in runs
        ],
        total=total,
    )


async def require_operation_run(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    operation_run_id: uuid.UUID,
) -> models.OperationRun:
    result = await db.execute(
        select(models.OperationRun).where(
            and_(
                models.OperationRun.id == operation_run_id,
                models.OperationRun.tenant_id == tenant_id,
            )
        )
    )
    run = result.scalars().first()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="History record not found.")
    return run


async def list_operation_events(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    operation_run_id: uuid.UUID,
) -> list[models.ActivityEvent]:
    result = await db.execute(
        select(models.ActivityEvent)
        .where(
            and_(
                models.ActivityEvent.tenant_id == tenant_id,
                models.ActivityEvent.operation_run_id == operation_run_id,
            )
        )
        .order_by(models.ActivityEvent.sequence_number, models.ActivityEvent.created_at)
    )
    return list(result.scalars().all())


async def list_operation_artifacts(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    operation_run_id: uuid.UUID,
) -> list[models.Artifact]:
    result = await db.execute(
        select(models.Artifact)
        .where(
            and_(
                models.Artifact.tenant_id == tenant_id,
                models.Artifact.operation_run_id == operation_run_id,
                models.Artifact.access_scope == "user",
                models.Artifact.sanitization_status == "sanitized",
            )
        )
        .order_by(models.Artifact.created_at, models.Artifact.id)
    )
    return list(result.scalars().all())


async def require_downloadable_artifact(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    operation_run_id: uuid.UUID,
    artifact_id: uuid.UUID,
) -> models.Artifact:
    result = await db.execute(
        select(models.Artifact).where(
            and_(
                models.Artifact.id == artifact_id,
                models.Artifact.tenant_id == tenant_id,
                models.Artifact.operation_run_id == operation_run_id,
                models.Artifact.access_scope == "user",
                models.Artifact.sanitization_status == "sanitized",
            )
        )
    )
    artifact = result.scalars().first()
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found.")
    return artifact
