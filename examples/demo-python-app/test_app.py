from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def test_health_endpoint():
    """Verify health endpoint returns 200 OK for Azure App Service probes."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["code"] == 200


def test_root_endpoint():
    """Verify root endpoint returns application metadata."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["app"] == "ZeroOps Demo"
    assert data["status"] == "running"
    assert "version" in data
