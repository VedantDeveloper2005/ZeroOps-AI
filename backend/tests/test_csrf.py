import pytest
from fastapi.testclient import TestClient

try:
    from backend.main import app
except ImportError:
    from main import app

client = TestClient(app)

def test_csrf_middleware_gating():
    # 1. GET requests should pass even without CSRF header (since CSRF only applies to state-changing methods)
    response = client.get("/api/health")
    assert response.status_code == 200
    
    # The middleware should set a non-httpOnly csrf_token cookie on the initial response
    assert "csrf_token" in response.cookies
    csrf_cookie_val = response.cookies["csrf_token"]
    assert csrf_cookie_val is not None

    # 2. POST request WITHOUT cookie authentication should pass (e.g. API keys or unauthenticated public routes)
    # The health GKE connection check or list projects or billing operations
    # Let's hit a POST route. If there is no session cookie, it passes the CSRF check (returning 401 or 503 depending on db status).
    response = client.post("/api/billing/operations", json={})
    assert response.status_code in [401, 503]

    # 3. POST request WITH cookie authentication but WITHOUT CSRF header must be rejected with 403 Forbidden!
    client.cookies.set("session_token", "fake-session-token-value")
    response = client.post("/api/billing/operations", json={})
    assert response.status_code == 403
    assert "CSRF token validation failed" in response.json()["detail"]

    # 4. POST request WITH cookie authentication and MATCHING CSRF header must pass the CSRF check!
    headers = {"X-CSRF-Token": csrf_cookie_val}
    client.cookies.set("csrf_token", csrf_cookie_val)
    response = client.post("/api/billing/operations", json={}, headers=headers)
    assert response.status_code in [401, 503]  # Successfully bypassed CSRF, hit auth/db layer!
    
    # Cleanup cookies
    client.cookies.clear()
