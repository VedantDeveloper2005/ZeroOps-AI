from __future__ import annotations

import json
from pathlib import Path
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import config, models
from backend.contracts.workflow import (
    BundleReferenceV1,
    TerraformGenerationJobV1,
    TerraformInputVariableV1,
    VerifiedCostEstimateV1,
)
from backend.services import history, repository_workflow, terraform_workflow
from backend.services.artifacts import LocalFilesystemArtifactStore, read_user_artifact
from backend.services.tenancy import ensure_personal_tenant


@pytest_asyncio.fixture
async def workflow_db(tmp_path: Path):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(models.Base.metadata.create_all)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        user = models.User(id=uuid.uuid4(), email="workflow@example.test")
        session.add(user)
        await session.flush()
        tenant = await ensure_personal_tenant(session, user)
        project = models.Project(
            id=uuid.uuid4(),
            user_id=user.id,
            name="api",
            full_name="zeroops/api",
            branch="main",
        )
        session.add(project)
        await session.commit()
        store = LocalFilesystemArtifactStore(
            root=tmp_path / "artifacts",
            namespace_key="workflow-test-namespace-key-at-least-32-bytes",
        )
        yield session, user, tenant, project, store
    await engine.dispose()


def test_backend_generation_contract_matches_consumer_limits():
    approved_artifact_id = str(uuid.uuid4())
    with pytest.raises(ValueError, match="less than or equal to 500"):
        TerraformGenerationJobV1.model_validate(
            {
                "schema_version": "terraform-generation-job.v1",
                "job_id": str(uuid.uuid4()),
                "tenant_id": str(uuid.uuid4()),
                "project_id": str(uuid.uuid4()),
                "run_id": str(uuid.uuid4()),
                "correlation_id": str(uuid.uuid4()),
                "user_id": str(uuid.uuid4()),
                "approved_plan_artifact": {
                    "schema_version": "artifact-reference.v1",
                    "artifact_id": approved_artifact_id,
                    "account_url": "https://artifacts.blob.core.windows.net",
                    "container": "t-" + "a" * 40,
                    "blob_name": f"objects/{approved_artifact_id}/v1/" + "a" * 64,
                    "sha256": "a" * 64,
                    "size_bytes": 1,
                    "media_type": "application/json",
                    "classification": "tenant-plan-sanitized",
                },
                "output_artifact_id": str(uuid.uuid4()),
                "output_container": "t-" + "a" * 40,
                "approved_plan_id": str(uuid.uuid4()),
                "approved_plan_revision": 1,
                "approved_plan_digest": "b" * 64,
                "target_environment": "production",
                "target_subscription_id": str(uuid.uuid4()),
                "target_tenant_id": str(uuid.uuid4()),
                "target_resource_group": "rg-zeroops",
                "terraform_version": "1.15.8",
                "input_variables": [],
                "maximum_resource_changes": 501,
                "maximum_delete_count": 0,
                "maximum_replace_count": 0,
            }
        )

    with pytest.raises(ValueError, match="unsafe"):
        TerraformInputVariableV1(
            name="database_connection_string",
            type="string",
            value="not-even-a-secret",
        )


def test_bundle_reference_rejects_credentials_and_unbound_paths():
    with pytest.raises(ValueError):
        BundleReferenceV1(
            uri="https://user:password@artifacts.blob.core.windows.net/t-"
            + "a" * 40
            + "/objects/"
            + str(uuid.uuid4())
            + "/v1/"
            + "b" * 64,
            etag='"etag"',
            sha256="b" * 64,
            size_bytes=100,
        )


@pytest.mark.asyncio
async def test_repository_analysis_producer_is_immutable_and_idempotent(
    workflow_db,
    tmp_path: Path,
    monkeypatch,
):
    session, user, tenant, project, store = workflow_db
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "app.py").write_text("print('real source')\n", encoding="utf-8")
    (repository / ".env").write_text("DATABASE_PASSWORD=do-not-persist\n", encoding="utf-8")
    monkeypatch.setattr(
        config,
        "ARTIFACT_STORAGE_ACCOUNT_URL",
        "https://artifacts.blob.core.windows.net",
    )
    raw_analysis = {
        "framework": "FastAPI",
        "language": "Python",
        "runtime": "Python 3.13",
        "package_manager": "pip",
        "docker_support": True,
        "port": 8000,
        "dependencies": ["fastapi"],
        "database_dependencies": ["postgresql"],
        "environment_variables": ["DATABASE_PASSWORD"],
    }

    queued = await repository_workflow.enqueue_repository_analysis(
        session,
        store=store,
        tenant=tenant,
        user=user,
        project=project,
        repo_path=str(repository),
        commit_sha="a" * 40,
        raw_analysis=raw_analysis,
    )
    await session.commit()
    replay = await repository_workflow.enqueue_repository_analysis(
        session,
        store=store,
        tenant=tenant,
        user=user,
        project=project,
        repo_path=str(repository),
        commit_sha="a" * 40,
        raw_analysis=raw_analysis,
    )

    assert queued.idempotent is False
    assert replay.idempotent is True
    assert replay.operation_run_id == queued.operation_run_id
    outbox = await session.get(models.WorkflowOutboxMessage, queued.outbox_message_id)
    assert outbox is not None
    assert outbox.queue_name == "repo-analysis"
    assert outbox.payload["source_commit"] == "a" * 40
    assert "do-not-persist" not in json.dumps(outbox.payload)
    source_artifact = await session.get(models.Artifact, queued.source_artifact_id)
    assert source_artifact is not None
    source_bytes = await read_user_artifact(store, source_artifact)
    assert b"do-not-persist" not in source_bytes
    assert b"DATABASE_PASSWORD" in source_bytes


