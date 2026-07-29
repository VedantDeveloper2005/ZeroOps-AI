import asyncio
import uuid
from types import SimpleNamespace

try:
    from backend import main, models
except ImportError:
    import main
    import models


class ScalarResult:
    def __init__(self, *, first=None, all_values=None):
        self._first = first
        self._all = all_values if all_values is not None else []

    def scalars(self):
        return self

    def first(self):
        return self._first

    def all(self):
        return self._all


class FakeWriteSession:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1

    async def refresh(self, _):
        return None


def test_project_analyze_uses_project_branch_and_persists_supported_fields(monkeypatch):
    project_id = uuid.uuid4()
    user_id = uuid.uuid4()
    project = SimpleNamespace(
        id=project_id,
        full_name="owner/repository",
        source_path=None,
        source_type="github",
        branch="release/selected",
    )
    user = SimpleNamespace(id=user_id, github_access_token_encrypted=None)
    clone_call = {}
    cleaned = []

    async def owned_project(*_):
        return project

    def clone_repo(full_name, token, **kwargs):
        clone_call.update(full_name=full_name, token=token, **kwargs)
        return str(main.config.WORKSPACE_DIR) + "/deployments/analysis-test"

    monkeypatch.setattr(main, "_owned_project_or_404", owned_project)
    monkeypatch.setattr(main.git, "clone_repo", clone_repo)
    monkeypatch.setattr(main.git, "cleanup_workspace", cleaned.append)
    monkeypatch.setattr(
        main.zeroops_analysis,
        "analyze_repository",
        lambda *_: {
            "framework": "FastAPI",
            "version": "1",
            "language": "Python",
            "risk_score": 17,
            "confidence": 91,
            "resources": {"cpu": "1", "memory": "1Gi", "storage": "5Gi"},
            "dependencies": [],
            "vulnerabilities": [],
            "database_dependencies": [],
            "environment_variables": [],
            "deployment_risk": "Runtime credentials still require verification.",
        },
    )
    db = FakeWriteSession()

    result = asyncio.run(main.analyze_project_repository(project_id, user, db))

    assert result["deployment_risk"].startswith("Runtime credentials")
    assert clone_call["full_name"] == "owner/repository"
    assert clone_call["branch"] == "release/selected"
    assert clone_call["workspace_key"].startswith("analysis-")
    assert cleaned == [str(main.config.WORKSPACE_DIR) + "/deployments/analysis-test"]
    stored_analysis = next(item for item in db.added if isinstance(item, models.AIAnalysis))
    assert stored_analysis.risk_score == 17
    assert not hasattr(stored_analysis, "deployment_risk")
    assert db.commits == 1


def test_security_status_reports_only_available_controls(monkeypatch):
    project = SimpleNamespace(
        id=uuid.uuid4(),
        custom_domains=[{"https_enabled": True}],
    )
    analysis = SimpleNamespace(vulnerabilities=["CVE-record"])
    responses = iter([
        ScalarResult(first=project),
        ScalarResult(first=analysis),
    ])

    class Session:
        async def execute(self, _):
            return next(responses)

    monkeypatch.setattr(main.vault, "get_project_secrets", lambda _: {"DATABASE_URL": "stored"})
    result = asyncio.run(
        main.get_security_status(
            str(project.id),
            Session(),
            SimpleNamespace(id=uuid.uuid4()),
        )
    )

    assert result["securityScore"] is None
    assert result["firewallStatus"] == "Unavailable"
    assert result["httpsStatus"] == "Not assessed"
    assert result["threatLevel"] == "Unavailable"
    assert result["namespaceIsolated"] is False
    assert result["rbacEnabled"] is False


def test_empty_activity_reads_do_not_insert_synthetic_events():
    project = SimpleNamespace(id=uuid.uuid4())

    class ProjectSession:
        def __init__(self):
            self.responses = iter([
                ScalarResult(first=project),
                ScalarResult(all_values=[]),
            ])
            self.added = []
            self.commits = 0

        async def execute(self, _):
            return next(self.responses)

        def add(self, value):
            self.added.append(value)

        async def commit(self):
            self.commits += 1

    project_db = ProjectSession()
    user = SimpleNamespace(id=uuid.uuid4())
    project_events = asyncio.run(main.get_project_activity(project.id, user, project_db))

    class GlobalRows:
        def all(self):
            return []

    class GlobalSession(ProjectSession):
        async def execute(self, _):
            return GlobalRows()

    global_db = GlobalSession()
    global_events = asyncio.run(main.get_global_activity(user, global_db))

    assert project_events == []
    assert global_events == []
    assert project_db.added == []
    assert project_db.commits == 0
    assert global_db.added == []
    assert global_db.commits == 0
