import json
import uuid
from datetime import datetime
from types import SimpleNamespace

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
    assert actions == ["generate", "persist", "pipeline"]
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
