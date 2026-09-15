from __future__ import annotations

import asyncio
from types import SimpleNamespace
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
import pytest

from backend import main, models
from backend.services import app_service


# ─────────────────────────────────────────────────────────────────────────────
# 1. teardown_project_resources unit tests
# ─────────────────────────────────────────────────────────────────────────────

def test_teardown_project_resources_requires_project_id():
    conn = SimpleNamespace(client_id="cid", tenant_id="tid", subscription_id="sub")
    with pytest.raises(app_service.AzureDeploymentError, match="A valid project ID is required"):
        app_service.teardown_project_resources(
            connection=conn,
            client_secret="secret",
            project_id="",
        )


def test_teardown_project_resources_success(monkeypatch):
    proj_id = uuid.uuid4()
    conn = SimpleNamespace(client_id="cid", tenant_id="tid", subscription_id="sub")
    monkeypatch.setattr(app_service, "_sign_in", lambda connection, client_secret, env: None)

    commands_run = []

    def mock_capture(cmd, *, env, cwd=None):
        commands_run.append(list(cmd))
        if cmd[:3] == ["az", "group", "exists"]:
            return "true"
        return ""

    def mock_run(cmd, *, env, cwd=None):
        commands_run.append(list(cmd))
        yield "Deleted"

    monkeypatch.setattr(app_service, "_capture", mock_capture)
    monkeypatch.setattr(app_service, "_run", mock_run)

    meta_list = [
        {
            "release": {"application_name": "zo-app-one"},
            "target": {"resource_group": f"rg-zeroops-{proj_id.hex}"},
        },
        {
            "release": {"application_name": "zo-app-two"},
            "target": {"resource_group": f"rg-zeroops-{proj_id.hex}"},
        },
    ]

    result = app_service.teardown_project_resources(
        connection=conn,
        client_secret="secret",
        project_id=proj_id,
        deployment_metadata_list=meta_list,
    )

    assert result["status"] == "success"
    assert "zo-app-one" in result["deleted_apps"]
    assert "zo-app-two" in result["deleted_apps"]
    assert result["deleted_rg"] is True
    assert result["project_resource_group"] == f"rg-zeroops-{proj_id.hex}"

    # Verify az commands were executed
    webapp_deletes = [c for c in commands_run if c[:3] == ["az", "webapp", "delete"]]
    assert len(webapp_deletes) == 2
    group_deletes = [c for c in commands_run if c[:3] == ["az", "group", "delete"]]
    assert len(group_deletes) == 1
    assert group_deletes[0][3:5] == ["--name", f"rg-zeroops-{proj_id.hex}"]


def test_teardown_project_resources_skips_nonexistent_group(monkeypatch):
    proj_id = uuid.uuid4()
    conn = SimpleNamespace(client_id="cid", tenant_id="tid", subscription_id="sub")
    monkeypatch.setattr(app_service, "_sign_in", lambda connection, client_secret, env: None)

    commands_run = []

    def mock_capture(cmd, *, env, cwd=None):
        commands_run.append(list(cmd))
        if cmd[:3] == ["az", "group", "exists"]:
            return "false"
        return ""

    monkeypatch.setattr(app_service, "_capture", mock_capture)
    monkeypatch.setattr(app_service, "_run", lambda cmd, *, env, cwd=None: iter([]))

    result = app_service.teardown_project_resources(
        connection=conn,
        client_secret="secret",
        project_id=proj_id,
        deployment_metadata_list=[],
    )

    assert result["status"] == "success"
    assert result["deleted_rg"] is False
    assert any("does not exist; skipping" in m for m in result["messages"])


