from datetime import datetime
from types import SimpleNamespace

import pytest

from backend.services.pipeline_state import (
    InvalidTransition,
    PipelineContext,
    UnsatisfiedPredecessor,
    guard_transition,
    initialize_stages,
    transition_pipeline_run,
    transition_stage,
)


def stage(status: str, order: int):
    return SimpleNamespace(
        status=status,
        stage_order=order,
        status_reason=None,
        failure_code=None,
        redacted_error=None,
        started_at=None,
        completed_at=None,
    )


def test_dynamic_stage_plan_is_ordered_and_explains_every_skip():
    stages = initialize_stages(
        PipelineContext(
            has_dependency_manifest=False,
            has_tests=False,
            has_build_step=False,
            container_required=False,
            has_iac=False,
            infrastructure_change=False,
            approval_required=False,
            kubernetes_required=False,
            monitoring_registration_required=False,
        )
    )

    assert [item.stage_order for item in stages] == list(range(1, len(stages) + 1))
    assert len({item.key for item in stages}) == len(stages)
    assert stages[0].key == "source"
    assert stages[-1].key == "deployment_complete"
    assert all(item.status in {"queued", "skipped"} for item in stages)
    assert all(item.status_reason for item in stages if item.status == "skipped")

    by_key = {item.key: item for item in stages}
    assert by_key["repository_analysis"].status == "queued"
    assert by_key["container_build"].status == "skipped"
    assert "not required" in by_key["container_build"].status_reason.lower()
    assert by_key["terraform_plan"].status == "skipped"
    assert by_key["application_deployment"].status == "queued"


def test_repository_analysis_can_be_transparently_reused():
    stages = initialize_stages(PipelineContext(repository_analysis_required=False))
    analysis = {item.key: item for item in stages}["repository_analysis"]

    assert analysis.status == "skipped"
    assert "reused" in analysis.status_reason.lower()


def test_applicable_security_and_infrastructure_stages_are_never_skipped_for_tool_availability():
    stages = initialize_stages(
        PipelineContext(
            container_required=True,
            has_iac=True,
            infrastructure_change=True,
            approval_required=True,
            kubernetes_required=True,
            generate_sbom=True,
        )
    )
    by_key = {item.key: item for item in stages}

    for key in (
        "sast",
        "secret_scan",
        "container_security",
        "sbom",
        "kubernetes_validation",
        "infrastructure_validation",
        "iac_security",
        "terraform_plan",
        "approval",
        "infrastructure_provisioning",
    ):
        assert by_key[key].status == "queued"
        assert by_key[key].is_required is True


def test_infrastructure_mutation_requires_approval_even_if_caller_omits_flag():
    stages = initialize_stages(
        PipelineContext(
            infrastructure_change=True,
            approval_required=False,
            deployment_mode="deploy_after_checks",
        )
    )
    by_key = {item.key: item for item in stages}
    assert by_key["approval"].status == "queued"
    assert by_key["infrastructure_provisioning"].status == "queued"


def test_validate_only_mode_never_initializes_mutating_or_post_deploy_work():
    stages = initialize_stages(
        PipelineContext(
            infrastructure_change=True,
            approval_required=True,
            deployment_mode="validate_only",
        )
    )
    by_key = {item.key: item for item in stages}

    assert by_key["terraform_plan"].status == "queued"
    for key in (
        "approval",
        "infrastructure_provisioning",
        "application_deployment",
        "health_check",
        "smoke_test",
        "monitoring_registration",
    ):
        assert by_key[key].status == "skipped"
        assert by_key[key].status_reason
    assert by_key["deployment_complete"].display_name == "Validation Complete"


def test_unknown_deployment_mode_fails_closed():
    with pytest.raises(ValueError):
        initialize_stages(PipelineContext(deployment_mode="best_effort"))


def test_transition_graph_is_fail_closed_and_requires_reasons():
    with pytest.raises(InvalidTransition):
        guard_transition("queued", "succeeded")
    with pytest.raises(InvalidTransition):
        guard_transition("running", "failed")
    with pytest.raises(InvalidTransition):
        guard_transition("blocked", "queued", reason="approval granted")

    guard_transition("running", "failed", reason="unit tests failed")
    guard_transition(
        "blocked",
        "queued",
        reason="approved plan was verified",
        allow_blocked_resume=True,
    )


def test_stage_cannot_start_until_all_predecessors_succeed_or_skip():
    current = stage("queued", 3)
    predecessors = [stage("succeeded", 1), stage("running", 2)]

    with pytest.raises(UnsatisfiedPredecessor):
        transition_stage(current, "running", predecessors=predecessors)

    predecessors[1].status = "skipped"
    transition_stage(current, "running", predecessors=predecessors)
    assert current.status == "running"
    assert current.started_at is not None


def test_terminal_stage_requires_new_attempt_instead_of_status_rewrite():
    current = stage("running", 1)
    transition_stage(
        current,
        "failed",
        reason="scanner returned a blocking result",
        failure_code="security_policy_blocked",
    )
    assert current.completed_at is not None
    assert current.failure_code == "security_policy_blocked"

    with pytest.raises(InvalidTransition):
        transition_stage(current, "running")


def test_pipeline_run_cancellation_records_terminal_timestamps_and_reason():
    run = SimpleNamespace(
        status="running",
        status_reason=None,
        failure_code=None,
        redacted_failure=None,
        started_at=None,
        completed_at=None,
        cancelled_at=None,
    )
    transition_pipeline_run(
        run,
        "cancelled",
        reason="cancelled by the project owner",
        failure_code="user_cancelled",
    )

    assert run.status == "cancelled"
    assert run.failure_code == "user_cancelled"
    assert run.status_reason == "cancelled by the project owner"
    assert run.redacted_failure is None
    assert run.completed_at is not None
    assert run.cancelled_at == run.completed_at


def test_transition_rejects_naive_timestamps():
    current = stage("queued", 1)
    with pytest.raises(ValueError, match="timezone-aware"):
        transition_stage(current, "running", at=datetime(2026, 1, 1))
