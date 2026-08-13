import asyncio
import json

from backend.services import github_oauth


class _Response:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _Client:
    def __init__(self, *_, **__):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def get(self, *_args, **_kwargs):
        paths = [
            "package.json",
            "Dockerfile",
            "README.md",
            ".env.example",
            "vite.config.js",
            "src/App.jsx",
        ]
        return _Response({"tree": [{"path": path, "type": "blob"} for path in paths]})


def test_github_context_fetches_bounded_client_entry_for_deterministic_scan(monkeypatch):
    requested = []

    async def fetch_file(_client, _token, _owner, _repo, path, _branch):
        requested.append(path)
        if path == "package.json":
            return json.dumps({"dependencies": {"react": "^19.2.8"}})
        if path == "src/App.jsx":
            # More than the old 3,000-character cap. The deterministic scanner
            # must receive the health claim near the end of the entry file.
            return "x" * 3_100 + "Healthy (200 OK) GET /api/health"
        return path

    monkeypatch.setattr(github_oauth.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(github_oauth, "fetch_github_file_content", fetch_file)

    context = asyncio.run(
        github_oauth.fetch_github_repo_context("token", "owner/repository", "main")
    )

    assert "src/App.jsx" in requested
    assert context["files_context"]["src/App.jsx"].endswith("GET /api/health")
    assert len(context["files_context"]["src/App.jsx"]) > 3_000
