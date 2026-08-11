from datetime import datetime, timedelta, timezone
import inspect
from types import SimpleNamespace
import uuid

import pytest

from backend.services import app_service, pipeline, pipeline_approval
from worker.terraform_runner import _pipeline_job_outcome


def test_required_environment_names_are_deterministic_and_database_aware():
    metadata = {
        "pricing_breakdown": {
            "detected_vars_detail": [
                {"key": "JWT_SECRET", "type": "required"},
                {"key": "OPTIONAL_FLAG", "type": "optional"},
                {"key": "not valid", "type": "required"},
            ]
        },
        "database_dependencies": ["PostgreSQL", "Redis"],
    }

    assert pipeline._required_environment_names(metadata) == {
        "DATABASE_URL",
        "JWT_SECRET",
        "REDIS_URL",
    }


def test_pipeline_approval_is_hmac_bound_to_new_run_and_source():
    now = datetime.now(timezone.utc)
    claims = {
        "schema": pipeline_approval.APPROVAL_SCHEMA,
        "tenant_id": "11111111-1111-4111-8111-111111111111",
        "project_id": "22222222-2222-4222-8222-222222222222",
        "validation_run_id": "33333333-3333-4333-8333-333333333333",
        "validation_deployment_id": "44444444-4444-4444-8444-444444444444",
        "approved_deployment_id": "55555555-5555-4555-8555-555555555555",
        "approved_pipeline_run_id": "66666666-6666-4666-8666-666666666666",
        "source_revision": "a" * 40,
        "branch": "main",
        "target_type": "azure-app-service",
        "plan_id": "77777777-7777-4777-8777-777777777777",
        "plan_revision": 2,
        "configuration_id": "88888888-8888-4888-8888-888888888888",
        "configuration_version": 3,
        "configuration_digest": "b" * 64,
        "approved_by_user_id": "99999999-9999-4999-8999-999999999999",
        "approved_at": now.isoformat(),
    }
    signed = pipeline_approval.sign_pipeline_approval(claims, secret="approval-secret")

    assert pipeline_approval.verify_pipeline_approval(
        signed,
        secret="approval-secret",
        expected={"approved_pipeline_run_id": claims["approved_pipeline_run_id"]},
        now=now,
    ).valid
    assert not pipeline_approval.verify_pipeline_approval(
        signed,
        secret="approval-secret",
        expected={"source_revision": "c" * 40},
        now=now,
    ).valid


