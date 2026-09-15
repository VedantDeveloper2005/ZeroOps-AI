import json
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest

try:
    from backend.services import app_service, pipeline
    from worker import terraform_runner
    from worker.terraform_runner import TerraformRunner
except ImportError:
    from services import app_service, pipeline
    import terraform_runner
    from terraform_runner import TerraformRunner


def test_database_snapshot_events_replay_cross_process_progress_once():
    deployment = SimpleNamespace(
        status="building",
        live_url=None,
        failure_reason=None,
        infrastructure_metadata={
            "stages": [
                {"id": 1, "label": "Repository", "status": "completed", "duration": "1.0s"},
                {"id": 2, "label": "Build", "status": "active", "duration": "..."},
            ]
        },
    )
    first_log = SimpleNamespace(
        id=uuid.uuid4(),
        line_number=1,
        level="INFO",
        message="Worker cloned the selected branch.",
        timestamp=datetime(2026, 7, 27, 10, 0, 0),
    )
    seen_log_ids = set()
    stage_states = {}

    events, last_status = pipeline._snapshot_events(
        deployment,
        [first_log],
        seen_log_ids,
        stage_states,
        None,
    )

    assert [event["type"] for event in events] == ["log", "stage", "stage", "status"]
    assert events[0]["text"] == "Worker cloned the selected branch."
    assert events[-1]["status"] == "building"

    repeated_events, last_status = pipeline._snapshot_events(
        deployment,
        [first_log],
        seen_log_ids,
        stage_states,
        last_status,
    )
    assert repeated_events == []

    second_log = SimpleNamespace(
        id=uuid.uuid4(),
        line_number=2,
        level="SUCCESS",
        message="Azure verified the public endpoint.",
        timestamp=datetime(2026, 7, 27, 10, 1, 0),
    )
    deployment.infrastructure_metadata["stages"][1].update(status="completed", duration="60.0s")
    deployment.status = "running"
    deployment.live_url = "https://example.azurewebsites.net"

    changed_events, _ = pipeline._snapshot_events(
        deployment,
        [first_log, second_log],
        seen_log_ids,
        stage_states,
        last_status,
    )

    assert [event["type"] for event in changed_events] == ["log", "stage", "status"]
    assert changed_events[-1]["live_url"] == "https://example.azurewebsites.net"


def test_app_service_name_truncation_preserves_stable_project_identity():
    normalized = app_service.normalize_app_name(
        "app-account-customer-repository-with-a-very-long-descriptive-name-acde1234"
    )
    assert len(normalized) <= 60
    assert normalized.endswith("-acde1234")


def test_worker_loads_branch_from_immutable_deployment_record(monkeypatch):
    executed = {}

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def execute(self, statement, params):
            executed["statement"] = statement
            executed["params"] = params

        def fetchone(self):
            return {
                "full_name": "owner/repository",
                "source_type": "github",
                "branch": "release/customer-selected",
                "commit_sha": "a" * 40,
                "github_access_token_encrypted": "ciphertext",
            }

    class Connection:
        def cursor(self, **_):
            return Cursor()

    monkeypatch.setattr(
        "worker.terraform_runner.github_oauth.decrypt_token",
        lambda encrypted: f"decrypted:{encrypted}",
    )
    runner = TerraformRunner("postgresql://example.invalid/zeroops")
    job = {
        "deployment_id": "deployment-id",
        "project_id": "project-id",
        "user_id": "user-id",
    }

    repository, branch, commit_sha, token = runner._load_pipeline_input(Connection(), job)

    assert repository == "owner/repository"
    assert branch == "release/customer-selected"
    assert commit_sha == "a" * 40
    assert token == "decrypted:ciphertext"
    assert "d.commit_sha" in executed["statement"]
    assert executed["params"] == ("deployment-id", "project-id", "user-id")


