"""Durable, change-aware DevSecOps deployment orchestration.

The worker executes immutable source revisions and records every material
decision in normalized pipeline tables.  Repository output, scanner output,
and provider failures are reduced to bounded redacted evidence before they are
logged, persisted, or sent to the analysis boundary.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import logging
import re
import time
import uuid
from typing import Any, Callable, Dict, Iterable, List, Mapping

from fastapi import WebSocket
from sqlalchemy import desc, func
from sqlalchemy.future import select
from sqlalchemy.orm.attributes import flag_modified

try:
    from backend import config, models
    from backend.database import AsyncSessionLocal
    from backend.services import (
        ai,
        aks,
        app_service,
        azure_connector,
        change_detection,
        deployment_targets,
        git,
        pipeline_evidence,
        pipeline_approval,
        pipeline_records,
        repository_checks,
        repository_snapshot,
        security_scanner,
        vault,
    )
    from backend.services.pipeline_state import PipelineContext, initialize_stages
    from backend.services.redaction import redact_sensitive_text, redact_sensitive_values
except ImportError:  # pragma: no cover - worker-style imports
    import config, models
    from database import AsyncSessionLocal
    from services import (
        ai,
        aks,
        app_service,
        azure_connector,
        change_detection,
        deployment_targets,
        git,
        pipeline_evidence,
        pipeline_approval,
        pipeline_records,
        repository_checks,
        repository_snapshot,
        security_scanner,
        vault,
    )
    from services.pipeline_state import PipelineContext, initialize_stages
    from services.redaction import redact_sensitive_text, redact_sensitive_values


logger = logging.getLogger("zeroops.pipeline")

# Same-process listeners remain a compatibility optimization.  The production
# WebSocket stream polls authoritative database state and works across workers.
connections: Dict[str, List[WebSocket]] = {}
deployments_history: list[Any] = []


def initialize_pipeline_stages(context: PipelineContext) -> list[dict[str, Any]]:
    """Serialize the normalized stage plan for legacy deployment responses."""

    return [
        {
            "id": stage.stage_order,
            "key": stage.key,
            "label": stage.display_name,
            "status": stage.status,
            "duration": "",
            "required": stage.is_required,
            "reason": stage.status_reason,
            "tool": stage.tool_name,
        }
        for stage in initialize_stages(context)
    ]


def normalize_project_id(repo_name: str) -> str:
    raw = (repo_name.split("/")[-1] or "web-app").lower()
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in raw).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned or "web-app"


async def register_connection(deploy_id: str, websocket: WebSocket) -> None:
    connections.setdefault(deploy_id, []).append(websocket)


def unregister_connection(deploy_id: str, websocket: WebSocket) -> None:
    listeners = connections.get(deploy_id)
    if not listeners:
        return
    if websocket in listeners:
        listeners.remove(websocket)
    if not listeners:
        connections.pop(deploy_id, None)


async def broadcast_message(deploy_id: str, message: dict[str, Any]) -> None:
    listeners = connections.get(deploy_id, ())
    if listeners:
        await asyncio.gather(
            *(listener.send_text(json.dumps(message)) for listener in listeners),
            return_exceptions=True,
        )


def _snapshot_events(
    deployment: models.Deployment,
    logs: Iterable[models.DeploymentLog],
    seen_log_ids: set[str],
    stage_states: dict[str, tuple[Any, ...]],
    last_status: str | None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Convert authoritative database state into de-duplicated stream events."""

    events: list[dict[str, Any]] = []
    for log_entry in logs:
        log_id = str(log_entry.id)
        if log_id in seen_log_ids:
            continue
        seen_log_ids.add(log_id)
        events.append({
            "type": "log",
            "text": log_entry.message,
            "lineType": str(log_entry.level or "info").lower(),
            "line_number": log_entry.line_number,
            "timestamp": log_entry.timestamp.isoformat() if log_entry.timestamp else None,
        })

    metadata = deployment.infrastructure_metadata or {}
    stages = metadata.get("stages") if isinstance(metadata, dict) else []
    if isinstance(stages, list):
        for stage in stages:
            if not isinstance(stage, dict) or stage.get("id") is None:
                continue
            stage_key = str(stage["id"])
            signature = (
                stage.get("label"),
                stage.get("status") or "queued",
                stage.get("duration") or "",
                stage.get("reason"),
            )
            if stage_states.get(stage_key) == signature:
                continue
            stage_states[stage_key] = signature
            events.append({
                "type": "stage",
                "id": stage["id"],
                "key": stage.get("key"),
                "label": stage.get("label"),
                "status": signature[1],
                "duration": signature[2],
                "reason": signature[3],
            })

    current_status = deployment.status
    if current_status != last_status:
        events.append({
            "type": "status",
            "status": current_status,
            "live_url": deployment.live_url,
            "failure_reason": deployment.failure_reason if current_status == "failed" else None,
        })
    return events, current_status


async def stream_deployment_updates(
    deploy_id: str,
    websocket: WebSocket,
    *,
    poll_interval: float = 0.75,
) -> None:
    """Stream logs and stage state from the shared database."""

    deployment_id = uuid.UUID(deploy_id)
    seen_log_ids: set[str] = set()
    stage_states: dict[str, tuple[Any, ...]] = {}
    last_status: str | None = None
    last_log_line = 0
    page_size = 500
    terminal_statuses = {"running", "failed", "stopped", "rolled_back"}

    while True:
        async with AsyncSessionLocal() as db:
            deployment_result = await db.execute(
                select(models.Deployment).where(models.Deployment.id == deployment_id)
            )
            deployment = deployment_result.scalars().first()
            if deployment is None:
                await websocket.send_text(json.dumps({"type": "status", "status": "unavailable"}))
                return
            logs_result = await db.execute(
                select(models.DeploymentLog)
                .where(
                    models.DeploymentLog.deployment_id == deployment_id,
                    models.DeploymentLog.line_number > last_log_line,
                )
                .order_by(
                    models.DeploymentLog.line_number.asc(),
                    models.DeploymentLog.timestamp.asc(),
                )
                .limit(page_size)
            )
            stored_logs = list(logs_result.scalars().all())

        events, last_status = _snapshot_events(
            deployment,
            stored_logs,
            seen_log_ids,
            stage_states,
            last_status,
        )
        for event in events:
            await websocket.send_text(json.dumps(event))
        if stored_logs:
            last_log_line = max(last_log_line, max(item.line_number for item in stored_logs))
        if deployment.status in terminal_statuses and len(stored_logs) < page_size:
            return
        if len(stored_logs) == page_size:
            continue
        await asyncio.sleep(poll_interval)


class PipelineLogger:
    """Redacting deployment logger with durable, ordered database writes."""

    def __init__(self, deploy_id: str):
        self.deploy_id = deploy_id
        self.log_buffer: list[dict[str, Any]] = []
        self.line_counter = 0

    async def log(self, message: str, level: str = "INFO") -> None:
        self.line_counter += 1
        safe_message = redact_sensitive_text(str(message), maximum_length=20_000)
        await broadcast_message(
            self.deploy_id,
            {"type": "log", "text": safe_message, "lineType": level.lower()},
        )
        self.log_buffer.append({
            "line_number": self.line_counter,
            "level": level,
            "message": safe_message,
            "timestamp": datetime.utcnow(),
        })

    async def flush_to_db(self, db_session: Any) -> None:
        if not self.log_buffer:
            return
        pending = list(self.log_buffer)
        try:
            for log_data in pending:
                db_session.add(models.DeploymentLog(
                    deployment_id=uuid.UUID(self.deploy_id),
                    **log_data,
                ))
            await db_session.commit()
            del self.log_buffer[: len(pending)]
        except Exception as error:
            await db_session.rollback()
            logger.error(
                "Deployment logs could not be persisted: %s",
                redact_sensitive_text(type(error).__name__, maximum_length=200),
            )
            raise RuntimeError("Deployment logs could not be persisted safely.") from error


def enqueue_deployment(
    deploy_id: str,
    repo_name: str,
    branch: str,
    background_tasks: Any,
    clone_token: str | None = None,
) -> None:
    background_tasks.add_task(
        run_deployment_pipeline,
        deploy_id,
        repo_name,
        branch,
        clone_token,
    )


class PipelineExecutionError(RuntimeError):
    """A pre-redacted failure with an explicit durable terminal state."""

    def __init__(
        self,
        message: str,
        *,
        failure_code: str,
        status: str = "failed",
        stage_key: str | None = None,
    ) -> None:
        self.safe_message = redact_sensitive_text(message, maximum_length=2_000)
        self.failure_code = re.sub(r"[^A-Z0-9_]", "_", failure_code.upper())[:64]
        self.status = status if status in {"failed", "blocked", "unavailable"} else "failed"
        self.stage_key = stage_key
        super().__init__(self.safe_message)


def _duration_label(started_at: datetime | None, completed_at: datetime | None) -> str:
    if not started_at or not completed_at:
        return "..." if started_at else ""
    start = started_at if started_at.tzinfo else started_at.replace(tzinfo=timezone.utc)
    end = completed_at if completed_at.tzinfo else completed_at.replace(tzinfo=timezone.utc)
    return f"{max(0.0, (end - start).total_seconds()):.1f}s"


def _stage_payload(stage: models.PipelineStageAttempt) -> dict[str, Any]:
    return {
        "id": stage.stage_order,
        "key": stage.stage_key,
        "label": stage.display_name,
        "status": stage.status,
        "duration": _duration_label(stage.started_at, stage.completed_at),
        "required": bool(stage.is_required),
        "reason": stage.status_reason or stage.redacted_error,
        "tool": stage.tool_name,
    }


def _evidence(label: str, value: Any, *, kind: str = "record") -> dict[str, Any]:
    safe = redact_sensitive_values({"label": label, "value": value, "kind": kind})
    return safe if isinstance(safe, dict) else {"label": label, "value": "Recorded", "kind": kind}