@pytest.mark.asyncio
async def test_runtime_approval_requires_prior_blocked_gate_and_matching_plan():
    now = datetime.now(timezone.utc)
    tenant_id = uuid.uuid4()
    project_id = uuid.uuid4()
    validation_run_id = uuid.uuid4()
    validation_deployment_id = uuid.uuid4()
    deployment_id = uuid.uuid4()
    pipeline_run_id = uuid.uuid4()
    configuration_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    approver_id = uuid.uuid4()
    user_id = uuid.uuid4()
    source_revision = "a" * 40
    configuration = SimpleNamespace(
        id=configuration_id,
        version=3,
        config_digest="b" * 64,
    )
    prior_run = SimpleNamespace(
        id=validation_run_id,
        tenant_id=tenant_id,
        project_id=project_id,
        deployment_id=validation_deployment_id,
        status="blocked",
        failure_code="DEPLOYMENT_APPROVAL_REQUIRED",
        source_revision=source_revision,
        branch="main",
        target_type="azure-app-service",
        configuration_id=configuration_id,
        configuration_version=3,
        approval_required=True,
    )
    prior_stages = [
        SimpleNamespace(stage_key="source", stage_order=1, status="succeeded"),
        SimpleNamespace(stage_key="approval", stage_order=10, status="blocked", is_required=True),
    ]
    prior_deployment = SimpleNamespace(
        id=validation_deployment_id,
        user_id=user_id,
        project_id=project_id,
        status="stopped",
        infrastructure_metadata={
            "architecture_plan": {"id": str(plan_id), "revision": 2}
        },
    )
    current_run = SimpleNamespace(
        id=pipeline_run_id,
        tenant_id=tenant_id,
        project_id=project_id,
        deployment_id=deployment_id,
        configuration_id=configuration_id,
        configuration_version=3,
        source_revision=source_revision,
        branch="main",
        target_type="azure-app-service",
    )
    claims = {
        "schema": pipeline_approval.APPROVAL_SCHEMA,
        "tenant_id": str(tenant_id),
        "project_id": str(project_id),
        "validation_run_id": str(validation_run_id),
        "validation_deployment_id": str(validation_deployment_id),
        "approved_deployment_id": str(deployment_id),
        "approved_pipeline_run_id": str(pipeline_run_id),
        "source_revision": source_revision,
        "branch": "main",
        "target_type": "azure-app-service",
        "plan_id": str(plan_id),
        "plan_revision": 2,
        "configuration_id": str(configuration_id),
        "configuration_version": 3,
        "configuration_digest": "b" * 64,
        "approved_by_user_id": str(approver_id),
        "approved_at": now.isoformat(),
    }
    signed = pipeline_approval.sign_pipeline_approval(
        claims,
        secret=pipeline.config.JWT_SECRET,
    )
    deployment = SimpleNamespace(
        id=deployment_id,
        user_id=user_id,
        project_id=project_id,
        infrastructure_metadata={
            "architecture_plan": {"id": str(plan_id), "revision": 2},
            "pipeline_approval": signed,
        },
    )

    class ScalarResult:
        def __init__(self, first=None, all_items=None):
            self._first = first
            self._all = all_items

        def scalars(self):
            return self

        def first(self):
            return self._first

        def all(self):
            return self._all if self._all is not None else ([] if self._first is None else [self._first])

    class Session:
        def __init__(self):
            self.results = iter([
                ScalarResult(configuration),
                ScalarResult(prior_run),
                ScalarResult(all_items=prior_stages),
                ScalarResult(prior_deployment),
            ])

        async def execute(self, _statement):
            return next(self.results)

    approval, reason = await pipeline._validated_pipeline_approval(
        Session(),
        pipeline_run=current_run,
        deployment=deployment,
    )

    assert approval is not None
    assert approval["validation_run_id"] == str(validation_run_id)
    assert "matches" in reason


def test_acr_digest_resolution_returns_only_registry_verified_digest(monkeypatch):
    captured = {}
    connection = SimpleNamespace(
        acr_login_server="example.azurecr.io",
        client_id="client",
        tenant_id="tenant",
        subscription_id="subscription",
    )
    monkeypatch.setattr(app_service, "_sign_in", lambda *_args, **_kwargs: None)

    def capture(command, *, env, cwd=None):
        captured["command"] = command
        return "sha256:" + "a" * 64

    monkeypatch.setattr(app_service, "_capture", capture)

    resolved = app_service.resolve_image_digest(
        connection=connection,
        client_secret="never-logged",
        image_ref="example.azurecr.io/team/api:v1",
    )

    assert resolved == "example.azurecr.io/team/api@sha256:" + "a" * 64
    assert captured["command"][captured["command"].index("--image") + 1] == "team/api:v1"
    assert "never-logged" not in captured["command"]


def test_acr_digest_resolution_rejects_malformed_provider_result(monkeypatch):
    connection = SimpleNamespace(
        acr_login_server="example.azurecr.io",
        client_id="client",
        tenant_id="tenant",
        subscription_id="subscription",
    )
    monkeypatch.setattr(app_service, "_sign_in", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_service, "_capture", lambda *_args, **_kwargs: "latest")

    with pytest.raises(app_service.AzureDeploymentError, match="verified image digest"):
        app_service.resolve_image_digest(
            connection=connection,
            client_secret="never-logged",
            image_ref="example.azurecr.io/team/api:v1",
        )