# ─────────────────────────────────────────────────────────────────────────────
# 2. DELETE /api/projects/{project_id} endpoint tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_project_not_found(monkeypatch):
    user = models.User(id=uuid.uuid4(), email="dev@zeroops.io", plan="starter")

    db = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.first.return_value = None
    exec_mock = MagicMock()
    exec_mock.scalars.return_value = scalars_mock
    db.execute.return_value = exec_mock

    with pytest.raises(HTTPException) as exc_info:
        await main.delete_project(
            project_id=uuid.uuid4(),
            current_user=user,
            db=db,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Project not found."


@pytest.mark.asyncio
async def test_delete_project_with_cloud_teardown(monkeypatch):
    user = models.User(id=uuid.uuid4(), email="dev@zeroops.io", plan="starter")
    project_id = uuid.uuid4()
    project = models.Project(id=project_id, user_id=user.id, name="demo-cloud-proj")

    deployment = models.Deployment(
        id=uuid.uuid4(),
        project_id=project_id,
        user_id=user.id,
        status="succeeded",
        infrastructure_metadata={
            "release": {"application_name": "zo-demo-app"},
            "target": {"resource_group": f"rg-zeroops-{project_id.hex}"},
        },
    )

    db = AsyncMock()

    call_count = 0

    def mock_execute(query):
        nonlocal call_count
        call_count += 1
        res = MagicMock()
        scalars = MagicMock()
        if call_count == 1:
            # First query is for project
            scalars.first.return_value = project
        elif call_count == 2:
            # Second query is for deployments
            scalars.all.return_value = [deployment]
        res.scalars.return_value = scalars
        return res

    db.execute = AsyncMock(side_effect=mock_execute)
    db.delete = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    conn = SimpleNamespace(client_id="cid", tenant_id="tid", subscription_id="sub")
    monkeypatch.setattr(main, "get_active_azure_connection", AsyncMock(return_value=conn))

    from backend.services import azure_connector as azconn
    monkeypatch.setattr(azconn, "get_credential_secret", lambda user_id: "fake-secret")

    teardown_called = False

    def mock_teardown(*, connection, client_secret, project_id, deployment_metadata_list):
        nonlocal teardown_called
        teardown_called = True
        return {
            "status": "success",
            "deleted_apps": ["zo-demo-app"],
            "deleted_rg": True,
            "messages": ["Cloud resources deleted successfully."],
        }

    monkeypatch.setattr(app_service, "teardown_project_resources", mock_teardown)

    response = await main.delete_project(
        project_id=project_id,
        current_user=user,
        db=db,
    )

    assert response["status"] == "success"
    assert teardown_called is True
    assert response["azure_teardown"]["status"] == "success"
    assert "zo-demo-app" in response["azure_teardown"]["deleted_apps"]

    db.delete.assert_called_once_with(project)
    db.commit.assert_called_once()
    assert db.add.called  # ActivityEvent logged


@pytest.mark.asyncio
async def test_delete_project_handles_cloud_teardown_error_gracefully(monkeypatch):
    user = models.User(id=uuid.uuid4(), email="dev@zeroops.io", plan="starter")
    project_id = uuid.uuid4()
    project = models.Project(id=project_id, user_id=user.id, name="demo-cloud-proj")

    db = AsyncMock()

    call_count = 0

    def mock_execute(query):
        nonlocal call_count
        call_count += 1
        res = MagicMock()
        scalars = MagicMock()
        if call_count == 1:
            scalars.first.return_value = project
        elif call_count == 2:
            scalars.all.return_value = []
        res.scalars.return_value = scalars
        return res

    db.execute = AsyncMock(side_effect=mock_execute)
    db.delete = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    conn = SimpleNamespace(client_id="cid", tenant_id="tid", subscription_id="sub")
    monkeypatch.setattr(main, "get_active_azure_connection", AsyncMock(return_value=conn))

    from backend.services import azure_connector as azconn
    monkeypatch.setattr(azconn, "get_credential_secret", lambda user_id: "fake-secret")

    def mock_teardown_failing(*args, **kwargs):
        raise RuntimeError("Azure ARM connection timeout")

    monkeypatch.setattr(app_service, "teardown_project_resources", mock_teardown_failing)

    response = await main.delete_project(
        project_id=project_id,
        current_user=user,
        db=db,
    )

    # Deletion of DB record must still succeed even if Azure teardown has an error
    assert response["status"] == "success"
    assert response["azure_teardown"]["status"] == "warning"
    assert "Azure ARM connection timeout" in response["azure_teardown"]["error"]

    db.delete.assert_called_once_with(project)
    db.commit.assert_called_once()