class _DurableRuntime:
    """Persist and publish guarded stage transitions from one DB session."""

    def __init__(
        self,
        *,
        db: Any,
        deployment: models.Deployment,
        pipeline_run: models.PipelineRun,
        deploy_id: str,
        lease_guard: Callable[[], bool] | None,
    ) -> None:
        self.db = db
        self.deployment = deployment
        self.pipeline_run = pipeline_run
        self.deploy_id = deploy_id
        self.lease_guard = lease_guard
        self.stages: dict[str, models.PipelineStageAttempt] = {}

    def require_lease(self) -> None:
        if self.lease_guard is not None and not self.lease_guard():
            raise PipelineExecutionError(
                "The deployment worker lost its queue lease; release processing stopped.",
                failure_code="WORKER_LEASE_LOST",
            )

    async def refresh(self) -> None:
        stages = await pipeline_records.list_stage_attempts(self.db, self.pipeline_run.id)
        self.stages = {stage.stage_key: stage for stage in stages}

    async def _sync_metadata(self) -> None:
        await self.refresh()
        ordered = sorted(self.stages.values(), key=lambda item: (item.stage_order, item.attempt_number))
        metadata = dict(self.deployment.infrastructure_metadata or {})
        metadata["stages"] = [_stage_payload(stage) for stage in ordered]
        self.deployment.infrastructure_metadata = metadata
        flag_modified(self.deployment, "infrastructure_metadata")

    async def reconcile(self, context: PipelineContext) -> None:
        self.require_lease()
        await pipeline_records.reconcile_pipeline_plan(
            self.db,
            pipeline_run=self.pipeline_run,
            context=context,
        )
        await self._sync_metadata()
        await self.db.commit()
        for stage in self.stages.values():
            await broadcast_message(self.deploy_id, {"type": "stage", **_stage_payload(stage)})

    async def transition(
        self,
        stage_key: str,
        status: str,
        *,
        reason: str | None = None,
        failure_code: str | None = None,
        redacted_error: str | None = None,
        evidence: list[dict[str, Any]] | None = None,
        result_metadata: dict[str, Any] | None = None,
        tool_version: str | None = None,
    ) -> models.PipelineStageAttempt:
        self.require_lease()
        stage = await pipeline_records.transition_pipeline_stage(
            self.db,
            pipeline_run=self.pipeline_run,
            stage_key=stage_key,
            target_status=status,
            reason=reason,
            failure_code=failure_code,
            redacted_error=redacted_error,
            evidence=redact_sensitive_values(evidence or []) if evidence is not None else None,
            result_metadata=(
                redact_sensitive_values(result_metadata or {})
                if result_metadata is not None
                else None
            ),
            tool_version=tool_version,
        )
        await self._sync_metadata()
        await self.db.commit()
        await broadcast_message(self.deploy_id, {"type": "stage", **_stage_payload(stage)})
        return stage

    async def start(self, stage_key: str) -> models.PipelineStageAttempt:
        return await self.transition(stage_key, "running")

    async def succeed(
        self,
        stage_key: str,
        *,
        evidence: list[dict[str, Any]] | None = None,
        result_metadata: dict[str, Any] | None = None,
        tool_version: str | None = None,
    ) -> models.PipelineStageAttempt:
        return await self.transition(
            stage_key,
            "succeeded",
            evidence=evidence,
            result_metadata=result_metadata,
            tool_version=tool_version,
        )

    async def skip_queued(self, stage_key: str, reason: str) -> models.PipelineStageAttempt:
        await self.refresh()
        stage = self.stages[stage_key]
        if stage.status == "skipped":
            return stage
        if stage.status != "queued":
            raise PipelineExecutionError(
                f"Stage {stage_key} could not be skipped from its recorded state.",
                failure_code="INVALID_PIPELINE_STATE",
                stage_key=stage_key,
            )
        return await self.transition(stage_key, "skipped", reason=reason)

    async def is_queued(self, stage_key: str) -> bool:
        await self.refresh()
        return self.stages.get(stage_key) is not None and self.stages[stage_key].status == "queued"


def _environment_variable_names(metadata: Mapping[str, Any], snapshot_names: Iterable[str]) -> tuple[str, ...]:
    names = {str(name).strip() for name in snapshot_names if str(name).strip()}
    for item in metadata.get("environment_variables") or []:
        if isinstance(item, str) and item.strip():
            names.add(item.strip())
        elif isinstance(item, Mapping) and str(item.get("key") or "").strip():
            names.add(str(item["key"]).strip())
    return tuple(sorted(names))


def _repository_capabilities(facts: repository_checks.RepositoryFacts) -> dict[str, bool]:
    components = tuple(facts.components)
    return {
        "dependencies": any(component.has_declared_dependencies for component in components),
        "quality": any(component.quality_tools or set(component.scripts) & {"lint", "typecheck", "check", "format:check"} for component in components),
        "tests": any(component.test_tool or set(component.scripts) & {"test", "test:ci", "test:unit"} for component in components),
        "build": any(component.build_kind for component in components),
    }


def _diff_evidence(
    *,
    repo_path: str,
    previous: models.RepositoryAnalysisSnapshot | None,
    current: change_detection.RepositoryFingerprint,
    snapshot: repository_snapshot.RepositorySnapshot,
    clone_token: str | None,
) -> tuple[Iterable[str] | Mapping[str, bytes], str]:
    if previous is None:
        return snapshot.files, "initial_snapshot"
    changed_paths: tuple[str, ...] | None = None
    if re.fullmatch(r"[0-9a-f]{40}", previous.source_revision or "") and re.fullmatch(
        r"[0-9a-f]{40}", current.commit_sha or ""
    ):
        try:
            changed_paths = git.get_changed_files(
                repo_path,
                previous.source_revision,
                current.commit_sha,
                clone_token,
            )
        except (OSError, RuntimeError, ValueError):
            changed_paths = None
    if changed_paths is not None:
        return changed_paths, "git_diff"
    if previous.repository_fingerprint == current.repository_fingerprint:
        return (), "matching_fingerprint"
    # Archive sources and shallow clones may not carry the baseline object.
    # Classifying the current bounded snapshot is conservative: it may request
    # extra analysis, but can never hide a deployment-relevant change.
    return snapshot.files, "fingerprint_fallback"


def _image_digest(image_ref: str | None) -> str | None:
    if not image_ref:
        return None
    match = re.search(r"@sha256:([0-9a-f]{64})$", image_ref)
    return match.group(1) if match else None


async def _validated_pipeline_approval(
    db: Any,
    *,
    pipeline_run: models.PipelineRun,
    deployment: models.Deployment,
) -> tuple[dict[str, Any] | None, str]:
    metadata = deployment.infrastructure_metadata or {}
    approval = metadata.get("pipeline_approval") if isinstance(metadata, Mapping) else None
    if not isinstance(approval, Mapping):
        return None, "No explicit pipeline approval is attached to this immutable release."
    architecture_plan = metadata.get("architecture_plan") if isinstance(metadata, Mapping) else None
    if not isinstance(architecture_plan, Mapping):
        return None, "The approved architecture plan reference is unavailable."
    if pipeline_run.configuration_id is None:
        return None, "The approved pipeline configuration reference is unavailable."
    configuration_result = await db.execute(
        select(models.ProjectPipelineConfiguration).where(
            models.ProjectPipelineConfiguration.id == pipeline_run.configuration_id
        )
    )
    configuration = configuration_result.scalars().first()
    if configuration is None:
        return None, "The approved pipeline configuration is unavailable."
    expected = {
        "tenant_id": str(pipeline_run.tenant_id),
        "project_id": str(pipeline_run.project_id),
        "approved_deployment_id": str(deployment.id),
        "approved_pipeline_run_id": str(pipeline_run.id),
        "source_revision": str(pipeline_run.source_revision).lower(),
        "branch": pipeline_run.branch,
        "target_type": pipeline_run.target_type,
        "plan_id": str(architecture_plan.get("id")),
        "plan_revision": int(architecture_plan.get("revision") or 0),
        "configuration_id": str(configuration.id),
        "configuration_version": configuration.version,
        "configuration_digest": str(configuration.config_digest or ""),
    }
    verification = pipeline_approval.verify_pipeline_approval(
        approval,
        secret=config.JWT_SECRET,
        expected=expected,
    )
    if not verification.valid or not verification.claims:
        return None, verification.reason
    claims = verification.claims
    try:
        prior_run_id = uuid.UUID(str(claims["validation_run_id"]))
        prior_deployment_id = uuid.UUID(str(claims["validation_deployment_id"]))
    except (TypeError, ValueError):  # pragma: no cover - schema verifier invariant
        return None, "Pipeline approval contains an invalid validation reference."

    prior_result = await db.execute(
        select(models.PipelineRun).where(
            models.PipelineRun.id == prior_run_id,
            models.PipelineRun.tenant_id == pipeline_run.tenant_id,
            models.PipelineRun.project_id == pipeline_run.project_id,
        )
    )
    prior_run = prior_result.scalars().first()
    signed_configuration_id = uuid.UUID(str(claims["configuration_id"]))
    if (
        prior_run is None
        or prior_run.status != "blocked"
        or prior_run.failure_code != "DEPLOYMENT_APPROVAL_REQUIRED"
        or not prior_run.approval_required
        or prior_run.source_revision != pipeline_run.source_revision
        or prior_run.branch != pipeline_run.branch
        or prior_run.target_type != pipeline_run.target_type
        or prior_run.deployment_id != prior_deployment_id
        or prior_run.configuration_id != signed_configuration_id
        or prior_run.configuration_version != int(claims["configuration_version"])
    ):
        return None, "The referenced validation run is not an approval-ready run for this release."
    prior_stages = await pipeline_records.list_stage_attempts(db, prior_run.id)
    approval_stage = next((stage for stage in prior_stages if stage.stage_key == "approval"), None)
    if (
        approval_stage is None
        or approval_stage.status != "blocked"
        or not approval_stage.is_required
    ):
        return None, "The referenced validation run did not stop at the approval gate."
    if any(
        stage.stage_order < approval_stage.stage_order
        and stage.status not in {"succeeded", "skipped"}
        for stage in prior_stages
    ):
        return None, "The referenced validation run did not pass every predecessor stage."

    prior_deployment_result = await db.execute(
        select(models.Deployment).where(models.Deployment.id == prior_deployment_id)
    )
    prior_deployment = prior_deployment_result.scalars().first()
    if (
        prior_deployment is None
        or prior_deployment.user_id != deployment.user_id
        or prior_deployment.project_id != deployment.project_id
        or prior_deployment.status != "stopped"
    ):
        return None, "The prior validation deployment does not match this approved release."
    prior_plan = (
        (prior_deployment.infrastructure_metadata or {}).get("architecture_plan")
        if prior_deployment is not None
        else None
    )
    if not isinstance(prior_plan, Mapping) or (
        str(prior_plan.get("id")) != str(claims.get("plan_id"))
        or int(prior_plan.get("revision") or 0) != int(claims.get("plan_revision") or 0)
    ):
        return None, "The prior validation run used a different architecture plan."
    return dict(claims), verification.reason