def test_acr_access_token_is_captured_in_memory_only(monkeypatch):
    captured = {}
    connection = SimpleNamespace(
        acr_login_server="example.azurecr.io",
        client_id="client",
        tenant_id="tenant",
        subscription_id="subscription",
    )
    monkeypatch.setattr(app_service.shutil, "which", lambda name: f"/tools/{name}")
    monkeypatch.setattr(app_service, "_sign_in", lambda *_args, **_kwargs: None)

    def run(command, **kwargs):
        captured["command"] = command
        captured["environment"] = kwargs["env"]
        return SimpleNamespace(
            returncode=0,
            stdout='{"accessToken":"short-lived-token","username":"00000000-0000-0000-0000-000000000000"}',
        )

    monkeypatch.setattr(app_service.subprocess, "run", run)
    credential = app_service.acquire_registry_access_token(
        connection=connection,
        client_secret="service-principal-secret",
    )

    assert credential.access_token == "short-lived-token"
    assert "short-lived-token" not in captured["command"]
    assert "short-lived-token" not in captured["environment"].values()


def test_azure_sign_in_supplies_secret_only_on_stdin(monkeypatch, tmp_path):
    captured = {}
    connection = SimpleNamespace(
        client_id="client",
        tenant_id="tenant",
        subscription_id="subscription",
    )
    secret = "service-principal-secret"
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "inherited-secret")
    monkeypatch.setenv("ARM_CLIENT_SECRET", "inherited-arm-secret")
    monkeypatch.setattr(app_service.shutil, "which", lambda name: f"/tools/{name}")

    def run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(app_service.subprocess, "run", run)
    monkeypatch.setattr(app_service, "_run", lambda *_args, **_kwargs: iter(()))
    environment = app_service._azure_environment(connection, str(tmp_path))
    environment["AZURE_CLIENT_SECRET"] = "unexpected-caller-secret"

    app_service._sign_in(connection, secret, environment)

    assert secret not in captured["command"]
    assert "--password" not in captured["command"]
    assert secret not in captured["kwargs"]["env"].values()
    assert "AZURE_CLIENT_SECRET" not in captured["kwargs"]["env"]
    assert "ARM_CLIENT_SECRET" not in captured["kwargs"]["env"]
    assert captured["kwargs"]["input"] == f"{secret}\n"


def test_azure_sign_in_fails_closed_when_cli_rejects(monkeypatch, tmp_path):
    connection = SimpleNamespace(
        client_id="client",
        tenant_id="tenant",
        subscription_id="subscription",
    )
    monkeypatch.setattr(app_service.shutil, "which", lambda name: f"/tools/{name}")
    monkeypatch.setattr(
        app_service.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout="provider detail"),
    )
    environment = app_service._azure_environment(connection, str(tmp_path))

    with pytest.raises(app_service.AzureDeploymentError, match="authentication was rejected"):
        app_service._sign_in(connection, "never-persisted", environment)


@pytest.mark.asyncio
async def test_repository_stage_uses_source_bound_disposable_executor(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"scripts":{"build":"next build"}}',
        encoding="utf-8",
    )
    facts = pipeline.repository_checks.inspect_repository(tmp_path)
    calls = []

    class Executor:
        def attest(self, request):
            calls.append(("attest", request))
            now = datetime.now(timezone.utc)
            return pipeline.repository_checks.RepositoryIsolationAttestation(
                isolation_id="sandbox-build-123",
                stage=request.stage,
                source_revision=request.source_revision,
                source_digest=request.source_digest,
                issued_at=now,
                expires_at=now + timedelta(seconds=700),
                disposable=True,
                fresh_source=True,
                worker_filesystem_access=False,
                database_access=False,
                key_vault_access=False,
                imds_access=False,
                network_policy="none",
            )

        def resolve_tool(self, tool, *, attestation):
            calls.append(("resolve", tool, attestation.isolation_id))
            return f"/sandbox/bin/{tool}"

        def execute(self, command, *, relative_cwd, timeout_seconds, attestation):
            calls.append(("execute", tuple(command), relative_cwd, attestation.isolation_id))
            return pipeline.repository_checks.CommandExecution(returncode=0)

    class Runtime:
        transitions = []

        async def is_queued(self, _stage):
            return True

        async def start(self, stage):
            self.transitions.append((stage, "running"))

        async def succeed(self, stage, **_kwargs):
            self.transitions.append((stage, "succeeded"))

        async def transition(self, stage, status, **_kwargs):
            self.transitions.append((stage, status))

    class Logger:
        async def log(self, *_args, **_kwargs):
            return None

    runtime = Runtime()
    source_revision = "a" * 40
    source_digest = "b" * 64

    await pipeline._run_repository_stage(
        runtime,
        Logger(),
        stage_key="build",
        repo_path=str(tmp_path),
        facts=facts,
        source_revision=source_revision,
        source_digest=source_digest,
        executor=Executor(),
    )

    request = calls[0][1]
    assert request.source_revision == source_revision
    assert request.source_digest == source_digest
    assert calls[-1][0] == "execute"
    assert runtime.transitions == [("build", "running"), ("build", "succeeded")]


