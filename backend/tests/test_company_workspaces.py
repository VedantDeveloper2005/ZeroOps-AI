from __future__ import annotations

import uuid
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from backend import auth, models
from backend.database import get_db
from backend.routes import workspaces
from backend.services.tenancy import ensure_personal_tenant, project_tenant_filter


@pytest_asyncio.fixture
async def workspace_harness(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)

    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        owner = models.User(
            id=uuid.uuid4(), email="owner@company.test", email_verified=True,
            mfa_enabled=True, first_name="Morgan", last_name="Owner",
        )
        outsider = models.User(
            id=uuid.uuid4(), email="outside@company.test", email_verified=True,
            mfa_enabled=True,
        )
        db.add_all([owner, outsider])
        await db.flush()
        await ensure_personal_tenant(db, owner)
        await ensure_personal_tenant(db, outsider)
        await db.commit()

        selected_user = {"value": owner}
        async def override_db():
            yield db

        async def override_user():
            return selected_user["value"]

        app = FastAPI()
        app.include_router(workspaces.router)
        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[auth.get_current_user] = override_user
        sent: dict[str, object] = {}

        def deliver(to_email: str, **kwargs):
            sent["email"] = to_email
            sent.update(kwargs)
            return True

        monkeypatch.setattr(workspaces.email_service, "send_workspace_invitation_email", deliver)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield SimpleNamespace(
                app=app, client=client, db=db, owner=owner, outsider=outsider,
                selected_user=selected_user, sent=sent,
            )

    await engine.dispose()


@pytest.mark.asyncio
async def test_owner_can_create_workspace_invite_verified_member_and_revoke_access(workspace_harness):
    harness = workspace_harness
    created = await harness.client.post("/api/workspaces", json={"name": "Acme Platform"})
    assert created.status_code == 201
    workspace_id = created.json()["id"]
    assert created.json()["require_mfa"] is True

    invitation_response = await harness.client.post(
        f"/api/workspaces/{workspace_id}/invitations",
        json={"email": "engineer@example.com", "role": "engineer"},
    )
    assert invitation_response.status_code == 201, invitation_response.text
    assert harness.sent["email"] == "engineer@example.com"
    invite_url = harness.sent["invitation_url"]
    token = str(invite_url).split("token=", 1)[1]
    invitation = await harness.db.scalar(select(models.WorkspaceInvitation))
    assert invitation is not None
    assert invitation.token_hash != token
    assert invitation.status == "pending"

    wrong_identity = await harness.client.post(
        "/api/workspaces/invitations/accept", json={"token": token}
    )
    assert wrong_identity.status_code == 403
    assert invitation.status == "pending"

    engineer = models.User(
        id=uuid.uuid4(), email="engineer@example.com", email_verified=True,
        mfa_enabled=False, first_name="Taylor", last_name="Engineer",
    )
    harness.db.add(engineer)
    await harness.db.flush()
    await ensure_personal_tenant(harness.db, engineer)
    await harness.db.commit()
    harness.selected_user["value"] = engineer

    accepted = await harness.client.post(
        "/api/workspaces/invitations/accept", json={"token": token}
    )
    assert accepted.status_code == 200
    assert accepted.json()["workspace_id"] == workspace_id
    assert accepted.json()["mfa_required"] is True
    replay = await harness.client.post(
        "/api/workspaces/invitations/accept", json={"token": token}
    )
    assert replay.status_code == 404
    member_rows = await harness.db.execute(
        select(models.TenantMembership).where(
            models.TenantMembership.tenant_id == uuid.UUID(workspace_id),
            models.TenantMembership.user_id == engineer.id,
        )
    )
    assert member_rows.scalars().one().role == "engineer"

    blocked_until_mfa = await harness.client.get(f"/api/workspaces/{workspace_id}/members")
    assert blocked_until_mfa.status_code == 403
    engineer.mfa_enabled = True
    await harness.db.commit()
    members = await harness.client.get(f"/api/workspaces/{workspace_id}/members")
    assert members.status_code == 200
    assert {member["email"] for member in members.json()} == {"owner@company.test", "engineer@example.com"}

    harness.selected_user["value"] = harness.owner
    duplicate_invitation = await harness.client.post(
        f"/api/workspaces/{workspace_id}/invitations",
        json={"email": "ENGINEER@EXAMPLE.COM", "role": "viewer"},
    )
    assert duplicate_invitation.status_code == 409

    removed = await harness.client.delete(
        f"/api/workspaces/{workspace_id}/members/{engineer.id}"
    )
    assert removed.status_code == 204
    assert (await harness.client.get(f"/api/workspaces/{workspace_id}/members")).status_code == 200
    still_active = await harness.db.scalar(
        select(models.TenantMembership).where(
            models.TenantMembership.tenant_id == uuid.UUID(workspace_id),
            models.TenantMembership.user_id == engineer.id,
        )
    )
    assert still_active.status == "removed"


