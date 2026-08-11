"""Authenticated DevSecOps pipeline, monitoring, incident, and webhook APIs."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

try:
    from backend import auth, config, models
    from backend.database import get_db
    from backend.services import app_service, deployment_targets, pipeline_approval, vault
    from backend.services.incident_detection import evaluate_incident_rules
    from backend.services.pipeline_state import (
        PipelineContext,
        initialize_stages,
        transition_pipeline_run,
        transition_stage,
    )
    from backend.services.pipeline_records import context_from_configuration, create_pipeline_run
    from backend.services.redaction import redact_sensitive_text, redact_sensitive_values
    from backend.services.tenancy import resolve_tenant
except ImportError:  # pragma: no cover - package execution fallback
    import auth, config, models
    from database import get_db
    from services import app_service, deployment_targets, pipeline_approval, vault
    from services.incident_detection import evaluate_incident_rules
    from services.pipeline_state import (
        PipelineContext,
        initialize_stages,
        transition_pipeline_run,
        transition_stage,
    )
    from services.pipeline_records import context_from_configuration, create_pipeline_run
    from services.redaction import redact_sensitive_text, redact_sensitive_values
    from services.tenancy import resolve_tenant


router = APIRouter(tags=["devsecops"])


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _expired(value: datetime | None) -> bool:
    if value is None:
        return False
    normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return normalized.astimezone(timezone.utc) < datetime.now(timezone.utc)


def _duration_seconds(started_at: datetime | None, completed_at: datetime | None) -> float | None:
    if not started_at:
        return None
    end = completed_at or datetime.now(started_at.tzinfo or timezone.utc)
    try:
        return max(0.0, round((end - started_at).total_seconds(), 3))
    except TypeError:
        # Legacy rows use naive UTC while new rows are timezone-aware.
        return max(0.0, round((end.replace(tzinfo=None) - started_at.replace(tzinfo=None)).total_seconds(), 3))


async def _project_for_user(
    db: AsyncSession,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
) -> models.Project:
    result = await db.execute(
        select(models.Project).where(
            models.Project.id == project_id,
            models.Project.user_id == user_id,
        )
    )
    project = result.scalars().first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


def _safe_evidence(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    evidence: list[dict[str, Any]] = []
    for index, item in enumerate(value[:100]):
        if not isinstance(item, dict):
            continue
        sanitized = redact_sensitive_values(item)
        if "label" not in sanitized:
            sanitized["label"] = str(
                sanitized.get("source") or sanitized.get("metric") or f"Evidence {index + 1}"
            )
        if "value" not in sanitized:
            sanitized["value"] = str(
                sanitized.get("summary")
                or sanitized.get("state")
                or sanitized.get("status")
                or "Recorded"
            )
        evidence.append(sanitized)
    return evidence


class PipelineConfigurationUpdate(BaseModel):
    automatic_deployment: bool = False
    branch: str = Field(default="main", min_length=1, max_length=255)
    deployment_mode: Literal["validate_only", "deploy_after_checks", "require_approval"] = "require_approval"
    run_tests: bool = True
    sast_enabled: bool = True
    dependency_scan_enabled: bool = True
    secret_scan_enabled: bool = True
    container_scan_enabled: bool = True
    iac_scan_enabled: bool = True
    production_approval_required: bool = True
    ai_failure_diagnosis_enabled: bool = True
    auto_retry_transient_failures: bool = False
    auto_rollback_enabled: bool = False

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, value: str) -> str:
        branch = value.strip()
        if branch.startswith("-") or ".." in branch or any(char.isspace() for char in branch):
            raise ValueError("branch is not a valid Git ref name")
        return branch


def _pipeline_config_response(
    record: models.ProjectPipelineConfiguration | None,
    *,
    project: models.Project,
    webhook_configured: bool,
) -> dict[str, Any]:
    return {
        "project_id": str(project.id),
        "automatic_deployment": bool(record.auto_deploy) if record else False,
        "branch": record.tracked_branch if record else (project.branch or "main"),
        "deployment_mode": record.deployment_mode if record else "require_approval",
        "run_tests": bool(record.run_unit_tests) if record else True,
        "sast_enabled": bool(record.run_sast) if record else True,
        "dependency_scan_enabled": bool(record.run_dependency_scan) if record else True,
        "secret_scan_enabled": bool(record.run_secret_scan) if record else True,
        "container_scan_enabled": bool(record.run_container_scan) if record else True,
        "iac_scan_enabled": bool(record.run_iac_scan) if record else True,
        "production_approval_required": bool(record.require_production_approval) if record else True,
        "ai_failure_diagnosis_enabled": bool(record.ai_failure_diagnosis) if record else True,
        "auto_retry_transient_failures": bool(record.auto_retry_transient_failures) if record else False,
        "auto_rollback_enabled": bool(record.auto_rollback_enabled) if record else False,
        "github_webhook_configured": webhook_configured,
        "updated_at": _iso(record.updated_at) if record else None,
    }


async def _latest_config(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
) -> models.ProjectPipelineConfiguration | None:
    result = await db.execute(
        select(models.ProjectPipelineConfiguration)
        .where(
            models.ProjectPipelineConfiguration.tenant_id == tenant_id,
            models.ProjectPipelineConfiguration.project_id == project_id,
        )
        .order_by(desc(models.ProjectPipelineConfiguration.version))
        .limit(1)
    )
    return result.scalars().first()


def _webhook_secret_configured(project_id: uuid.UUID) -> bool:
    return bool(vault.get_project_secret(str(project_id), "GITHUB_WEBHOOK_SECRET"))


@router.get("/api/projects/{project_id}/pipeline-config")
async def get_pipeline_configuration(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    project = await _project_for_user(db, project_id, current_user.id)
    tenant = await resolve_tenant(db, user=current_user)
    record = await _latest_config(db, tenant_id=tenant.id, project_id=project.id)
    return _pipeline_config_response(
        record,
        project=project,
        webhook_configured=_webhook_secret_configured(project.id),
    )


@router.put("/api/projects/{project_id}/pipeline-config")
async def update_pipeline_configuration(
    project_id: uuid.UUID,
    request: PipelineConfigurationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    project = await _project_for_user(db, project_id, current_user.id)
    tenant = await resolve_tenant(db, user=current_user)
    webhook_configured = _webhook_secret_configured(project.id)
    if request.automatic_deployment and not webhook_configured:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Configure the signed GitHub webhook before enabling automatic deployment.",
        )
    previous = await _latest_config(db, tenant_id=tenant.id, project_id=project.id)
    version = (previous.version + 1) if previous else 1
    payload = request.model_dump(mode="json")
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    trigger_mode = "manual_and_push" if request.automatic_deployment else "manual"
    record = models.ProjectPipelineConfiguration(
        tenant_id=tenant.id,
        project_id=project.id,
        created_by_user_id=current_user.id,
        updated_by_user_id=current_user.id,
        version=version,
        enabled=True,
        trigger_mode=trigger_mode,
        tracked_branch=request.branch,
        auto_deploy=request.automatic_deployment,
        deployment_mode=request.deployment_mode,
        require_production_approval=request.production_approval_required,
        require_infrastructure_approval=True,
        run_dependency_install=True,
        run_code_quality=True,
        run_unit_tests=request.run_tests,
        run_sast=request.sast_enabled,
        run_dependency_scan=request.dependency_scan_enabled,
        run_secret_scan=request.secret_scan_enabled,
        run_container_scan=request.container_scan_enabled,
        run_iac_scan=request.iac_scan_enabled,
        generate_sbom=False,
        ai_failure_diagnosis=request.ai_failure_diagnosis_enabled,
        auto_retry_transient_failures=request.auto_retry_transient_failures,
        auto_rollback_enabled=request.auto_rollback_enabled,
        config_digest=digest,
    )
    db.add(record)
    db.add(models.ActivityEvent(
        tenant_id=tenant.id,
        user_id=current_user.id,
        project_id=project.id,
        action="Pipeline configuration updated",
        actor_type="user",
        details=f"Pipeline configuration version {version} saved with secure defaults.",
        event_data={
            "configuration_version": version,
            "config_digest": digest,
            "automatic_deployment": request.automatic_deployment,
            "deployment_mode": request.deployment_mode,
        },
    ))
    await db.commit()
    await db.refresh(record)
    return _pipeline_config_response(record, project=project, webhook_configured=webhook_configured)


@router.post("/api/projects/{project_id}/github-webhook-secret/regenerate")
async def regenerate_github_webhook_secret(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    project = await _project_for_user(db, project_id, current_user.id)
    tenant = await resolve_tenant(db, user=current_user)
    public_url = config.ZEROOPS_BACKEND_URL.rstrip("/")
    if not public_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ZEROOPS_BACKEND_URL is not configured, so a public webhook URL cannot be issued.",
        )
    value = secrets.token_urlsafe(48)
    try:
        vault.set_project_secret(str(project.id), "GITHUB_WEBHOOK_SECRET", value)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Azure Key Vault is unavailable. The webhook secret was not generated.",
        ) from error
    db.add(models.ActivityEvent(
        tenant_id=tenant.id,
        user_id=current_user.id,
        project_id=project.id,
        action="GitHub webhook secret rotated",
        actor_type="user",
        details="A new project-scoped webhook secret was stored in Azure Key Vault.",
        event_data={"secret_returned_once": True},
    ))
    await db.commit()
    return {
        "webhook_url": f"{public_url}/api/webhooks/github/{project.id}",
        "secret": value,
        "warning": "This secret is shown once. Add it to the GitHub webhook and store it securely.",
    }


def _change_categories(record: models.ChangeAnalysis) -> list[str]:
    categories: list[str] = []
    flags = (
        (record.architecture_changed, "MAJOR_ARCHITECTURE_CHANGE"),
        (record.kubernetes_changed, "KUBERNETES_CHANGE"),
        (record.infrastructure_changed, "INFRASTRUCTURE_CHANGE"),
        (record.deployment_config_changed, "DEPLOYMENT_CONFIG_CHANGE"),
        (record.dependencies_changed, "DEPENDENCY_CHANGE"),
        (record.security_policy_changed, "SECURITY_RELEVANT_CHANGE"),
        (record.application_source_changed, "APPLICATION_CODE_CHANGE"),
    )
    for enabled, name in flags:
        if enabled and name not in categories:
            categories.append(name)
    return categories or ["NO_RELEVANT_CHANGE"]


def _change_response(record: models.ChangeAnalysis, *, ai_used: bool = False) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "project_id": str(record.project_id),
        "deployment_id": str(record.deployment_id) if record.deployment_id else None,
        "previous_commit_sha": record.baseline_revision,
        "current_commit_sha": record.target_revision,
        "classifications": _change_categories(record),
        "changed_paths": list(record.sampled_paths or []),
        "architecture_analysis_required": bool(record.repository_ai_required),
        "architecture_analysis_reason": record.decision_reason,
        "ai_used": ai_used,
        "decision_source": f"deterministic:{record.classifier_version}",
        "created_at": _iso(record.created_at),
    }


def _finding_response(record: models.SecurityFinding, *, scanner: str) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "category": record.category,
        "severity": "info" if record.severity == "informational" else record.severity,
        "title": record.title,
        "description": record.description,
        "scanner": scanner,
        "rule_id": record.rule_id,
        "file_path": record.location_path,
        "line_number": record.line_start,
        "remediation": None,
        "blocking": bool(record.is_blocking),
        "redacted": True,
    }


def _security_scan_response(record: models.SecurityScan) -> dict[str, Any]:
    findings = [_finding_response(item, scanner=record.tool_name) for item in (record.findings or [])]
    return {
        "id": str(record.id),
        "project_id": str(record.project_id),
        "deployment_id": str(record.deployment_id) if record.deployment_id else None,
        "commit_sha": record.target_revision,
        "status": record.status,
        "policy_result": record.policy_status,
        "blocking_findings": sum(1 for item in record.findings or [] if item.is_blocking),
        "finding_counts": {
            "critical": record.critical_count,
            "high": record.high_count,
            "medium": record.medium_count,
            "low": record.low_count,
            "info": record.info_count,
        },
        "tools": [{
            "category": record.scan_type,
            "tool": record.tool_name,
            "status": record.status,
            "reason": record.redacted_error or (record.summary or {}).get("message"),
            "blocking_findings": sum(1 for item in record.findings or [] if item.is_blocking),
            "finding_count": record.finding_count,
            "completed_at": _iso(record.completed_at),
        }],
        "findings": findings,
        "started_at": _iso(record.started_at),
        "completed_at": _iso(record.completed_at),
    }


def _investigation_response(record: models.AIInvestigation | None) -> dict[str, Any] | None:
    if record is None:
        return None
    return {
        "id": str(record.id),
        "project_id": str(record.project_id),
        "deployment_id": str(record.deployment_id) if record.deployment_id else None,
        "incident_id": str(record.incident_id) if record.incident_id else None,
        "failed_stage_attempt_id": str(record.stage_attempt_id) if record.stage_attempt_id else None,
        "status": record.status,
        "unavailable_reason": record.redacted_error,
        "failure_summary": record.failure_summary,
        "probable_root_cause": record.root_cause,
        "confidence": record.confidence,
        "evidence": _safe_evidence(record.evidence),
        "recommended_fix": record.recommended_fix,
        "safe_automatic_action_available": bool(record.safe_action_available),
        "requires_user_action": bool(record.requires_user_action),
        "resolution_steps": list(record.resolution_steps or []),
        "sanitized_context": True,
        "created_at": _iso(record.created_at),
        "completed_at": _iso(record.completed_at),
    }


def _stage_response(record: models.PipelineStageAttempt) -> dict[str, Any]:
    result = record.result_metadata if isinstance(record.result_metadata, dict) else {}
    tool = record.tool_name
    if tool and record.tool_version:
        tool = f"{tool} {record.tool_version}"
    return {
        "id": str(record.id),
        "pipeline_run_id": str(record.pipeline_run_id),
        "stage_key": record.stage_key,
        "name": record.display_name,
        "description": result.get("description"),
        "order": record.stage_order,
        "attempt": record.attempt_number,
        "status": record.status,
        "required": bool(record.is_required),
        "tool": tool,
        "reason": record.status_reason or record.redacted_error,
        "summary": result.get("summary"),
        "evidence": _safe_evidence(record.evidence),
        "started_at": _iso(record.started_at),
        "completed_at": _iso(record.completed_at),
        "duration_seconds": _duration_seconds(record.started_at, record.completed_at),
        "logs_available": bool(record.log_artifact_id),
        "log_count": int(result.get("log_count") or 0),
        "ai_used": bool(result.get("ai_used")),
        "approval_required": record.stage_key == "approval" and record.is_required,
    }


async def _pipeline_response(db: AsyncSession, run: models.PipelineRun) -> dict[str, Any]:
    stage_result = await db.execute(
        select(models.PipelineStageAttempt)
        .where(models.PipelineStageAttempt.pipeline_run_id == run.id)
        .order_by(models.PipelineStageAttempt.stage_order, models.PipelineStageAttempt.attempt_number)
    )
    stages = list(stage_result.scalars().all())
    change_result = await db.execute(
        select(models.ChangeAnalysis)
        .where(models.ChangeAnalysis.pipeline_run_id == run.id)
        .order_by(desc(models.ChangeAnalysis.created_at))
        .limit(1)
    )
    change = change_result.scalars().first()
    scan_result = await db.execute(
        select(models.SecurityScan)
        .options(selectinload(models.SecurityScan.findings))
        .where(models.SecurityScan.pipeline_run_id == run.id)
        .order_by(desc(models.SecurityScan.created_at))
        .limit(1)
    )
    scan = scan_result.scalars().first()
    investigation_result = await db.execute(
        select(models.AIInvestigation)
        .where(models.AIInvestigation.pipeline_run_id == run.id)
        .order_by(desc(models.AIInvestigation.created_at))
        .limit(1)
    )
    investigation = investigation_result.scalars().first()
    deployment = await db.get(models.Deployment, run.deployment_id) if run.deployment_id else None
    deployment_metadata = (
        deployment.infrastructure_metadata
        if deployment is not None and isinstance(deployment.infrastructure_metadata, dict)
        else {}
    )
    decision = deployment_metadata.get("pipeline_approval_decision")
    signed_approval = deployment_metadata.get("pipeline_approval")
    approval_stage = next((stage for stage in stages if stage.stage_key == "approval"), None)
    if not run.approval_required:
        approval_status = "not_required"
    elif (
        isinstance(decision, dict)
        and decision.get("status") == "approved"
        and decision.get("consumed") is True
    ):
        approval_status = "approved_consumed"
    elif isinstance(decision, dict) and decision.get("status") == "rejected":
        approval_status = "rejected"
    elif isinstance(signed_approval, dict):
        approval_status = "approved"
    elif approval_stage and approval_stage.status == "blocked":
        approval_status = "pending"
    else:
        approval_status = "required"
    reached = sum(
        1 for stage in stages if stage.status in {"succeeded", "failed", "skipped", "blocked", "unavailable", "cancelled"}
    )
    progress = round((reached / len(stages)) * 100) if stages else 0
    trigger = "github_push" if run.trigger_type == "push" else run.trigger_type
    target = "azure-aks" if run.target_type in {"aks", "azure-kubernetes-service"} else run.target_type
    return {
        "id": str(run.id),
        "project_id": str(run.project_id),
        "deployment_id": str(run.deployment_id) if run.deployment_id else None,
        "status": run.status,
        "reason": run.redacted_failure,
        "failure_code": run.failure_code,
        "approval_required": bool(run.approval_required),
        "approval_status": approval_status,
        "approved_deployment_id": (
            str(decision.get("approved_deployment_id"))
            if isinstance(decision, dict) and decision.get("approved_deployment_id")
            else None
        ),
        "approved_pipeline_run_id": (
            str(decision.get("approved_pipeline_run_id"))
            if isinstance(decision, dict) and decision.get("approved_pipeline_run_id")
            else None
        ),
        "trigger": trigger,
        "branch": run.branch,
        "commit_sha": run.source_revision,
        "target_provider": target if target != "undecided" else None,
        "progress_percent": progress,
        "stages": [_stage_response(stage) for stage in stages],
        "change_analysis": _change_response(change, ai_used=run.repository_ai_used) if change else None,
        "security_scan": _security_scan_response(scan) if scan else None,
        "investigation": _investigation_response(investigation),
        "created_at": _iso(run.created_at),
        "started_at": _iso(run.started_at),
        "completed_at": _iso(run.completed_at),
    }


@router.get("/api/deployments/{deployment_id}/pipeline")
async def get_deployment_pipeline(
    deployment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    deployment_result = await db.execute(
        select(models.Deployment.id).where(
            models.Deployment.id == deployment_id,
            models.Deployment.user_id == current_user.id,
        )
    )
    if deployment_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found.")
    result = await db.execute(
        select(models.PipelineRun)
        .where(models.PipelineRun.deployment_id == deployment_id)
        .order_by(desc(models.PipelineRun.created_at))
        .limit(1)
    )
    run = result.scalars().first()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This legacy deployment has no durable pipeline record.",
        )
    return await _pipeline_response(db, run)


@router.get("/api/projects/{project_id}/change-analysis")
async def list_project_change_analysis(
    project_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    await _project_for_user(db, project_id, current_user.id)
    tenant = await resolve_tenant(db, user=current_user)
    result = await db.execute(
        select(models.ChangeAnalysis, models.PipelineRun.repository_ai_used)
        .outerjoin(models.PipelineRun, models.PipelineRun.id == models.ChangeAnalysis.pipeline_run_id)
        .where(
            models.ChangeAnalysis.tenant_id == tenant.id,
            models.ChangeAnalysis.project_id == project_id,
        )
        .order_by(desc(models.ChangeAnalysis.created_at))
        .limit(limit)
    )
    return [_change_response(record, ai_used=bool(ai_used)) for record, ai_used in result.all()]


@router.get("/api/projects/{project_id}/security-scans")
async def list_project_security_scans(
    project_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    await _project_for_user(db, project_id, current_user.id)
    tenant = await resolve_tenant(db, user=current_user)
    result = await db.execute(
        select(models.SecurityScan)
        .options(selectinload(models.SecurityScan.findings))
        .where(
            models.SecurityScan.tenant_id == tenant.id,
            models.SecurityScan.project_id == project_id,
        )
        .order_by(desc(models.SecurityScan.created_at))
        .limit(limit)
    )
    return [_security_scan_response(record) for record in result.scalars().all()]


class MetricIngestRequest(BaseModel):
    recorded_at: datetime | None = None
    source: Literal["azure-monitor", "application-insights", "container-insights", "health-check", "worker"]
    cpu_percent: float | None = Field(default=None, ge=0, le=100)
    memory_percent: float | None = Field(default=None, ge=0, le=100)
    request_count: int | None = Field(default=None, ge=0)
    request_rate: float | None = Field(default=None, ge=0)
    response_latency_ms: int | None = Field(default=None, ge=0)
    http_error_rate_percent: float | None = Field(default=None, ge=0, le=100)
    availability_percent: float | None = Field(default=None, ge=0, le=100)
    pod_restarts: int | None = Field(default=None, ge=0)
    pods_ready: int | None = Field(default=None, ge=0)
    replica_count: int | None = Field(default=None, ge=0)
    failed_pods: int | None = Field(default=None, ge=0)
    deployment_health: Literal[
        "healthy", "degraded", "unhealthy", "unknown", "rollout_failed", "unavailable"
    ] | None = None

    @field_validator("recorded_at")
    @classmethod
    def validate_recorded_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        now = datetime.now(timezone.utc)
        normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if normalized > now + timedelta(minutes=5) or normalized < now - timedelta(days=7):
            raise ValueError("recorded_at is outside the accepted ingestion window")
        return normalized


async def require_worker_token(
    worker_token: str | None = Header(default=None, alias="X-ZeroOps-Worker-Token"),
) -> None:
    if not config.WORKER_EVENT_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Worker event authentication is not configured.",
        )
    if not worker_token or not hmac.compare_digest(worker_token, config.WORKER_EVENT_TOKEN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid worker credentials.")


def _monitoring_sample(record: models.DeploymentMetric) -> dict[str, Any]:
    return {
        "recorded_at": _iso(record.timestamp),
        "cpu_percent": record.cpu_utilization,
        "memory_percent": record.memory_utilization,
        "request_count": record.request_count,
        "request_rate": record.request_rate,
        "response_latency_ms": record.response_time_ms,
        "http_error_rate_percent": record.error_rate,
        "availability_percent": record.availability_percent,
        "pod_restarts": record.pod_restarts,
        "pods_ready": record.pods_ready,
        "replica_count": record.replica_count,
        "failed_pods": record.failed_pods,
    }


async def _upsert_incidents_from_metrics(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    deployment: models.Deployment,
    samples: list[models.DeploymentMetric],
) -> list[models.Incident]:
    created: list[models.Incident] = []
    for signal in evaluate_incident_rules(samples):
        result = await db.execute(
            select(models.Incident).where(
                models.Incident.tenant_id == tenant_id,
                models.Incident.deployment_id == deployment.id,
                models.Incident.rule_key == signal.rule_key,
                models.Incident.status.in_(["open", "investigating", "mitigated"]),
            )
        )
        incident = result.scalars().first()
        if incident:
            incident.last_observed_at = signal.last_observed_at
            incident.evidence = list(signal.evidence)
            incident.redacted_summary = signal.summary
            continue
        incident_key = f"metric:{deployment.id}:{signal.rule_key}:{signal.first_observed_at.isoformat()}"
        incident = models.Incident(
            tenant_id=tenant_id,
            project_id=deployment.project_id,
            deployment_id=deployment.id,
            idempotency_key=hashlib.sha256(incident_key.encode("utf-8")).hexdigest(),
            status="open",
            severity=signal.severity,
            detection_source="telemetry_rule",
            rule_key=signal.rule_key,
            title=signal.title,
            redacted_summary=signal.summary,
            evidence=list(signal.evidence),
            first_observed_at=signal.first_observed_at,
            last_observed_at=signal.last_observed_at,
        )
        db.add(incident)
        await db.flush()
        db.add(models.ActivityEvent(
            tenant_id=tenant_id,
            user_id=deployment.user_id,
            project_id=deployment.project_id,
            operation_run_id=None,
            action="Incident created",
            actor_type="system",
            details=signal.summary,
            event_data={
                "incident_id": str(incident.id),
                "rule": signal.rule_key,
                "severity": signal.severity,
                "deployment_id": str(deployment.id),
            },
        ))
        if signal.rule_key == "deployment_health_failed" and deployment.live_url:
            params = {"deployment_id": str(deployment.id), "action": "rerun_health_check"}
            parameter_digest = hashlib.sha256(
                json.dumps(params, sort_keys=True).encode("utf-8")
            ).hexdigest()
            db.add(models.RemediationProposal(
                tenant_id=tenant_id,
                project_id=deployment.project_id,
                deployment_id=deployment.id,
                incident_id=incident.id,
                idempotency_key=f"health-check:{incident.id}",
                action_type="rerun_health_check",
                title="Rerun application health check",
                description="Repeat the same non-mutating public endpoint verification.",
                risk_tier="low",
                status="proposed",
                approval_required=False,
                parameter_digest=parameter_digest,
                redacted_parameters=params,
                rationale="The health signal failed; repeating the check is non-mutating and can distinguish a transient outage.",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            ))
        created.append(incident)
    return created


@router.post("/api/deployments/{deployment_id}/metrics", status_code=status.HTTP_202_ACCEPTED)
async def ingest_deployment_metric(
    deployment_id: uuid.UUID,
    request: MetricIngestRequest,
    _: None = Depends(require_worker_token),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(models.Deployment).where(models.Deployment.id == deployment_id))
    deployment = result.scalars().first()
    if deployment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found.")
    user = await db.get(models.User, deployment.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Deployment owner is unavailable.")
    tenant = await resolve_tenant(db, user=user)
    recorded_at = request.recorded_at or datetime.now(timezone.utc)
    metric = models.DeploymentMetric(
        deployment_id=deployment.id,
        project_id=deployment.project_id,
        cpu_utilization=request.cpu_percent,
        memory_utilization=request.memory_percent,
        request_count=request.request_count,
        error_rate=request.http_error_rate_percent,
        response_time_ms=request.response_latency_ms,
        request_rate=request.request_rate,
        availability_percent=request.availability_percent,
        pod_restarts=request.pod_restarts,
        pods_ready=request.pods_ready,
        replica_count=request.replica_count,
        failed_pods=request.failed_pods,
        source=request.source,
        deployment_health=request.deployment_health,
        timestamp=recorded_at.replace(tzinfo=None),
    )
    db.add(metric)
    await db.flush()
    samples_result = await db.execute(
        select(models.DeploymentMetric)
        .where(models.DeploymentMetric.deployment_id == deployment.id)
        .order_by(desc(models.DeploymentMetric.timestamp))
        .limit(10)
    )
    samples = list(reversed(samples_result.scalars().all()))
    incidents = await _upsert_incidents_from_metrics(
        db,
        tenant_id=tenant.id,
        deployment=deployment,
        samples=samples,
    )
    await db.commit()
    return {
        "status": "accepted",
        "metric_id": str(metric.id),
        "incident_ids": [str(incident.id) for incident in incidents],
    }


async def _proposal_response(record: models.RemediationProposal) -> dict[str, Any]:
    status_value = "rejected" if record.status == "denied" else record.status
    return {
        "id": str(record.id),
        "incident_id": str(record.incident_id) if record.incident_id else None,
        "deployment_id": str(record.deployment_id) if record.deployment_id else None,
        "title": record.title,
        "description": record.description,
        "action_type": record.action_type,
        "risk": record.risk_tier,
        "status": status_value,
        "requires_approval": bool(record.approval_required),
        "safe_automatic_action": record.risk_tier == "low" and not record.approval_required,
        "evidence": [{"label": "Policy rationale", "value": record.rationale, "kind": "policy"}],
        "created_at": _iso(record.created_at),
    }


async def _incident_response(db: AsyncSession, record: models.Incident) -> dict[str, Any]:
    investigation_result = await db.execute(
        select(models.AIInvestigation)
        .where(models.AIInvestigation.incident_id == record.id)
        .order_by(desc(models.AIInvestigation.created_at))
        .limit(1)
    )
    investigation = investigation_result.scalars().first()
    proposal_result = await db.execute(
        select(models.RemediationProposal)
        .where(models.RemediationProposal.incident_id == record.id)
        .order_by(desc(models.RemediationProposal.created_at))
    )
    proposals = proposal_result.scalars().all()
    deployment_revision = None
    if record.deployment_id:
        deployment = await db.get(models.Deployment, record.deployment_id)
        deployment_revision = deployment.commit_sha if deployment else None
    return {
        "id": str(record.id),
        "project_id": str(record.project_id),
        "deployment_id": str(record.deployment_id) if record.deployment_id else None,
        "deployment_revision": deployment_revision,
        "title": record.title,
        "summary": record.redacted_summary,
        "severity": record.severity,
        "status": record.status,
        "rule": record.rule_key,
        "detected_at": _iso(record.first_observed_at),
        "acknowledged_at": _iso(record.acknowledged_at),
        "resolved_at": _iso(record.resolved_at),
        "evidence": [
            {
                "source": item.get("source", "metric"),
                "summary": str(item.get("summary") or item.get("metric") or item.get("state") or "Recorded evidence"),
                "recorded_at": item.get("recorded_at"),
            }
            for item in redact_sensitive_values(record.evidence or [])
            if isinstance(item, dict)
        ],
        "investigation": _investigation_response(investigation),
        "remediation_proposals": [await _proposal_response(item) for item in proposals],
    }


@router.get("/api/projects/{project_id}/monitoring")
async def get_project_monitoring(
    project_id: uuid.UUID,
    window: Literal["live", "1h", "6h", "24h"] = Query(default="live"),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    project = await _project_for_user(db, project_id, current_user.id)
    tenant = await resolve_tenant(db, user=current_user)
    deployment_result = await db.execute(
        select(models.Deployment)
        .where(
            models.Deployment.project_id == project.id,
            models.Deployment.user_id == current_user.id,
        )
        .order_by(desc(models.Deployment.started_at))
        .limit(1)
    )
    deployment = deployment_result.scalars().first()
    if deployment is None:
        return {
            "project_id": str(project.id),
            "window": window,
            "available_windows": ["live"],
            "availability": "no_telemetry",
            "source": None,
            "target_provider": None,
            "deployment_revision": None,
            "deployment_health": None,
            "latest_incidents": [],
            "samples": [],
            "message": "No deployment exists, so no telemetry can be collected.",
        }
    duration = {"live": timedelta(minutes=15), "1h": timedelta(hours=1), "6h": timedelta(hours=6), "24h": timedelta(hours=24)}[window]
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now_naive - duration
    metrics_result = await db.execute(
        select(models.DeploymentMetric)
        .where(
            models.DeploymentMetric.project_id == project.id,
            models.DeploymentMetric.deployment_id == deployment.id,
            models.DeploymentMetric.timestamp >= cutoff,
        )
        .order_by(models.DeploymentMetric.timestamp)
        .limit(1000)
    )
    metrics = metrics_result.scalars().all()
    earliest_result = await db.execute(
        select(func.min(models.DeploymentMetric.timestamp)).where(
            models.DeploymentMetric.project_id == project.id,
            models.DeploymentMetric.deployment_id == deployment.id,
        )
    )
    earliest_metric_at = earliest_result.scalar_one_or_none()
    available_windows = ["live"]
    for candidate, candidate_duration in (
        ("1h", timedelta(hours=1)),
        ("6h", timedelta(hours=6)),
        ("24h", timedelta(hours=24)),
    ):
        if earliest_metric_at and earliest_metric_at <= now_naive - candidate_duration:
            available_windows.append(candidate)
    incident_result = await db.execute(
        select(models.Incident)
        .where(models.Incident.tenant_id == tenant.id, models.Incident.project_id == project.id)
        .order_by(desc(models.Incident.last_observed_at))
        .limit(5)
    )
    incidents = [await _incident_response(db, item) for item in incident_result.scalars().all()]
    metadata = deployment.infrastructure_metadata if isinstance(deployment.infrastructure_metadata, dict) else {}
    target = metadata.get("target_provider") or (metadata.get("target") or {}).get("provider")
    if target in {"aks", "azure-kubernetes-service"}:
        target = "azure-aks"
    latest_metric = metrics[-1] if metrics else None
    return {
        "project_id": str(project.id),
        "window": window,
        "available_windows": available_windows,
        "availability": "available" if metrics else "no_telemetry",
        "source": latest_metric.source if latest_metric else None,
        "target_provider": target,
        "deployment_revision": metadata.get("revision") or deployment.commit_sha,
        "deployment_health": latest_metric.deployment_health if latest_metric else None,
        "latest_incidents": incidents,
        "samples": [_monitoring_sample(metric) for metric in metrics],
        "message": None if metrics else "No telemetry received in the selected window.",
    }


@router.get("/api/projects/{project_id}/incidents")
async def list_project_incidents(
    project_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    await _project_for_user(db, project_id, current_user.id)
    tenant = await resolve_tenant(db, user=current_user)
    result = await db.execute(
        select(models.Incident)
        .where(models.Incident.tenant_id == tenant.id, models.Incident.project_id == project_id)
        .order_by(desc(models.Incident.last_observed_at))
        .limit(limit)
    )
    return [await _incident_response(db, record) for record in result.scalars().all()]


async def _incident_for_user(
    db: AsyncSession,
    incident_id: uuid.UUID,
    user: models.User,
) -> tuple[models.Incident, models.Tenant]:
    tenant = await resolve_tenant(db, user=user)
    result = await db.execute(
        select(models.Incident)
        .join(models.Project, models.Project.id == models.Incident.project_id)
        .where(
            models.Incident.id == incident_id,
            models.Incident.tenant_id == tenant.id,
            models.Project.user_id == user.id,
        )
    )
    incident = result.scalars().first()
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found.")
    return incident, tenant


@router.get("/api/incidents/{incident_id}")
async def get_incident(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    incident, _ = await _incident_for_user(db, incident_id, current_user)
    return await _incident_response(db, incident)


@router.post("/api/incidents/{incident_id}/acknowledge")
async def acknowledge_incident(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    incident, tenant = await _incident_for_user(db, incident_id, current_user)
    if incident.status in {"resolved", "dismissed"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Closed incidents cannot be acknowledged.")
    incident.acknowledged_by_user_id = current_user.id
    incident.acknowledged_at = datetime.now(timezone.utc)
    db.add(models.ActivityEvent(
        tenant_id=tenant.id,
        user_id=current_user.id,
        project_id=incident.project_id,
        action="Incident acknowledged",
        actor_type="user",
        details="The incident owner acknowledged the detected condition.",
        event_data={"incident_id": str(incident.id)},
    ))
    await db.commit()
    return await _incident_response(db, incident)


@router.post("/api/incidents/{incident_id}/dismiss")
async def dismiss_incident(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    incident, tenant = await _incident_for_user(db, incident_id, current_user)
    if incident.status == "resolved":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Resolved incidents cannot be dismissed.")
    incident.status = "dismissed"
    incident.closed_at = datetime.now(timezone.utc)
    incident.resolved_by_user_id = current_user.id
    db.add(models.ActivityEvent(
        tenant_id=tenant.id,
        user_id=current_user.id,
        project_id=incident.project_id,
        action="Incident dismissed",
        actor_type="user",
        details="The user dismissed the incident without executing a remediation.",
        event_data={"incident_id": str(incident.id)},
    ))
    await db.commit()
    return await _incident_response(db, incident)


@router.post("/api/incidents/{incident_id}/investigate")
async def request_incident_investigation(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    incident, tenant = await _incident_for_user(db, incident_id, current_user)
    existing_result = await db.execute(
        select(models.AIInvestigation)
        .where(models.AIInvestigation.incident_id == incident.id)
        .order_by(desc(models.AIInvestigation.created_at))
        .limit(1)
    )
    existing = existing_result.scalars().first()
    if existing and existing.status in {"queued", "running", "succeeded"}:
        return _investigation_response(existing)
    evidence = redact_sensitive_values(incident.evidence or [])
    evidence_digest = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    # The current durable worker consumes deployment jobs only. Persist an
    # explicit unavailable investigation instead of pretending a background
    # model job was queued. Pipeline failures are investigated inside the
    # deployment worker where their source/log context exists.
    investigation = models.AIInvestigation(
        tenant_id=tenant.id,
        project_id=incident.project_id,
        deployment_id=incident.deployment_id,
        pipeline_run_id=incident.pipeline_run_id,
        incident_id=incident.id,
        requested_by_user_id=current_user.id,
        idempotency_key=f"manual-incident:{incident.id}:{evidence_digest[:24]}",
        trigger_type="incident",
        status="unavailable",
        model_provider="unavailable",
        model_name="unavailable",
        prompt_version="incident-investigation.v1",
        evidence_digest=evidence_digest,
        evidence=evidence,
        requires_user_action=True,
        error_code="INVESTIGATION_WORKER_UNAVAILABLE",
        redacted_error="A durable incident-investigation worker is not configured for manual requests.",
        completed_at=datetime.now(timezone.utc),
    )
    db.add(investigation)
    await db.commit()
    await db.refresh(investigation)
    return _investigation_response(investigation)


async def _proposal_for_user(
    db: AsyncSession,
    proposal_id: uuid.UUID,
    user: models.User,
) -> tuple[models.RemediationProposal, models.Tenant]:
    tenant = await resolve_tenant(db, user=user)
    result = await db.execute(
        select(models.RemediationProposal)
        .join(models.Project, models.Project.id == models.RemediationProposal.project_id)
        .where(
            models.RemediationProposal.id == proposal_id,
            models.RemediationProposal.tenant_id == tenant.id,
            models.Project.user_id == user.id,
        )
    )
    proposal = result.scalars().first()
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Remediation proposal not found.")
    return proposal, tenant


@router.post("/api/remediation-proposals/{proposal_id}/approve")
async def approve_remediation(
    proposal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    proposal, tenant = await _proposal_for_user(db, proposal_id, current_user)
    if _expired(proposal.expires_at):
        proposal.status = "expired"
        await db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Remediation proposal has expired.")
    if proposal.status not in {"proposed", "pending_approval"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Proposal is no longer awaiting a decision.")
    proposal.status = "approved"
    proposal.decided_by_user_id = current_user.id
    proposal.decided_at = datetime.now(timezone.utc)
    db.add(models.ActivityEvent(
        tenant_id=tenant.id,
        user_id=current_user.id,
        project_id=proposal.project_id,
        action="Remediation approved",
        actor_type="user",
        details=f"Approved {proposal.risk_tier}-risk action {proposal.action_type}.",
        event_data={"proposal_id": str(proposal.id), "risk_tier": proposal.risk_tier},
    ))
    await db.commit()
    return await _proposal_response(proposal)


@router.post("/api/remediation-proposals/{proposal_id}/reject")
async def reject_remediation(
    proposal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    proposal, tenant = await _proposal_for_user(db, proposal_id, current_user)
    if proposal.status not in {"proposed", "pending_approval", "approved"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Proposal is no longer awaiting a decision.")
    proposal.status = "denied"
    proposal.decided_by_user_id = current_user.id
    proposal.decided_at = datetime.now(timezone.utc)
    db.add(models.ActivityEvent(
        tenant_id=tenant.id,
        user_id=current_user.id,
        project_id=proposal.project_id,
        action="Remediation rejected",
        actor_type="user",
        details=f"Rejected {proposal.risk_tier}-risk action {proposal.action_type}.",
        event_data={"proposal_id": str(proposal.id), "risk_tier": proposal.risk_tier},
    ))
    await db.commit()
    return await _proposal_response(proposal)


@router.post("/api/remediation-proposals/{proposal_id}/execute")
async def execute_remediation(
    proposal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    proposal, tenant = await _proposal_for_user(db, proposal_id, current_user)
    if _expired(proposal.expires_at):
        proposal.status = "expired"
        await db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Remediation proposal has expired.")
    if proposal.approval_required and proposal.status != "approved":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This remediation requires explicit approval.")
    if proposal.status not in {"proposed", "approved"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Remediation cannot be executed from its current state.")

    attempt_result = await db.execute(
        select(func.count(models.RemediationExecution.id)).where(
            models.RemediationExecution.proposal_id == proposal.id
        )
    )
    attempt = int(attempt_result.scalar() or 0) + 1
    execution = models.RemediationExecution(
        tenant_id=tenant.id,
        project_id=proposal.project_id,
        deployment_id=proposal.deployment_id,
        incident_id=proposal.incident_id,
        proposal_id=proposal.id,
        requested_by_user_id=current_user.id,
        idempotency_key=f"execute:{proposal.id}:{attempt}",
        attempt_number=attempt,
        executor_kind="deterministic",
        executor_name="zeroops-health-verifier",
        status="running",
        verification_status="running",
        started_at=datetime.now(timezone.utc),
    )
    db.add(execution)
    await db.commit()
    if proposal.action_type != "rerun_health_check" or not proposal.deployment_id:
        execution.status = "unavailable"
        execution.verification_status = "unavailable"
        execution.failure_code = "REMEDIATION_EXECUTOR_UNAVAILABLE"
        execution.redacted_error = "No deterministic executor is registered for this remediation action."
        execution.completed_at = datetime.now(timezone.utc)
        await db.commit()
    else:
        deployment = await db.get(models.Deployment, proposal.deployment_id)
        deployment_metadata = (
            deployment.infrastructure_metadata
            if deployment and isinstance(deployment.infrastructure_metadata, dict)
            else {}
        )
        release_metadata = deployment_metadata.get("release")
        expected_app_name = (
            str(release_metadata.get("application_name") or "").strip()
            if isinstance(release_metadata, dict)
            else ""
        )
        if not deployment or not deployment.live_url or not expected_app_name:
            execution.status = "unavailable"
            execution.verification_status = "unavailable"
            execution.failure_code = "HEALTH_ENDPOINT_UNAVAILABLE"
            execution.redacted_error = (
                "The deployment has no App Service endpoint and provider-issued application name "
                "that can be safely rechecked."
            )
            execution.completed_at = datetime.now(timezone.utc)
            await db.commit()
        else:
            try:
                app_service.verify_public_endpoint(
                    deployment.live_url,
                    expected_app_name=expected_app_name,
                    attempts=1,
                    delay_seconds=0,
                )
                execution.status = "succeeded"
                execution.verification_status = "succeeded"
                execution.result_summary = "The existing public endpoint responded to the repeated health check."
                execution.completed_at = datetime.now(timezone.utc)
                execution.verified_at = execution.completed_at
                proposal.status = "executed"
                if proposal.incident_id:
                    incident = await db.get(models.Incident, proposal.incident_id)
                    if incident and incident.status not in {"resolved", "dismissed"}:
                        incident.status = "resolved"
                        incident.resolved_at = execution.completed_at
                        incident.closed_at = execution.completed_at
                        incident.resolved_by_user_id = current_user.id
                await db.commit()
            except Exception as error:
                execution.status = "failed"
                execution.verification_status = "failed"
                execution.failure_code = "HEALTH_CHECK_FAILED"
                execution.redacted_error = redact_sensitive_text(str(error), maximum_length=1_000)
                execution.completed_at = datetime.now(timezone.utc)
                await db.commit()
    return {
        "id": str(execution.id),
        "proposal_id": str(execution.proposal_id),
        "status": execution.status,
        "requested_by": str(current_user.id),
        "started_at": _iso(execution.started_at),
        "completed_at": _iso(execution.completed_at),
        "verification_summary": execution.result_summary,
        "error": execution.redacted_error,
    }


def verify_github_webhook_signature(secret: str, body: bytes, signature: str | None) -> bool:
    if not secret or not signature or not signature.startswith("sha256="):
        return False
    supplied = signature.removeprefix("sha256=").strip().lower()
    if len(supplied) != 64 or any(char not in "0123456789abcdef" for char in supplied):
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(supplied, expected)


def _push_branch(ref: Any) -> str | None:
    value = str(ref or "")
    prefix = "refs/heads/"
    return value[len(prefix):] if value.startswith(prefix) else None


async def _approved_plan(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID):
    result = await db.execute(
        select(models.InfrastructurePlan)
        .where(
            models.InfrastructurePlan.project_id == project_id,
            models.InfrastructurePlan.user_id == user_id,
            models.InfrastructurePlan.status == "approved",
        )
        .order_by(desc(models.InfrastructurePlan.updated_at), desc(models.InfrastructurePlan.created_at))
        .limit(1)
    )
    return result.scalars().first()


async def _active_azure_connection(db: AsyncSession, user_id: uuid.UUID):
    result = await db.execute(
        select(models.UserAzureConnection)
        .where(
            models.UserAzureConnection.user_id == user_id,
            models.UserAzureConnection.is_active.is_(True),
            models.UserAzureConnection.connection_status == "connected",
        )
        .order_by(desc(models.UserAzureConnection.created_at))
        .limit(1)
    )
    return result.scalars().first()


async def _latest_analysis_hint(db: AsyncSession, project: models.Project) -> dict[str, Any]:
    result = await db.execute(
        select(models.AIAnalysis)
        .where(models.AIAnalysis.project_id == project.id)
        .order_by(desc(models.AIAnalysis.created_at))
        .limit(1)
    )
    analysis = result.scalars().first()
    if analysis is None:
        return {"framework": project.framework, "language": project.language}
    return {
        "framework": analysis.framework,
        "language": analysis.language,
        "runtime": analysis.runtime,
        "docker_support": analysis.docker_support,
        "deployment_strategy": analysis.deployment_strategy,
        "kubernetes_manifest": analysis.kubernetes_manifest,
    }


def _approval_metadata(deployment: models.Deployment) -> dict[str, Any]:
    return (
        dict(deployment.infrastructure_metadata)
        if isinstance(deployment.infrastructure_metadata, dict)
        else {}
    )


def _approval_decision(metadata: dict[str, Any]) -> dict[str, Any] | None:
    decision = metadata.get("pipeline_approval_decision")
    return dict(decision) if isinstance(decision, dict) else None


async def _owned_approval_run(
    db: AsyncSession,
    *,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[models.PipelineRun, models.Deployment, models.Project, models.Tenant]:
    result = await db.execute(
        select(models.PipelineRun, models.Deployment)
        .join(models.Deployment, models.Deployment.id == models.PipelineRun.deployment_id)
        .where(
            models.PipelineRun.id == run_id,
            models.Deployment.user_id == user_id,
        )
        .with_for_update()
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline run not found.")
    pipeline_run, deployment = row
    project = await _project_for_user(db, pipeline_run.project_id, user_id)
    owner = await db.get(models.User, user_id)
    if owner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline run not found.")
    tenant = await resolve_tenant(db, user=owner)
    if pipeline_run.tenant_id != tenant.id or deployment.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline run not found.")
    return pipeline_run, deployment, project, tenant


async def _approval_ready_stages(
    db: AsyncSession,
    pipeline_run: models.PipelineRun,
) -> tuple[list[models.PipelineStageAttempt], models.PipelineStageAttempt]:
    stage_result = await db.execute(
        select(models.PipelineStageAttempt)
        .where(models.PipelineStageAttempt.pipeline_run_id == pipeline_run.id)
        .order_by(models.PipelineStageAttempt.stage_order, models.PipelineStageAttempt.attempt_number)
    )
    stages = list(stage_result.scalars().all())
    approval_stage = next(
        (stage for stage in stages if stage.stage_key == "approval" and stage.is_required),
        None,
    )
    if (
        pipeline_run.status != "blocked"
        or pipeline_run.failure_code != "DEPLOYMENT_APPROVAL_REQUIRED"
        or not pipeline_run.approval_required
        or approval_stage is None
        or approval_stage.status != "blocked"
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This pipeline run is not waiting at its deployment approval gate.",
        )
    incomplete = [
        stage
        for stage in stages
        if stage.is_required
        and stage.stage_order < approval_stage.stage_order
        and stage.status not in {"succeeded", "skipped"}
    ]
    if incomplete:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Every required validation stage must pass before deployment approval.",
        )
    return stages, approval_stage


def _metadata_uuid(value: Any, *, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"The validated release has no valid {field} binding.",
        ) from error


async def _exact_approval_inputs(
    db: AsyncSession,
    *,
    pipeline_run: models.PipelineRun,
    deployment: models.Deployment,
    project: models.Project,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> tuple[models.InfrastructurePlan, models.ProjectPipelineConfiguration]:
    metadata = _approval_metadata(deployment)
    plan_reference = metadata.get("architecture_plan")
    config_reference = metadata.get("pipeline_configuration")
    if not isinstance(plan_reference, dict) or not isinstance(config_reference, dict):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The validated release is missing immutable plan or pipeline configuration evidence.",
        )

    plan_id = _metadata_uuid(plan_reference.get("id"), field="infrastructure plan")
    try:
        plan_revision = int(plan_reference.get("revision"))
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The validated release has no valid infrastructure plan revision.",
        ) from error
    latest_plan = await _approved_plan(db, project.id, user_id)
    if (
        latest_plan is None
        or latest_plan.id != plan_id
        or latest_plan.revision != plan_revision
        or latest_plan.status != "approved"
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The approved infrastructure plan changed after validation; run the checks again.",
        )

    if pipeline_run.configuration_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The validation run is not bound to a versioned pipeline configuration.",
        )
    configuration_result = await db.execute(
        select(models.ProjectPipelineConfiguration).where(
            models.ProjectPipelineConfiguration.id == pipeline_run.configuration_id,
            models.ProjectPipelineConfiguration.tenant_id == tenant_id,
            models.ProjectPipelineConfiguration.project_id == project.id,
            models.ProjectPipelineConfiguration.version == pipeline_run.configuration_version,
        )
    )
    configuration = configuration_result.scalars().first()
    latest_configuration = await _latest_config(
        db,
        tenant_id=tenant_id,
        project_id=project.id,
    )
    reference_id = _metadata_uuid(config_reference.get("id"), field="pipeline configuration")
    try:
        reference_version = int(config_reference.get("version"))
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The validated release has no valid pipeline configuration version.",
        ) from error
    reference_digest = str(config_reference.get("digest") or "").strip().lower()
    if (
        configuration is None
        or latest_configuration is None
        or latest_configuration.id != configuration.id
        or configuration.id != reference_id
        or configuration.version != reference_version
        or (configuration.config_digest or "") != reference_digest
        or configuration.deployment_mode != "require_approval"
        or not configuration.enabled
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The pipeline configuration changed after validation; run the checks again.",
        )

    if (
        deployment.commit_sha != pipeline_run.source_revision
        or deployment.branch != pipeline_run.branch
        or metadata.get("target_provider") != pipeline_run.target_type
        or pipeline_run.target_type not in {"azure-app-service", "azure-aks"}
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The validated source or deployment target binding is inconsistent.",
        )
    return latest_plan, configuration


def _approved_image_reference(image: str | None, version: str) -> str | None:
    if not image:
        return None
    tagged = image.split("@", 1)[0]
    slash = tagged.rfind("/")
    colon = tagged.rfind(":")
    repository = tagged[:colon] if colon > slash else tagged
    return f"{repository}:{version}"


def _approval_response(
    *,
    validation_run_id: uuid.UUID,
    deployment_id: uuid.UUID,
    pipeline_run_id: uuid.UUID,
    idempotent: bool,
) -> dict[str, Any]:
    return {
        "status": "approved",
        "approval_status": "approved_consumed",
        "idempotent": idempotent,
        "validation_pipeline_run_id": str(validation_run_id),
        "deployment_id": str(deployment_id),
        "pipeline_run_id": str(pipeline_run_id),
    }


@router.post("/api/pipeline-runs/{run_id}/approve")
async def approve_pipeline_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    pipeline_run, deployment, project, tenant = await _owned_approval_run(
        db,
        run_id=run_id,
        user_id=current_user.id,
    )
    metadata = _approval_metadata(deployment)
    decision = _approval_decision(metadata)
    if decision and decision.get("status") == "approved" and decision.get("consumed") is True:
        approved_deployment_id = _metadata_uuid(
            decision.get("approved_deployment_id"),
            field="approved deployment",
        )
        approved_run_id = _metadata_uuid(
            decision.get("approved_pipeline_run_id"),
            field="approved pipeline run",
        )
        approved_result = await db.execute(
            select(models.PipelineRun, models.Deployment)
            .join(models.Deployment, models.Deployment.id == models.PipelineRun.deployment_id)
            .where(
                models.PipelineRun.id == approved_run_id,
                models.PipelineRun.deployment_id == approved_deployment_id,
                models.Deployment.user_id == current_user.id,
            )
        )
        if approved_result.first() is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The recorded approval result is unavailable.",
            )
        return _approval_response(
            validation_run_id=pipeline_run.id,
            deployment_id=approved_deployment_id,
            pipeline_run_id=approved_run_id,
            idempotent=True,
        )
    if decision and decision.get("status") == "rejected":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This approval was already rejected.")
    if decision and decision.get("status") not in {None, "pending"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This approval decision is not pending.")

    await _approval_ready_stages(db, pipeline_run)
    if deployment.status != "stopped":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The validation deployment has not stopped safely at its approval boundary.",
        )
    plan, configuration = await _exact_approval_inputs(
        db,
        pipeline_run=pipeline_run,
        deployment=deployment,
        project=project,
        user_id=current_user.id,
        tenant_id=tenant.id,
    )

    approved_deployment_id = uuid.uuid4()
    approved_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    version = f"v{datetime.now(timezone.utc).strftime('%Y%m%d')}.{approved_deployment_id.hex[:12]}"
    approved_metadata = {
        key: metadata[key]
        for key in (
            "target_provider",
            "target_reason",
            "target",
            "available_targets",
            "source_type",
            "source_revision",
            "architecture_plan",
            "pipeline_configuration",
        )
        if key in metadata
    }
    approved_metadata["requested_target"] = pipeline_run.target_type
    approved_deployment = models.Deployment(
        id=approved_deployment_id,
        user_id=current_user.id,
        project_id=project.id,
        status="queued",
        environment=deployment.environment,
        branch=pipeline_run.branch,
        version=version,
        commit_sha=pipeline_run.source_revision,
        image=_approved_image_reference(deployment.image, version),
        deployed_by="Authenticated pipeline approval",
        infrastructure_metadata=dict(approved_metadata),
    )
    db.add(approved_deployment)
    await db.flush()
    context = context_from_configuration(
        configuration,
        target_type=pipeline_run.target_type,
        has_dependencies=True,
        has_tests=configuration.run_unit_tests,
        has_iac=bool(plan.plan_data),
        infrastructure_change=False,
    )
    approved_run = await create_pipeline_run(
        db,
        tenant_id=tenant.id,
        project_id=project.id,
        deployment_id=approved_deployment.id,
        requested_by_user_id=current_user.id,
        configuration=configuration,
        trigger_type="retry",
        branch=pipeline_run.branch,
        source_revision=pipeline_run.source_revision,
        target_type=pipeline_run.target_type,
        idempotency_key=f"approval:{pipeline_run.id}",
        context=context,
        previous_successful_revision=pipeline_run.previous_successful_revision,
    )
    claims = {
        "schema": pipeline_approval.APPROVAL_SCHEMA,
        "tenant_id": str(tenant.id),
        "project_id": str(project.id),
        "validation_run_id": str(pipeline_run.id),
        "validation_deployment_id": str(deployment.id),
        "approved_deployment_id": str(approved_deployment.id),
        "approved_pipeline_run_id": str(approved_run.id),
        "source_revision": pipeline_run.source_revision,
        "branch": pipeline_run.branch,
        "target_type": pipeline_run.target_type,
        "plan_id": str(plan.id),
        "plan_revision": plan.revision,
        "configuration_id": str(configuration.id),
        "configuration_version": configuration.version,
        "configuration_digest": configuration.config_digest or "",
        "approved_by_user_id": str(current_user.id),
        "approved_at": approved_at,
    }
    signed_evidence = pipeline_approval.sign_pipeline_approval(claims, secret=config.JWT_SECRET)
    approved_metadata["pipeline_approval"] = signed_evidence
    approved_metadata["pipeline_approval_decision"] = {
        "status": "approved",
        "consumed": False,
        "validation_pipeline_run_id": str(pipeline_run.id),
    }
    # Assign a fresh object so SQLAlchemy records the post-flush JSON update;
    # mutating the constructor's dictionary in place is not change tracked.
    approved_deployment.infrastructure_metadata = dict(approved_metadata)

    db.add(models.DeploymentJob(
        id=uuid.uuid4(),
        user_id=current_user.id,
        project_id=project.id,
        deployment_id=approved_deployment.id,
        status="queued",
        cloud="azure",
        region=plan.region,
        infrastructure_spec=plan.plan_data,
    ))
    original_metadata = dict(metadata)
    original_metadata["pipeline_approval_decision"] = {
        "status": "approved",
        "consumed": True,
        "approved_by_user_id": str(current_user.id),
        "approved_at": approved_at,
        "approved_deployment_id": str(approved_deployment.id),
        "approved_pipeline_run_id": str(approved_run.id),
    }
    deployment.infrastructure_metadata = original_metadata
    project.status = "deploying"
    db.add(models.ActivityEvent(
        tenant_id=tenant.id,
        user_id=current_user.id,
        project_id=project.id,
        action="Pipeline deployment approved",
        actor_type="user",
        actor_id=str(current_user.id),
        details="A validated immutable release was approved and queued for a fresh execution.",
        event_data={
            "validation_pipeline_run_id": str(pipeline_run.id),
            "approved_pipeline_run_id": str(approved_run.id),
            "approved_deployment_id": str(approved_deployment.id),
            "source_revision": pipeline_run.source_revision,
            "target_type": pipeline_run.target_type,
            "plan_id": str(plan.id),
            "plan_revision": plan.revision,
            "configuration_id": str(configuration.id),
            "configuration_version": configuration.version,
        },
    ))
    db.add(models.Notification(
        user_id=current_user.id,
        title="Deployment Approved",
        message=f"The validated release for {project.name} was approved and queued for fresh checks.",
        type="info",
        category="deployment",
    ))
    await db.commit()
    return _approval_response(
        validation_run_id=pipeline_run.id,
        deployment_id=approved_deployment.id,
        pipeline_run_id=approved_run.id,
        idempotent=False,
    )


@router.post("/api/pipeline-runs/{run_id}/reject")
async def reject_pipeline_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    pipeline_run, deployment, project, tenant = await _owned_approval_run(
        db,
        run_id=run_id,
        user_id=current_user.id,
    )
    metadata = _approval_metadata(deployment)
    decision = _approval_decision(metadata)
    if decision and decision.get("status") in {"approved", "rejected"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This pipeline approval already has a final decision.",
        )
    stages, approval_stage = await _approval_ready_stages(db, pipeline_run)
    rejection_reason = "Deployment approval was rejected by the authenticated project owner."
    for stage in stages:
        if stage.stage_order < approval_stage.stage_order:
            continue
        if stage.status in {"queued", "blocked"}:
            transition_stage(
                stage,
                "cancelled",
                predecessors=stages,
                reason=rejection_reason,
                failure_code="DEPLOYMENT_APPROVAL_REJECTED",
                redacted_error=rejection_reason,
            )
    transition_pipeline_run(
        pipeline_run,
        "cancelled",
        reason=rejection_reason,
        failure_code="DEPLOYMENT_APPROVAL_REJECTED",
    )
    pipeline_run.current_stage_key = None
    deployment.status = "stopped"
    deployment.failure_reason = None
    deployment.completed_at = deployment.completed_at or datetime.now(timezone.utc).replace(tzinfo=None)
    rejected_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    metadata["pipeline_approval_decision"] = {
        "status": "rejected",
        "consumed": True,
        "rejected_by_user_id": str(current_user.id),
        "rejected_at": rejected_at,
    }
    deployment.infrastructure_metadata = metadata
    project.status = "active"
    db.add(models.ActivityEvent(
        tenant_id=tenant.id,
        user_id=current_user.id,
        project_id=project.id,
        action="Pipeline deployment rejected",
        actor_type="user",
        actor_id=str(current_user.id),
        details="The validated immutable release was rejected and will not be deployed.",
        event_data={
            "validation_pipeline_run_id": str(pipeline_run.id),
            "deployment_id": str(deployment.id),
            "source_revision": pipeline_run.source_revision,
            "target_type": pipeline_run.target_type,
        },
    ))
    db.add(models.Notification(
        user_id=current_user.id,
        title="Deployment Rejected",
        message=f"The validated release for {project.name} was rejected and stopped.",
        type="warning",
        category="deployment",
    ))
    await db.commit()
    return {
        "status": "rejected",
        "approval_status": "rejected",
        "validation_pipeline_run_id": str(pipeline_run.id),
        "deployment_id": str(deployment.id),
    }


async def _queue_push_deployment(
    db: AsyncSession,
    *,
    tenant: models.Tenant,
    owner: models.User,
    project: models.Project,
    configuration: models.ProjectPipelineConfiguration,
    branch: str,
    commit_sha: str,
    delivery: models.WebhookDelivery,
) -> tuple[models.Deployment, models.PipelineRun]:
    existing_result = await db.execute(
        select(models.PipelineRun).where(
            models.PipelineRun.tenant_id == tenant.id,
            models.PipelineRun.idempotency_key == f"push:{project.id}:{commit_sha}",
        )
    )
    existing = existing_result.scalars().first()
    if existing:
        deployment = await db.get(models.Deployment, existing.deployment_id) if existing.deployment_id else None
        if deployment is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This commit already has a validation run without a deployment record.",
            )
        return deployment, existing

    plan = await _approved_plan(db, project.id, owner.id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The GitHub push was verified, but the project has no approved infrastructure plan.",
        )
    connection = await _active_azure_connection(db, owner.id)
    hint = await _latest_analysis_hint(db, project)
    try:
        selected_target = deployment_targets.choose_target(hint, connection, "auto")
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

    deployment_id = uuid.uuid4()
    version = f"v{datetime.now(timezone.utc).strftime('%Y%m%d')}.{deployment_id.hex[:12]}"
    name_prefix = deployment_targets.namespace_prefix(selected_target, owner.id)
    image_name = re.sub(
        r"-+", "-", re.sub(r"[^a-z0-9-]", "-", f"{name_prefix}-{project.name}-{str(project.id)[:8]}".lower())
    ).strip("-")
    image_ref = deployment_targets.image_ref_for_target(selected_target, image_name, version)
    deployment = models.Deployment(
        id=deployment_id,
        user_id=owner.id,
        project_id=project.id,
        status="queued",
        environment="production",
        branch=branch,
        version=version,
        commit_sha=commit_sha,
        deployed_by="GitHub push",
        image=image_ref,
        infrastructure_metadata={
            # The worker must re-resolve an automatic target from the current
            # immutable clone.  The selected target below is only a preflight
            # readiness hint until that deterministic inspection completes.
            "requested_target": "auto",
            "target_provider": selected_target.provider,
            "target_reason": selected_target.reason,
            "target": deployment_targets.metadata_for_target(selected_target),
            "source_type": "github",
            "source_revision": {"provider": "github", "branch": branch, "commit_sha": commit_sha},
            "architecture_plan": {
                "id": str(plan.id),
                "revision": plan.revision,
                "provider": plan.provider,
                "region": plan.region,
            },
            "pipeline_configuration": {
                "id": str(configuration.id),
                "version": configuration.version,
                "digest": configuration.config_digest or "",
            },
            "pipeline_approval_decision": {
                "status": "pending" if configuration.deployment_mode == "require_approval" else "not_required",
                "consumed": False,
            },
        },
    )
    db.add(deployment)
    await db.flush()
    previous_result = await db.execute(
        select(models.Deployment.commit_sha)
        .where(
            models.Deployment.project_id == project.id,
            models.Deployment.status == "running",
            models.Deployment.commit_sha.is_not(None),
        )
        .order_by(desc(models.Deployment.completed_at))
        .limit(1)
    )
    previous_revision = previous_result.scalar_one_or_none()
    has_dependencies = bool(getattr((await db.execute(
        select(models.AIAnalysis)
        .where(models.AIAnalysis.project_id == project.id)
        .order_by(desc(models.AIAnalysis.created_at))
        .limit(1)
    )).scalars().first(), "package_manager", None))
    context = context_from_configuration(
        configuration,
        target_type=selected_target.provider,
        has_dependencies=has_dependencies,
        has_tests=configuration.run_unit_tests,
        has_iac=bool(plan.plan_data),
        infrastructure_change=False,
    )
    run = await create_pipeline_run(
        db,
        tenant_id=tenant.id,
        project_id=project.id,
        deployment_id=deployment.id,
        requested_by_user_id=None,
        configuration=configuration,
        trigger_type="push",
        branch=branch,
        source_revision=commit_sha,
        target_type=selected_target.provider,
        idempotency_key=f"push:{project.id}:{commit_sha}",
        context=context,
        previous_successful_revision=previous_revision,
    )
    delivery.deployment_id = deployment.id
    delivery.pipeline_run_id = run.id
    project.status = "deploying"

    # Every mode is executed by the same durable worker.  Approval-mode runs
    # perform all deterministic checks and stop at their Approval stage;
    # validation-only runs complete without crossing a cloud release boundary.
    db.add(models.DeploymentJob(
        id=uuid.uuid4(),
        user_id=owner.id,
        project_id=project.id,
        deployment_id=deployment.id,
        status="queued",
        cloud="azure",
        region=plan.region,
        infrastructure_spec=plan.plan_data,
    ))
    db.add(models.Notification(
        user_id=owner.id,
        title="GitHub Push Received",
        message=f"Verified {project.full_name}@{commit_sha[:12]} on branch {branch}.",
        type="info",
        category="deployment",
    ))
    return deployment, run


@router.post("/api/webhooks/github/{project_id}", status_code=status.HTTP_202_ACCEPTED)
async def github_push_webhook(
    project_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    github_event: str | None = Header(default=None, alias="X-GitHub-Event"),
    github_delivery: str | None = Header(default=None, alias="X-GitHub-Delivery"),
    github_signature: str | None = Header(default=None, alias="X-Hub-Signature-256"),
):
    body = await request.body()
    if len(body) > 2 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Webhook payload is too large.")
    if not github_event or not github_delivery or len(github_delivery) > 128:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Required GitHub delivery headers are missing.")
    project = await db.get(models.Project, project_id)
    if project is None:
        # Do not confirm project identifiers to unsigned callers.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature.")
    webhook_secret = vault.get_project_secret(str(project.id), "GITHUB_WEBHOOK_SECRET")
    if not webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="This project webhook is not configured or Azure Key Vault is unavailable.",
        )
    if not verify_github_webhook_signature(webhook_secret, body, github_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature.")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Webhook payload is not valid JSON.") from error
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Webhook payload must be an object.")

    owner = await db.get(models.User, project.user_id)
    if owner is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project owner is unavailable.")
    tenant = await resolve_tenant(db, user=owner)
    duplicate_result = await db.execute(
        select(models.WebhookDelivery).where(
            models.WebhookDelivery.tenant_id == tenant.id,
            models.WebhookDelivery.provider == "github",
            models.WebhookDelivery.external_delivery_id == github_delivery,
        )
    )
    duplicate = duplicate_result.scalars().first()
    if duplicate:
        return {
            "status": "duplicate",
            "delivery_id": str(duplicate.id),
            "pipeline_run_id": str(duplicate.pipeline_run_id) if duplicate.pipeline_run_id else None,
        }

    repository = payload.get("repository") if isinstance(payload.get("repository"), dict) else {}
    repository_name = str(repository.get("full_name") or "")
    payload_digest = hashlib.sha256(body).hexdigest()
    delivery = models.WebhookDelivery(
        tenant_id=tenant.id,
        project_id=project.id,
        provider="github",
        external_delivery_id=github_delivery,
        event_type=github_event[:64],
        event_action=str(payload.get("action") or "")[:64] or None,
        signature_status="verified",
        status="running",
        repository_external_id=str(repository.get("id") or "")[:128] or None,
        payload_digest=payload_digest,
        attempt_count=1,
        validated_at=datetime.now(timezone.utc),
    )
    db.add(delivery)
    await db.flush()
    if repository_name.lower() != project.full_name.lower():
        delivery.status = "blocked"
        delivery.failure_code = "REPOSITORY_MISMATCH"
        delivery.redacted_error = "Webhook repository does not match the configured project."
        delivery.processed_at = datetime.now(timezone.utc)
        await db.commit()
        return {"status": "blocked", "reason": delivery.redacted_error}
    if github_event == "ping":
        delivery.status = "succeeded"
        delivery.processed_at = datetime.now(timezone.utc)
        await db.commit()
        return {"status": "verified", "delivery_id": str(delivery.id)}
    if github_event != "push":
        delivery.status = "skipped"
        delivery.redacted_error = f"GitHub event {github_event!r} does not trigger a deployment pipeline."
        delivery.processed_at = datetime.now(timezone.utc)
        await db.commit()
        return {"status": "skipped", "reason": delivery.redacted_error}

    branch = _push_branch(payload.get("ref"))
    commit_sha = str(payload.get("after") or "").lower()
    delivery.branch = branch
    delivery.source_revision = commit_sha if len(commit_sha) <= 64 else None
    if payload.get("deleted") or not branch or not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
        delivery.status = "skipped"
        delivery.redacted_error = "Deleted refs and non-branch or invalid revisions do not trigger pipelines."
        delivery.processed_at = datetime.now(timezone.utc)
        await db.commit()
        return {"status": "skipped", "reason": delivery.redacted_error}
    configuration = await _latest_config(db, tenant_id=tenant.id, project_id=project.id)
    if not configuration or not configuration.enabled or configuration.trigger_mode not in {"push", "manual_and_push"}:
        delivery.status = "skipped"
        delivery.redacted_error = "Push-triggered pipeline execution is disabled for this project."
        delivery.processed_at = datetime.now(timezone.utc)
        await db.commit()
        return {"status": "skipped", "reason": delivery.redacted_error}
    if branch != configuration.tracked_branch:
        delivery.status = "skipped"
        delivery.redacted_error = f"Push branch {branch!r} is not the configured branch {configuration.tracked_branch!r}."
        delivery.processed_at = datetime.now(timezone.utc)
        await db.commit()
        return {"status": "skipped", "reason": delivery.redacted_error}
    try:
        deployment, run = await _queue_push_deployment(
            db,
            tenant=tenant,
            owner=owner,
            project=project,
            configuration=configuration,
            branch=branch,
            commit_sha=commit_sha,
            delivery=delivery,
        )
    except HTTPException as error:
        delivery.status = "blocked"
        delivery.failure_code = "PREFLIGHT_BLOCKED"
        delivery.redacted_error = redact_sensitive_text(str(error.detail), maximum_length=1_000)
        delivery.processed_at = datetime.now(timezone.utc)
        await db.commit()
        return {"status": "blocked", "delivery_id": str(delivery.id), "reason": delivery.redacted_error}
    delivery.status = "succeeded" if run.status == "queued" else "blocked"
    delivery.processed_at = datetime.now(timezone.utc)
    await db.commit()
    return {
        "status": "queued" if run.status == "queued" else "blocked",
        "delivery_id": str(delivery.id),
        "deployment_id": str(deployment.id),
        "pipeline_run_id": str(run.id),
    }