@pytest.mark.asyncio
async def test_repository_stage_fails_closed_without_isolation_executor(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"scripts":{"build":"next build"}}',
        encoding="utf-8",
    )
    facts = pipeline.repository_checks.inspect_repository(tmp_path)

    class Runtime:
        transitions = []

        async def is_queued(self, _stage):
            return True

        async def start(self, stage):
            self.transitions.append((stage, "running"))

        async def succeed(self, stage, **_kwargs):
            self.transitions.append((stage, "succeeded"))

        async def transition(self, stage, status, **kwargs):
            self.transitions.append((stage, status, kwargs.get("failure_code")))

    class Logger:
        async def log(self, *_args, **_kwargs):
            return None

    runtime = Runtime()
    with pytest.raises(
        pipeline.PipelineExecutionError,
        match="repository isolation executor",
    ) as failure:
        await pipeline._run_repository_stage(
            runtime,
            Logger(),
            stage_key="build",
            repo_path=str(tmp_path),
            facts=facts,
            source_revision="a" * 40,
            source_digest="b" * 64,
            executor=None,
        )

    assert failure.value.failure_code == "REPOSITORY_CHECK_UNAVAILABLE"
    assert runtime.transitions[-1] == (
        "build",
        "unavailable",
        "REPOSITORY_CHECK_UNAVAILABLE",
    )


