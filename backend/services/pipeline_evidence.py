"""Adapters from deterministic runtime results to the durable DevSecOps model."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import uuid
from typing import Any, Iterable, Mapping

from sqlalchemy import desc
from sqlalchemy.future import select

try:
    from backend import models
    from backend.services.change_detection import (
        AnalysisReuseDecision,
        ChangeDetectionService,
        RepositoryFingerprint,
    )
    from backend.services.redaction import redact_sensitive_text, redact_sensitive_values
    from backend.services.security_scanner import SecurityScanResult
except ImportError:  # pragma: no cover
    import models
    from services.change_detection import AnalysisReuseDecision, ChangeDetectionService, RepositoryFingerprint
    from services.redaction import redact_sensitive_text, redact_sensitive_values
    from services.security_scanner import SecurityScanResult


_SCAN_TYPE = {"dependencies": "dependency", "secrets": "secret"}
_EXECUTION_STATUS = {
    "passed": "succeeded",
    "warning": "succeeded",
    "failed": "failed",
    "blocked": "blocked",
    "unavailable": "unavailable",
}
_SAFE_ANALYSIS_FIELDS = (
    "framework",
    "version",
    "language",
    "runtime",
    "package_manager",
    "docker_support",
    "monorepo_structure",
    "database_dependencies",
    "deployment_strategy",
    "build_commands",
    "start_commands",
    "port",
    "recommended_compute_tier",
    "kubernetes_detected",
    "helm_detected",
    "kustomize_detected",
    "kubernetes_assets",
)


def safe_analysis_summary(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Return deployment facts without source, credentials, or env values."""

    summary = {
        key: metadata.get(key)
        for key in _SAFE_ANALYSIS_FIELDS
        if metadata.get(key) is not None
    }
    resources = metadata.get("resources")
    if isinstance(resources, Mapping):
        summary["resources"] = {
            key: resources.get(key)
            for key in ("cpu", "memory", "storage")
            if resources.get(key) is not None
        }
    return redact_sensitive_values(summary)


def fingerprint_from_record(record: models.RepositoryAnalysisSnapshot) -> RepositoryFingerprint:
    return RepositoryFingerprint(
        commit_sha=record.source_revision,
        repository_fingerprint=record.repository_fingerprint,
        architecture_fingerprint=record.architecture_fingerprint,
        dependency_files_hash=record.dependency_files_hash,
        dockerfile_hash=record.dockerfile_hash,
        infrastructure_files_hash=record.infrastructure_files_hash,
        kubernetes_manifests_hash=record.kubernetes_manifests_hash,
        important_configuration_files_hash=record.important_configuration_files_hash,
        application_framework=record.application_framework,
        detected_services=tuple(record.detected_services or ()),
        environment_variable_names=tuple(record.environment_variable_names or ()),
        version=record.fingerprint_version,
    )


async def latest_repository_snapshot(
    db,
    *,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    exclude_pipeline_run_id: uuid.UUID | None = None,
) -> models.RepositoryAnalysisSnapshot | None:
    statement = select(models.RepositoryAnalysisSnapshot).where(
        models.RepositoryAnalysisSnapshot.tenant_id == tenant_id,
        models.RepositoryAnalysisSnapshot.project_id == project_id,
        models.RepositoryAnalysisSnapshot.status == "succeeded",
    )
    if exclude_pipeline_run_id is not None:
        statement = statement.where(
            models.RepositoryAnalysisSnapshot.pipeline_run_id != exclude_pipeline_run_id
        )
    result = await db.execute(statement.order_by(desc(models.RepositoryAnalysisSnapshot.created_at)).limit(1))
    return result.scalars().first()


async def persist_change_evidence(
    db,
    *,
    pipeline_run: models.PipelineRun,
    current: RepositoryFingerprint,
    previous_snapshot: models.RepositoryAnalysisSnapshot | None,
    changed_files: Iterable[str] | Mapping[str, str | bytes],
    decision: AnalysisReuseDecision,
    metadata: Mapping[str, Any],
    ai_used: bool,
) -> tuple[models.ChangeAnalysis, models.RepositoryAnalysisSnapshot]:
    """Persist the decision and reusable content-free snapshot idempotently."""

    existing_result = await db.execute(
        select(models.ChangeAnalysis)
        .where(models.ChangeAnalysis.pipeline_run_id == pipeline_run.id)
        .limit(1)
    )
    existing_change = existing_result.scalars().first()
    snapshot_result = await db.execute(
        select(models.RepositoryAnalysisSnapshot)
        .where(models.RepositoryAnalysisSnapshot.pipeline_run_id == pipeline_run.id)
        .limit(1)
    )
    existing_snapshot = snapshot_result.scalars().first()
    if existing_change is not None and existing_snapshot is not None:
        return existing_change, existing_snapshot

    now = datetime.now(timezone.utc)
    persistence = ChangeDetectionService.build_change_analysis_persistence(
        previous=fingerprint_from_record(previous_snapshot) if previous_snapshot else None,
        current=current,
        changed_files=changed_files,
    )
    if existing_change is None:
        existing_change = models.ChangeAnalysis(
            tenant_id=pipeline_run.tenant_id,
            project_id=pipeline_run.project_id,
            deployment_id=pipeline_run.deployment_id,
            pipeline_run_id=pipeline_run.id,
            baseline_snapshot_id=previous_snapshot.id if previous_snapshot else None,
            idempotency_key=f"change:{pipeline_run.id}",
            baseline_revision=previous_snapshot.source_revision if previous_snapshot else None,
            target_revision=current.commit_sha,
            status="succeeded",
            started_at=now,
            completed_at=now,
            **persistence.to_dict(),
        )
        db.add(existing_change)

    if existing_snapshot is None:
        existing_snapshot = models.RepositoryAnalysisSnapshot(
            tenant_id=pipeline_run.tenant_id,
            project_id=pipeline_run.project_id,
            deployment_id=pipeline_run.deployment_id,
            pipeline_run_id=pipeline_run.id,
            reused_from_snapshot_id=(previous_snapshot.id if decision.reuse_previous_analysis and previous_snapshot else None),
            idempotency_key=f"snapshot:{pipeline_run.id}",
            source_revision=current.commit_sha,
            repository_fingerprint=current.repository_fingerprint,
            architecture_fingerprint=current.architecture_fingerprint,
            dependency_files_hash=current.dependency_files_hash,
            dockerfile_hash=current.dockerfile_hash,
            infrastructure_files_hash=current.infrastructure_files_hash,
            kubernetes_manifests_hash=current.kubernetes_manifests_hash,
            important_configuration_files_hash=current.important_configuration_files_hash,
            fingerprint_version=current.version,
            analyzer_version="zeroops-repository-analyzer-v1",
            analysis_mode="model" if ai_used else ("reused" if decision.reuse_previous_analysis else "deterministic"),
            status="succeeded",
            ai_required=decision.requires_repository_analysis,
            ai_used=ai_used,
            application_framework=current.application_framework,
            detected_services=list(current.detected_services),
            environment_variable_names=list(current.environment_variable_names),
            summary=safe_analysis_summary(metadata),
            evidence=[
                {
                    "source": "change-detection",
                    "summary": decision.message,
                    "classifier_version": decision.version,
                }
            ],
            started_at=now,
            completed_at=now,
        )
        db.add(existing_snapshot)
    pipeline_run.repository_ai_required = decision.requires_repository_analysis
    pipeline_run.repository_ai_used = ai_used
    await db.flush()
    return existing_change, existing_snapshot