async def _run_repository_stage(
    runtime: _DurableRuntime,
    p_logger: PipelineLogger,
    *,
    stage_key: str,
    repo_path: str,
    facts: repository_checks.RepositoryFacts,
    source_revision: str,
    source_digest: str,
    executor: repository_checks.RepositoryCheckExecutor | None,
) -> None:
    if not await runtime.is_queued(stage_key):
        return
    await runtime.start(stage_key)
    result = await asyncio.to_thread(
        repository_checks.run_repository_check,
        stage_key,
        repo_path,
        facts=facts,
        required=True,
        executor=executor,
        source_revision=source_revision,
        source_digest=source_digest,
    )
    evidence = [
        _evidence("Check result", result.summary, kind="repository-check"),
        _evidence("Command count", len(result.commands), kind="repository-check"),
    ]
    metadata = {"summary": result.summary, "result": result.to_dict()}
    if result.status == "passed":
        await runtime.succeed(stage_key, evidence=evidence, result_metadata=metadata)
        await p_logger.log(f"{stage_key.replace('_', ' ').title()} passed.", "success")
        return
    if result.status == "skipped":
        await runtime.transition(
            stage_key,
            "unavailable",
            reason="Repository command planning changed after stage reconciliation.",
            failure_code="REPOSITORY_PLAN_UNAVAILABLE",
            redacted_error=result.reason or result.summary,
            evidence=evidence,
            result_metadata=metadata,
        )
        raise PipelineExecutionError(
            "A required repository check had no validated command plan.",
            failure_code="REPOSITORY_PLAN_UNAVAILABLE",
            status="unavailable",
            stage_key=stage_key,
        )
    target_status = "unavailable" if result.status == "unavailable" else "failed"
    failure_code = "REPOSITORY_CHECK_UNAVAILABLE" if target_status == "unavailable" else "REPOSITORY_CHECK_FAILED"
    safe_reason = result.reason or result.summary
    await runtime.transition(
        stage_key,
        target_status,
        reason=safe_reason,
        failure_code=failure_code,
        redacted_error=safe_reason,
        evidence=evidence,
        result_metadata=metadata,
    )
    raise PipelineExecutionError(
        safe_reason,
        failure_code=failure_code,
        status=target_status,
        stage_key=stage_key,
    )


async def _run_security_stage(
    runtime: _DurableRuntime,
    p_logger: PipelineLogger,
    *,
    stage_key: str,
    scan_kind: security_scanner.ScanKind,
    repo_path: str,
    target_revision: str,
    target_kind: str,
    image_ref: str | None = None,
    scan_callable: Callable[..., security_scanner.SecurityScanResult] | None = None,
) -> security_scanner.SecurityScanResult | None:
    if not await runtime.is_queued(stage_key):
        return None
    stage = await runtime.start(stage_key)
    if scan_callable is None:
        result = await asyncio.to_thread(
            security_scanner.run_scan,
            scan_kind,
            repo_path,
            image_ref=image_ref,
            required=True,
        )
    else:
        result = await asyncio.to_thread(scan_callable, repo_path, required=True)
    await pipeline_evidence.persist_security_scan(
        runtime.db,
        pipeline_run=runtime.pipeline_run,
        stage_attempt=stage,
        result=result,
        target_revision=target_revision,
        target_kind=target_kind,
        target_digest=_image_digest(image_ref),
    )
    evidence = [
        _evidence("Scanner", result.tool, kind="security-scan"),
        _evidence("Evidence target", target_kind, kind="security-scan"),
        _evidence("Policy result", result.status, kind="security-scan"),
        _evidence("Validated findings", len(result.findings), kind="security-scan"),
    ]
    metadata = {"summary": result.summary, "scanner": result.to_dict()}
    if not result.blocking and result.status in {"passed", "warning"}:
        await runtime.succeed(
            stage_key,
            evidence=evidence,
            result_metadata=metadata,
            tool_version=result.tool_version,
        )
        await p_logger.log(
            f"{result.tool} completed with policy result {result.status}.",
            "warning" if result.status == "warning" else "success",
        )
        return result

    target_status = (
        "unavailable" if result.status == "unavailable" else "blocked" if result.blocking else "failed"
    )
    failure_code = "SCANNER_UNAVAILABLE" if target_status == "unavailable" else "SECURITY_POLICY_BLOCKED"
    await runtime.transition(
        stage_key,
        target_status,
        reason=result.summary,
        failure_code=failure_code,
        redacted_error=result.summary,
        evidence=evidence,
        result_metadata=metadata,
        tool_version=result.tool_version,
    )
    raise PipelineExecutionError(
        result.summary,
        failure_code=failure_code,
        status=target_status,
        stage_key=stage_key,
    )


async def _block_unverified_aks_external_endpoint(
    runtime: _DurableRuntime,
    *,
    reported_endpoint: str | None,
    release_metadata: Mapping[str, Any],
) -> None:
    """Fail closed until AKS endpoints have a hardened external verifier."""

    reason = (
        "AKS reported an external Service or Ingress endpoint, but no hardened external verifier is configured."
        if reported_endpoint
        else "AKS did not provide evidence that this workload is intentionally endpoint-less; external verification is unavailable."
    )
    await runtime.transition(
        "smoke_test",
        "unavailable",
        reason=reason,
        failure_code="AKS_EXTERNAL_VERIFICATION_UNAVAILABLE",
        redacted_error=reason,
        evidence=[
            _evidence("Rollout status", release_metadata.get("rollout_status"), kind="health"),
            _evidence("Pod status", release_metadata.get("pod_status"), kind="health"),
            _evidence("Cluster endpoint reported", bool(reported_endpoint), kind="health"),
        ],
    )
    raise PipelineExecutionError(
        reason,
        failure_code="AKS_EXTERNAL_VERIFICATION_UNAVAILABLE",
        status="unavailable",
        stage_key="smoke_test",
    )


async def _block_unverified_terraform_validation(runtime: _DurableRuntime) -> None:
    """Do not equate a TFLint result with Terraform validation."""

    reason = (
        "Terraform fmt, isolated initialization, and validate are not available in a verified disposable executor."
    )
    safe_error = (
        "A verified disposable Terraform validation boundary is required before this pipeline can continue."
    )
    await runtime.transition(
        "infrastructure_validation",
        "unavailable",
        reason=reason,
        failure_code="TERRAFORM_VALIDATION_UNAVAILABLE",
        redacted_error=safe_error,
    )
    raise PipelineExecutionError(
        safe_error,
        failure_code="TERRAFORM_VALIDATION_UNAVAILABLE",
        status="unavailable",
        stage_key="infrastructure_validation",
    )


async def _block_unverified_aks_deployment(runtime: _DurableRuntime) -> None:
    """Stop before mutating a cluster when release verification cannot finish."""

    reason = (
        "AKS external Service/Ingress verification is not available, so ZeroOps did not mutate the cluster."
    )
    await runtime.transition(
        "application_deployment",
        "unavailable",
        reason=reason,
        failure_code="AKS_EXTERNAL_VERIFICATION_UNAVAILABLE",
        redacted_error=reason,
        evidence=[
            _evidence("Cluster mutation attempted", False, kind="deployment"),
            _evidence("External endpoint verifier available", False, kind="health"),
        ],
        result_metadata={"summary": reason},
    )
    raise PipelineExecutionError(
        reason,
        failure_code="AKS_EXTERNAL_VERIFICATION_UNAVAILABLE",
        status="unavailable",
        stage_key="application_deployment",
    )


async def _verify_app_service_stage(
    live_url: str,
    expected_app_name: str,
    *,
    stage_key: str,
    attempts: int = 12,
    delay_seconds: float = 5,
) -> None:
    """Translate a bounded endpoint rejection into an explicit stage failure."""

    if stage_key not in {"health_check", "smoke_test"}:
        raise ValueError("Unsupported App Service verification stage.")
    try:
        await asyncio.to_thread(
            app_service.verify_public_endpoint,
            live_url,
            expected_app_name=expected_app_name,
            attempts=attempts,
            delay_seconds=delay_seconds,
        )
    except app_service.AzureDeploymentError as error:
        label = "health" if stage_key == "health_check" else "smoke"
        raise PipelineExecutionError(
            f"The App Service release did not pass the exact-origin {label} check.",
            failure_code=(
                "APP_SERVICE_HEALTH_CHECK_FAILED"
                if stage_key == "health_check"
                else "APP_SERVICE_SMOKE_TEST_FAILED"
            ),
            status="failed",
            stage_key=stage_key,
        ) from error


def _required_environment_names(metadata: Mapping[str, Any]) -> set[str]:
    required_names: set[str] = set()
    pricing = metadata.get("pricing_breakdown")
    details = pricing.get("detected_vars_detail", []) if isinstance(pricing, Mapping) else []
    for detail in details if isinstance(details, list) else []:
        if not isinstance(detail, Mapping):
            continue
        key = str(detail.get("key") or "").strip()
        if detail.get("type") == "required" and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            required_names.add(key)
    for database_name in metadata.get("database_dependencies") or []:
        lowered = str(database_name).lower()
        if "postgres" in lowered or "mysql" in lowered:
            required_names.add("DATABASE_URL")
        elif "mongo" in lowered:
            required_names.add("MONGODB_URI")
        elif "redis" in lowered:
            required_names.add("REDIS_URL")
    return required_names


