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
# 1. teardown_app_service tests
# ─────────────────────────────────────────────────────────────────────────────

def test_teardown_app_service_requires_valid_app_name_and_rg():
    conn = SimpleNamespace(client_id="cid", tenant_id="tid", subscription_id="sub")

    with pytest.raises(app_service.AzureDeploymentError, match="A valid application name is required"):
        app_service.teardown_app_service(
            connection=conn,
            client_secret="secret",
            app_name="",
            resource_group="rg-test",
        )

    with pytest.raises(app_service.AzureDeploymentError, match="A valid resource group is required"):
        app_service.teardown_app_service(
            connection=conn,
            client_secret="secret",
            app_name="app-test",
            resource_group="   ",
        )


def test_teardown_app_service_success(monkeypatch):
    conn = SimpleNamespace(client_id="cid", tenant_id="tid", subscription_id="sub")
    monkeypatch.setattr(app_service, "_sign_in", lambda connection, client_secret, env: None)

    commands_run = []

    def mock_capture(cmd, *, env, cwd=None):
        commands_run.append(list(cmd))
        if "show" in cmd:
            return "Running"
        return ""

    def mock_run(cmd, *, env, cwd=None):
        commands_run.append(list(cmd))
        yield "Deleted"

    monkeypatch.setattr(app_service, "_capture", mock_capture)
    monkeypatch.setattr(app_service, "_run", mock_run)

    messages = app_service.teardown_app_service(
        connection=conn,
        client_secret="secret",
        app_name="zo-demo-app",
        resource_group="rg-demo",
    )

    assert any("deleted successfully" in m for m in messages)
    assert any(c[:3] == ["az", "webapp", "show"] for c in commands_run)
    assert any(c[:3] == ["az", "webapp", "delete"] for c in commands_run)


def test_teardown_app_service_skips_when_app_not_found(monkeypatch):
    conn = SimpleNamespace(client_id="cid", tenant_id="tid", subscription_id="sub")
    monkeypatch.setattr(app_service, "_sign_in", lambda connection, client_secret, env: None)

    def mock_capture(cmd, *, env, cwd=None):
        if "show" in cmd:
            raise app_service.AzureDeploymentError("App not found")
        return ""

    monkeypatch.setattr(app_service, "_capture", mock_capture)

    messages = app_service.teardown_app_service(
        connection=conn,
        client_secret="secret",
        app_name="zo-demo-app",
        resource_group="rg-demo",
    )

    assert any("skipping deletion" in m for m in messages)