@pytest.mark.asyncio
async def test_workspace_project_scope_shares_only_company_projects(workspace_harness):
    harness = workspace_harness
    team = models.Tenant(
        id=uuid.uuid4(), display_name="Engineering", kind="organization",
        status="active", require_mfa=True,
    )
    engineer = models.User(
        id=uuid.uuid4(), email="shared@company.test", email_verified=True, mfa_enabled=True
    )
    harness.db.add_all([team, engineer])
    await harness.db.flush()
    harness.db.add_all([
        models.TenantMembership(tenant_id=team.id, user_id=harness.owner.id, role="owner", status="active"),
        models.TenantMembership(tenant_id=team.id, user_id=engineer.id, role="engineer", status="active"),
    ])
    await ensure_personal_tenant(harness.db, engineer)
    company_project = models.Project(
        id=uuid.uuid4(), user_id=harness.owner.id, tenant_id=team.id,
        name="shared-api", full_name="acme/shared-api",
    )
    personal_project = models.Project(
        id=uuid.uuid4(), user_id=harness.owner.id, tenant_id=harness.owner.id,
        name="private-api", full_name="morgan/private-api",
    )
    legacy_personal_project = models.Project(
        id=uuid.uuid4(), user_id=harness.owner.id, tenant_id=None,
        name="legacy-private-api", full_name="morgan/legacy-private-api",
    )
    harness.db.add_all([company_project, personal_project, legacy_personal_project])
    await harness.db.commit()

    engineer.active_tenant_id = team.id
    rows = await harness.db.execute(select(models.Project).where(project_tenant_filter(engineer)))
    assert {project.id for project in rows.scalars().all()} == {company_project.id}

    harness.owner.active_tenant_id = team.id
    owner_rows = await harness.db.execute(select(models.Project).where(project_tenant_filter(harness.owner)))
    assert {project.id for project in owner_rows.scalars().all()} == {company_project.id}

    harness.owner.active_tenant_id = harness.owner.id
    personal_rows = await harness.db.execute(select(models.Project).where(project_tenant_filter(harness.owner)))
    assert {project.id for project in personal_rows.scalars().all()} == {
        personal_project.id, legacy_personal_project.id,
    }

    harness.outsider.active_tenant_id = harness.outsider.id
    outsider_rows = await harness.db.execute(select(models.Project).where(project_tenant_filter(harness.outsider)))
    assert outsider_rows.scalars().all() == []


@pytest.mark.asyncio
async def test_workspace_context_rejects_cross_tenant_and_read_only_writes(workspace_harness):
    harness = workspace_harness
    company = models.Tenant(
        id=uuid.uuid4(), display_name="Read only", kind="organization",
        status="active", require_mfa=True,
    )
    viewer = models.User(
        id=uuid.uuid4(), email="viewer@company.test", email_verified=True, mfa_enabled=True
    )
    harness.db.add_all([company, viewer])
    await harness.db.flush()
    harness.db.add(models.TenantMembership(
        tenant_id=company.id, user_id=viewer.id, role="viewer", status="active"
    ))
    await ensure_personal_tenant(harness.db, viewer)
    await harness.db.commit()

    read_request = Request({
        "type": "http", "method": "GET", "path": "/api/projects",
        "headers": [(b"x-zeroops-tenant", str(company.id).encode())],
    })
    attached = await auth._attach_active_workspace(read_request, harness.db, viewer)
    assert attached.active_tenant_id == company.id
    assert attached.active_tenant_role == "viewer"

    request = Request({
        "type": "http", "method": "POST", "path": "/api/projects",
        "headers": [(b"x-zeroops-tenant", str(company.id).encode())],
    })
    with pytest.raises(HTTPException) as read_only:
        await auth._attach_active_workspace(request, harness.db, viewer)
    assert read_only.value.status_code == 403

    outsider_request = Request({
        "type": "http", "method": "GET", "path": "/api/projects",
        "headers": [(b"x-zeroops-tenant", str(company.id).encode())],
    })
    with pytest.raises(HTTPException) as not_member:
        await auth._attach_active_workspace(outsider_request, harness.db, harness.outsider)
    assert not_member.value.status_code == 404

    viewer_membership = await harness.db.scalar(
        select(models.TenantMembership).where(
            models.TenantMembership.tenant_id == company.id,
            models.TenantMembership.user_id == viewer.id,
        )
    )
    viewer_membership.status = "removed"
    await harness.db.commit()
    recovery_request = Request({
        "type": "http", "method": "GET", "path": "/api/workspaces",
        "headers": [(b"x-zeroops-tenant", str(company.id).encode())],
    })
    recovered = await auth._attach_active_workspace(recovery_request, harness.db, viewer)
    assert recovered.active_tenant_id == viewer.id


@pytest.mark.asyncio
async def test_company_workspace_creation_requires_mfa(workspace_harness):
    harness = workspace_harness
    harness.owner.mfa_enabled = False
    await harness.db.commit()
    response = await harness.client.post("/api/workspaces", json={"name": "No MFA"})
    assert response.status_code == 403
    organizations = await harness.db.scalars(
        select(models.Tenant).where(models.Tenant.kind == "organization")
    )
    assert organizations.all() == []
