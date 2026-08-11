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
from backend.services import pipeline_approval
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
    monkeypatch.setattr(devsecops.vault, "get_project_secret", lambda *_: secret)
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
            models.UserAzureConnection(
                user_id=harness.owner.id,
                tenant_id="entra-tenant",
                subscription_id="azure-subscription",
                client_id="service-principal-client",
                connection_status="connected",
                region="eastus",
                resource_group="zeroops-test",
                acr_login_server="zeroopstest.azurecr.io",
                app_service_plan="zeroops-linux-plan",
                is_active=True,
            ),
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
    assert deployment.infrastructure_metadata["requested_target"] == "auto"
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


@pytest.mark.asyncio
async def test_pipeline_approval_is_owner_scoped_signed_pinned_and_idempotent(
    devsecops_harness,
    monkeypatch,
):
    harness = devsecops_harness
    monkeypatch.setattr(config, "JWT_SECRET", "pipeline-approval-test-secret")
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
