import json
import uuid

import httpx
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateTable

from backend import auth, models
from backend.database import get_db
from backend.main import app
from backend.routes import history as history_routes
from backend.services import history as history_service
from backend.services.artifacts import LocalFilesystemArtifactStore, persist_user_artifact
from backend.services.tenancy import ensure_personal_tenant


@pytest_asyncio.fixture
async def tenant_db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(models.Base.metadata.create_all)

    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        first = models.User(id=uuid.uuid4(), email="first@example.test", first_name="First")
        second = models.User(id=uuid.uuid4(), email="second@example.test", first_name="Second")
        session.add_all([first, second])
        await session.flush()
        first_tenant = await ensure_personal_tenant(session, first)
        second_tenant = await ensure_personal_tenant(session, second)
        await session.commit()
        yield session, first, second, first_tenant, second_tenant

    async with engine.begin() as connection:
        await connection.run_sync(models.Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_personal_tenant_is_not_customer_entra_tenant(tenant_db):
    session, user, _, tenant, _ = tenant_db
    connection = models.UserAzureConnection(
        user_id=user.id,
        tenant_id="customer-entra-directory-id",
        subscription_id="subscription-id",
    )
    session.add(connection)
    await session.commit()

    assert tenant.id == user.id
    assert str(tenant.id) != connection.tenant_id


@pytest.mark.asyncio
async def test_history_service_isolates_tenants_and_redacts_persisted_fields(tenant_db):
    session, first, second, first_tenant, second_tenant = tenant_db
    first_run = await history_service.create_operation_run(
        session,
        tenant_id=first_tenant.id,
        requested_by_user_id=first.id,
        operation_type="repository_analysis",
        input_digest="a" * 64,
        idempotency_key="commit-a",
        summary={
            "framework": "FastAPI",
            "database_url": "postgresql://user:password@db/app",
            "diagnostic_endpoint": "postgresql://other:secret@db/app",
        },
    )
    second_run = await history_service.create_operation_run(
        session,
        tenant_id=second_tenant.id,
        requested_by_user_id=second.id,
        operation_type="terraform_generation",
        input_digest="b" * 64,
        summary={"region": "centralindia"},
    )
    event = await history_service.append_activity_event(
        session,
        tenant_id=first_tenant.id,
        operation_run_id=first_run.id,
        actor_user_id=first.id,
        action="analysis_completed",
        details="Authorization: Bearer secret-token",
        event_data={"api_key": "secret", "finding_count": 3},
        external_event_id="workflow-message-001",
    )
    duplicate_event = await history_service.append_activity_event(
        session,
        tenant_id=first_tenant.id,
        operation_run_id=first_run.id,
        actor_user_id=first.id,
        action="analysis_completed",
        details="Authorization: Bearer secret-token",
        event_data={"api_key": "secret", "finding_count": 3},
        external_event_id="workflow-message-001",
    )
    with pytest.raises(ValueError, match="different event content"):
        await history_service.append_activity_event(
            session,
            tenant_id=first_tenant.id,
            operation_run_id=first_run.id,
            actor_user_id=first.id,
            action="analysis_completed",
            event_data={"finding_count": 999},
            external_event_id="workflow-message-001",
        )
    await session.commit()

    page = await history_service.list_operation_runs(
        session,
        tenant_id=first_tenant.id,
        page=1,
        per_page=25,
    )
    assert page.total == 1
    assert page.items[0][0].id == first_run.id
    assert page.items[0][0].summary["database_url"] == "<REDACTED>"
    assert "other:secret" not in page.items[0][0].summary["diagnostic_endpoint"]
    assert event.event_data == {"api_key": "<REDACTED>", "finding_count": 3}
    assert "secret-token" not in event.details
    assert duplicate_event.id == event.id
    assert event.actor_id == str(first.id)
    assert len(event.event_fingerprint) == 64

    events = await history_service.list_operation_events(
        session,
        tenant_id=first_tenant.id,
        operation_run_id=first_run.id,
    )
    assert [item.external_event_id for item in events] == ["workflow-message-001"]

    with pytest.raises(Exception) as error:
        await history_service.require_operation_run(
            session,
            tenant_id=first_tenant.id,
            operation_run_id=second_run.id,
        )
    assert getattr(error.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_operation_idempotency_key_rejects_changed_immutable_request(tenant_db):
    session, user, _, tenant, _ = tenant_db
    first = await history_service.create_operation_run(
        session,
        tenant_id=tenant.id,
        requested_by_user_id=user.id,
        operation_type="repository_analysis",
        source_revision="abc1234",
        input_digest="a" * 64,
        idempotency_key="repository:abc1234",
    )
    replay = await history_service.create_operation_run(
        session,
        tenant_id=tenant.id,
        requested_by_user_id=user.id,
        operation_type="repository_analysis",
        source_revision="abc1234",
        input_digest="a" * 64,
        idempotency_key="repository:abc1234",
        summary={"safe_retry_metadata": True},
    )
    assert replay.id == first.id

    with pytest.raises(ValueError, match="different operation request"):
        await history_service.create_operation_run(
            session,
            tenant_id=tenant.id,
            requested_by_user_id=user.id,
            operation_type="repository_analysis",
            source_revision="different",
            input_digest="b" * 64,
            idempotency_key="repository:abc1234",
        )


@pytest.mark.asyncio
async def test_inactive_personal_tenant_is_not_resolved(tenant_db):
    session, user, _, tenant, _ = tenant_db
    tenant.status = "suspended"
    await session.flush()

    with pytest.raises(HTTPException) as error:
        await ensure_personal_tenant(session, user)
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_history_api_paginates_and_blocks_cross_tenant_detail(
    tenant_db,
    tmp_path,
):
    session, first, second, first_tenant, second_tenant = tenant_db
    first_run = await history_service.create_operation_run(
        session,
        tenant_id=first_tenant.id,
        requested_by_user_id=first.id,
        operation_type="repository_analysis",
        input_digest="c" * 64,
        summary={"result": "ready"},
    )
    second_run = await history_service.create_operation_run(
        session,
        tenant_id=second_tenant.id,
        requested_by_user_id=second.id,
        operation_type="terraform_generation",
        input_digest="d" * 64,
    )
    store = LocalFilesystemArtifactStore(root=tmp_path)
    artifact = await persist_user_artifact(
        session,
        store=store,
        tenant_id=first_tenant.id,
        operation_run_id=first_run.id,
        created_by_user_id=first.id,
        kind="repository_analysis",
        display_name="../analysis.json",
        content_type="application/json",
        data=json.dumps(
            {
                "framework": "FastAPI",
                "client_secret": "must-not-be-stored",
            }
        ).encode(),
    )
    await session.commit()

    selected_user = {"value": first}

    async def override_db():
        yield session

    async def override_current_user():
        return selected_user["value"]

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[auth.get_current_user] = override_current_user
    app.dependency_overrides[history_routes.artifact_store_dependency] = lambda: store
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/history", params={"page": 1, "per_page": 1})
            assert response.status_code == 200
            body = response.json()
            assert body["total"] == 1
            assert body["items"][0]["id"] == str(first_run.id)
            assert body["items"][0]["artifact_count"] == 1

            cross_tenant = await client.get(f"/api/history/{second_run.id}")
            assert cross_tenant.status_code == 404

            download = await client.get(
                f"/api/history/{first_run.id}/artifacts/{artifact.id}/download"
            )
            assert download.status_code == 200
            downloaded = download.json()
            assert downloaded["framework"] == "FastAPI"
            assert downloaded["client_secret"] == "<REDACTED>"
            assert "must-not-be-stored" not in download.text
            assert download.headers["x-artifact-sha256"] == artifact.sha256_digest

            selected_user["value"] = second
            guessed_artifact = await client.get(
                f"/api/history/{first_run.id}/artifacts/{artifact.id}/download"
            )
            assert guessed_artifact.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_artifact_paths_are_opaque_immutable_and_integrity_checked(tenant_db, tmp_path):
    session, first, second, first_tenant, second_tenant = tenant_db
    first_run = await history_service.create_operation_run(
        session,
        tenant_id=first_tenant.id,
        requested_by_user_id=first.id,
        operation_type="cost_analysis",
    )
    second_run = await history_service.create_operation_run(
        session,
        tenant_id=second_tenant.id,
        requested_by_user_id=second.id,
        operation_type="cost_analysis",
    )
    store = LocalFilesystemArtifactStore(root=tmp_path)
    first_artifact = await persist_user_artifact(
        session,
        store=store,
        tenant_id=first_tenant.id,
        operation_run_id=first_run.id,
        created_by_user_id=first.id,
        kind="cost_estimate",
        display_name="estimate.json",
        content_type="application/json",
        data=b'{"monthly_usd": 12.50}',
    )
    second_artifact = await persist_user_artifact(
        session,
        store=store,
        tenant_id=second_tenant.id,
        operation_run_id=second_run.id,
        created_by_user_id=second.id,
        kind="cost_estimate",
        display_name="estimate.json",
        content_type="application/json",
        data=b'{"monthly_usd": 18.00}',
    )
    await session.commit()

    assert first_artifact.storage_container != second_artifact.storage_container
    assert str(first_tenant.id) not in first_artifact.storage_container
    assert "estimate.json" not in first_artifact.storage_path
    assert first_artifact.sha256_digest in first_artifact.storage_path

    # Mutate the file through the adapter's validated locator to exercise the
    # download-time digest boundary.
    from backend.services.artifacts import ArtifactIntegrityError, ArtifactLocation

    actual_path = store._file_path(  # noqa: SLF001 - intentional test-double inspection
        ArtifactLocation(
            container=first_artifact.storage_container,
            path=first_artifact.storage_path,
        )
    )
    actual_path.write_bytes(b"tampered")
    with pytest.raises(ArtifactIntegrityError):
        await store.read_verified(
            tenant_id=first_tenant.id,
            location=ArtifactLocation(
                container=first_artifact.storage_container,
                path=first_artifact.storage_path,
            ),
            expected_digest=first_artifact.sha256_digest,
            expected_size=first_artifact.size_bytes,
        )


def test_postgresql_history_ddl_uses_jsonb_checks_and_durable_event_ownership():
    dialect = postgresql.dialect()
    operation_ddl = str(
        CreateTable(models.OperationRun.__table__).compile(dialect=dialect)
    )
    artifact_ddl = str(CreateTable(models.Artifact.__table__).compile(dialect=dialect))
    event_ddl = str(
        CreateTable(models.ActivityEvent.__table__).compile(dialect=dialect)
    )

    assert "summary JSONB NOT NULL" in operation_ddl
    assert "ck_operation_runs_input_digest" in operation_ddl
    assert "metadata JSONB NOT NULL" in artifact_ddl
    assert "ck_artifacts_sha256" in artifact_ddl
    assert "ck_artifacts_size" in artifact_ddl
    assert "ck_artifacts_version" in artifact_ddl
    assert "event_data JSONB NOT NULL" in event_ddl
    assert "actor_id VARCHAR(128)" in event_ddl
    assert "event_fingerprint VARCHAR(64)" in event_ddl
    assert "ck_activity_events_fingerprint" in event_ddl
    assert "FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL" in event_ddl