@pytest.mark.asyncio
async def test_zero_incremental_cost_evidence_binds_exact_saved_plan(workflow_db):
    session, user, tenant, project, store = workflow_db
    run = await history.create_operation_run(
        session,
        tenant_id=tenant.id,
        requested_by_user_id=user.id,
        operation_type="infrastructure_pipeline",
        project_id=project.id,
        input_digest="1" * 64,
        idempotency_key="terraform-cost-test",
    )
    artifact_id = uuid.uuid4()
    bundle_digest = "2" * 64
    variables_digest = "3" * 64
    scope_digest = "4" * 64
    policy_digest = "5" * 64
    plan_digest = "6" * 64
    plan_job_digest = "7" * 64
    session.add(
        models.TerraformPlanResult(
            operation_run_id=run.id,
            tenant_id=tenant.id,
            project_id=project.id,
            plan_job_id=uuid.uuid4(),
            plan_job_digest=plan_job_digest,
            revision=1,
            bundle={
                "uri": (
                    "https://artifacts.blob.core.windows.net/"
                    + store.container_for_tenant(tenant.id)
                    + f"/objects/{artifact_id}/v1/{bundle_digest}"
                ),
                "etag": '"bundle-etag"',
                "sha256": bundle_digest,
                "size_bytes": 1_024,
            },
            input_variables={
                "file_name": "zeroops.auto.tfvars.json",
                "sha256": variables_digest,
                "definitions": [
                    {"name": "application_name", "type": "string"},
                    {"name": "resource_group_name", "type": "string"},
                ],
            },
            guardrails={
                "target_resource_group": "rg-customer",
                "allowed_resource_types": ["azurerm_linux_web_app"],
                "maximum_resource_changes": 25,
                "maximum_delete_count": 0,
                "maximum_replace_count": 0,
                "scope_digest": scope_digest,
                "policy_digest": policy_digest,
                "monthly_budget_microunits": None,
                "budget_currency": None,
            },
            saved_plan={
                "blob_name": f"tenants/{tenant.id}/workflows/{run.id}/plans/approved.tfplan",
                "etag": '"plan-etag"',
                "sha256": plan_digest,
                "plan_job_digest": plan_job_digest,
                "bundle_sha256": bundle_digest,
                "input_variables_sha256": variables_digest,
                "scope_digest": scope_digest,
                "policy_digest": policy_digest,
            },
            plan_summary={
                "actions": {
                    "create": 1,
                    "update": 0,
                    "delete": 0,
                    "replace": 0,
                    "read": 0,
                    "no_op": 0,
                },
                    "resource_kinds": ["azurerm_linux_web_app"],
                    "changes": [
                        {
                            "address": "azurerm_linux_web_app.application",
                            "type": "azurerm_linux_web_app",
                            "actions": ["create"],
                        }
                    ],
                "terraform_version": "1.15.8",
                "format_version": "1.2",
            },
            planned_at=models.utc_now(),
        )
    )
    await session.flush()

    issued = await terraform_workflow.issue_verified_cost_evidence(
        session,
        store=store,
        user=user,
        project=project,
        tenant=tenant,
        operation_run_id=run.id,
    )
    await session.commit()
    replay = await terraform_workflow.issue_verified_cost_evidence(
        session,
        store=store,
        user=user,
        project=project,
        tenant=tenant,
        operation_run_id=run.id,
    )

    assert issued.idempotent is False
    assert replay.idempotent is True
    assert issued.monthly_cost_microunits == 0
    plan_result = await session.get(models.TerraformPlanResult, run.id)
    cost = VerifiedCostEstimateV1.model_validate(plan_result.cost_estimate)
    assert cost.artifact_sha256 == issued.artifact_sha256
    artifact = await session.get(models.Artifact, issued.artifact_id)
    evidence = json.loads((await read_user_artifact(store, artifact)).decode("utf-8"))
    assert evidence["plan_sha256"] == plan_digest
    assert evidence["bundle_sha256"] == bundle_digest
    assert evidence["monthly_cost_microunits"] == 0
