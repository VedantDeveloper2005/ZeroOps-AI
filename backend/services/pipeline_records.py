"""Persistence helpers for durable pipeline runs and initial stage attempts."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from sqlalchemy import delete
from sqlalchemy.future import select

try:
    from backend import models
    from backend.services.pipeline_state import (
        PipelineContext,
        initialize_stages,
        transition_pipeline_run,
        transition_stage,
    )
except ImportError:  # pragma: no cover
    import models
    from services.pipeline_state import (
        PipelineContext,
        initialize_stages,
        transition_pipeline_run,
        transition_stage,
    )


async def create_pipeline_run(
    db,
    *,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    deployment_id: uuid.UUID | None,
    requested_by_user_id: uuid.UUID | None,
    configuration: models.ProjectPipelineConfiguration | None,
    trigger_type: str,
    branch: str,
    source_revision: str,
    target_type: str,
    idempotency_key: str,
    context: PipelineContext,
    previous_successful_revision: str | None = None,
) -> models.PipelineRun:
    """Create one run and its complete, dynamically skipped stage graph."""
    run = models.PipelineRun(
        tenant_id=tenant_id,
        project_id=project_id,
        deployment_id=deployment_id,
        configuration_id=configuration.id if configuration else None,
        requested_by_user_id=requested_by_user_id,
        idempotency_key=idempotency_key[:128],
        trigger_type=trigger_type,
        status="queued",
        branch=branch,
        source_revision=source_revision,
        previous_successful_revision=previous_successful_revision,
        target_type=target_type,
        configuration_version=configuration.version if configuration else 1,
        repository_ai_required=False,
        repository_ai_used=False,
        approval_required=context.approval_required,
    )
    db.add(run)
    await db.flush()
    for planned in initialize_stages(context):
        digest = hashlib.sha256(
            f"{run.id}:{planned.key}:1".encode("utf-8")
        ).hexdigest()
        db.add(models.PipelineStageAttempt(
            tenant_id=tenant_id,
            project_id=project_id,
            deployment_id=deployment_id,
            pipeline_run_id=run.id,
            idempotency_key=f"stage:{digest}"[:128],
            stage_key=planned.key,
            display_name=planned.display_name,
            stage_order=planned.stage_order,
            attempt_number=1,
            is_required=planned.is_required,
            status=planned.status,
            tool_name=planned.tool_name,
            status_reason=planned.status_reason,
            evidence=[],
            result_metadata={},
        ))
    await db.flush()
    return run


def context_from_configuration(
    configuration: models.ProjectPipelineConfiguration | None,
    *,
    target_type: str,
    has_dependencies: bool = True,
    has_tests: bool = True,
    has_iac: bool = False,
    infrastructure_change: bool = False,
    repository_analysis_required: bool = True,
) -> PipelineContext:
    config = configuration
    return PipelineContext(
        has_dependency_manifest=has_dependencies,
        has_application_source=True,
        repository_analysis_required=repository_analysis_required,
        has_tests=has_tests,
        has_build_step=True,
        container_required=True,
        has_iac=has_iac,
        infrastructure_change=infrastructure_change,
        approval_required=bool(config and config.deployment_mode == "require_approval"),
        kubernetes_required=target_type == "azure-aks",
        monitoring_registration_required=True,
        deployment_mode=config.deployment_mode if config else "deploy_after_checks",
        run_dependency_install=bool(config.run_dependency_install) if config else True,
        run_code_quality=bool(config.run_code_quality) if config else True,
        run_unit_tests=bool(config.run_unit_tests) if config else True,
        run_sast=bool(config.run_sast) if config else True,
        run_dependency_scan=bool(config.run_dependency_scan) if config else True,
        run_secret_scan=bool(config.run_secret_scan) if config else True,
        run_container_scan=bool(config.run_container_scan) if config else True,
        run_iac_scan=bool(config.run_iac_scan) if config else True,
        generate_sbom=bool(config.generate_sbom) if config else False,
    )


async def get_pipeline_run(db, deployment_id: uuid.UUID) -> models.PipelineRun | None:
    result = await db.execute(
        select(models.PipelineRun)
        .where(models.PipelineRun.deployment_id == deployment_id)
        .order_by(models.PipelineRun.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


async def list_stage_attempts(db, pipeline_run_id: uuid.UUID) -> list[models.PipelineStageAttempt]:
    result = await db.execute(
        select(models.PipelineStageAttempt)
        .where(models.PipelineStageAttempt.pipeline_run_id == pipeline_run_id)
        .order_by(
            models.PipelineStageAttempt.stage_order,
            models.PipelineStageAttempt.attempt_number,
        )
    )
    return list(result.scalars().all())


async def reconcile_pipeline_plan(
    db,
    *,
    pipeline_run: models.PipelineRun,
    context: PipelineContext,
) -> list[models.PipelineStageAttempt]:
    """Reconcile queued/skipped stages once source facts become available.

    The API creates an initial graph before a worker has cloned the immutable
    source.  After the Source stage, repository facts can make a stage
    irrelevant or required.  Only never-started ``queued``/``skipped`` rows
    may be re-planned; execution history is immutable.
    """

    existing = await list_stage_attempts(db, pipeline_run.id)
    by_key = {item.stage_key: item for item in existing}
    planned_keys: set[str] = set()
    for planned in initialize_stages(context):
        planned_keys.add(planned.key)
        record = by_key.get(planned.key)
        if record is None:
            digest = hashlib.sha256(
                f"{pipeline_run.id}:{planned.key}:1".encode("utf-8")
            ).hexdigest()
            record = models.PipelineStageAttempt(
                tenant_id=pipeline_run.tenant_id,
                project_id=pipeline_run.project_id,
                deployment_id=pipeline_run.deployment_id,
                pipeline_run_id=pipeline_run.id,
                idempotency_key=f"stage:{digest}"[:128],
                stage_key=planned.key,
                display_name=planned.display_name,
                stage_order=planned.stage_order,
                attempt_number=1,
                is_required=planned.is_required,
                status=planned.status,
                tool_name=planned.tool_name,
                status_reason=planned.status_reason,
                evidence=[],
                result_metadata={},
            )
            db.add(record)
            continue
        if record.status not in {"queued", "skipped"}:
            # Source (and any already completed work on a resumed worker) is
            # immutable; only its display order can remain as originally set.
            continue
        record.display_name = planned.display_name
        record.stage_order = planned.stage_order
        record.is_required = planned.is_required
        record.status = planned.status
        record.status_reason = planned.status_reason
        record.tool_name = planned.tool_name

    # There should not be unknown stages, but deleting an unstarted stale row
    # is safer than showing a phantom stage after a version upgrade.
    stale_ids = [
        item.id
        for item in existing
        if item.stage_key not in planned_keys and item.status in {"queued", "skipped"}
    ]
    if stale_ids:
        await db.execute(
            delete(models.PipelineStageAttempt).where(
                models.PipelineStageAttempt.id.in_(stale_ids)
            )
        )
    await db.flush()
    return await list_stage_attempts(db, pipeline_run.id)


async def transition_pipeline_stage(
    db,
    *,
    pipeline_run: models.PipelineRun,
    stage_key: str,
    target_status: str,
    reason: str | None = None,
    failure_code: str | None = None,
    redacted_error: str | None = None,
    evidence: list[dict[str, Any]] | None = None,
    result_metadata: dict[str, Any] | None = None,
    tool_version: str | None = None,
) -> models.PipelineStageAttempt:
    """Transition one durable stage while enforcing predecessor ordering."""

    stages = await list_stage_attempts(db, pipeline_run.id)
    stage = next((item for item in stages if item.stage_key == stage_key), None)
    if stage is None:
        raise ValueError(f"Pipeline stage {stage_key!r} is not part of this run.")
    if stage.status == "skipped":
        if target_status == "skipped":
            return stage
        raise ValueError(f"Skipped pipeline stage {stage_key!r} cannot execute.")

    transition_stage(
        stage,
        target_status,
        predecessors=stages,
        reason=reason,
        failure_code=failure_code,
        redacted_error=redacted_error,
    )
    if evidence is not None:
        stage.evidence = evidence[:100]
    if result_metadata is not None:
        stage.result_metadata = result_metadata
    if tool_version is not None:
        stage.tool_version = tool_version[:128]
    if target_status == "running":
        pipeline_run.current_stage_key = stage_key
        if pipeline_run.status == "queued":
            transition_pipeline_run(pipeline_run, "running")
    await db.flush()
    return stage


async def finish_pipeline_run(
    db,
    *,
    pipeline_run: models.PipelineRun,
    status: str,
    reason: str | None = None,
    failure_code: str | None = None,
) -> models.PipelineRun:
    transition_pipeline_run(
        pipeline_run,
        status,
        reason=reason,
        failure_code=failure_code,
    )
    pipeline_run.current_stage_key = None
    await db.flush()
    return pipeline_run