def test_teardown_app_service_raises_on_delete_failure(monkeypatch):
    conn = SimpleNamespace(client_id="cid", tenant_id="tid", subscription_id="sub")
    monkeypatch.setattr(app_service, "_sign_in", lambda connection, client_secret, env: None)

    monkeypatch.setattr(app_service, "_capture", lambda cmd, *, env, cwd=None: "Running")

    def mock_run(cmd, *, env, cwd=None):
        if "delete" in cmd:
            raise app_service.AzureDeploymentError("Azure RBAC permission denied")
        yield "output"

    monkeypatch.setattr(app_service, "_run", mock_run)

    with pytest.raises(app_service.AzureDeploymentError, match="Azure RBAC permission denied"):
        app_service.teardown_app_service(
            connection=conn,
            client_secret="secret",
            app_name="zo-demo-app",
            resource_group="rg-demo",
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. poll_app_service_metrics tests
# ─────────────────────────────────────────────────────────────────────────────

def test_poll_app_service_metrics_parses_values(monkeypatch):
    conn = SimpleNamespace(client_id="cid", tenant_id="tid", subscription_id="sub-123")
    monkeypatch.setattr(app_service, "_sign_in", lambda connection, client_secret, env: None)

    def mock_capture(cmd, *, env, cwd=None):
        metric_idx = cmd.index("--metric") + 1
        metric_name = cmd[metric_idx]
        if metric_name == "CpuPercentage":
            return "12.34"
        elif metric_name == "Requests":
            return "500"
        elif metric_name == "Http5xx":
            return "5"
        elif metric_name == "AverageResponseTime":
            return "0.045"  # 45 ms in seconds
        return ""

    monkeypatch.setattr(app_service, "_capture", mock_capture)

    metrics = app_service.poll_app_service_metrics(
        connection=conn,
        client_secret="secret",
        app_name="zo-demo-app",
        resource_group="rg-demo",
    )

    assert metrics["cpu_percent"] == 12.34
    assert metrics["request_count"] == 500
    assert metrics["http_error_rate_percent"] == 1.0  # 5 / 500 * 100
    assert metrics["response_latency_ms"] == 45.0


def test_poll_app_service_metrics_handles_nulls_gracefully(monkeypatch):
    conn = SimpleNamespace(client_id="cid", tenant_id="tid", subscription_id="sub-123")
    monkeypatch.setattr(app_service, "_sign_in", lambda connection, client_secret, env: None)

    def mock_capture(cmd, *, env, cwd=None):
        raise app_service.AzureDeploymentError("Data not ready yet")

    monkeypatch.setattr(app_service, "_capture", mock_capture)

    metrics = app_service.poll_app_service_metrics(
        connection=conn,
        client_secret="secret",
        app_name="zo-demo-app",
        resource_group="rg-demo",
    )

    assert metrics["cpu_percent"] is None
    assert metrics["request_count"] is None
    assert metrics["http_error_rate_percent"] is None
    assert metrics["response_latency_ms"] is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. DELETE /api/deployments/{deploy_id} endpoint tests
# ─────────────────────────────────────────────────────────────────────────────

class MockScalarResult:
    def __init__(self, item):
        self._item = item

    def scalars(self):
        return self

    def first(self):
        return self._item


@pytest.mark.asyncio
async def test_delete_deployment_404_when_not_found():
    mock_db = AsyncMock()
    mock_db.execute.return_value = MockScalarResult(None)
    user = SimpleNamespace(id=uuid.uuid4())

    with pytest.raises(HTTPException) as exc:
        await main.delete_deployment(
            deploy_id=uuid.uuid4(),
            current_user=user,
            db=mock_db,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["queued", "building", "deploying"])
async def test_delete_deployment_409_when_active(status):
    mock_db = AsyncMock()
    dep_id = uuid.uuid4()
    mock_deployment = SimpleNamespace(
        id=dep_id,
        user_id=uuid.uuid4(),
        status=status,
    )
    mock_db.execute.return_value = MockScalarResult(mock_deployment)
    user = SimpleNamespace(id=mock_deployment.user_id)

    with pytest.raises(HTTPException) as exc:
        await main.delete_deployment(
            deploy_id=dep_id,
            current_user=user,
            db=mock_db,
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_delete_deployment_success(monkeypatch):
    user_id = uuid.uuid4()
    dep_id = uuid.uuid4()
    proj_id = uuid.uuid4()

    mock_deployment = SimpleNamespace(
        id=dep_id,
        user_id=user_id,
        project_id=proj_id,
        version="v1.0.0",
        status="succeeded",
        infrastructure_metadata={
            "release": {"application_name": "zo-demo-app"},
            "target": {"resource_group": "rg-demo"},
        },
    )

    deleted_items = []
    added_items = []

    mock_db = AsyncMock()
    mock_db.execute.return_value = MockScalarResult(mock_deployment)

    async def mock_delete(item):
        deleted_items.append(item)

    mock_db.delete = mock_delete
    mock_db.add = lambda item: added_items.append(item)

    conn = SimpleNamespace(client_id="cid", tenant_id="tid", subscription_id="sub")

    async def mock_get_conn(db, uid):
        return conn

    monkeypatch.setattr(main, "get_active_azure_connection", mock_get_conn)

    from backend.services import azure_connector as azconn
    monkeypatch.setattr(azconn, "get_credential_secret", lambda uid: "mock-secret")

    from backend.services import app_service as appsrv
    monkeypatch.setattr(
        appsrv,
        "teardown_app_service",
        lambda *, connection, client_secret, app_name, resource_group: ["Deleted app service successfully."],
    )

    res = await main.delete_deployment(
        deploy_id=dep_id,
        current_user=SimpleNamespace(id=user_id),
        db=mock_db,
    )

    assert res["status"] == "deleted"
    assert res["azure_teardown"] == "success"
    assert res["azure_teardown_error"] is None
    assert mock_deployment in deleted_items
    assert any(isinstance(x, models.ActivityEvent) and x.action == "Deployment Deleted" for x in added_items)
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_deployment_best_effort_when_teardown_fails(monkeypatch):
    user_id = uuid.uuid4()
    dep_id = uuid.uuid4()
    proj_id = uuid.uuid4()

    mock_deployment = SimpleNamespace(
        id=dep_id,
        user_id=user_id,
        project_id=proj_id,
        version="v1.0.0",
        status="failed",
        infrastructure_metadata={
            "release": {"application_name": "zo-demo-app"},
            "target": {"resource_group": "rg-demo"},
        },
    )

    deleted_items = []
    mock_db = AsyncMock()
    mock_db.execute.return_value = MockScalarResult(mock_deployment)

    async def mock_delete(item):
        deleted_items.append(item)

    mock_db.delete = mock_delete
    mock_db.add = lambda item: None

    conn = SimpleNamespace(client_id="cid", tenant_id="tid", subscription_id="sub")
    monkeypatch.setattr(main, "get_active_azure_connection", AsyncMock(return_value=conn))

    from backend.services import azure_connector as azconn
    monkeypatch.setattr(azconn, "get_credential_secret", lambda uid: "mock-secret")

    from backend.services import app_service as appsrv

    def failing_teardown(**kwargs):
        raise appsrv.AzureDeploymentError("Azure CLI timed out")

    monkeypatch.setattr(appsrv, "teardown_app_service", failing_teardown)

    res = await main.delete_deployment(
        deploy_id=dep_id,
        current_user=SimpleNamespace(id=user_id),
        db=mock_db,
    )

    # Database delete still completed
    assert res["status"] == "deleted"
    assert res["azure_teardown"] == "failed"
    assert "Azure CLI timed out" in res["azure_teardown_error"]
    assert mock_deployment in deleted_items
    mock_db.commit.assert_awaited_once()