async def _runtime_environment(
    db: Any,
    *,
    deployment: models.Deployment,
    metadata: Mapping[str, Any],
    p_logger: PipelineLogger,
) -> dict[str, tuple[str, bool]]:
    env_result = await db.execute(
        select(models.Environment).where(
            models.Environment.project_id == deployment.project_id,
            models.Environment.name == "production",
        )
    )
    environment = env_result.scalars().first()
    if environment is None:
        environment = models.Environment(project_id=deployment.project_id, name="production")
        db.add(environment)
        await db.flush()

    variables_result = await db.execute(
        select(models.EnvironmentVariable).where(
            models.EnvironmentVariable.environment_id == environment.id
        )
    )
    variables = list(variables_result.scalars().all())
    by_key = {variable.key: variable for variable in variables}
    required_names = _required_environment_names(metadata)

    runtime_variables: dict[str, tuple[str, bool]] = {}
    missing: list[str] = []
    for key in sorted(required_names):
        if key not in by_key:
            missing.append(key)
    for variable in variables:
        if variable.is_secret:
            value = vault.get_project_secret(str(deployment.project_id), variable.key)
            if not value:
                if variable.key in required_names:
                    missing.append(variable.key)
                continue
            runtime_variables[variable.key] = (value, True)
        else:
            value = str(variable.value or "")
            if variable.key in required_names and not value:
                missing.append(variable.key)
                continue
            runtime_variables[variable.key] = (value, False)
    missing = sorted(set(missing))
    if missing:
        await p_logger.log(
            "Required environment configuration is missing: " + ", ".join(missing) + ".",
            "error",
        )
        raise PipelineExecutionError(
            "Required environment configuration is missing: " + ", ".join(missing) + ".",
            failure_code="REQUIRED_ENVIRONMENT_MISSING",
            stage_key="container_build",
        )
    await p_logger.log(
        f"Resolved {len(runtime_variables)} configured environment variable name(s); values remain secret.",
        "info",
    )
    return runtime_variables


def _analysis_record(deployment: models.Deployment, metadata: Mapping[str, Any]) -> models.AIAnalysis:
    resources = metadata.get("resources") if isinstance(metadata.get("resources"), Mapping) else {}
    return models.AIAnalysis(
        user_id=deployment.user_id,
        project_id=deployment.project_id,
        framework=metadata.get("framework"),
        framework_version=metadata.get("version"),
        language=metadata.get("language"),
        risk_score=metadata.get("risk_score", 0),
        confidence=metadata.get("confidence", 0),
        cpu_recommendation=resources.get("cpu"),
        memory_recommendation=resources.get("memory"),
        storage_recommendation=resources.get("storage"),
        dependencies=metadata.get("dependencies", []),
        vulnerabilities=metadata.get("vulnerabilities", []),
        dockerfile=metadata.get("dockerfile"),
        kubernetes_manifest=metadata.get("kubernetes_manifest"),
        runtime=metadata.get("runtime"),
        package_manager=metadata.get("package_manager"),
        docker_support=bool(metadata.get("docker_support")),
        monorepo_structure=metadata.get("monorepo_structure"),
        database_dependencies=metadata.get("database_dependencies", []),
        deployment_strategy=metadata.get("deployment_strategy"),
        build_commands=metadata.get("build_commands"),
        start_commands=metadata.get("start_commands"),
        environment_variables=metadata.get("environment_variables", []),
        recommended_compute_tier=metadata.get("recommended_compute_tier"),
        estimated_cost=metadata.get("estimated_cost"),
        recommended_region=metadata.get("recommended_region"),
        expected_traffic=metadata.get("expected_traffic"),
        pricing_breakdown=metadata.get("pricing_breakdown"),
    )


async def _persist_pipeline_change_evidence(
    db: Any,
    *,
    pipeline_run: models.PipelineRun,
    current: change_detection.RepositoryFingerprint,
    previous_snapshot: models.RepositoryAnalysisSnapshot | None,
    changed_files: Iterable[str] | Mapping[str, bytes],
    decision: change_detection.AnalysisReuseDecision,
    metadata: Mapping[str, Any],
    ai_used: bool,
) -> tuple[models.ChangeAnalysis, models.RepositoryAnalysisSnapshot]:
    """Persist evidence while safely reusing an identical immutable snapshot.

    The schema intentionally de-duplicates snapshots by project, revision, and
    fingerprint.  An approved rerun of the same SHA therefore references the
    prior snapshot instead of attempting to create a duplicate row.
    """

    identical_snapshot = bool(
        previous_snapshot
        and previous_snapshot.source_revision == current.commit_sha
        and previous_snapshot.repository_fingerprint == current.repository_fingerprint
        and previous_snapshot.architecture_fingerprint == current.architecture_fingerprint
    )
    if not identical_snapshot:
        return await pipeline_evidence.persist_change_evidence(
            db,
            pipeline_run=pipeline_run,
            current=current,
            previous_snapshot=previous_snapshot,
            changed_files=changed_files,
            decision=decision,
            metadata=metadata,
            ai_used=ai_used,
        )

    existing_result = await db.execute(
        select(models.ChangeAnalysis).where(
            models.ChangeAnalysis.pipeline_run_id == pipeline_run.id
        )
    )
    existing = existing_result.scalars().first()
    if existing is None:
        persistence = change_detection.ChangeDetectionService.build_change_analysis_persistence(
            previous=pipeline_evidence.fingerprint_from_record(previous_snapshot),
            current=current,
            changed_files=changed_files,
        )
        now = datetime.now(timezone.utc)
        existing = models.ChangeAnalysis(
            tenant_id=pipeline_run.tenant_id,
            project_id=pipeline_run.project_id,
            deployment_id=pipeline_run.deployment_id,
            pipeline_run_id=pipeline_run.id,
            baseline_snapshot_id=previous_snapshot.id,
            idempotency_key=f"change:{pipeline_run.id}",
            baseline_revision=previous_snapshot.source_revision,
            target_revision=current.commit_sha,
            status="succeeded",
            started_at=now,
            completed_at=now,
            **persistence.to_dict(),
        )
        db.add(existing)
    pipeline_run.repository_ai_required = decision.requires_repository_analysis
    pipeline_run.repository_ai_used = ai_used
    await db.flush()
    return existing, previous_snapshot


