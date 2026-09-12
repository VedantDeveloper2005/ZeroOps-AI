"""The production outbox must drain and recover without losing durable commands."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services import workflow_outbox


@pytest.mark.asyncio
async def test_dispatcher_retries_with_a_fresh_session_after_failure(monkeypatch):
    sessions = MagicMock()
    db = sessions.return_value.__aenter__.return_value
    dispatch = AsyncMock(side_effect=[RuntimeError("transient database error"), 1])
    publisher = object()
    sleep = AsyncMock(side_effect=[None, asyncio.CancelledError()])
    monkeypatch.setattr(workflow_outbox, "publisher_from_config", lambda: publisher)
    monkeypatch.setattr(workflow_outbox, "dispatch_pending", dispatch)
    monkeypatch.setattr(workflow_outbox.asyncio, "sleep", sleep)

    with pytest.raises(asyncio.CancelledError):
        await workflow_outbox.run_dispatcher(sessions)
    assert sessions.call_count == 2
    assert dispatch.await_count == 2
    dispatch.assert_awaited_with(db, publisher=publisher)
    assert sessions.return_value.__aexit__.await_count == 2


@pytest.mark.asyncio
async def test_dispatcher_shutdown_is_not_swallowed_or_retried(monkeypatch):
    sessions = MagicMock()
    dispatch = AsyncMock(side_effect=asyncio.CancelledError())
    sleep = AsyncMock()
    monkeypatch.setattr(workflow_outbox, "publisher_from_config", lambda: object())
    monkeypatch.setattr(workflow_outbox, "dispatch_pending", dispatch)
    monkeypatch.setattr(workflow_outbox.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await workflow_outbox.run_dispatcher(sessions)
    assert dispatch.await_count == 1
    sleep.assert_not_awaited()
