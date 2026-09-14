from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import uuid

from fastapi import FastAPI
import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import auth, config, models
from backend.database import get_db
from backend.routes import devsecops
from backend.services import deployment_targets, pipeline_approval
from backend.services.pipeline_records import context_from_configuration, create_pipeline_run
from backend.services.tenancy import ensure_personal_tenant


@dataclass
class DevSecOpsHarness:
    session: AsyncSession
    client: httpx.AsyncClient
    owner: models.User
    outsider: models.User
    owner_tenant: models.Tenant
    project: models.Project
    deployment: models.Deployment
    current_user: dict[str, models.User]


@dataclass(frozen=True)
class StubTerraformApplyProof:
    operation_run_id: uuid.UUID

    def deployment_metadata(self):
        return {
            "schema_version": "terraform-apply-proof.v1",
            "operation_run_id": str(self.operation_run_id),
            "approval_id": "20000000-0000-0000-0000-000000000001",
            "apply_job_id": "30000000-0000-0000-0000-000000000001",
            "approved_plan_digest": "1" * 64,
            "plan_job_digest": "2" * 64,
            "plan_sha256": "3" * 64,
            "bundle_sha256": "4" * 64,
            "target_fingerprint": "5" * 64,
            "completion_event_id": "evt-test-completed-apply",
            "completed_at": "2026-01-01T00:00:00+00:00",
        }


@pytest_asyncio.fixture
async def devsecops_harness():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(models.Base.metadata.create_all)

    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        owner = models.User(id=uuid.uuid4(), email="owner@example.test")
        outsider = models.User(id=uuid.uuid4(), email="outsider@example.test")
        session.add_all([owner, outsider])
        await session.flush()
        owner_tenant = await ensure_personal_tenant(session, owner)
        await ensure_personal_tenant(session, outsider)

        project = models.Project(
            id=uuid.uuid4(),
            user_id=owner.id,
            name="api",
            full_name="zeroops/api",
            branch="main",
        )
        deployment = models.Deployment(
            id=uuid.uuid4(),
            user_id=owner.id,
            project_id=project.id,
            status="running",
            environment="production",
            branch="main",
            commit_sha="a" * 40,
            live_url="https://api.example.test",
            infrastructure_metadata={"target_provider": "azure-app-service"},
        )
        session.add_all([project, deployment])
        await session.commit()

        current_user = {"value": owner}

        async def override_db():
            yield session

        async def override_current_user():
            return current_user["value"]

        test_app = FastAPI()
        test_app.include_router(devsecops.router)
        test_app.dependency_overrides[get_db] = override_db
        test_app.dependency_overrides[auth.get_current_user] = override_current_user
        transport = httpx.ASGITransport(app=test_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield DevSecOpsHarness(
                session=session,
                client=client,
                owner=owner,
                outsider=outsider,
                owner_tenant=owner_tenant,
                project=project,
                deployment=deployment,
                current_user=current_user,
            )

    async with engine.begin() as connection:
        await connection.run_sync(models.Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "PUT"])
