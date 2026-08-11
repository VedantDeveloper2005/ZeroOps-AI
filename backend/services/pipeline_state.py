"""Pure, fail-closed pipeline planning and lifecycle guards.

This module deliberately does not perform database I/O. Callers may pass
SQLAlchemy records or simple model-like objects to the transition helpers and
commit the resulting mutation in the same transaction as their audit event.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Protocol


EXECUTION_STATUSES = frozenset(
    {
        "queued",
        "running",
        "succeeded",
        "failed",
        "skipped",
        "blocked",
        "unavailable",
        "cancelled",
    }
)
TERMINAL_STATUSES = frozenset(
    {"succeeded", "failed", "skipped", "unavailable", "cancelled"}
)
SUCCESSFUL_PREDECESSOR_STATUSES = frozenset({"succeeded", "skipped"})

_ALLOWED_TRANSITIONS = {
    "queued": frozenset({"running", "skipped", "blocked", "unavailable", "cancelled"}),
    "running": frozenset({"succeeded", "failed", "blocked", "unavailable", "cancelled"}),
    "blocked": frozenset({"queued", "cancelled"}),
    "succeeded": frozenset(),
    "failed": frozenset(),
    "skipped": frozenset(),
    "unavailable": frozenset(),
    "cancelled": frozenset(),
}

_REASON_REQUIRED_STATUSES = frozenset(
    {"failed", "skipped", "blocked", "unavailable", "cancelled"}
)


def _utc_timestamp(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise PipelineStateError("Pipeline transition timestamps must be timezone-aware.")
    return value.astimezone(timezone.utc)


class PipelineStateError(ValueError):
    """Base error for invalid or unsafe pipeline state changes."""


class InvalidTransition(PipelineStateError):
    """Raised when a lifecycle transition would weaken pipeline guarantees."""


class UnsatisfiedPredecessor(PipelineStateError):
    """Raised when a stage is started before every predecessor is successful."""


class _StateRecord(Protocol):
    status: str


class _StageRecord(_StateRecord, Protocol):
    stage_order: int
    status_reason: str | None
    failure_code: str | None
    redacted_error: str | None
    started_at: datetime | None
    completed_at: datetime | None


@dataclass(frozen=True)
class PipelineContext:
    """Deterministic facts used to decide stage applicability.

    Tool availability is intentionally absent. An applicable scanner or
    validator that cannot run must transition to ``unavailable`` and block the
    pipeline; it must never be represented as an irrelevant/skipped stage.
    """

    has_dependency_manifest: bool = True
    has_application_source: bool = True
    repository_analysis_required: bool = True
    has_tests: bool = True
    has_build_step: bool = True
    container_required: bool = True
    has_iac: bool = False
    infrastructure_change: bool = False
    approval_required: bool = False
    kubernetes_required: bool = False
    monitoring_registration_required: bool = True
    deployment_mode: str = "deploy_after_checks"
    run_dependency_install: bool = True
    run_code_quality: bool = True
    run_unit_tests: bool = True
    run_sast: bool = True
    run_dependency_scan: bool = True
    run_secret_scan: bool = True
    run_container_scan: bool = True
    run_iac_scan: bool = True
    generate_sbom: bool = False


@dataclass(frozen=True)
class PlannedStage:
    key: str
    display_name: str
    stage_order: int
    status: str
    is_required: bool
    status_reason: str | None = None
    tool_name: str | None = None


def _planned_stage(
    *,
    key: str,
    display_name: str,
    order: int,
    applicable: bool,
    skip_reason: str,
    tool_name: str | None = None,
) -> PlannedStage:
    if applicable:
        return PlannedStage(
            key=key,
            display_name=display_name,
            stage_order=order,
            status="queued",
            is_required=True,
            tool_name=tool_name,
        )
    if not skip_reason.strip():
        raise PipelineStateError(f"Skipped stage {key!r} requires a reason.")
    return PlannedStage(
        key=key,
        display_name=display_name,
        stage_order=order,
        status="skipped",
        is_required=False,
        status_reason=skip_reason,
        tool_name=tool_name,
    )


def initialize_stages(context: PipelineContext) -> tuple[PlannedStage, ...]:
    """Build the ordered pipeline, explicitly marking irrelevant work skipped."""

    if context.deployment_mode not in {
        "validate_only",
        "deploy_after_checks",
        "require_approval",
    }:
        raise PipelineStateError(f"Unknown deployment mode: {context.deployment_mode!r}.")

    needs_infrastructure = context.has_iac or context.infrastructure_change
    performs_deployment = context.deployment_mode != "validate_only"
    approval_required = performs_deployment and (
        context.approval_required
        or context.infrastructure_change
        or context.deployment_mode == "require_approval"
    )
    stages: list[PlannedStage] = []

    def add(
        key: str,
        label: str,
        applicable: bool = True,
        reason: str = "Stage is not applicable to this repository or target.",
        tool: str | None = None,
    ) -> None:
        stages.append(
            _planned_stage(
                key=key,
                display_name=label,
                order=len(stages) + 1,
                applicable=applicable,
                skip_reason=reason,
                tool_name=tool,
            )
        )

    add("source", "Source")
    add("change_detection", "Change Detection")
    add(
        "repository_analysis",
        "Repository Analysis",
        context.repository_analysis_required,
        "Repository AI analysis was reused because no deployment-relevant architecture change was detected.",
        "zeroops-ai",
    )
    add(
        "dependency_installation",
        "Dependency Installation",
        context.run_dependency_install and context.has_dependency_manifest,
        "No supported dependency manifest was detected or dependency installation is disabled.",
    )
    add(
        "code_quality",
        "Code Quality",
        context.run_code_quality and context.has_application_source,
        "No application source was detected or code-quality checks are disabled.",
    )
    add(
        "unit_tests",
        "Unit Tests",
        context.run_unit_tests and context.has_tests,
        "No test suite was detected or unit-test execution is disabled.",
    )
    add(
        "sast",
        "SAST",
        context.run_sast and context.has_application_source,
        "No application source was detected or SAST is disabled.",
        "semgrep",
    )
    add(
        "dependency_security",
        "Dependency Security Scan",
        context.run_dependency_scan and context.has_dependency_manifest,
        "No supported dependency manifest was detected or dependency scanning is disabled.",
    )
    add(
        "secret_scan",
        "Secret Scan",
        context.run_secret_scan,
        "Secret scanning is disabled by project policy.",
        "gitleaks",
    )
    add(
        "build",
        "Build",
        context.has_build_step,
        "No build step is required for the detected application.",
    )
    add(
        "container_build",
        "Container Build",
        context.container_required,
        "Container deployment is not required for this target.",
    )
    add(
        "container_security",
        "Container Security Scan",
        context.container_required and context.run_container_scan,
        "No container image is produced or container scanning is disabled.",
        "trivy",
    )
    add(
        "sbom",
        "SBOM Generation",
        context.container_required and context.generate_sbom,
        "SBOM generation is disabled or no container image is produced.",
        "syft",
    )
    add(
        "kubernetes_validation",
        "Kubernetes Validation",
        context.kubernetes_required,
        "The selected deployment target does not use Kubernetes.",
        "kubeconform",
    )
    add(
        "infrastructure_validation",
        "Infrastructure Validation",
        needs_infrastructure,
        "No infrastructure definition or infrastructure change was detected.",
        "terraform",
    )
    add(
        "iac_security",
        "IaC Security Scan",
        needs_infrastructure and context.run_iac_scan,
        "No infrastructure definition changed or IaC scanning is disabled.",
        "checkov",
    )
    add(
        "terraform_plan",
        "Terraform Plan",
        context.infrastructure_change,
        "No infrastructure change requires a Terraform plan.",
        "terraform",
    )
    add(
        "approval",
        "Approval",
        approval_required,
        "This run does not require an approval gate.",
    )
    add(
        "infrastructure_provisioning",
        "Infrastructure Provisioning",
        context.infrastructure_change and performs_deployment,
        "No approved infrastructure change requires provisioning in this run mode.",
        "terraform",
    )
    add(
        "application_deployment",
        "Application Deployment",
        performs_deployment,
        "This pipeline is configured for validation only.",
    )
    add(
        "health_check",
        "Health Check",
        performs_deployment,
        "No application was deployed in validation-only mode.",
    )
    add(
        "smoke_test",
        "Smoke Test",
        performs_deployment,
        "No application was deployed in validation-only mode.",
    )
    add(
        "monitoring_registration",
        "Monitoring Registration",
        context.monitoring_registration_required and performs_deployment,
        "No deployment requires monitoring registration in this run mode.",
    )
    add(
        "deployment_complete",
        "Deployment Complete" if performs_deployment else "Validation Complete",
    )
    return tuple(stages)


def guard_transition(
    current_status: str,
    target_status: str,
    *,
    reason: str | None = None,
    allow_blocked_resume: bool = False,
) -> None:
    """Validate one lifecycle transition without mutating state."""

    if current_status not in EXECUTION_STATUSES:
        raise InvalidTransition(f"Unknown current status: {current_status!r}.")
    if target_status not in EXECUTION_STATUSES:
        raise InvalidTransition(f"Unknown target status: {target_status!r}.")
    if current_status == target_status:
        return
    if current_status == "blocked" and target_status == "queued" and not allow_blocked_resume:
        raise InvalidTransition("A blocked record requires an explicitly authorized resume.")
    if target_status not in _ALLOWED_TRANSITIONS[current_status]:
        raise InvalidTransition(f"Cannot transition from {current_status!r} to {target_status!r}.")
    if target_status in _REASON_REQUIRED_STATUSES and not (reason or "").strip():
        raise InvalidTransition(f"Transition to {target_status!r} requires a redacted reason.")


def ensure_predecessors_complete(
    stage_order: int,
    stages: Iterable[_StateRecord],
) -> None:
    """Require every earlier stage to have succeeded or been explicitly skipped."""

    for predecessor in stages:
        predecessor_order = getattr(predecessor, "stage_order", None)
        if predecessor_order is None or predecessor_order >= stage_order:
            continue
        if predecessor.status not in SUCCESSFUL_PREDECESSOR_STATUSES:
            raise UnsatisfiedPredecessor(
                f"Stage {stage_order} is blocked by predecessor {predecessor_order} "
                f"in status {predecessor.status!r}."
            )


def transition_stage(
    stage: _StageRecord,
    target_status: str,
    *,
    predecessors: Iterable[_StateRecord] = (),
    reason: str | None = None,
    failure_code: str | None = None,
    redacted_error: str | None = None,
    allow_blocked_resume: bool = False,
    at: datetime | None = None,
) -> _StageRecord:
    """Guard and mutate a model-like stage attempt in memory."""

    guard_transition(
        stage.status,
        target_status,
        reason=reason,
        allow_blocked_resume=allow_blocked_resume,
    )
    if stage.status == target_status:
        return stage
    if target_status == "running":
        ensure_predecessors_complete(stage.stage_order, predecessors)

    timestamp = _utc_timestamp(at)
    stage.status = target_status
    stage.status_reason = (
        reason.strip() if reason and target_status in _REASON_REQUIRED_STATUSES else None
    )
    stage.failure_code = failure_code
    stage.redacted_error = redacted_error
    if target_status == "running" and stage.started_at is None:
        stage.started_at = timestamp
    if target_status in TERMINAL_STATUSES:
        stage.completed_at = timestamp
    return stage


def transition_pipeline_run(
    pipeline_run: _StateRecord,
    target_status: str,
    *,
    reason: str | None = None,
    failure_code: str | None = None,
    allow_blocked_resume: bool = False,
    at: datetime | None = None,
) -> _StateRecord:
    """Guard and mutate a model-like pipeline run in memory."""

    guard_transition(
        pipeline_run.status,
        target_status,
        reason=reason,
        allow_blocked_resume=allow_blocked_resume,
    )
    if pipeline_run.status == target_status:
        return pipeline_run

    timestamp = _utc_timestamp(at)
    pipeline_run.status = target_status
    if hasattr(pipeline_run, "status_reason"):
        pipeline_run.status_reason = (
            reason.strip() if reason and target_status in _REASON_REQUIRED_STATUSES else None
        )
    if hasattr(pipeline_run, "failure_code"):
        pipeline_run.failure_code = failure_code
    if hasattr(pipeline_run, "redacted_failure"):
        pipeline_run.redacted_failure = (
            reason.strip() if reason and target_status in {"failed", "unavailable"} else None
        )
    if target_status == "running" and getattr(pipeline_run, "started_at", None) is None:
        pipeline_run.started_at = timestamp
    if target_status in TERMINAL_STATUSES:
        pipeline_run.completed_at = timestamp
    if target_status == "cancelled" and hasattr(pipeline_run, "cancelled_at"):
        pipeline_run.cancelled_at = timestamp
    return pipeline_run