@pytest.mark.asyncio
async def test_source_sbom_persistence_does_not_claim_container_digest(monkeypatch, tmp_path):
    captured = {}
    result = pipeline.security_scanner.SecurityScanResult(
        kind="sbom",
        tool="syft",
        status="passed",
        required=True,
        blocking=False,
        summary="Source SBOM generated.",
        tool_version="1.0.0",
    )

    async def persist_scan(_db, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(
        pipeline.pipeline_evidence,
        "persist_security_scan",
        persist_scan,
    )

    class Runtime:
        db = object()
        pipeline_run = SimpleNamespace(id=uuid.uuid4())

        async def is_queued(self, _stage):
            return True

        async def start(self, _stage):
            return SimpleNamespace(id=uuid.uuid4())

        async def succeed(self, *_args, **_kwargs):
            return None

    class Logger:
        async def log(self, *_args, **_kwargs):
            return None

    await pipeline._run_security_stage(
        Runtime(),
        Logger(),
        stage_key="sbom",
        scan_kind="sbom",
        repo_path=str(tmp_path),
        target_revision="a" * 40,
        target_kind="repository",
        image_ref=None,
        scan_callable=lambda *_args, **_kwargs: result,
    )

    assert captured["target_kind"] == "repository"
    assert captured["target_digest"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("reported_endpoint", ["https://public.example", None])
async def test_aks_external_smoke_fails_closed_without_hardened_verifier(
    reported_endpoint,
):
    captured = {}

    class Runtime:
        async def transition(self, stage, status, **kwargs):
            captured.update({"stage": stage, "status": status, **kwargs})

    with pytest.raises(pipeline.PipelineExecutionError) as failure:
        await pipeline._block_unverified_aks_external_endpoint(
            Runtime(),
            reported_endpoint=reported_endpoint,
            release_metadata={
                "rollout_status": {"ready": True},
                "pod_status": {"ready": 2, "total": 2},
            },
        )

    assert failure.value.failure_code == "AKS_EXTERNAL_VERIFICATION_UNAVAILABLE"
    assert captured["stage"] == "smoke_test"
    assert captured["status"] == "unavailable"
    assert captured["failure_code"] == "AKS_EXTERNAL_VERIFICATION_UNAVAILABLE"
    evidence = {item["label"]: item["value"] for item in captured["evidence"]}
    assert evidence["Rollout status"] == {"ready": True}
    assert evidence["Pod status"] == {"ready": 2, "total": 2}
    assert evidence["Cluster endpoint reported"] is bool(reported_endpoint)


@pytest.mark.asyncio
async def test_aks_deployment_blocks_before_cluster_mutation_without_external_verifier():
    captured = {}

    class Runtime:
        async def transition(self, stage, status, **kwargs):
            captured.update({"stage": stage, "status": status, **kwargs})

    with pytest.raises(pipeline.PipelineExecutionError) as failure:
        await pipeline._block_unverified_aks_deployment(Runtime())

    assert failure.value.failure_code == "AKS_EXTERNAL_VERIFICATION_UNAVAILABLE"
    assert failure.value.stage_key == "application_deployment"
    assert captured["stage"] == "application_deployment"
    assert captured["status"] == "unavailable"
    evidence = {item["label"]: item["value"] for item in captured["evidence"]}
    assert evidence["Cluster mutation attempted"] is False
    assert evidence["External endpoint verifier available"] is False

    runtime_source = inspect.getsource(pipeline.run_deployment_pipeline)
    aks_branch = runtime_source.index('if selected_target.provider == "azure-aks":')
    pre_mutation_block = runtime_source.index(
        "await _block_unverified_aks_deployment(runtime)",
        aks_branch,
    )
    cluster_mutation = runtime_source.index("aks.deploy_existing_cluster", aks_branch)
    assert pre_mutation_block < cluster_mutation


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stage_key", "failure_code"),
    [
        ("health_check", "APP_SERVICE_HEALTH_CHECK_FAILED"),
        ("smoke_test", "APP_SERVICE_SMOKE_TEST_FAILED"),
    ],
)
async def test_app_service_endpoint_rejection_uses_explicit_stage_failure(
    monkeypatch,
    stage_key,
    failure_code,
):
    def reject(*_args, **_kwargs):
        raise pipeline.app_service.AzureDeploymentError("safe adapter detail")

    monkeypatch.setattr(pipeline.app_service, "verify_public_endpoint", reject)

    with pytest.raises(pipeline.PipelineExecutionError) as failure:
        await pipeline._verify_app_service_stage(
            "https://example.azurewebsites.net",
            "example",
            stage_key=stage_key,
            attempts=1,
            delay_seconds=0,
        )

    assert failure.value.failure_code == failure_code
    assert failure.value.stage_key == stage_key
    assert failure.value.status == "failed"


@pytest.mark.asyncio
async def test_terraform_validation_does_not_treat_tflint_as_terraform_validate():
    captured = {}

    class Runtime:
        async def transition(self, stage, status, **kwargs):
            captured.update({"stage": stage, "status": status, **kwargs})

    with pytest.raises(pipeline.PipelineExecutionError) as failure:
        await pipeline._block_unverified_terraform_validation(Runtime())

    assert failure.value.failure_code == "TERRAFORM_VALIDATION_UNAVAILABLE"
    assert captured["stage"] == "infrastructure_validation"
    assert captured["status"] == "unavailable"
    assert captured["failure_code"] == "TERRAFORM_VALIDATION_UNAVAILABLE"
    assert "Terraform fmt" in captured["reason"]
    assert "validate" in captured["reason"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("ai_used", "expected_status", "expected_error"),
    [
        (True, "succeeded", None),
        (False, "unavailable", "AI_PROVIDER_UNAVAILABLE"),
    ],
)
async def test_failure_investigation_persists_truthful_ai_provenance(
    monkeypatch,
    ai_used,
    expected_status,
    expected_error,
):
    class ScalarResult:
        def __init__(self, *, first=None, all_items=None):
            self._first = first
            self._all = all_items

        def scalars(self):
            return self

        def first(self):
            return self._first

        def all(self):
            return self._all if self._all is not None else []

    class Session:
        def __init__(self):
            self.results = iter([
                ScalarResult(),
                ScalarResult(all_items=[]),
                ScalarResult(first=SimpleNamespace(
                    baseline_revision="b" * 40,
                    target_revision="a" * 40,
                    decision_reason="deployment_relevant_change",
                    category_counts={"APPLICATION_CODE_CHANGE": 1},
                    changed_file_count=1,
                    sampled_paths=["src/main.py"],
                )),
                ScalarResult(),
            ])
            self.added = []
            self.committed_statuses = []

        async def execute(self, _statement):
            return next(self.results)

        def add(self, value):
            self.added.append(value)

        async def commit(self):
            investigation = next(
                (
                    value
                    for value in reversed(self.added)
                    if isinstance(value, pipeline.models.AIInvestigation)
                ),
                None,
            )
            if investigation is not None:
                self.committed_statuses.append(investigation.status)

    outcome = pipeline.ai.FailureAnalysisOutcome(
        analysis={
            "failure_summary": "The build failed.",
            "root_cause": "The bounded evidence reports a compiler error.",
            "severity": "error",
            "recommended_fix": "Correct the compiler error.",
            "step_by_step_resolution": ["Run the production build locally."],
        },
        ai_used=ai_used,
        provider="groq" if ai_used else "none",
        model="openai/gpt-oss-120b" if ai_used else "deterministic-scanner",
        input_tokens=12 if ai_used else 0,
        output_tokens=6 if ai_used else 0,
        unavailable_reason=None if ai_used else "provider_not_configured",
    )
    captured_model_events = []

    def analyze_failure(*args, **_kwargs):
        captured_model_events.extend(args[2])
        return outcome

    monkeypatch.setattr(pipeline.ai, "analyze_failure_nemotron", analyze_failure)
    session = Session()
    project_id = uuid.uuid4()
    deployment = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        project_id=project_id,
    )
    pipeline_run = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        project_id=project_id,
        requested_by_user_id=deployment.user_id,
        source_revision="a" * 40,
        branch="main",
    )
    failed_stage = SimpleNamespace(
        id=uuid.uuid4(),
        stage_key="build",
        status="failed",
        failure_code="BUILD_FAILED",
        evidence=[{"label": "compiler", "value": "token=stage-secret"}],
        result_metadata={"diagnostic_excerpt": "password=result-secret"},
    )

    await pipeline._persist_failure_investigation(
        session,
        deployment=deployment,
        pipeline_run=pipeline_run,
        failed_stage=failed_stage,
        failure_code="BUILD_FAILED",
        safe_message="The repository build failed.",
        diagnosis_enabled=True,
    )

    investigation = session.added[0]
    assert session.committed_statuses == ["running", expected_status]
    assert investigation.status == expected_status
    assert investigation.error_code == expected_error
    assert investigation.model_provider == ("groq" if ai_used else "none")
    assert investigation.model_name == (
        "openai/gpt-oss-120b" if ai_used else "deterministic-scanner"
    )
    assert investigation.input_tokens == (12 if ai_used else 0)
    if ai_used:
        assert investigation.redacted_error is None
    else:
        assert investigation.redacted_error
    model_context = "\n".join(captured_model_events)
    assert "stage-secret" not in model_context
    assert "result-secret" not in model_context
    assert "src/main.py" in model_context
    assert "stage-secret" not in str(investigation.evidence)
    assert "result-secret" not in str(investigation.evidence)


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        (
            {"status": "running", "pipeline_status": "succeeded", "pipeline_failure_code": None},
            "deployed",
        ),
        (
            {"status": "stopped", "pipeline_status": "succeeded", "pipeline_failure_code": None},
            "validation_completed",
        ),
        (
            {
                "status": "stopped",
                "pipeline_status": "blocked",
                "pipeline_failure_code": "DEPLOYMENT_APPROVAL_REQUIRED",
            },
            "approval_required",
        ),
        (
            {"status": "stopped", "pipeline_status": "failed", "pipeline_failure_code": "CHECK_FAILED"},
            "failed",
        ),
    ],
)
def test_worker_pipeline_outcome_distinguishes_non_deployment_success(record, expected):
    assert _pipeline_job_outcome(record) == expected