def _finding_digest(result: SecurityScanResult, finding: Any) -> str:
    payload = {
        "tool": result.tool,
        "kind": result.kind,
        "rule": finding.rule_id,
        "path": finding.path,
        "line": finding.line,
        "fingerprint": finding.fingerprint,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


async def persist_security_scan(
    db,
    *,
    pipeline_run: models.PipelineRun,
    stage_attempt: models.PipelineStageAttempt,
    result: SecurityScanResult,
    target_revision: str,
    target_kind: str,
    target_digest: str | None = None,
) -> models.SecurityScan:
    """Persist only validated, redacted scanner evidence and finding metadata."""

    scan_type = _SCAN_TYPE.get(result.kind, result.kind)
    idempotency_key = f"scan:{pipeline_run.id}:{stage_attempt.stage_key}:{stage_attempt.attempt_number}:{result.tool}"
    existing_result = await db.execute(
        select(models.SecurityScan).where(
            models.SecurityScan.tenant_id == pipeline_run.tenant_id,
            models.SecurityScan.idempotency_key == idempotency_key,
        )
    )
    existing = existing_result.scalars().first()
    if existing is not None:
        return existing

    counts = {severity: 0 for severity in ("critical", "high", "medium", "low", "info")}
    for finding in result.findings:
        severity = finding.severity if finding.severity in counts else "info"
        counts[severity] += 1
    safe_result = result.to_dict()
    result_digest = hashlib.sha256(
        json.dumps(safe_result, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    scan = models.SecurityScan(
        tenant_id=pipeline_run.tenant_id,
        project_id=pipeline_run.project_id,
        deployment_id=pipeline_run.deployment_id,
        pipeline_run_id=pipeline_run.id,
        stage_attempt_id=stage_attempt.id,
        idempotency_key=idempotency_key,
        scan_type=scan_type,
        status=_EXECUTION_STATUS[result.status],
        policy_status=result.status if result.status in {"warning", "blocked", "unavailable"} else "passed",
        blocking_enabled=result.required,
        tool_name=result.tool,
        tool_version=result.tool_version,
        target_kind=target_kind,
        target_revision=target_revision[:128] if target_revision else None,
        target_digest=target_digest,
        finding_count=len(result.findings),
        critical_count=counts["critical"],
        high_count=counts["high"],
        medium_count=counts["medium"],
        low_count=counts["low"],
        info_count=counts["info"],
        result_digest=result_digest,
        error_code=("SCANNER_UNAVAILABLE" if result.status == "unavailable" else None),
        redacted_error=(
            redact_sensitive_text(result.summary, maximum_length=2_000)
            if result.status in {"failed", "blocked", "unavailable"}
            else None
        ),
        summary={
            "message": redact_sensitive_text(result.summary, maximum_length=2_000),
            "evidence": redact_sensitive_values(result.evidence),
            "raw_output_retained": False,
        },
        started_at=datetime.fromisoformat(result.started_at),
        completed_at=datetime.fromisoformat(result.completed_at),
    )
    db.add(scan)
    await db.flush()
    for finding in result.findings:
        severity = finding.severity if finding.severity in counts else "info"
        db.add(models.SecurityFinding(
            tenant_id=pipeline_run.tenant_id,
            project_id=pipeline_run.project_id,
            deployment_id=pipeline_run.deployment_id,
            security_scan_id=scan.id,
            fingerprint=_finding_digest(result, finding),
            rule_id=redact_sensitive_text(finding.rule_id, maximum_length=256),
            category=scan_type,
            severity=severity,
            status="open",
            title=redact_sensitive_text(finding.title, maximum_length=1_000),
            location_path=finding.path,
            line_start=finding.line,
            is_blocking=result.blocking and severity in {"critical", "high"},
            masked_evidence="Finding evidence was reduced to rule, severity, and location metadata.",
            evidence={"source_retained": False, "secret_retained": False},
        ))
    await db.flush()
    return scan
