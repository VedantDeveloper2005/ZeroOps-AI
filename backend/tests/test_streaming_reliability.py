import json
import uuid
from types import SimpleNamespace

import pytest

from backend.services import pipeline


@pytest.mark.asyncio
async def test_terminal_deployment_stream_sends_new_logs_and_closes(monkeypatch):
    deployment = SimpleNamespace(
        status="running",
        live_url="https://example.invalid",
        failure_reason=None,
        infrastructure_metadata={},
    )
    log = SimpleNamespace(
        id=uuid.uuid4(),
        line_number=1,
        level="INFO",
        message="Release endpoint responded.",
        timestamp=None,
    )
    statements = []

    class ScalarResult:
        def __init__(self, *, first=None, all_rows=None):
            self._first = first
            self._all_rows = all_rows

        def first(self):
            return self._first

        def all(self):
            return self._all_rows

    class Result:
        def __init__(self, scalar_result):
            self._scalar_result = scalar_result

        def scalars(self):
            return self._scalar_result

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def execute(self, statement):
            statements.append(str(statement))
            if len(statements) == 1:
                return Result(ScalarResult(first=deployment))
            return Result(ScalarResult(all_rows=[log]))

    class WebSocket:
        def __init__(self):
            self.messages = []

        async def send_text(self, payload):
            self.messages.append(json.loads(payload))

    monkeypatch.setattr(pipeline, "AsyncSessionLocal", Session)
    websocket = WebSocket()

    await pipeline.stream_deployment_updates(
        str(uuid.uuid4()),
        websocket,
        poll_interval=0,
    )

    assert [message["type"] for message in websocket.messages] == ["log", "status"]
    assert websocket.messages[-1]["status"] == "running"
    assert "deployment_logs.line_number >" in statements[1]
    assert "LIMIT" in statements[1]
