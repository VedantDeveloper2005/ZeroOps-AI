import asyncio
import subprocess
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


def test_new_project_defaults_do_not_claim_an_unscanned_framework():
    request = main.schemas.ProjectCreate(
        name="unscanned",
        full_name="owner/unscanned",
        repo_url="https://github.com/owner/unscanned",
    )

    assert request.framework == "Unknown"
    assert request.language == "Unknown"
    assert models.Project.__table__.c.framework.default.arg == "Unknown"
    assert models.Project.__table__.c.language.default.arg == "Unknown"


def test_project_analyze_uses_project_branch_and_persists_supported_fields(monkeypatch):
    project_id = uuid.uuid4()
    user_id = uuid.uuid4()
    project = SimpleNamespace(
        id=project_id,
        full_name="owner/repository",
        source_path=None,
        source_type="github",
        branch="release/selected",
        framework="Next.js",
        language="TypeScript",
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
            "application_type": "FastAPI web service",
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
    assert stored_analysis.application_type == "FastAPI web service"
    assert not hasattr(stored_analysis, "deployment_risk")
    assert project.framework == "FastAPI"
    assert project.language == "Python"
    assert db.commits == 1


def test_initial_github_analysis_syncs_existing_project_identity(monkeypatch):
    project = SimpleNamespace(
        id=uuid.uuid4(),
        framework="Next.js",
        language="TypeScript",
    )
    user = SimpleNamespace(
        id=uuid.uuid4(),
        github_connected=True,
        github_access_token_encrypted="encrypted-token",
    )

    class Session(FakeWriteSession):
        def __init__(self):
            super().__init__()
            self.results = iter([
                ScalarResult(first=project),
                ScalarResult(first=None),
            ])

        async def execute(self, _):
            return next(self.results)

    async def fetch_context(*_args, **_kwargs):
        return {"files_context": {}, "files_list": [], "scanned_vars": []}

    monkeypatch.setattr(main.github_oauth, "decrypt_token", lambda _: "github-token")
    monkeypatch.setattr(main.github_oauth, "fetch_github_repo_context", fetch_context)
    monkeypatch.setattr(
        main.ai,
        "analyze_repository",
        lambda *_: {
            "framework": "React",
            "version": "19.2.8",
            "language": "JavaScript",
            "application_type": "React single-page application (Vite 8.2.0)",
            "resources": {},
            "dependencies": [],
            "vulnerabilities": [],
            "database_dependencies": [],
            "environment_variables": [],
        },
    )
    db = Session()

    result = asyncio.run(
        main.analyze_repo(
            main.schemas.DeployRequest(repo="owner/repository", branch="main"),
            user,
            db,
        )
    )

    assert result["framework"] == "React"
    assert project.framework == "React"
    assert project.language == "JavaScript"
    stored_analysis = next(item for item in db.added if isinstance(item, models.AIAnalysis))
    assert stored_analysis.application_type == "React single-page application (Vite 8.2.0)"
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


def test_azure_cli_readiness_timeout_is_reported_unavailable(monkeypatch):
    def time_out(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(main.config.subprocess, "run", time_out)

    assert main.config.check_azure_cli() is False


def test_chat_plan_update_persists_normalized_authoritative_region():
    plan = SimpleNamespace(
        plan_data={"region_label": "East US"},
        region="eastus",
        cost_estimate=None,
        security_score=88,
        performance_score=91,
        reliability_score=90,
        estimated_deploy_time="5 minutes",
        ai_explanations={},
        status="approved",
        revision=4,
        approval_note="approved",
        approved_at=object(),
    )
    updated = {
        "region_label": "West Europe",
        "cost": {"monthly_estimate": None},
        "assessment": {
            "security": {"value": None},
            "performance": {"value": None},
            "reliability": {"value": None},
        },
        "deployment_time": {"estimate": None},
        "ai_explanations": {},
    }

    main._apply_chat_plan_update(plan, updated)

    assert plan.region == "westeurope"
    assert plan.plan_data["region_label"] == "West Europe"
    assert plan.status == "draft"
    assert plan.revision == 5
    assert plan.approval_note is None
    assert plan.approved_at is None


def test_chat_telemetry_summary_handles_partial_nullable_samples():
    metrics = [
        SimpleNamespace(
            cpu_utilization=None,
            memory_utilization=None,
            error_rate=None,
            response_time_ms=120,
        ),
        SimpleNamespace(
            cpu_utilization=42.5,
            memory_utilization=None,
            error_rate=0.75,
            response_time_ms=None,
        ),
    ]

    summary = main._chat_telemetry_summary(metrics)

    assert summary == {
        "avg_cpu_utilization": "42.5%",
        "avg_memory_utilization": "Not recorded",
        "recent_error_rate": "0.75%",
        "recent_response_time_ms": "120ms",
    }
    assert main._chat_telemetry_summary([
        SimpleNamespace(
            cpu_utilization=None,
            memory_utilization=None,
            error_rate=None,
            response_time_ms=None,
        )
    ]) is None
