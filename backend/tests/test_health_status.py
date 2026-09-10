import asyncio

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend import database, main


def test_health_aliases_report_current_database_state(monkeypatch):
    client = TestClient(main.app, raise_server_exceptions=False)
    for available in (True, False, True):
        monkeypatch.setattr(database, "database_available", available)
        for path in ("/health", "/api/health"):
            response = client.get(path)
            assert response.status_code == (200 if available else 503)
            assert response.json()["database"] is available
            assert response.json()["status"] == ("healthy" if available else "degraded")
        assert client.get("/healthz").status_code == 200


def test_health_routes_are_registered_once_and_match_openapi():
    for path in ("/health", "/api/health"):
        matches = [route for route in main.app.routes if getattr(route, "path", None) == path]
        assert len(matches) == 1
        assert matches[0].endpoint is main.health_check


def test_database_health_marks_shared_state_unavailable_without_exposing_errors(monkeypatch):
    class UnavailableSession:
        async def execute(self, _):
            raise RuntimeError("postgresql://sensitive-user:secret-password@private-db/zeroops")

    monkeypatch.setattr(database, "database_available", True)
    with pytest.raises(HTTPException) as error:
        asyncio.run(main.health_database(UnavailableSession()))

    assert error.value.status_code == 503
    assert error.value.detail == "Database connection is unavailable."
    assert database.database_available is False