def _bounded_failure_diagnostic(value: Any, *, maximum_length: int = 8_000) -> str:
    """Serialize redacted pipeline evidence within the model/persistence budget."""

    try:
        serialized = json.dumps(
            redact_sensitive_values(value),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
    except (TypeError, ValueError):
        serialized = "Failure evidence could not be serialized safely."
    return redact_sensitive_text(serialized, maximum_length=maximum_length)


async def _persist_failure_investigation(
    db: Any,
    *,
    deployment: models.Deployment,
    pipeline_run: models.PipelineRun,
    failed_stage: models.PipelineStageAttempt | None,
    failure_code: str,
    safe_message: str,
    diagnosis_enabled: bool,
) -> None:
    existing_result = await db.execute(
        select(models.AIInvestigation).where(
            models.AIInvestigation.tenant_id == pipeline_run.tenant_id,
            models.AIInvestigation.idempotency_key == f"pipeline-failure:{pipeline_run.id}",
        )
    )
    investigation = existing_result.scalars().first()
    if investigation is not None and investigation.status not in {"queued", "running"}:
        return
    logs_result = await db.execute(
        select(models.DeploymentLog)
        .where(models.DeploymentLog.deployment_id == deployment.id)
        .order_by(desc(models.DeploymentLog.line_number))
        .limit(100)
    )
    messages = [
        redact_sensitive_text(item.message, maximum_length=2_000)
        for item in reversed(list(logs_result.scalars().all()))
    ]
    change_result = await db.execute(
        select(models.ChangeAnalysis)
        .where(models.ChangeAnalysis.pipeline_run_id == pipeline_run.id)
        .limit(1)
    )
    change_record = change_result.scalars().first()
    stage_context = _bounded_failure_diagnostic({
        "stage_key": failed_stage.stage_key if failed_stage else None,
        "status": failed_stage.status if failed_stage else None,
        "failure_code": failed_stage.failure_code if failed_stage else failure_code,
        "evidence": list(failed_stage.evidence or [])[:25] if failed_stage else [],
        "result_metadata": failed_stage.result_metadata if failed_stage else {},
    })
    change_context = _bounded_failure_diagnostic({
        "source_revision": pipeline_run.source_revision,
        "branch": pipeline_run.branch,
        "baseline_revision": change_record.baseline_revision if change_record else None,
        "target_revision": change_record.target_revision if change_record else pipeline_run.source_revision,
        "decision_reason": change_record.decision_reason if change_record else None,
        "category_counts": change_record.category_counts if change_record else {},
        "changed_file_count": change_record.changed_file_count if change_record else None,
        "sampled_paths": list(change_record.sampled_paths or [])[:50] if change_record else [],
    })
    evidence = [
        _evidence("Failed stage", failed_stage.stage_key if failed_stage else "pipeline"),
        _evidence("Failure code", failure_code),
        _evidence("Sanitized diagnostic", safe_message),
        _evidence("Source revision", pipeline_run.source_revision, kind="source"),
        _evidence("Failed-stage evidence", stage_context, kind="stage-evidence"),
        _evidence("Change evidence", change_context, kind="change-detection"),
    ]
    digest = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    now = datetime.now(timezone.utc)
    trigger_type = "security_failure" if failure_code in {
        "SCANNER_UNAVAILABLE",
        "SECURITY_POLICY_BLOCKED",
    } else "test_failure" if failed_stage and failed_stage.stage_key == "unit_tests" else "pipeline_failure"
    if not diagnosis_enabled:
        if investigation is None:
            investigation = models.AIInvestigation(
                tenant_id=pipeline_run.tenant_id,
                project_id=pipeline_run.project_id,
                deployment_id=deployment.id,
                pipeline_run_id=pipeline_run.id,
                stage_attempt_id=failed_stage.id if failed_stage else None,
                requested_by_user_id=pipeline_run.requested_by_user_id,
                idempotency_key=f"pipeline-failure:{pipeline_run.id}",
                trigger_type=trigger_type,
                failed_stage_key=failed_stage.stage_key if failed_stage else None,
                prompt_version="pipeline-failure.v1",
                started_at=now,
            )
        investigation.status = "skipped"
        investigation.model_provider = "disabled-by-project-policy"
        investigation.model_name = "none"
        investigation.evidence_digest = digest
        investigation.evidence = evidence
        investigation.error_code = "AI_DIAGNOSIS_DISABLED"
        investigation.redacted_error = "Failure diagnosis is disabled by project policy."
        investigation.completed_at = now
        db.add(investigation)
        await db.commit()
        return

    if investigation is None:
        investigation = models.AIInvestigation(
            tenant_id=pipeline_run.tenant_id,
            project_id=pipeline_run.project_id,
            deployment_id=deployment.id,
            pipeline_run_id=pipeline_run.id,
            stage_attempt_id=failed_stage.id if failed_stage else None,
            requested_by_user_id=pipeline_run.requested_by_user_id,
            idempotency_key=f"pipeline-failure:{pipeline_run.id}",
            trigger_type=trigger_type,
            failed_stage_key=failed_stage.stage_key if failed_stage else None,
            prompt_version="pipeline-failure.v1",
            started_at=now,
        )
    investigation.status = "running"
    investigation.model_provider = "pending"
    investigation.model_name = "pending"
    investigation.evidence_digest = digest
    investigation.evidence = evidence
    investigation.error_code = None
    investigation.redacted_error = None
    investigation.completed_at = None
    db.add(investigation)
    # Make the running state observable before crossing the model boundary.
    await db.commit()

    try:
        result = await asyncio.to_thread(
            ai.analyze_failure_nemotron,
            messages,
            messages,
            [
                f"Pipeline stage {failed_stage.stage_key if failed_stage else 'unknown'} failed with {failure_code}.",
                f"Bounded failed-stage evidence: {stage_context}",
                f"Bounded revision and change evidence: {change_context}",
            ],
            include_provenance=True,
        )
    except Exception:
        result = ai.FailureAnalysisOutcome(
            analysis=ai.analyze_failure_local(messages, messages),
            ai_used=False,
            provider="unavailable",
            model="deterministic-failure-analysis",
            unavailable_reason="provider_or_adapter_failure",
        )
    if isinstance(result, ai.FailureAnalysisOutcome):
        analysis = result.analysis
        ai_used = result.ai_used
        model_provider = result.provider
        model_name = result.model
        input_tokens = result.input_tokens
        output_tokens = result.output_tokens
    else:
        # A compatibility adapter or test double may still return the legacy
        # dictionary. It can provide a useful deterministic diagnosis, but it
        # cannot prove that a model ran.
        analysis = result if isinstance(result, Mapping) else {}
        ai_used = False
        model_provider = "unavailable"
        model_name = "deterministic-failure-analysis"
        input_tokens = 0
        output_tokens = 0
    safe_result = redact_sensitive_values(analysis)
    severity_value = str(safe_result.get("severity") or "error").lower()
    severity = {"critical": "critical", "warning": "medium", "error": "high"}.get(severity_value, "high")
    steps = [
        redact_sensitive_text(str(step), maximum_length=1_000)
        for step in (safe_result.get("step_by_step_resolution") or [])[:20]
    ]
    investigation.status = "succeeded" if ai_used else "unavailable"
    investigation.model_provider = (
        redact_sensitive_text(str(model_provider), maximum_length=64)
        or "unavailable"
    )
    investigation.model_name = (
        redact_sensitive_text(str(model_name), maximum_length=128)
        or "deterministic-failure-analysis"
    )
    investigation.failure_summary = redact_sensitive_text(
        str(safe_result.get("failure_summary") or safe_message),
        maximum_length=2_000,
    )
    investigation.root_cause = redact_sensitive_text(
        str(safe_result.get("root_cause") or "The available evidence did not establish a more specific root cause."),
        maximum_length=4_000,
    )
    investigation.severity = severity
    investigation.recommended_fix = redact_sensitive_text(
        str(safe_result.get("recommended_fix") or "Review the recorded stage evidence and correct the blocking condition."),
        maximum_length=4_000,
    )
    investigation.resolution_steps = steps
    investigation.confidence = None
    investigation.safe_action_available = False
    investigation.requires_user_action = True
    investigation.input_tokens = input_tokens
    investigation.output_tokens = output_tokens
    investigation.error_code = None if ai_used else "AI_PROVIDER_UNAVAILABLE"
    investigation.redacted_error = (
        None
        if ai_used
        else "No configured AI route returned a validated diagnosis; deterministic analysis is shown."
    )
    investigation.completed_at = datetime.now(timezone.utc)
    db.add(investigation)

    legacy_result = await db.execute(
        select(models.FailureAnalysis).where(models.FailureAnalysis.deployment_id == deployment.id)
    )
    if legacy_result.scalars().first() is None:
        db.add(models.FailureAnalysis(
            user_id=deployment.user_id,
            project_id=deployment.project_id,
            deployment_id=deployment.id,
            failure_summary=investigation.failure_summary,
            root_cause=investigation.root_cause,
            severity=severity_value if severity_value in {"critical", "warning", "error"} else "error",
            recommended_fix=investigation.recommended_fix,
            step_by_step_resolution=steps,
            confidence=0,
            impact="Deployment halted before verified completion.",
        ))
    await db.commit()


async def run_deployment_pipeline(
    deploy_id: str,
    repo_name: str,
    branch: str,
    clone_token: str | None = None,
    *,
    commit_sha: str | None = None,
    lease_guard: Callable[[], bool] | None = None,
    repository_executor: repository_checks.RepositoryCheckExecutor | None = None,
) -> None:
    """Execute one immutable release and persist all stage outcomes."""

    deployment_uuid = uuid.UUID(deploy_id)
    p_logger = PipelineLogger(deploy_id)
    workspace_path: str | None = None
    started = time.time()
    pipeline_run_id: uuid.UUID | None = None
    diagnosis_enabled = True

    try:
        async with AsyncSessionLocal() as db:
            deployment_result = await db.execute(
                select(models.Deployment).where(models.Deployment.id == deployment_uuid)
            )
            deployment = deployment_result.scalars().first()
            if deployment is None:
                raise PipelineExecutionError(
                    "The queued deployment record is unavailable.",
                    failure_code="DEPLOYMENT_NOT_FOUND",
                    status="unavailable",
                )
            if deployment.status != "building":
                raise PipelineExecutionError(
                    "The deployment is not authorized to cross the build boundary from its recorded state.",
                    failure_code="DEPLOYMENT_STATE_NOT_AUTHORIZED",
                    status="blocked",
                )
            project_result = await db.execute(
                select(models.Project).where(models.Project.id == deployment.project_id)
            )
            project = project_result.scalars().first()
            if project is None:
                raise PipelineExecutionError(
                    "The project record is unavailable.",
                    failure_code="PROJECT_NOT_FOUND",
                    status="unavailable",
                )
            pipeline_run = await pipeline_records.get_pipeline_run(db, deployment.id)
            if pipeline_run is None:
                raise PipelineExecutionError(
                    "The normalized pipeline run is unavailable; execution was not started.",
                    failure_code="PIPELINE_RUN_NOT_FOUND",
                    status="unavailable",
                )
            pipeline_run_id = pipeline_run.id
            configuration = None
            if pipeline_run.configuration_id:
                config_result = await db.execute(
                    select(models.ProjectPipelineConfiguration).where(
                        models.ProjectPipelineConfiguration.id == pipeline_run.configuration_id
                    )
                )
                configuration = config_result.scalars().first()
            diagnosis_enabled = not configuration or bool(configuration.ai_failure_diagnosis)
            max_line_result = await db.execute(
                select(func.max(models.DeploymentLog.line_number)).where(
                    models.DeploymentLog.deployment_id == deployment.id
                )
            )
            p_logger.line_counter = int(max_line_result.scalar_one_or_none() or 0)
            runtime = _DurableRuntime(
                db=db,
                deployment=deployment,
                pipeline_run=pipeline_run,
                deploy_id=deploy_id,
                lease_guard=lease_guard,
            )
            await runtime.refresh()
            if configuration and not configuration.enabled:
                await runtime.transition(
                    "source",
                    "blocked",
                    reason="Pipeline execution is disabled by project configuration.",
                    failure_code="PIPELINE_DISABLED",
                )
                raise PipelineExecutionError(
                    "Pipeline execution is disabled by project configuration.",
                    failure_code="PIPELINE_DISABLED",
                    status="blocked",
                    stage_key="source",
                )

            await runtime.start("source")
            await p_logger.log(f"Starting immutable source preparation for {repo_name} at {commit_sha or deployment.commit_sha}.")
            if getattr(project, "source_type", "github") == "upload":
                if not project.source_path:
                    raise PipelineExecutionError(
                        "The uploaded project has no source artifact path.",
                        failure_code="SOURCE_ARTIFACT_MISSING",
                        stage_key="source",
                    )
                repo_path = await asyncio.to_thread(git.prepare_local_source, project.source_path, deploy_id)
            else:
                repo_path = await asyncio.to_thread(
                    git.clone_repo,
                    repo_name,
                    clone_token,
                    branch=branch,
                    commit_sha=commit_sha,
                    workspace_key=deploy_id,
                )
            workspace_path = repo_path
            source_snapshot = await asyncio.to_thread(repository_snapshot.collect_repository_snapshot, repo_path)
            repository_facts = await asyncio.to_thread(repository_checks.inspect_repository, repo_path)
            local_metadata = await asyncio.to_thread(ai.analyze_repo_local, repo_path, normalize_project_id(repo_name))

            azure_result = await db.execute(
                select(models.UserAzureConnection)
                .where(
                    models.UserAzureConnection.user_id == deployment.user_id,
                    models.UserAzureConnection.connection_status == "connected",
                    models.UserAzureConnection.is_active.is_(True),
                )
                .order_by(desc(models.UserAzureConnection.created_at))
                .limit(1)
            )
            azure_connection = azure_result.scalars().first()
            deployment_metadata = deployment.infrastructure_metadata or {}
            if not isinstance(deployment_metadata, Mapping):
                deployment_metadata = {}
            requested_provider = (
                deployment_metadata.get("requested_target")
                if isinstance(deployment_metadata, Mapping)
                else None
            ) or pipeline_run.target_type or deployment_metadata.get("target_provider", "auto")
            if requested_provider == "undecided":
                requested_provider = "auto"
            selected_target = deployment_targets.choose_target(
                local_metadata,
                azure_connection,
                requested_provider,
            )
            pipeline_run.target_type = selected_target.provider
            namespace_prefix = deployment_targets.namespace_prefix(selected_target, deployment.user_id)
            application_name = normalize_project_id(
                f"{namespace_prefix}-{project.name}-{str(project.id)[:8]}"
            )
            tagged_image = deployment_targets.image_ref_for_target(
                selected_target,
                application_name,
                deployment.version or "latest",
            )
            deployment.image = tagged_image
            metadata_container = dict(deployment.infrastructure_metadata or {})
            metadata_container.update({
                "target_provider": selected_target.provider,
                "target_reason": selected_target.reason,
                "target": deployment_targets.metadata_for_target(selected_target),
                "available_targets": deployment_targets.status_payload(azure_connection)["targets"],
            })
            deployment.infrastructure_metadata = metadata_container
            flag_modified(deployment, "infrastructure_metadata")
            await runtime.succeed(
                "source",
                evidence=[
                    _evidence("Source revision", pipeline_run.source_revision, kind="source"),
                    _evidence("Files represented", source_snapshot.file_count, kind="source"),
                    _evidence("Target", selected_target.provider, kind="target"),
                ],
                result_metadata={
                    "summary": "Immutable source was prepared and bounded repository evidence was collected.",
                    "represented_bytes": source_snapshot.represented_bytes,
                },
            )
            await p_logger.log("Immutable source preparation completed.", "success")
            await p_logger.flush_to_db(db)

            await runtime.start("change_detection")
            previous_snapshot = await pipeline_evidence.latest_repository_snapshot(
                db,
                tenant_id=pipeline_run.tenant_id,
                project_id=pipeline_run.project_id,
                exclude_pipeline_run_id=pipeline_run.id,
            )
            current_revision = str(commit_sha or deployment.commit_sha or pipeline_run.source_revision).strip().lower()
            current_fingerprint = change_detection.ChangeDetectionService.fingerprint_repository(
                source_snapshot.files,
                commit_sha=current_revision,
                application_framework=local_metadata.get("framework"),
                detected_services=local_metadata.get("detected_services") or (),
                environment_variable_names=_environment_variable_names(
                    local_metadata,
                    source_snapshot.environment_variable_names,
                ),
            )
            changed_files, diff_source = _diff_evidence(
                repo_path=repo_path,
                previous=previous_snapshot,
                current=current_fingerprint,
                snapshot=source_snapshot,
                clone_token=clone_token,
            )
            previous_fingerprint = (
                pipeline_evidence.fingerprint_from_record(previous_snapshot)
                if previous_snapshot
                else None
            )
            reuse_decision = change_detection.ChangeDetectionService.compare(
                previous=previous_fingerprint,
                current=current_fingerprint,
                changed_files=changed_files,
            )
            await runtime.succeed(
                "change_detection",
                evidence=[
                    _evidence("Decision", reuse_decision.message, kind="change-detection"),
                    _evidence("Diff evidence", diff_source, kind="change-detection"),
                    _evidence("Changed paths", len(reuse_decision.changed_files), kind="change-detection"),
                ],
                result_metadata={
                    "summary": reuse_decision.message,
                    "decision": reuse_decision.to_dict(),
                },
            )

            capabilities = _repository_capabilities(repository_facts)
            classified_repository = change_detection.ChangeDetectionService.classify_changes(source_snapshot.files)
            category_names = {item.value for item in classified_repository.categories}
            changed_category_names = {item.value for item in reuse_decision.categories}
            deployment_mode = configuration.deployment_mode if configuration else "deploy_after_checks"
            context = pipeline_records.context_from_configuration(
                configuration,
                target_type=selected_target.provider,
                has_dependencies=capabilities["dependencies"],
                has_tests=capabilities["tests"],
                has_iac="INFRASTRUCTURE_CHANGE" in category_names,
                infrastructure_change="INFRASTRUCTURE_CHANGE" in changed_category_names,
                repository_analysis_required=reuse_decision.requires_repository_analysis,
            )
            # Validation-only is a non-mutating check.  ACR builds and image
            # scans require publishing an image, so they are not applicable.
            context = replace(
                context,
                has_application_source=bool(source_snapshot.paths),
                has_build_step=capabilities["build"],
                container_required=deployment_mode != "validate_only",
                monitoring_registration_required=False,
            )
            await runtime.reconcile(context)
            if not capabilities["quality"] and await runtime.is_queued("code_quality"):
                await runtime.skip_queued(
                    "code_quality",
                    "No supported code-quality command is configured in the immutable source.",
                )
            await runtime.refresh()
            monitoring_stage = runtime.stages.get("monitoring_registration")
            if monitoring_stage and monitoring_stage.status == "skipped":
                monitoring_stage.status_reason = (
                    "No application telemetry collector is configured; ZeroOps will not claim monitoring coverage."
                )
                await runtime._sync_metadata()
                await db.commit()

            analysis_metadata = dict(local_metadata)
            repository_ai_used = False
            if reuse_decision.requires_repository_analysis:
                await runtime.start("repository_analysis")
                analysis_result = await asyncio.to_thread(
                    ai.analyze_repository,
                    repo_path,
                    application_name,
                    include_provenance=True,
                )
                if isinstance(analysis_result, ai.RepositoryAnalysisOutcome):
                    analysis_metadata = analysis_result.analysis
                    repository_ai_used = analysis_result.ai_used
                    analysis_provider = (
                        f"{analysis_result.provider}/{analysis_result.model}"
                        if analysis_result.ai_used
                        else "deterministic fallback"
                    )
                else:
                    # Legacy adapters return only deterministic metadata and
                    # cannot prove that model inference occurred.
                    analysis_metadata = (
                        dict(analysis_result)
                        if isinstance(analysis_result, Mapping)
                        else dict(local_metadata)
                    )
                    analysis_provider = "deterministic fallback"
                db.add(_analysis_record(deployment, analysis_metadata))
                await runtime.succeed(
                    "repository_analysis",
                    evidence=[
                        _evidence("Analysis decision", reuse_decision.message, kind="analysis"),
                        _evidence("AI model used", str(repository_ai_used).lower(), kind="analysis"),
                        _evidence("Analysis provider", analysis_provider, kind="analysis"),
                    ],
                    result_metadata={
                        "summary": (
                            "Bounded repository model enrichment completed; deployment facts remain deterministically verified."
                            if repository_ai_used
                            else "Deterministic repository analysis completed; no model result was available."
                        ),
                        "ai_used": repository_ai_used,
                    },
                )
            elif previous_snapshot:
                await p_logger.log(reuse_decision.message, "info")

            change_record, snapshot_record = await _persist_pipeline_change_evidence(
                db,
                pipeline_run=pipeline_run,
                current=current_fingerprint,
                previous_snapshot=previous_snapshot,
                changed_files=changed_files,
                decision=reuse_decision,
                metadata=analysis_metadata,
                ai_used=repository_ai_used,
            )
            await db.commit()
            await p_logger.log(
                f"Change decision recorded as {change_record.decision_reason}",
                "info",
            )
            await p_logger.flush_to_db(db)

            for check_stage in ("dependency_installation", "code_quality", "unit_tests"):
                await _run_repository_stage(
                    runtime,
                    p_logger,
                    stage_key=check_stage,
                    repo_path=repo_path,
                    facts=repository_facts,
                    source_revision=current_revision,
                    source_digest=current_fingerprint.repository_fingerprint,
                    executor=repository_executor,
                )
                await p_logger.flush_to_db(db)

            for stage_key, scan_kind in (
                ("sast", "sast"),
                ("dependency_security", "dependencies"),
                ("secret_scan", "secrets"),
            ):
                await _run_security_stage(
                    runtime,
                    p_logger,
                    stage_key=stage_key,
                    scan_kind=scan_kind,
                    repo_path=repo_path,
                    target_revision=current_revision,
                    target_kind="repository",
                )
                await p_logger.flush_to_db(db)

            await _run_repository_stage(
                runtime,
                p_logger,
                stage_key="build",
                repo_path=repo_path,
                facts=repository_facts,
                source_revision=current_revision,
                source_digest=current_fingerprint.repository_fingerprint,
                executor=repository_executor,
            )
            await p_logger.flush_to_db(db)

            runtime_variables: dict[str, tuple[str, bool]] = {}
            client_secret: str | None = None
            verified_image: str | None = None
            registry_access: app_service.RegistryAccessToken | None = None
            if await runtime.is_queued("container_build"):
                await runtime.start("container_build")
                runtime_variables = await _runtime_environment(
                    db,
                    deployment=deployment,
                    metadata=analysis_metadata,
                    p_logger=p_logger,
                )
                client_secret = azure_connector.get_credential_secret(deployment.user_id)
                if not client_secret:
                    raise PipelineExecutionError(
                        "Azure credentials are unavailable. Reconnect Azure and try again.",
                        failure_code="AZURE_CREDENTIAL_UNAVAILABLE",
                        status="unavailable",
                        stage_key="container_build",
                    )
                build_output = await asyncio.to_thread(
                    lambda: list(app_service.build_image(
                        connection=selected_target.connection,
                        client_secret=client_secret,
                        repo_path=repo_path,
                        image_ref=tagged_image,
                        generated_dockerfile=analysis_metadata.get("dockerfile"),
                    ))
                )
                for line in build_output:
                    await p_logger.log(str(line), "info")
                verified_image = await asyncio.to_thread(
                    app_service.resolve_image_digest,
                    connection=selected_target.connection,
                    client_secret=client_secret,
                    image_ref=tagged_image,
                )
                if not _image_digest(verified_image):
                    raise PipelineExecutionError(
                        "Azure Container Registry did not return a verified image digest.",
                        failure_code="IMAGE_DIGEST_UNAVAILABLE",
                        status="unavailable",
                        stage_key="container_build",
                    )
                try:
                    registry_access = await asyncio.to_thread(
                        app_service.acquire_registry_access_token,
                        connection=selected_target.connection,
                        client_secret=client_secret,
                    )
                except app_service.AzureDeploymentError as token_error:
                    raise PipelineExecutionError(
                        "A short-lived Azure Container Registry scan credential could not be obtained.",
                        failure_code="REGISTRY_SCAN_AUTH_UNAVAILABLE",
                        status="unavailable",
                        stage_key="container_build",
                    ) from token_error
                deployment.image = verified_image
                await runtime.succeed(
                    "container_build",
                    evidence=[
                        _evidence("Image digest", verified_image, kind="container-image"),
                    ],
                    result_metadata={"summary": "Azure Container Registry build completed and the immutable digest was verified."},
                )
                await p_logger.flush_to_db(db)

            authenticated_container_scan = None
            if registry_access is not None and verified_image is not None:
                authenticated_container_scan = lambda path, *, required: (
                    security_scanner.run_authenticated_container_scan(
                        path,
                        image_ref=verified_image,
                        registry_server=registry_access.registry_server,
                        username=registry_access.username,
                        access_token=registry_access.access_token,
                        required=required,
                    )
                )
            await _run_security_stage(
                runtime,
                p_logger,
                stage_key="container_security",
                scan_kind="container",
                repo_path=repo_path,
                target_revision=current_revision,
                target_kind="container_image",
                image_ref=verified_image,
                scan_callable=authenticated_container_scan,
            )
            registry_access = None
            await _run_security_stage(
                runtime,
                p_logger,
                stage_key="sbom",
                scan_kind="sbom",
                repo_path=repo_path,
                target_revision=current_revision,
                # The current Syft adapter runs against the checked-out
                # repository (``syft .``), not the authenticated ACR image.
                # Persist it as source evidence and never associate the image
                # digest until an authenticated immutable-image SBOM exists.
                target_kind="repository",
                image_ref=None,
            )
            await _run_security_stage(
                runtime,
                p_logger,
                stage_key="kubernetes_validation",
                scan_kind="kubernetes",
                repo_path=repo_path,
                target_revision=current_revision,
                target_kind="kubernetes_configuration",
            )
            if await runtime.is_queued("infrastructure_validation"):
                await _block_unverified_terraform_validation(runtime)
            await _run_security_stage(
                runtime,
                p_logger,
                stage_key="iac_security",
                scan_kind="iac",
                repo_path=repo_path,
                target_revision=current_revision,
                target_kind="infrastructure_configuration",
            )
            await p_logger.flush_to_db(db)

            if await runtime.is_queued("terraform_plan"):
                await runtime.transition(
                    "terraform_plan",
                    "unavailable",
                    reason="Repository infrastructure changed, but this application deployment worker has no approved Terraform plan artifact.",
                    failure_code="TERRAFORM_PLAN_ARTIFACT_REQUIRED",
                    redacted_error="An approved immutable Terraform plan artifact is required before infrastructure mutation.",
                )
                raise PipelineExecutionError(
                    "An approved immutable Terraform plan artifact is required before infrastructure mutation.",
                    failure_code="TERRAFORM_PLAN_ARTIFACT_REQUIRED",
                    status="unavailable",
                    stage_key="terraform_plan",
                )

            if await runtime.is_queued("approval"):
                await runtime.start("approval")
                approval_record, approval_reason = await _validated_pipeline_approval(
                    db,
                    pipeline_run=pipeline_run,
                    deployment=deployment,
                )
                if approval_record is None:
                    await runtime.transition(
                        "approval",
                        "blocked",
                        reason=(
                            "This release requires an explicit authenticated approval before application rollout. "
                            + approval_reason
                        ),
                        failure_code="DEPLOYMENT_APPROVAL_REQUIRED",
                    )
                    raise PipelineExecutionError(
                        "This release requires an explicit authenticated approval before application rollout.",
                        failure_code="DEPLOYMENT_APPROVAL_REQUIRED",
                        status="blocked",
                        stage_key="approval",
                    )
                await runtime.succeed(
                    "approval",
                    evidence=[
                        _evidence("Approval source", approval_record["validation_run_id"], kind="approval"),
                        _evidence("Approved by user", approval_record["approved_by_user_id"], kind="approval"),
                        _evidence("Signature verified", "true", kind="approval"),
                    ],
                    result_metadata={"summary": approval_reason},
                )

            if await runtime.is_queued("infrastructure_provisioning"):
                await runtime.transition(
                    "infrastructure_provisioning",
                    "unavailable",
                    reason="Automatic infrastructure apply is disabled in the application deployment worker.",
                    failure_code="INFRASTRUCTURE_APPLY_DISABLED",
                )
                raise PipelineExecutionError(
                    "Automatic infrastructure apply is disabled in the application deployment worker.",
                    failure_code="INFRASTRUCTURE_APPLY_DISABLED",
                    status="unavailable",
                    stage_key="infrastructure_provisioning",
                )

            if deployment_mode == "validate_only":
                if await runtime.is_queued("deployment_complete"):
                    await runtime.start("deployment_complete")
                    await runtime.succeed(
                        "deployment_complete",
                        evidence=[_evidence("Mode", "Validation only", kind="pipeline")],
                        result_metadata={"summary": "All applicable validation stages passed; no cloud release was created."},
                    )
                await pipeline_records.finish_pipeline_run(db, pipeline_run=pipeline_run, status="succeeded")
                deployment.status = "stopped"
                deployment.completed_at = datetime.utcnow()
                deployment.duration_seconds = int(time.time() - started)
                deployment.failure_reason = None
                validation_metadata = dict(deployment.infrastructure_metadata or {})
                validation_metadata["validation_only"] = True
                validation_metadata["telemetry"] = {
                    "status": "unavailable",
                    "reason": "No application was deployed and no metrics collector was registered.",
                }
                deployment.infrastructure_metadata = validation_metadata
                flag_modified(deployment, "infrastructure_metadata")
                project.status = "active"
                db.add(models.Notification(
                    user_id=deployment.user_id,
                    title="Validation Succeeded",
                    message=f"Project {repo_name} passed all applicable validation stages. No application was deployed.",
                    type="success",
                    category="deployment",
                ))
                await db.commit()
                await p_logger.log("Validation completed without publishing a release.", "success")
                await p_logger.flush_to_db(db)
                await broadcast_message(deploy_id, {"type": "status", "status": "stopped"})
                return

            if not verified_image or not client_secret:
                raise PipelineExecutionError(
                    "A verified immutable image and Azure credential are required before deployment.",
                    failure_code="VERIFIED_RELEASE_INPUT_MISSING",
                    status="unavailable",
                    stage_key="application_deployment",
                )

            await runtime.start("application_deployment")
            deployment.status = "deploying"
            await db.commit()
            live_url: str | None = None
            reported_endpoint: str | None = None
            expected_app_name: str | None = None
            release_metadata: dict[str, Any]
            if selected_target.provider == "azure-aks":
                # Rollout readiness alone cannot satisfy the required external
                # verification contract. Stop before server-side apply so a
                # known-incomplete pipeline cannot leave an unmanaged public
                # workload behind while reporting failure.
                await _block_unverified_aks_deployment(runtime)
                if runtime_variables:
                    raise PipelineExecutionError(
                        "AKS environment injection is unavailable; configured values were not applied to the cluster.",
                        failure_code="AKS_ENVIRONMENT_INJECTION_UNAVAILABLE",
                        status="unavailable",
                        stage_key="application_deployment",
                    )
                namespace = normalize_project_id(
                    f"{namespace_prefix}-{str(project.id)[:8]}"
                )[:63].strip("-")
                aks_release = await asyncio.to_thread(
                    aks.deploy_existing_cluster,
                    connection=selected_target.connection,
                    client_secret=client_secret,
                    repo_path=repo_path,
                    namespace=namespace,
                    image_ref=verified_image,
                    release_name=application_name,
                )
                # Service/Ingress values are repository and cluster derived.
                # Until a redirect-safe public-endpoint verifier is wired, do
                # not make a server-side request or publish one as verified.
                reported_endpoint = aks_release.service_endpoint
                live_url = None
                release_metadata = {
                    "cluster": aks_release.cluster,
                    "namespace": aks_release.namespace,
                    "workloads": list(aks_release.workloads),
                    "image_digest": aks_release.image_digest,
                    "revision": aks_release.deployment_revision,
                    "rollout_status": aks_release.rollout_status,
                    "pod_status": aks_release.pod_status,
                    "service_endpoint": None,
                    "reported_service_endpoint": reported_endpoint,
                    "external_endpoint_verified": False,
                }
            else:
                deployment_output = await asyncio.to_thread(
                    lambda: list(app_service.deploy_image(
                        connection=selected_target.connection,
                        client_secret=client_secret,
                        app_name=application_name,
                        image_ref=verified_image,
                        metadata=analysis_metadata,
                        environment_variables=runtime_variables,
                    ))
                )
                app_release = next(
                    (item for item in deployment_output if isinstance(item, app_service.AppServiceRelease)),
                    None,
                )
                for line in deployment_output:
                    if not isinstance(line, app_service.AppServiceRelease):
                        await p_logger.log(str(line), "info")
                if app_release is None:
                    raise PipelineExecutionError(
                        "Azure did not return a verified application release.",
                        failure_code="APP_SERVICE_RELEASE_UNAVAILABLE",
                        status="unavailable",
                        stage_key="application_deployment",
                    )
                live_url = app_release.live_url
                expected_app_name = app_release.app_name
                release_metadata = {
                    "application_name": app_release.app_name,
                    "revision": app_release.revision,
                    "image_digest": verified_image,
                    "service_endpoint": live_url,
                }
            await runtime.succeed(
                "application_deployment",
                evidence=[
                    _evidence("Target", selected_target.provider, kind="deployment"),
                    _evidence("Image digest", verified_image, kind="deployment"),
                    _evidence("Release", release_metadata.get("revision") or "Recorded", kind="deployment"),
                ],
                result_metadata={"summary": "The target provider returned a deployed release record.", **release_metadata},
            )

            if await runtime.is_queued("health_check"):
                await runtime.start("health_check")
                if selected_target.provider == "azure-app-service":
                    if not live_url:
                        raise PipelineExecutionError(
                            "Azure App Service did not return a public endpoint for health validation.",
                            failure_code="PUBLIC_ENDPOINT_UNAVAILABLE",
                            status="unavailable",
                            stage_key="health_check",
                        )
                    if not expected_app_name:
                        raise PipelineExecutionError(
                            "Azure App Service did not return a verified application name.",
                            failure_code="APP_SERVICE_IDENTITY_UNAVAILABLE",
                            status="unavailable",
                            stage_key="health_check",
                        )
                    await _verify_app_service_stage(
                        live_url,
                        expected_app_name,
                        stage_key="health_check",
                    )
                    health_evidence = (
                        "The exact App Service HTTPS origin returned a direct 2xx response from a validated public address."
                    )
                else:
                    health_evidence = "AKS rollout and pod readiness were verified by the isolated cluster deployment adapter."
                await runtime.succeed(
                    "health_check",
                    evidence=[_evidence("Health evidence", health_evidence, kind="health")],
                    result_metadata={"summary": health_evidence},
                )

            if await runtime.is_queued("smoke_test"):
                if selected_target.provider == "azure-aks":
                    await _block_unverified_aks_external_endpoint(
                        runtime,
                        reported_endpoint=reported_endpoint,
                        release_metadata=release_metadata,
                    )
                else:
                    if not live_url or not expected_app_name:
                        raise PipelineExecutionError(
                            "Azure App Service did not return a verified public release endpoint.",
                            failure_code="PUBLIC_ENDPOINT_UNAVAILABLE",
                            status="unavailable",
                            stage_key="smoke_test",
                        )
                    await runtime.start("smoke_test")
                    await _verify_app_service_stage(
                        live_url,
                        expected_app_name,
                        stage_key="smoke_test",
                        attempts=2,
                        delay_seconds=1,
                    )
                    await runtime.succeed(
                        "smoke_test",
                        evidence=[_evidence("Endpoint", live_url, kind="smoke-test")],
                        result_metadata={
                            "summary": "A second direct 2xx check passed for the exact public App Service origin."
                        },
                    )

            await runtime.start("deployment_complete")
            await runtime.succeed(
                "deployment_complete",
                evidence=[
                    _evidence("Target", selected_target.provider, kind="deployment"),
                    _evidence("Image digest", verified_image, kind="container-image"),
                ],
                result_metadata={"summary": "Deployment and available runtime checks completed successfully."},
            )
            await pipeline_records.finish_pipeline_run(db, pipeline_run=pipeline_run, status="succeeded")
            deployment.status = "running"
            deployment.duration_seconds = int(time.time() - started)
            deployment.live_url = live_url
            deployment.completed_at = datetime.utcnow()
            deployment.failure_reason = None
            final_metadata = dict(deployment.infrastructure_metadata or {})
            final_metadata.update({
                "region": getattr(selected_target.connection, "region", None) or project.region,
                "image": verified_image,
                "target_provider": selected_target.provider,
                "target_reason": selected_target.reason,
                "target": deployment_targets.metadata_for_target(selected_target),
                "release": release_metadata,
                "framework": analysis_metadata.get("framework"),
                "language": analysis_metadata.get("language"),
                "telemetry": {
                    "status": "unavailable",
                    "reason": "No application telemetry collector is configured; monitoring registration was not claimed.",
                },
            })
            deployment.infrastructure_metadata = final_metadata
            flag_modified(deployment, "infrastructure_metadata")
            project.status = "active"
            project.last_deployed_at = datetime.utcnow()
            evaluation_result = await db.execute(
                select(models.DecisionEvaluation).where(
                    models.DecisionEvaluation.deployment_id == deployment.id
                )
            )
            evaluation = evaluation_result.scalars().first()
            if evaluation:
                evaluation.status = "successful"
                evaluation.outcome_metadata = {
                    "outcome": "Deployment completed and configured runtime health checks passed.",
                    "completed_at": datetime.utcnow().isoformat(),
                    "target_provider": selected_target.provider,
                    "telemetry_registered": False,
                }
            db.add(models.Notification(
                user_id=deployment.user_id,
                title="Deployment Succeeded",
                message=f"Project {repo_name} was deployed to {selected_target.label}.",
                type="success",
                category="deployment",
            ))
            db.add(models.ActivityEvent(
                user_id=deployment.user_id,
                project_id=deployment.project_id,
                action="Deployment Succeeded",
                details=f"Deployed immutable version {deployment.version} to the production environment.",
            ))
            await db.commit()
            await p_logger.log("Deployment completed with verified provider and health evidence.", "success")
            await p_logger.flush_to_db(db)
            await broadcast_message(
                deploy_id,
                {"type": "status", "status": "running", "live_url": live_url},
            )

    except Exception as error:
        if isinstance(error, PipelineExecutionError):
            safe_message = error.safe_message
            failure_code = error.failure_code
            terminal_status = error.status
            failed_stage_key = error.stage_key
        else:
            safe_message = "The deployment pipeline stopped unexpectedly. Review the sanitized investigation for the failed stage."
            failure_code = "PIPELINE_UNEXPECTED_FAILURE"
            terminal_status = "failed"
            failed_stage_key = None
            logger.error("Unexpected pipeline failure type: %s", type(error).__name__)
        await p_logger.log(f"Deployment stopped: {safe_message}", "error")

        async with AsyncSessionLocal() as failure_db:
            deployment_result = await failure_db.execute(
                select(models.Deployment).where(models.Deployment.id == deployment_uuid)
            )
            deployment = deployment_result.scalars().first()
            pipeline_run = (
                await pipeline_records.get_pipeline_run(failure_db, deployment_uuid)
                if deployment is not None
                else None
            )
            failed_stage: models.PipelineStageAttempt | None = None
            if deployment is not None and pipeline_run is not None:
                awaiting_approval = (
                    terminal_status == "blocked"
                    and failure_code == "DEPLOYMENT_APPROVAL_REQUIRED"
                )
                stages = await pipeline_records.list_stage_attempts(failure_db, pipeline_run.id)
                failed_stage = next(
                    (
                        item
                        for item in stages
                        if item.stage_key == (failed_stage_key or pipeline_run.current_stage_key)
                    ),
                    None,
                )
                if failed_stage and failed_stage.status == "running":
                    stage_status = terminal_status
                    await pipeline_records.transition_pipeline_stage(
                        failure_db,
                        pipeline_run=pipeline_run,
                        stage_key=failed_stage.stage_key,
                        target_status=stage_status,
                        reason=safe_message,
                        failure_code=failure_code,
                        redacted_error=safe_message,
                        evidence=[_evidence("Sanitized diagnostic", safe_message)],
                        result_metadata={"summary": safe_message},
                    )
                refreshed = await pipeline_records.list_stage_attempts(failure_db, pipeline_run.id)
                failed_order = failed_stage.stage_order if failed_stage else 0
                for stage in refreshed:
                    if stage.status == "queued" and stage.stage_order > failed_order:
                        await pipeline_records.transition_pipeline_stage(
                            failure_db,
                            pipeline_run=pipeline_run,
                            stage_key=stage.stage_key,
                            target_status="cancelled",
                            reason="Not executed because an earlier required stage did not pass.",
                            failure_code="PREDECESSOR_NOT_SUCCESSFUL",
                        )
                await pipeline_records.finish_pipeline_run(
                    failure_db,
                    pipeline_run=pipeline_run,
                    status=terminal_status,
                    reason=safe_message,
                    failure_code=failure_code,
                )
                failure_runtime = _DurableRuntime(
                    db=failure_db,
                    deployment=deployment,
                    pipeline_run=pipeline_run,
                    deploy_id=deploy_id,
                    lease_guard=None,
                )
                await failure_runtime._sync_metadata()
                deployment.status = "stopped" if awaiting_approval else "failed"
                deployment.completed_at = datetime.utcnow()
                deployment.duration_seconds = int(time.time() - started)
                deployment.failure_reason = None if awaiting_approval else safe_message
                project_result = await failure_db.execute(
                    select(models.Project).where(models.Project.id == deployment.project_id)
                )
                project = project_result.scalars().first()
                if project:
                    project.status = "active" if awaiting_approval else "failed"
                evaluation_result = await failure_db.execute(
                    select(models.DecisionEvaluation).where(
                        models.DecisionEvaluation.deployment_id == deployment.id
                    )
                )
                evaluation = evaluation_result.scalars().first()
                if evaluation and not awaiting_approval:
                    evaluation.status = "failed"
                    evaluation.outcome_metadata = {
                        "outcome": "Deployment stopped before verified runtime completion.",
                        "failure_code": failure_code,
                        "completed_at": datetime.utcnow().isoformat(),
                    }
                failure_db.add(models.Notification(
                    user_id=deployment.user_id,
                    title="Deployment Approval Required" if awaiting_approval else "Deployment Stopped",
                    message=(
                        f"Project {repo_name} passed its configured checks and is waiting for explicit approval."
                        if awaiting_approval
                        else f"Project {repo_name} stopped: {safe_message}"
                    ),
                    type="info" if awaiting_approval else "critical",
                    category="deployment",
                ))
                await failure_db.commit()
                await p_logger.flush_to_db(failure_db)

                investigation_result = await failure_db.execute(
                    select(models.PipelineStageAttempt).where(
                        models.PipelineStageAttempt.id == failed_stage.id
                    )
                ) if failed_stage else None
                persisted_failed_stage = investigation_result.scalars().first() if investigation_result else None
                try:
                    if awaiting_approval:
                        await broadcast_message(
                            deploy_id,
                            {"type": "status", "status": "stopped", "reason": "approval_required"},
                        )
                        return
                    await _persist_failure_investigation(
                        failure_db,
                        deployment=deployment,
                        pipeline_run=pipeline_run,
                        failed_stage=persisted_failed_stage,
                        failure_code=failure_code,
                        safe_message=safe_message,
                        diagnosis_enabled=diagnosis_enabled,
                    )
                    await failure_db.commit()
                except Exception as investigation_error:
                    await failure_db.rollback()
                    logger.error(
                        "Failure investigation could not be persisted: %s",
                        type(investigation_error).__name__,
                    )
            elif deployment is not None:
                deployment.status = "failed"
                deployment.failure_reason = safe_message
                deployment.completed_at = datetime.utcnow()
                await failure_db.commit()
                await p_logger.flush_to_db(failure_db)
        await broadcast_message(
            deploy_id,
            {"type": "status", "status": "failed", "failure_reason": safe_message},
        )
    finally:
        if workspace_path:
            try:
                git.cleanup_workspace(workspace_path)
            except Exception as cleanup_error:
                logger.warning("Workspace cleanup failed: %s", type(cleanup_error).__name__)