def test_worker_generates_internal_artifact_and_persists_metadata_only(monkeypatch, tmp_path):
    deployment_id = "6f94058e-ed35-4fe9-8070-75aadcda2db7"
    secret_value = "must-never-enter-deployment-metadata"
    actions = []
    captured = {}

    class Cursor:
        def __init__(self):
            self.result = None
            self.rowcount = 1

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def execute(self, statement, params):
            normalized = " ".join(statement.split())
            if "p.source_type" in normalized and "d.commit_sha" in normalized:
                self.result = {
                    "full_name": "owner/customer-portal",
                    "source_type": "github",
                    "branch": "release/approved",
                    "commit_sha": "b" * 40,
                    "github_access_token_encrypted": "ciphertext",
                }
            elif normalized.startswith("SELECT infrastructure_metadata"):
                self.result = {
                    "infrastructure_metadata": {
                        "target_provider": "azure-app-service",
                    }
                }
            elif normalized.startswith("UPDATE deployments AS d SET infrastructure_metadata"):
                captured["deployment_metadata"] = params[0].adapted
                actions.append("persist")
                self.result = {"id": deployment_id}
            elif normalized.startswith("WITH owned_job AS"):
                self.result = {"id": deployment_id}
            elif normalized.startswith("SELECT status, failure_reason"):
                self.result = {
                    "status": "running",
                    "failure_reason": None,
                    "live_url": "https://customer.example",
                }
            else:
                self.result = None

        def fetchone(self):
            return self.result

    class Connection:
        def __init__(self):
            self.autocommit = False
            self.closed = False

        def cursor(self, **_):
            return Cursor()

        def close(self):
            self.closed = True

    queued_spec = {
        "cloud": "Azure",
        "region_label": "East US",
        "revision": 8,
        "components": [
            {"id": "compute", "service": "Azure App Service", "tier": "B1"},
            {"id": "secrets", "service": "Azure Key Vault", "tier": "standard"},
        ],
        "environment_variables": ["DATABASE_URL", "CLIENT_SECRET"],
        "client_secret": secret_value,
    }
    connection = Connection()
    runner = TerraformRunner("postgresql://example.invalid/zeroops")
    monkeypatch.setattr(runner, "_get_connection", lambda: connection)
    monkeypatch.setattr(
        runner,
        "_require_completed_terraform_apply",
        lambda *_args, **_kwargs: (
            actions.append("terraform-gate")
            or {
                "operation_run_id": "10000000-0000-0000-0000-000000000001",
                "plan_id": "20000000-0000-0000-0000-000000000001",
                "plan_revision": 8,
                "plan_digest": "a" * 64,
            }
        ),
    )
    monkeypatch.setattr(terraform_runner.terraform_generator.config, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(
        terraform_runner.github_oauth,
        "decrypt_token",
        lambda encrypted: f"decrypted:{encrypted}",
    )

    real_generate = terraform_runner.terraform_generator.generate_internal_artifact

    def generate_with_untrusted_extra_fields(**kwargs):
        actions.append("generate")
        assert kwargs["plan"] is queued_spec
        generated = real_generate(**kwargs)
        # These simulate an accidental future generator expansion. The worker
        # metadata allowlist must discard all source and secret-bearing fields.
        generated["hcl"] = f'resource "unsafe" "example" {{ value = "{secret_value}" }}'
        generated["variables"] = {"CLIENT_SECRET": secret_value}
        generated["client_secret"] = secret_value
        return generated

    async def fake_pipeline(
        deploy_id,
        repository,
        branch,
        clone_token,
        *,
        commit_sha,
        lease_guard,
        repository_executor=None,
    ):
        actions.append("pipeline")
        assert deploy_id == deployment_id
        assert repository == "owner/customer-portal"
        assert branch == "release/approved"
        assert commit_sha == "b" * 40
        assert clone_token == "decrypted:ciphertext"
        assert lease_guard() is True

    monkeypatch.setattr(
        terraform_runner.terraform_generator,
        "generate_internal_artifact",
        generate_with_untrusted_extra_fields,
    )
    monkeypatch.setattr(terraform_runner.pipeline, "run_deployment_pipeline", fake_pipeline)

    succeeded = runner.execute_job({
        "id": "job-id",
        "deployment_id": deployment_id,
        "project_id": "project-id",
        "user_id": "user-id",
        "worker_id": "worker-test",
        "lease_token": "lease-test",
        "infrastructure_spec": queued_spec,
    })

    assert succeeded is True
    assert actions == ["generate", "persist", "terraform-gate", "pipeline"]
    assert connection.closed is True

    artifact_path = tmp_path / "internal-iac" / deployment_id / "main.tf"
    assert artifact_path.is_file()
    artifact_source = artifact_path.read_text(encoding="utf-8")
    assert secret_value not in artifact_source
    assert "DATABASE_URL" not in artifact_source
    assert "CLIENT_SECRET" not in artifact_source

    deployment_metadata = captured["deployment_metadata"]
    assert deployment_metadata["target_provider"] == "azure-app-service"
    internal_iac = deployment_metadata["internal_iac"]
    assert internal_iac["engine"] == "terraform"
    assert internal_iac["status"] == "generated"
    assert internal_iac["execution"] == "not_run"
    assert internal_iac["plan_revision"] == 8
    assert internal_iac["resource_kinds"] == [
        "azurerm_key_vault",
        "azurerm_linux_web_app",
    ]
    assert len(internal_iac["artifact_sha256"]) == 64
    serialized_metadata = json.dumps(internal_iac)
    assert secret_value not in serialized_metadata
    assert "hcl" not in internal_iac
    assert "variables" not in internal_iac
    assert "client_secret" not in internal_iac
    assert "artifact_path" not in internal_iac


def _completed_apply_gate_fixture():
    tenant_id = uuid.UUID("a1000000-0000-0000-0000-000000000001")
    project_id = uuid.UUID("a2000000-0000-0000-0000-000000000001")
    user_id = uuid.UUID("a3000000-0000-0000-0000-000000000001")
    plan_id = uuid.UUID("a4000000-0000-0000-0000-000000000001")
    operation_run_id = uuid.UUID("a5000000-0000-0000-0000-000000000001")
    approval_id = uuid.UUID("a6000000-0000-0000-0000-000000000001")
    apply_job_id = uuid.UUID("a7000000-0000-0000-0000-000000000001")
    plan_job_digest = "1" * 64
    plan_sha256 = "2" * 64
    bundle_sha256 = "3" * 64
    input_variables_sha256 = "4" * 64
    scope_digest = "5" * 64
    policy_digest = "6" * 64
    cost_digest = "7" * 64
    event_id = "evt-completed-exact-apply"
    plan_data = {
        "components": [
            {
                "id": "application",
                "service": "Azure App Service",
                "tier": "zeroops-linux-plan",
                "deployable": True,
            }
        ]
    }
    azure_connection = SimpleNamespace(
        tenant_id="entra-tenant",
        subscription_id="azure-subscription",
        client_id="service-principal-client",
        connection_status="connected",
        region="eastus",
        resource_group="zeroops-test",
        acr_login_server="zeroopstest.azurecr.io",
        app_service_plan="zeroops-linux-plan",
        deployment_target_fingerprint=None,
        deployment_target_verified_at=datetime(2026, 1, 1),
        namespace_prefix=None,
        is_active=True,
    )
    azure_connection.deployment_target_fingerprint = (
        terraform_runner.deployment_targets.configuration_fingerprint(azure_connection)
    )
    plan_digest = terraform_runner.canonical_digest(
        {
            "id": str(plan_id),
            "project_id": str(project_id),
            "provider": "azure",
            "region": "eastus",
            "status": "approved",
            "revision": 3,
            "plan": plan_data,
            "cost_estimate": None,
        }
    )
    proof = {
        "schema_version": "terraform-apply-proof.v1",
        "operation_run_id": str(operation_run_id),
        "approval_id": str(approval_id),
        "apply_job_id": str(apply_job_id),
        "approved_plan_digest": plan_digest,
        "plan_job_digest": plan_job_digest,
        "plan_sha256": plan_sha256,
        "bundle_sha256": bundle_sha256,
        "target_fingerprint": azure_connection.deployment_target_fingerprint,
        "completion_event_id": event_id,
        "completed_at": "2026-01-01T00:00:00+00:00",
    }
    current = {
        "terraform_operation_run_id": operation_run_id,
        "infrastructure_metadata": {
            "architecture_plan": {"id": str(plan_id), "revision": 3},
            "terraform_apply": proof,
        },
        "deployment_tenant_id": tenant_id,
        "plan_id": plan_id,
        "plan_project_id": project_id,
        "plan_user_id": user_id,
        "plan_provider": "azure",
        "plan_region": "eastus",
        "plan_status": "approved",
        "plan_revision": 3,
        "plan_data": plan_data,
        "plan_cost_estimate": None,
        "azure_tenant_id": azure_connection.tenant_id,
        "azure_subscription_id": azure_connection.subscription_id,
        "azure_client_id": azure_connection.client_id,
        "azure_connection_status": azure_connection.connection_status,
        "azure_region": azure_connection.region,
        "azure_resource_group": azure_connection.resource_group,
        "azure_acr_login_server": azure_connection.acr_login_server,
        "azure_app_service_plan": azure_connection.app_service_plan,
        "deployment_target_fingerprint": azure_connection.deployment_target_fingerprint,
        "deployment_target_verified_at": azure_connection.deployment_target_verified_at,
        "azure_namespace_prefix": None,
        "azure_is_active": True,
    }
    applied = {
        "input_digest": plan_digest,
        "operation_tenant_id": tenant_id,
        "operation_status": "completed",
        "summary": {
            "approved_plan_id": str(plan_id),
            "approved_plan_revision": 3,
            "approved_plan_digest": plan_digest,
            "target_fingerprint": azure_connection.deployment_target_fingerprint,
        },
        "plan_job_digest": plan_job_digest,
        "plan_tenant_id": tenant_id,
        "terraform_revision": 3,
        "bundle": {"sha256": bundle_sha256},
        "input_variables": {"sha256": input_variables_sha256},
        "guardrails": {"scope_digest": scope_digest, "policy_digest": policy_digest},
        "saved_plan": {
            "sha256": plan_sha256,
            "plan_job_digest": plan_job_digest,
            "bundle_sha256": bundle_sha256,
            "input_variables_sha256": input_variables_sha256,
            "scope_digest": scope_digest,
            "policy_digest": policy_digest,
        },
        "cost_estimate": {
            "artifact_sha256": cost_digest,
            "currency": "USD",
            "monthly_cost_microunits": 0,
        },
        "approval_id": approval_id,
        "approval_tenant_id": tenant_id,
        "apply_job_id": apply_job_id,
        "approval_status": "consumed",
        "approved_plan_job_digest": plan_job_digest,
        "approved_plan_sha256": plan_sha256,
        "approved_bundle_sha256": bundle_sha256,
        "approved_input_variables_sha256": input_variables_sha256,
        "approved_scope_digest": scope_digest,
        "approved_policy_digest": policy_digest,
        "approved_cost_estimate_sha256": cost_digest,
        "approved_currency": "USD",
        "approved_monthly_cost_microunits": 0,
        "event_data": {
            "status": "completed",
            "stage": "terraform-apply",
            "metadata": {
                "operation": "apply",
                "job_id": str(apply_job_id),
                "approval_id": str(approval_id),
                "plan_sha256": plan_sha256,
                "bundle_sha256": bundle_sha256,
            },
        },
        "event_tenant_id": tenant_id,
        "external_event_id": event_id,
        "event_fingerprint": "8" * 64,
    }
    job = {
        "deployment_id": "a8000000-0000-0000-0000-000000000001",
        "project_id": str(project_id),
        "user_id": str(user_id),
    }
    return current, applied, job


class _GateConnection:
    def __init__(self, current, applied):
        self.current = current
        self.applied = applied

    def cursor(self, **_kwargs):
        connection = self

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def execute(self, statement, _params):
                normalized = " ".join(statement.split())
                self.result = (
                    connection.current
                    if "d.terraform_operation_run_id" in normalized
                    else connection.applied
                )

            def fetchone(self):
                return self.result

        return Cursor()


def test_worker_requires_the_exact_completed_terraform_operation_before_cloud_execution():
    current, applied, job = _completed_apply_gate_fixture()
    runner = TerraformRunner("postgresql://example.invalid/zeroops")

    proof = runner._require_completed_terraform_apply(
        _GateConnection(current, applied),
        job,
    )

    assert proof["operation_run_id"] == str(current["terraform_operation_run_id"])
    assert proof["plan_revision"] == 3


@pytest.mark.parametrize(
    "operation_binding",
    [
        None,
        uuid.UUID("a5000000-0000-0000-0000-000000000099"),
    ],
    ids=["legacy-missing-fk", "rebound-to-different-operation"],
)
def test_worker_rejects_legacy_or_rebound_deployment_without_matching_operation_fk(
    operation_binding,
):
    current, applied, job = _completed_apply_gate_fixture()
    current["terraform_operation_run_id"] = operation_binding
    runner = TerraformRunner("postgresql://example.invalid/zeroops")

    with pytest.raises(RuntimeError, match="operation binding"):
        runner._require_completed_terraform_apply(
            _GateConnection(current, applied),
            job,
        )


def test_app_code_only_existing_app_service_deployment_does_not_require_terraform():
    """App-code-only existing App Service deployment does not require Terraform."""
    current, applied, job = _completed_apply_gate_fixture()
    current["terraform_operation_run_id"] = None
    current["infrastructure_metadata"] = {
        "target_provider": "azure-app-service",
        "app_service_reused": True,
        "terraform_apply_required": False,
    }
    runner = TerraformRunner("postgresql://example.invalid/zeroops")

    proof = runner._require_completed_terraform_apply(
        _GateConnection(current, applied),
        job,
    )

    assert proof is not None
    assert proof.get("app_service_reused") is True
    assert proof.get("plan_id") == str(current["plan_id"])
    assert proof.get("plan_revision") == current["plan_revision"]


def test_infrastructure_changing_deployment_still_requires_real_terraform_approval_apply_evidence():
    """Infrastructure-changing deployment still requires real Terraform approval/apply evidence."""
    current, applied, job = _completed_apply_gate_fixture()
    current["terraform_operation_run_id"] = None
    current["infrastructure_metadata"] = {
        "target_provider": "azure-app-service",
        "app_service_reused": False,
        "terraform_apply_required": True,
    }
    runner = TerraformRunner("postgresql://example.invalid/zeroops")

    with pytest.raises(RuntimeError, match="Terraform apply proof is invalid|no exact completed Terraform apply proof"):
        runner._require_completed_terraform_apply(
            _GateConnection(current, applied),
            job,
        )


def test_no_terraform_apply_completed_record_created_for_app_service_reused():
    """No fake terraform.apply.completed record is created when Terraform never ran."""
    from backend.services.deployment_targets import is_app_service_reused_deployment
    from types import SimpleNamespace

    connection = SimpleNamespace(
        connection_status="connected",
        is_active=True,
        deployment_target_verified_at=datetime.utcnow(),
        deployment_target_fingerprint="dummy",
    )
    from backend.services.deployment_targets import configuration_fingerprint
    connection.deployment_target_fingerprint = configuration_fingerprint(connection)

    # Reused when no infrastructure change
    assert is_app_service_reused_deployment(
        target="azure-app-service",
        connection=connection,
        infrastructure_change=False,
        has_iac=False,
    ) is True

    # Not reused when infrastructure changed
    assert is_app_service_reused_deployment(
        target="azure-app-service",
        connection=connection,
        infrastructure_change=True,
        has_iac=False,
    ) is False

    # Not reused when IaC files present
    assert is_app_service_reused_deployment(
        target="azure-app-service",
        connection=connection,
        infrastructure_change=False,
        has_iac=True,
    ) is False
