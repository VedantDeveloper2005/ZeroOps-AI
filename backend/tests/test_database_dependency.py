import asyncio

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError

from backend import database


class _Session:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def close(self):
        self.closed += 1


def test_get_db_preserves_route_http_errors(monkeypatch):
    """An expected route error must not poison the shared DB availability flag."""

    async def scenario():
        session = _Session()
        monkeypatch.setattr(database, "AsyncSessionLocal", lambda: session)
        monkeypatch.setattr(database, "database_available", True)

        dependency = database.get_db()
        assert await anext(dependency) is session

        with pytest.raises(HTTPException) as error:
            await dependency.athrow(HTTPException(status_code=401, detail="Not authenticated"))

        assert error.value.status_code == 401
        assert session.commits == 0
        assert session.rollbacks == 1
        assert session.closed == 1
        assert database.database_available is True

    asyncio.run(scenario())


def test_get_db_preserves_request_validation_errors(monkeypatch):
    """Invalid input must remain a 422 and not poison database availability."""

    async def scenario():
        session = _Session()
        monkeypatch.setattr(database, "AsyncSessionLocal", lambda: session)
        monkeypatch.setattr(database, "database_available", True)

        dependency = database.get_db()
        assert await anext(dependency) is session
        validation_error = RequestValidationError([
            {
                "type": "string_too_short",
                "loc": ("body", "password"),
                "msg": "String should have at least 12 characters",
                "input": "short",
                "ctx": {"min_length": 12},
            }
        ])

        with pytest.raises(RequestValidationError):
            await dependency.athrow(validation_error)

        assert session.commits == 0
        assert session.rollbacks == 1
        assert session.closed == 1
        assert database.database_available is True

    asyncio.run(scenario())