async def test_pipeline_configuration_returns_actionable_error_when_vault_is_unavailable(
    devsecops_harness, monkeypatch, method,
):
    harness = devsecops_harness

    def unavailable(*_):
        raise RuntimeError("private-vault-host credential-details")

    monkeypatch.setattr(devsecops.vault, "get_project_secret", unavailable)
    response = await harness.client.request(
        method, f"/api/projects/{harness.project.id}/pipeline-config",
        **({"json": {"branch": "main"}} if method == "PUT" else {}),
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Azure Key Vault is unavailable. GitHub webhook configuration could not be checked."
    assert (await harness.session.execute(select(func.count(models.ProjectPipelineConfiguration.id)))).scalar() == 0


@pytest.mark.asyncio
async def test_pipeline_configuration_persists_versioned_settings_without_webhook(
    devsecops_harness, monkeypatch,
):
    harness = devsecops_harness
    monkeypatch.setattr(devsecops.vault, "get_project_secret", lambda *_: None)
    url = f"/api/projects/{harness.project.id}/pipeline-config"

    first = await harness.client.put(url, json={"branch": "release/2026", "run_tests": False})
    assert first.status_code == 200
    assert first.json()["github_webhook_configured"] is False
    assert first.json()["run_tests"] is False
    assert (await harness.client.get(url)).json() == first.json()

    blocked = await harness.client.put(url, json={"automatic_deployment": True})
    assert blocked.status_code == 409
    assert (await harness.session.execute(select(func.count(models.ProjectPipelineConfiguration.id)))).scalar() == 1

    second = await harness.client.put(url, json={"branch": "main", "run_tests": True})
    assert second.status_code == 200
    assert second.json()["run_tests"] is True
    assert (await harness.client.get(url)).json() == second.json()
    records = (await harness.session.execute(select(models.ProjectPipelineConfiguration).order_by(models.ProjectPipelineConfiguration.version))).scalars().all()
    assert [record.version for record in records] == [1, 2]
    assert [record.tracked_branch for record in records] == ["release/2026", "main"]


@pytest.mark.asyncio
async def test_github_webhook_returns_actionable_error_when_vault_is_unavailable(
    devsecops_harness, monkeypatch,
):
    harness = devsecops_harness

    def unavailable(*_):
        raise RuntimeError("private-vault-host credential-details")

    monkeypatch.setattr(devsecops.vault, "get_project_secret", unavailable)
    response = await harness.client.post(
        f"/api/webhooks/github/{harness.project.id}", json={},
        headers={"X-GitHub-Event": "push", "X-GitHub-Delivery": "vault-unavailable"},
    )

    assert response.status_code == 503
    assert "Azure Key Vault is unavailable" in response.json()["detail"]
    assert (await harness.session.execute(select(func.count(models.WebhookDelivery.id)))).scalar() == 0


@pytest.mark.parametrize("branch", ["   ", "refs/heads/", "feature:broken", "feature@{1}"])
def test_pipeline_configuration_rejects_invalid_git_branches(branch):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        devsecops.PipelineConfigurationUpdate(branch=branch)


@pytest.mark.asyncio
async def test_monitoring_reports_no_telemetry_instead_of_fabricating_samples(
    devsecops_harness,
):
    harness = devsecops_harness

    response = await harness.client.get(
        f"/api/projects/{harness.project.id}/monitoring",
        params={"window": "1h"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["availability"] == "no_telemetry"
    assert payload["samples"] == []
    assert payload["deployment_health"] is None
    assert payload["source"] is None
    assert payload["available_windows"] == ["live"]
    assert payload["message"] == "No telemetry received in the selected window."


@pytest.mark.asyncio
async def test_monitoring_does_not_attribute_prior_revision_metrics_to_latest_deployment(
    devsecops_harness,
):
    harness = devsecops_harness
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    prior = models.Deployment(
        id=uuid.uuid4(),
        user_id=harness.owner.id,
        project_id=harness.project.id,
        status="stopped",
        environment="production",
        branch="main",
        commit_sha="9" * 40,
        started_at=now_naive - timedelta(days=1),
        completed_at=now_naive - timedelta(hours=23),
    )
    harness.session.add(prior)
    await harness.session.flush()
    harness.session.add(
        models.DeploymentMetric(
            deployment_id=prior.id,
            project_id=harness.project.id,
            cpu_utilization=88.0,
            source="azure-monitor",
            timestamp=now_naive - timedelta(minutes=2),
        )
    )
    await harness.session.commit()

    response = await harness.client.get(
        f"/api/projects/{harness.project.id}/monitoring",
        params={"window": "live"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["deployment_revision"] == harness.deployment.commit_sha
    assert payload["availability"] == "no_telemetry"
    assert payload["samples"] == []
    assert payload["available_windows"] == ["live"]


@pytest.mark.asyncio
async def test_metric_ingestion_persists_real_nullable_fields_and_worker_auth(
    devsecops_harness,
    monkeypatch,
):
    harness = devsecops_harness
    monkeypatch.setattr(config, "WORKER_EVENT_TOKEN", "worker-test-token")
    recorded_at = datetime.now(timezone.utc).replace(microsecond=0)
    url = f"/api/deployments/{harness.deployment.id}/metrics"
    body = {
        "recorded_at": recorded_at.isoformat(),
        "source": "container-insights",
        "cpu_percent": 24.5,
        "memory_percent": 61.25,
        "request_count": 120,
        "request_rate": 4.75,
        "response_latency_ms": 187,
        "http_error_rate_percent": 0.5,
        "availability_percent": 99.95,
        "pod_restarts": 1,
        "pods_ready": 3,
        "replica_count": 3,
        "failed_pods": 0,
        "deployment_health": "healthy",
    }

    forbidden = await harness.client.post(url, json=body)
    assert forbidden.status_code == 403

    accepted = await harness.client.post(
        url,
        json=body,
        headers={"X-ZeroOps-Worker-Token": "worker-test-token"},
    )

    assert accepted.status_code == 202
    assert accepted.json()["status"] == "accepted"
    metric = await harness.session.get(
        models.DeploymentMetric,
        uuid.UUID(accepted.json()["metric_id"]),
    )
    assert metric is not None
    assert metric.source == "container-insights"
    assert metric.request_rate == 4.75
    assert metric.availability_percent == 99.95
    assert metric.pod_restarts == 1
    assert metric.pods_ready == 3
    assert metric.replica_count == 3
    assert metric.failed_pods == 0
    assert metric.deployment_health == "healthy"
    # The legacy column is TIMESTAMP WITHOUT TIME ZONE; the route normalizes
    # an aware API value at the persistence boundary.
    assert metric.timestamp.tzinfo is None
    assert metric.timestamp == recorded_at.replace(tzinfo=None)

    minimal = await harness.client.post(
        url,
        json={"source": "health-check"},
        headers={"X-ZeroOps-Worker-Token": "worker-test-token"},
    )
    assert minimal.status_code == 202
    minimal_metric = await harness.session.get(
        models.DeploymentMetric,
        uuid.UUID(minimal.json()["metric_id"]),
    )
    assert minimal_metric.cpu_utilization is None
    assert minimal_metric.memory_utilization is None
    assert minimal_metric.request_count is None
    assert minimal_metric.request_rate is None
    assert minimal_metric.deployment_health is None


def _signed_github_headers(secret: str, body: bytes, delivery_id: str) -> dict[str, str]:
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-GitHub-Event": "push",
        "X-GitHub-Delivery": delivery_id,
        "X-Hub-Signature-256": f"sha256={signature}",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("deployment_mode", "approval_required", "decision_status"),
    [
        ("require_approval", True, "pending"),
        ("validate_only", False, "not_required"),
    ],
)
async def test_github_webhook_verifies_hmac_is_idempotent_and_queues_approval_validation(
    devsecops_harness,
    monkeypatch,
    deployment_mode,
    approval_required,
    decision_status,
):
    harness = devsecops_harness
    secret = "github-webhook-test-secret"
    proof = StubTerraformApplyProof(uuid.UUID("a0000000-0000-0000-0000-000000000001"))

    async def completed_apply(*_args, **_kwargs):
        return proof

    monkeypatch.setattr(
        devsecops.terraform_workflow,
        "require_completed_apply_for_plan",
        completed_apply,
    )
    monkeypatch.setattr(devsecops.vault, "get_project_secret", lambda *_: secret)
    azure_connection = models.UserAzureConnection(
        user_id=harness.owner.id,
        tenant_id="entra-tenant",
        subscription_id="azure-subscription",
        client_id="service-principal-client",
        connection_status="connected",
        region="eastus",
        resource_group="zeroops-test",
        acr_login_server="zeroopstest.azurecr.io",
        app_service_plan="zeroops-linux-plan",
        deployment_target_verified_at=datetime(2026, 1, 1),
        is_active=True,
    )
    azure_connection.deployment_target_fingerprint = (
        deployment_targets.configuration_fingerprint(azure_connection)
    )
    harness.session.add_all(
        [
            models.ProjectPipelineConfiguration(
                tenant_id=harness.owner_tenant.id,
                project_id=harness.project.id,
                version=1,
                enabled=True,
                trigger_mode="manual_and_push",
                tracked_branch="main",
                auto_deploy=True,
                deployment_mode=deployment_mode,
            ),
            models.InfrastructurePlan(
                user_id=harness.owner.id,
                project_id=harness.project.id,
                provider="azure",
                region="eastus",
                status="approved",
                revision=1,
                plan_data={"resource_group": "zeroops-test"},
            ),
            azure_connection,
        ]
    )
    await harness.session.commit()

    body = json.dumps(
        {
            "ref": "refs/heads/main",
            "after": "b" * 40,
            "deleted": False,
            "repository": {"id": 42, "full_name": harness.project.full_name},
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    url = f"/api/webhooks/github/{harness.project.id}"

    invalid_headers = _signed_github_headers(secret, body, "invalid-signature")
    invalid_headers["X-Hub-Signature-256"] = "sha256=" + "0" * 64
    invalid = await harness.client.post(url, content=body, headers=invalid_headers)
    assert invalid.status_code == 401

    headers = _signed_github_headers(secret, body, "delivery-001")
    accepted = await harness.client.post(url, content=body, headers=headers)
    assert accepted.status_code == 202
    assert accepted.json()["status"] == "queued"
    run_id = uuid.UUID(accepted.json()["pipeline_run_id"])
    run = await harness.session.get(models.PipelineRun, run_id)
    assert run is not None
    assert run.status == "queued"
    assert run.failure_code is None
    assert run.approval_required is approval_required
    deployment = await harness.session.get(
        models.Deployment,
        uuid.UUID(accepted.json()["deployment_id"]),
    )
    assert deployment.status == "queued"
    assert deployment.infrastructure_metadata["requested_target"] == "azure-app-service"
    assert deployment.terraform_operation_run_id == proof.operation_run_id
    assert deployment.infrastructure_metadata["pipeline_configuration"]["id"] == str(run.configuration_id)
    assert deployment.infrastructure_metadata["pipeline_approval_decision"] == {
        "status": decision_status,
        "consumed": False,
    }
    queued_job_count = await harness.session.scalar(
        select(func.count(models.DeploymentJob.id)).where(
            models.DeploymentJob.deployment_id == deployment.id,
            models.DeploymentJob.status == "queued",
        )
    )
    assert queued_job_count == 1

    duplicate = await harness.client.post(url, content=body, headers=headers)
    assert duplicate.status_code == 202
    assert duplicate.json() == {
        "status": "duplicate",
        "delivery_id": accepted.json()["delivery_id"],
        "pipeline_run_id": str(run.id),
    }
    delivery_count = await harness.session.scalar(
        select(func.count(models.WebhookDelivery.id)).where(
            models.WebhookDelivery.external_delivery_id == "delivery-001"
        )
    )
    assert delivery_count == 1
    delivery = await harness.session.get(
        models.WebhookDelivery,
        uuid.UUID(accepted.json()["delivery_id"]),
    )
    assert delivery.signature_status == "verified"
    assert delivery.payload_digest == hashlib.sha256(body).hexdigest()
    assert "payload" not in models.WebhookDelivery.__table__.columns


async def _seed_approval_ready_run(
    harness: DevSecOpsHarness,
    *,
    source_revision: str = "c" * 40,
) -> tuple[
    models.PipelineRun,
    models.Deployment,
    models.ProjectPipelineConfiguration,
    models.InfrastructurePlan,
]:
    configuration = models.ProjectPipelineConfiguration(
        tenant_id=harness.owner_tenant.id,
        project_id=harness.project.id,
        created_by_user_id=harness.owner.id,
        updated_by_user_id=harness.owner.id,
        version=1,
        enabled=True,
        trigger_mode="manual_and_push",
        tracked_branch="main",
        auto_deploy=True,
        deployment_mode="require_approval",
        require_production_approval=True,
        config_digest="d" * 64,
    )
    plan = models.InfrastructurePlan(
        user_id=harness.owner.id,
        project_id=harness.project.id,
        provider="azure",
        region="eastus",
        status="approved",
        revision=7,
        plan_data={"resource_group": "zeroops-test", "revision": 7},
    )
    harness.session.add_all([configuration, plan])
    await harness.session.flush()
    deployment = models.Deployment(
        id=uuid.uuid4(),
        user_id=harness.owner.id,
        project_id=harness.project.id,
        status="stopped",
        environment="production",
        branch="main",
        version="v-validation",
        commit_sha=source_revision,
        image="zeroopstest.azurecr.io/app-api@sha256:" + "e" * 64,
        deployed_by="GitHub push",
        completed_at=datetime.now(timezone.utc).replace(tzinfo=None),
        infrastructure_metadata={
            "requested_target": "auto",
            "target_provider": "azure-app-service",
            "target_reason": "Validated web application target.",
            "target": {
                "provider": "azure-app-service",
                "subscription_id": "azure-subscription",
                "region": "eastus",
                "resource_group": "zeroops-test",
                "acr_login_server": "zeroopstest.azurecr.io",
                "app_service_plan": "zeroops-linux-plan",
            },
            "source_type": "github",
            "source_revision": {
                "provider": "github",
                "branch": "main",
                "commit_sha": source_revision,
            },
            "architecture_plan": {
                "id": str(plan.id),
                "revision": plan.revision,
                "provider": plan.provider,
                "region": plan.region,
            },
            "pipeline_configuration": {
                "id": str(configuration.id),
                "version": configuration.version,
                "digest": configuration.config_digest,
            },
            "pipeline_approval_decision": {"status": "pending", "consumed": False},
            "stages": [{"key": "approval", "status": "blocked"}],
            "internal_iac": {"status": "generated", "artifact_sha256": "f" * 64},
        },
    )
    harness.session.add(deployment)
    await harness.session.flush()
    context = context_from_configuration(
        configuration,
        target_type="azure-app-service",
        has_dependencies=True,
        has_tests=True,
        has_iac=True,
        infrastructure_change=False,
    )
    run = await create_pipeline_run(
        harness.session,
        tenant_id=harness.owner_tenant.id,
        project_id=harness.project.id,
        deployment_id=deployment.id,
        requested_by_user_id=None,
        configuration=configuration,
        trigger_type="push",
        branch="main",
        source_revision=source_revision,
        target_type="azure-app-service",
        idempotency_key=f"approval-validation:{source_revision}",
        context=context,
    )
    stages_result = await harness.session.execute(
        select(models.PipelineStageAttempt)
        .where(models.PipelineStageAttempt.pipeline_run_id == run.id)
        .order_by(models.PipelineStageAttempt.stage_order)
    )
    stages = list(stages_result.scalars().all())
    approval_order = next(stage.stage_order for stage in stages if stage.stage_key == "approval")
    now = datetime.now(timezone.utc)
    for stage in stages:
        if stage.stage_key == "approval":
            stage.status = "blocked"
            stage.status_reason = "Explicit authenticated deployment approval is required."
            stage.failure_code = "DEPLOYMENT_APPROVAL_REQUIRED"
            stage.started_at = now
            continue
        if stage.stage_order < approval_order:
            if stage.is_required:
                stage.status = "succeeded"
                stage.status_reason = None
                stage.started_at = now
                stage.completed_at = now
            # Dynamically irrelevant stages are already skipped.
            continue
        if stage.status == "queued":
            stage.status = "cancelled"
            stage.status_reason = "Not executed before approval."
            stage.failure_code = "PREDECESSOR_NOT_SUCCESSFUL"
            stage.completed_at = now
    run.status = "blocked"
    run.failure_code = "DEPLOYMENT_APPROVAL_REQUIRED"
    run.status_reason = "Explicit authenticated deployment approval is required."
    run.redacted_failure = None
    run.approval_required = True
    run.current_stage_key = None
    harness.project.status = "active"
    await harness.session.commit()
    return run, deployment, configuration, plan


async def _seed_terraform_review(
    harness: DevSecOpsHarness,
    *,
    with_plan_result: bool = True,
    with_apply_approval: bool = False,
) -> tuple[
    models.InfrastructurePlan,
    models.OperationRun | None,
    models.TerraformPlanResult | None,
]:
    plan = models.InfrastructurePlan(
        user_id=harness.owner.id,
        project_id=harness.project.id,
        provider="azure",
        region="eastus",
        status="approved",
        revision=3,
        plan_data={
            "resource_group": "zeroops-test",
            "resources": [
                {
                    "type": "Azure App Service",
                    "name": "api",
                    "properties": {
                        "identity": "SystemAssigned",
                        "registry_access": "AcrPull",
                    },
                }
            ],
        },
    )
    harness.session.add(plan)
    await harness.session.flush()
    if not with_plan_result:
        await harness.session.commit()
        return plan, None, None

    run = models.OperationRun(
        tenant_id=harness.owner_tenant.id,
        project_id=harness.project.id,
        requested_by_user_id=harness.owner.id,
        operation_type="infrastructure_pipeline",
        status="completed",
        input_digest=devsecops.terraform_workflow.approved_plan_digest(plan),
        idempotency_key=f"terraform-review:{plan.id}:{plan.revision}",
    )
    harness.session.add(run)
    await harness.session.flush()

    bundle_sha256 = "2" * 64
    variables_sha256 = "3" * 64
    scope_digest = "4" * 64
    policy_digest = "5" * 64
    plan_sha256 = "6" * 64
    plan_job_digest = "7" * 64
    cost_sha256 = "8" * 64
    result = models.TerraformPlanResult(
        operation_run_id=run.id,
        tenant_id=harness.owner_tenant.id,
        project_id=harness.project.id,
        plan_job_id=uuid.uuid4(),
        plan_job_digest=plan_job_digest,
        revision=plan.revision,
        bundle={
            "uri": (
                "https://artifacts.blob.core.windows.net/"
                f"t-{'a' * 40}/objects/{uuid.uuid4()}/v1/{bundle_sha256}"
            ),
            "etag": '"bundle-etag"',
            "sha256": bundle_sha256,
            "size_bytes": 4096,
        },
        input_variables={
            "file_name": "zeroops.auto.tfvars.json",
            "sha256": variables_sha256,
            "definitions": [
                {"name": "application_name", "type": "string"},
                {"name": "app_service_plan_id", "type": "string"},
                {"name": "container_registry_id", "type": "string"},
                {"name": "location", "type": "string"},
                {"name": "resource_group_name", "type": "string"},
            ],
        },
        guardrails={
            "target_resource_group": "zeroops-test",
            "allowed_resource_types": [
                "azurerm_linux_web_app",
                "azurerm_role_assignment",
            ],
            "maximum_resource_changes": 25,
            "maximum_delete_count": 0,
            "maximum_replace_count": 0,
            "scope_digest": scope_digest,
            "policy_digest": policy_digest,
            "monthly_budget_microunits": 0,
            "budget_currency": "USD",
        },
        saved_plan={
            "blob_name": f"tenants/{harness.owner_tenant.id}/workflows/{run.id}/plans/approved.tfplan",
            "etag": '"plan-etag"',
            "sha256": plan_sha256,
            "plan_job_digest": plan_job_digest,
            "bundle_sha256": bundle_sha256,
            "input_variables_sha256": variables_sha256,
            "scope_digest": scope_digest,
            "policy_digest": policy_digest,
        },
        plan_summary={
            "actions": {
                "create": 2,
                "update": 0,
                "delete": 0,
                "replace": 0,
                "read": 0,
                "no_op": 0,
            },
            "resource_kinds": [
                "azurerm_linux_web_app",
                "azurerm_role_assignment",
            ],
            "changes": [
                {
                    "address": "azurerm_linux_web_app.application",
                    "type": "azurerm_linux_web_app",
                    "actions": ["create"],
                },
                {
                    "address": "azurerm_role_assignment.acr_pull",
                    "type": "azurerm_role_assignment",
                    "actions": ["create"],
                },
            ],
            "terraform_version": "1.15.8",
            "format_version": "1.2",
        },
        cost_estimate={
            "artifact_sha256": cost_sha256,
            "currency": "USD",
            "monthly_cost_microunits": 0,
            "captured_at": datetime.now(timezone.utc).isoformat(),
        },
        planned_at=datetime.now(timezone.utc),
    )
    harness.session.add(result)
    if with_apply_approval:
        approved_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        harness.session.add(
            models.TerraformApplyApproval(
                tenant_id=harness.owner_tenant.id,
                project_id=harness.project.id,
                operation_run_id=run.id,
                approved_by_user_id=harness.owner.id,
                apply_job_id=uuid.uuid4(),
                status="consumed",
                plan_job_digest=plan_job_digest,
                plan_sha256=plan_sha256,
                plan_etag='"plan-etag"',
                bundle_sha256=bundle_sha256,
                input_variables_sha256=variables_sha256,
                scope_digest=scope_digest,
                policy_digest=policy_digest,
                cost_estimate_sha256=cost_sha256,
                currency="USD",
                monthly_cost_microunits=0,
                approved_at=approved_at,
                expires_at=approved_at + timedelta(hours=1),
                consumed_at=approved_at,
            )
        )
    await harness.session.commit()
    return plan, run, result


@pytest.mark.asyncio
async def test_project_terraform_review_reports_not_approved_then_not_queued(
    devsecops_harness,
):
    harness = devsecops_harness
    url = f"/api/projects/{harness.project.id}/terraform-review"

    not_approved = await harness.client.get(url)
    assert not_approved.status_code == 200
    assert not_approved.json() == {
        "status": "not_approved",
        "project_id": str(harness.project.id),
    }

    plan, _run, _result = await _seed_terraform_review(
        harness,
        with_plan_result=False,
    )
    not_queued = await harness.client.get(url)
    assert not_queued.status_code == 200
    assert not_queued.json() == {
        "status": "not_queued",
        "project_id": str(harness.project.id),
        "plan_id": str(plan.id),
        "revision": plan.revision,
    }

    harness.current_user["value"] = harness.outsider
    cross_tenant = await harness.client.get(url)
    assert cross_tenant.status_code == 404


@pytest.mark.asyncio
async def test_project_terraform_review_returns_exact_safe_plan_and_verified_cost(
    devsecops_harness,
):
    harness = devsecops_harness
    _plan, run, result = await _seed_terraform_review(harness)

    response = await harness.client.get(
        f"/api/projects/{harness.project.id}/terraform-review"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready_for_approval"
    assert payload["operation_run_id"] == str(run.id)
    assert payload["revision"] == result.revision
    assert payload["plan_job_digest"] == result.plan_job_digest
    assert payload["plan_sha256"] == result.saved_plan["sha256"]
    assert payload["bundle_sha256"] == result.bundle["sha256"]
    assert payload["input_variables_sha256"] == result.input_variables["sha256"]
    assert payload["scope_digest"] == result.guardrails["scope_digest"]
    assert payload["policy_digest"] == result.guardrails["policy_digest"]
    assert payload["guardrails"] == {
        "target_resource_group": "zeroops-test",
        "allowed_resource_types": [
            "azurerm_linux_web_app",
            "azurerm_role_assignment",
        ],
        "maximum_resource_changes": 25,
        "maximum_delete_count": 0,
        "maximum_replace_count": 0,
        "monthly_budget_microunits": 0,
        "budget_currency": "USD",
    }
    assert payload["plan_summary"] == result.plan_summary
    assert payload["cost_estimate"]["artifact_sha256"] == "8" * 64
    assert payload["cost_estimate"]["currency"] == "USD"
    assert payload["cost_estimate"]["monthly_cost_microunits"] == 0
    assert payload["approval"] is None
    assert "uri" not in json.dumps(payload)
    assert "blob_name" not in json.dumps(payload)


@pytest.mark.asyncio
async def test_project_terraform_review_reports_applied_with_bound_proof(
    devsecops_harness,
    monkeypatch,
):
    harness = devsecops_harness
    _plan, run, _result = await _seed_terraform_review(
        harness,
        with_apply_approval=True,
    )
    proof = StubTerraformApplyProof(run.id)

    async def active_connection(*_args, **_kwargs):
        return object()

    async def completed_apply(*_args, **_kwargs):
        return proof

    monkeypatch.setattr(devsecops, "_active_azure_connection", active_connection)
    monkeypatch.setattr(
        devsecops.terraform_workflow,
        "find_completed_apply_for_plan",
        completed_apply,
    )

    response = await harness.client.get(
        f"/api/projects/{harness.project.id}/terraform-review"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "applied"
    assert payload["operation_run_id"] == str(run.id)
    assert payload["approval"]["approval_id"]
    assert payload["approval"]["apply_job_id"]
    assert payload["approval"]["consumed_at"] is not None
    assert payload["apply_proof"] == proof.deployment_metadata()


@pytest.mark.asyncio
async def test_pipeline_approval_is_owner_scoped_signed_pinned_and_idempotent(
    devsecops_harness,
    monkeypatch,
):
    harness = devsecops_harness
    monkeypatch.setattr(config, "JWT_SECRET", "pipeline-approval-test-secret")
    proof = StubTerraformApplyProof(uuid.UUID("a0000000-0000-0000-0000-000000000002"))

    async def active_connection(*_args, **_kwargs):
        return object()

    async def completed_apply(*_args, **_kwargs):
        return proof

    monkeypatch.setattr(devsecops, "_active_azure_connection", active_connection)
    monkeypatch.setattr(
        devsecops.terraform_workflow,
        "require_completed_apply_for_plan",
        completed_apply,
    )
    run, validation_deployment, configuration, plan = await _seed_approval_ready_run(harness)
    url = f"/api/pipeline-runs/{run.id}/approve"

    harness.current_user["value"] = harness.outsider
    forbidden = await harness.client.post(url)
    assert forbidden.status_code == 404

    harness.current_user["value"] = harness.owner
    approved = await harness.client.post(url)
    assert approved.status_code == 200
    payload = approved.json()
    assert payload["status"] == "approved"
    assert payload["idempotent"] is False
    approved_deployment_id = uuid.UUID(payload["deployment_id"])
    approved_run_id = uuid.UUID(payload["pipeline_run_id"])
    assert approved_deployment_id != validation_deployment.id
    assert approved_run_id != run.id

    approved_deployment = await harness.session.get(models.Deployment, approved_deployment_id)
    approved_run = await harness.session.get(models.PipelineRun, approved_run_id)
    assert approved_deployment is not None
    assert approved_run is not None
    assert approved_deployment.status == "queued"
    assert approved_deployment.terraform_operation_run_id == proof.operation_run_id
    assert approved_deployment.commit_sha == run.source_revision
    assert approved_deployment.branch == run.branch
    assert approved_run.status == "queued"
    assert approved_run.source_revision == run.source_revision
    assert approved_run.target_type == run.target_type
    assert approved_run.configuration_id == configuration.id
    assert approved_run.configuration_version == configuration.version
    assert approved_run.requested_by_user_id == harness.owner.id
    assert approved_deployment.infrastructure_metadata["requested_target"] == run.target_type
    assert "stages" not in approved_deployment.infrastructure_metadata
    assert "internal_iac" not in approved_deployment.infrastructure_metadata

    evidence = approved_deployment.infrastructure_metadata["pipeline_approval"]
    verification = pipeline_approval.verify_pipeline_approval(
        evidence,
        secret="pipeline-approval-test-secret",
        expected={
            "tenant_id": str(harness.owner_tenant.id),
            "project_id": str(harness.project.id),
            "validation_run_id": str(run.id),
            "validation_deployment_id": str(validation_deployment.id),
            "approved_deployment_id": str(approved_deployment.id),
            "approved_pipeline_run_id": str(approved_run.id),
            "source_revision": run.source_revision,
            "branch": run.branch,
            "target_type": run.target_type,
            "plan_id": str(plan.id),
            "plan_revision": plan.revision,
            "configuration_id": str(configuration.id),
            "configuration_version": configuration.version,
            "configuration_digest": configuration.config_digest,
            "approved_by_user_id": str(harness.owner.id),
        },
    )
    assert verification.valid is True
    assert evidence["signature"] not in json.dumps(
        approved_deployment.infrastructure_metadata.get("pipeline_approval_decision")
    )
    approved_job = (
        await harness.session.execute(
            select(models.DeploymentJob).where(
            models.DeploymentJob.deployment_id == approved_deployment.id,
            models.DeploymentJob.status == "queued",
        )
        )
    ).scalars().one()
    assert approved_job.region == plan.region
    assert approved_job.infrastructure_spec == plan.plan_data
    approved_stages = (
        await harness.session.execute(
            select(models.PipelineStageAttempt).where(
                models.PipelineStageAttempt.pipeline_run_id == approved_run.id
            )
        )
    ).scalars().all()
    assert next(stage for stage in approved_stages if stage.stage_key == "source").status == "queued"
    assert next(stage for stage in approved_stages if stage.stage_key == "approval").status == "queued"

    await harness.session.refresh(validation_deployment)
    decision = validation_deployment.infrastructure_metadata["pipeline_approval_decision"]
    assert decision["status"] == "approved"
    assert decision["consumed"] is True
    assert decision["approved_deployment_id"] == str(approved_deployment.id)
    approval_event = (
        await harness.session.execute(
            select(models.ActivityEvent).where(
                models.ActivityEvent.project_id == harness.project.id,
                models.ActivityEvent.action == "Pipeline deployment approved",
            )
        )
    ).scalars().one()
    assert approval_event.user_id == harness.owner.id
    assert approval_event.event_data["approved_pipeline_run_id"] == str(approved_run.id)
    assert "signature" not in json.dumps(approval_event.event_data)
    approval_notification = (
        await harness.session.execute(
            select(models.Notification).where(
                models.Notification.user_id == harness.owner.id,
                models.Notification.title == "Deployment Approved",
            )
        )
    ).scalars().one()
    assert approval_notification.category == "deployment"

    repeated = await harness.client.post(url)
    assert repeated.status_code == 200
    assert repeated.json()["idempotent"] is True
    assert repeated.json()["deployment_id"] == str(approved_deployment.id)
    assert repeated.json()["pipeline_run_id"] == str(approved_run.id)
    all_approved_jobs = await harness.session.scalar(
        select(func.count(models.DeploymentJob.id)).where(
            models.DeploymentJob.deployment_id == approved_deployment.id
        )
    )
    assert all_approved_jobs == 1

    conflicting_reject = await harness.client.post(f"/api/pipeline-runs/{run.id}/reject")
    assert conflicting_reject.status_code == 409


@pytest.mark.asyncio
async def test_pipeline_approval_rejects_plan_or_configuration_drift(
    devsecops_harness,
):
    harness = devsecops_harness
    run, _deployment, _configuration, plan = await _seed_approval_ready_run(harness)
    plan.revision += 1
    await harness.session.commit()

    stale_plan = await harness.client.post(f"/api/pipeline-runs/{run.id}/approve")
    assert stale_plan.status_code == 409
    assert "plan changed" in stale_plan.json()["detail"]
    approved_run_count = await harness.session.scalar(
        select(func.count(models.PipelineRun.id)).where(
            models.PipelineRun.idempotency_key == f"approval:{run.id}"
        )
    )
    assert approved_run_count == 0

    plan.revision -= 1
    drifted_configuration = models.ProjectPipelineConfiguration(
        tenant_id=harness.owner_tenant.id,
        project_id=harness.project.id,
        created_by_user_id=harness.owner.id,
        updated_by_user_id=harness.owner.id,
        version=2,
        enabled=True,
        trigger_mode="manual_and_push",
        tracked_branch="main",
        auto_deploy=True,
        deployment_mode="require_approval",
        config_digest="9" * 64,
    )
    harness.session.add(drifted_configuration)
    await harness.session.commit()
    stale_configuration = await harness.client.post(f"/api/pipeline-runs/{run.id}/approve")
    assert stale_configuration.status_code == 409
    assert "configuration changed" in stale_configuration.json()["detail"]


@pytest.mark.asyncio
async def test_pipeline_approval_requires_every_required_predecessor_to_pass(
    devsecops_harness,
):
    harness = devsecops_harness
    run, _deployment, _configuration, _plan = await _seed_approval_ready_run(harness)
    stages = (
        await harness.session.execute(
            select(models.PipelineStageAttempt)
            .where(models.PipelineStageAttempt.pipeline_run_id == run.id)
            .order_by(models.PipelineStageAttempt.stage_order)
        )
    ).scalars().all()
    approval_stage = next(stage for stage in stages if stage.stage_key == "approval")
    predecessor = next(
        stage
        for stage in stages
        if stage.is_required and stage.stage_order < approval_stage.stage_order
    )
    predecessor.status = "failed"
    predecessor.status_reason = "A required validation check did not pass."
    predecessor.failure_code = "VALIDATION_FAILED"
    await harness.session.commit()

    blocked = await harness.client.post(f"/api/pipeline-runs/{run.id}/approve")
    assert blocked.status_code == 409
    assert "Every required validation stage" in blocked.json()["detail"]
    assert await harness.session.scalar(
        select(func.count(models.PipelineRun.id)).where(
            models.PipelineRun.idempotency_key == f"approval:{run.id}"
        )
    ) == 0


@pytest.mark.asyncio
async def test_pipeline_rejection_cancels_gate_and_cannot_be_repeated(
    devsecops_harness,
):
    harness = devsecops_harness
    run, deployment, _configuration, _plan = await _seed_approval_ready_run(harness)
    url = f"/api/pipeline-runs/{run.id}/reject"

    stages_before = (
        await harness.session.execute(
            select(models.PipelineStageAttempt)
            .where(models.PipelineStageAttempt.pipeline_run_id == run.id)
            .order_by(models.PipelineStageAttempt.stage_order)
        )
    ).scalars().all()
    approval_before = next(stage for stage in stages_before if stage.stage_key == "approval")
    later_stage = next(stage for stage in stages_before if stage.stage_order > approval_before.stage_order)
    later_stage.status = "queued"
    later_stage.status_reason = None
    later_stage.failure_code = None
    later_stage.completed_at = None
    await harness.session.commit()

    rejected = await harness.client.post(url)
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    await harness.session.refresh(run)
    await harness.session.refresh(deployment)
    assert run.status == "cancelled"
    assert run.failure_code == "DEPLOYMENT_APPROVAL_REJECTED"
    assert deployment.status == "stopped"
    assert deployment.failure_reason is None
    assert deployment.infrastructure_metadata["pipeline_approval_decision"]["status"] == "rejected"
    stages = (
        await harness.session.execute(
            select(models.PipelineStageAttempt).where(
                models.PipelineStageAttempt.pipeline_run_id == run.id
            )
        )
    ).scalars().all()
    approval_stage = next(stage for stage in stages if stage.stage_key == "approval")
    assert approval_stage.status == "cancelled"
    assert next(stage for stage in stages if stage.id == later_stage.id).status == "cancelled"
    rejection_event = (
        await harness.session.execute(
            select(models.ActivityEvent).where(
                models.ActivityEvent.project_id == harness.project.id,
                models.ActivityEvent.action == "Pipeline deployment rejected",
            )
        )
    ).scalars().one()
    assert rejection_event.user_id == harness.owner.id
    assert rejection_event.event_data["validation_pipeline_run_id"] == str(run.id)
    rejection_notification = (
        await harness.session.execute(
            select(models.Notification).where(
                models.Notification.user_id == harness.owner.id,
                models.Notification.title == "Deployment Rejected",
            )
        )
    ).scalars().one()
    assert rejection_notification.type == "warning"

    assert (await harness.client.post(url)).status_code == 409
    assert (await harness.client.post(f"/api/pipeline-runs/{run.id}/approve")).status_code == 409


def test_pipeline_approval_signature_is_strict_and_tamper_evident():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    claims = {
        "schema": pipeline_approval.APPROVAL_SCHEMA,
        "tenant_id": str(uuid.uuid4()),
        "project_id": str(uuid.uuid4()),
        "validation_run_id": str(uuid.uuid4()),
        "validation_deployment_id": str(uuid.uuid4()),
        "approved_deployment_id": str(uuid.uuid4()),
        "approved_pipeline_run_id": str(uuid.uuid4()),
        "source_revision": "a" * 40,
        "branch": "main",
        "target_type": "azure-app-service",
        "plan_id": str(uuid.uuid4()),
        "plan_revision": 1,
        "configuration_id": str(uuid.uuid4()),
        "configuration_version": 1,
        "configuration_digest": "b" * 64,
        "approved_by_user_id": str(uuid.uuid4()),
        "approved_at": now.isoformat().replace("+00:00", "Z"),
    }
    evidence = pipeline_approval.sign_pipeline_approval(claims, secret="approval-secret")
    assert pipeline_approval.verify_pipeline_approval(
        evidence,
        secret="approval-secret",
        expected={"source_revision": "a" * 40},
        now=now,
    ).valid

    tampered = {**evidence, "source_revision": "c" * 40}
    rejected = pipeline_approval.verify_pipeline_approval(
        tampered,
        secret="approval-secret",
        now=now,
    )
    assert rejected.valid is False
    assert rejected.reason == "Pipeline approval signature is invalid."
    expanded = {**evidence, "unexpected": "field"}
    assert not pipeline_approval.verify_pipeline_approval(
        expanded,
        secret="approval-secret",
        now=now,
    ).valid

    # A consumed approval is pinned to unique new deployment/run identifiers;
    # it must survive a durable queue outage instead of expiring while idle.
    old_claims = {
        **claims,
        "approved_at": (now - timedelta(days=2)).isoformat().replace("+00:00", "Z"),
    }
    old_evidence = pipeline_approval.sign_pipeline_approval(
        old_claims,
        secret="approval-secret",
    )
    assert pipeline_approval.verify_pipeline_approval(
        old_evidence,
        secret="approval-secret",
        now=now,
    ).valid

    future_claims = {
        **claims,
        "approved_at": (now + timedelta(minutes=6)).isoformat().replace("+00:00", "Z"),
    }
    future_evidence = pipeline_approval.sign_pipeline_approval(
        future_claims,
        secret="approval-secret",
    )
    assert not pipeline_approval.verify_pipeline_approval(
        future_evidence,
        secret="approval-secret",
        now=now,
    ).valid


@pytest.mark.asyncio
async def test_remediation_is_owner_scoped_and_high_risk_execution_requires_approval(
    devsecops_harness,
):
    harness = devsecops_harness
    parameters = {"action": "terraform_apply", "plan_digest": "c" * 64}
    proposal = models.RemediationProposal(
        tenant_id=harness.owner_tenant.id,
        project_id=harness.project.id,
        deployment_id=harness.deployment.id,
        idempotency_key="proposal-owner-authorization",
        action_type="terraform_apply",
        title="Apply an infrastructure change",
        description="Apply a previously reviewed infrastructure change.",
        risk_tier="high",
        status="pending_approval",
        approval_required=True,
        parameter_digest=hashlib.sha256(
            json.dumps(parameters, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        redacted_parameters=parameters,
        rationale="Infrastructure mutation always requires explicit owner approval.",
    )
    harness.session.add(proposal)
    await harness.session.commit()
    url = f"/api/remediation-proposals/{proposal.id}"

    harness.current_user["value"] = harness.outsider
    cross_tenant = await harness.client.post(f"{url}/approve")
    assert cross_tenant.status_code == 404

    harness.current_user["value"] = harness.owner
    blocked = await harness.client.post(f"{url}/execute")
    assert blocked.status_code == 409
    execution_count = await harness.session.scalar(
        select(func.count(models.RemediationExecution.id)).where(
            models.RemediationExecution.proposal_id == proposal.id
        )
    )
    assert execution_count == 0

    approved = await harness.client.post(f"{url}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    await harness.session.refresh(proposal)
    assert proposal.decided_by_user_id == harness.owner.id
    assert proposal.decided_at is not None

    executed = await harness.client.post(f"{url}/execute")
    assert executed.status_code == 200
    assert executed.json()["status"] == "unavailable"
    assert executed.json()["error"] == (
        "No deterministic executor is registered for this remediation action."
    )
    execution_result = await harness.session.execute(
        select(models.RemediationExecution).where(
            models.RemediationExecution.proposal_id == proposal.id
        )
    )
    execution = execution_result.scalar_one()
    assert execution.requested_by_user_id == harness.owner.id
    assert execution.status == "unavailable"
    assert execution.verification_status == "unavailable"
    assert proposal.status == "approved"


@pytest.mark.asyncio
async def test_health_remediation_reuses_provider_bound_app_service_identity(
    devsecops_harness,
    monkeypatch,
):
    harness = devsecops_harness
    app_name = "zeroops-api-release"
    harness.deployment.live_url = f"https://{app_name}.azurewebsites.net"
    harness.deployment.infrastructure_metadata = {
        "target_provider": "azure-app-service",
        "release": {"application_name": app_name},
    }
    proposal = models.RemediationProposal(
        tenant_id=harness.owner_tenant.id,
        project_id=harness.project.id,
        deployment_id=harness.deployment.id,
        idempotency_key="safe-health-recheck",
        action_type="rerun_health_check",
        title="Rerun application health check",
        description="Repeat the provider-bound endpoint verification.",
        risk_tier="low",
        status="proposed",
        approval_required=False,
        parameter_digest="e" * 64,
        redacted_parameters={"deployment_id": str(harness.deployment.id)},
        rationale="This check is non-mutating.",
    )
    harness.session.add(proposal)
    await harness.session.commit()
    observed = {}

    def verify(live_url, *, expected_app_name, attempts, delay_seconds):
        observed.update(
            live_url=live_url,
            expected_app_name=expected_app_name,
            attempts=attempts,
            delay_seconds=delay_seconds,
        )

    monkeypatch.setattr(devsecops.app_service, "verify_public_endpoint", verify)

    response = await harness.client.post(
        f"/api/remediation-proposals/{proposal.id}/execute"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    assert observed == {
        "live_url": harness.deployment.live_url,
        "expected_app_name": app_name,
        "attempts": 1,
        "delay_seconds": 0,
    }


@pytest.mark.asyncio
async def test_project_terraform_review_supports_slash_path(devsecops_harness):
    harness = devsecops_harness
    _plan, run, result = await _seed_terraform_review(harness)

    # Test the slash path matching frontend api.ts
    response = await harness.client.get(
        f"/api/projects/{harness.project.id}/terraform/review"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready_for_approval"
    assert payload["operation_run_id"] == str(run.id)
    assert payload["revision"] == result.revision


@pytest.mark.asyncio
async def test_project_terraform_review_reports_failed_generation(devsecops_harness):
    harness = devsecops_harness
    plan = models.InfrastructurePlan(
        user_id=harness.owner.id,
        project_id=harness.project.id,
        provider="azure",
        region="eastus",
        status="approved",
        revision=1,
        plan_data={"terraform_status": "failed", "terraform_error": "aiohttp package is not installed"},
    )
    harness.session.add(plan)
    await harness.session.commit()

    response = await harness.client.get(
        f"/api/projects/{harness.project.id}/terraform/review"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["error_code"] == "TERRAFORM_GENERATION_FAILED"
    assert "aiohttp" in payload["message"]

