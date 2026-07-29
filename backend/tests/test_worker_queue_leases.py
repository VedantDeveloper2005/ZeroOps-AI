import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend import main, schemas
from worker.queue import (
    PostgresJobQueue,
    postgres_connection_kwargs,
    stale_job_disposition,
)


def test_stale_job_recovery_requeues_only_before_side_effect_boundary():
    assert stale_job_disposition("queued", 1, 3) == "requeue"
    assert stale_job_disposition("queued", 3, 3) == "fail"
    assert stale_job_disposition("building", 1, 3) == "fail"
    assert stale_job_disposition("deploying", 1, 3) == "fail"
    assert stale_job_disposition("running", 1, 3) == "complete"
    assert stale_job_disposition("rolled_back", 1, 3) == "cancel"


def test_worker_postgres_connections_use_verified_tls_with_root_certificate():
    kwargs = postgres_connection_kwargs(
        ssl_enabled=True,
        ssl_verify=True,
        ssl_root_cert="/certs/postgres-root.pem",
    )
    assert kwargs == {
        "sslmode": "verify-full",
        "sslrootcert": "/certs/postgres-root.pem",
    }
    assert postgres_connection_kwargs(
        ssl_enabled=False,
        ssl_verify=True,
        ssl_root_cert=None,
    ) == {"sslmode": "disable"}


def test_queue_claim_is_atomic_and_returns_an_opaque_lease(monkeypatch):
    statements = []

    class Cursor:
        rowcount = 1

        def __init__(self):
            self.result = None

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def execute(self, statement, params):
            normalized = " ".join(statement.split())
            statements.append((normalized, params))
            if normalized.startswith("SELECT id, user_id"):
                self.result = {
                    "id": "job-id",
                    "user_id": "user-id",
                    "project_id": "project-id",
                    "deployment_id": "deployment-id",
                    "cloud": "azure",
                    "region": "eastus",
                    "infrastructure_spec": {"revision": 2},
                }
            elif normalized.startswith("UPDATE deployment_jobs"):
                self.result = {"attempt_count": 2}

        def fetchone(self):
            return self.result

    class Connection:
        def __init__(self):
            self.autocommit = True
            self.commits = 0
            self.rollbacks = 0
            self.closed = False

        def cursor(self, **_):
            return Cursor()

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            self.closed = True

    connection = Connection()
    queue = PostgresJobQueue(
        "postgresql://example.invalid/zeroops",
        lease_seconds=90,
        max_attempts=3,
    )
    monkeypatch.setattr(queue, "recover_stale_jobs", lambda: {})
    monkeypatch.setattr(queue, "_get_connection", lambda: connection)

    job = queue.pop_job(worker_id="worker-a")

    assert job is not None
    assert job["worker_id"] == "worker-a"
    assert job["attempt_count"] == 2
    assert len(job["lease_token"]) == 32
    assert connection.commits == 1
    claim_sql, claim_params = statements[-1]
    assert "status = 'running'" in claim_sql
    assert "attempt_count = attempt_count + 1" in claim_sql
    assert "lease_expires_at = NOW()" in claim_sql
    assert claim_params[0] == "worker-a"
    assert claim_params[2] == 90


def test_queue_heartbeat_is_fenced_by_worker_and_lease_token(monkeypatch):
    captured = {}

    class Cursor:
        rowcount = 0

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def execute(self, statement, params):
            captured["statement"] = " ".join(statement.split())
            captured["params"] = params

    class Connection:
        def cursor(self):
            return Cursor()

        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

    queue = PostgresJobQueue("postgresql://example.invalid/zeroops")
    monkeypatch.setattr(queue, "_get_connection", Connection)

    assert queue.heartbeat_job("job-id", "worker-a", "lease-a") is False
    assert "worker_id = %s" in captured["statement"]
    assert "lease_token = %s" in captured["statement"]
    assert captured["params"][-2:] == ("worker-a", "lease-a")


def test_api_startup_requeues_only_an_expired_pre_execution_claim(monkeypatch):
    job = SimpleNamespace(
        status="running",
        attempt_count=1,
        worker_id="worker-old",
        lease_token="lease-old",
        lease_expires_at=object(),
        heartbeat_at=object(),
        started_at=object(),
        completed_at=None,
        failure_reason="old",
        deployment_status="pending",
        live_url=None,
    )
    deployment = SimpleNamespace(
        status="queued",
        live_url=None,
        failure_reason=None,
        completed_at=None,
        project_id="project-id",
    )

    class Result:
        def all(self):
            return [(job, deployment)]

    class Session:
        def __init__(self):
            self.commits = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def execute(self, _statement):
            return Result()

        async def commit(self):
            self.commits += 1

    session = Session()
    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(main.config, "WORKER_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(main.config, "WORKER_LEASE_SECONDS", 180)
    monkeypatch.setattr(main.config, "WORKER_RECOVERY_BATCH_SIZE", 25)

    asyncio.run(main.recover_interrupted_deployments())

    assert job.status == "queued"
    assert job.worker_id is None
    assert job.lease_token is None
    assert job.started_at is None
    assert job.failure_reason is None
    assert deployment.status == "queued"
    assert session.commits == 1


def test_uploaded_source_and_unsaved_branch_cannot_enter_worker_queue():
    uploaded = SimpleNamespace(source_type="upload", branch="uploaded")
    with pytest.raises(HTTPException, match="durable shared source storage") as upload_error:
        main.deployment_branch_for_queue(uploaded, "uploaded")
    assert upload_error.value.status_code == 409

    github_project = SimpleNamespace(source_type="github", branch="release/reviewed")
    with pytest.raises(HTTPException, match="configured for branch") as branch_error:
        main.deployment_branch_for_queue(github_project, "main")
    assert branch_error.value.status_code == 409
    assert main.deployment_branch_for_queue(github_project, "release/reviewed") == "release/reviewed"


def test_deployment_request_rejects_non_production_environment():
    with pytest.raises(ValidationError):
        schemas.DeploymentCreate(
            project_id="6f94058e-ed35-4fe9-8070-75aadcda2db7",
            branch="main",
            environment="staging",
        )
