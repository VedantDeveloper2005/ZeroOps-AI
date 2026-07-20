"""Run queued releases through the production Azure App Service pipeline.

The old worker manufactured build, health-check, and live-URL success results.
This adapter intentionally delegates to the same pipeline used by the control
plane so a release is only marked running after Azure reports it ready and its
public endpoint has been verified.
"""

from __future__ import annotations

import asyncio
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

try:
    from backend.services import github_oauth, pipeline
except ImportError:
    from services import github_oauth, pipeline


class TerraformRunner:
    """Compatibility name for the worker's real deployment-pipeline runner."""

    def __init__(self, db_url: str, worker_id: str | None = None):
        self.db_url = db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        self.worker_id = worker_id

    def _get_connection(self):
        if "postgres.database.azure.com" in self.db_url:
            return psycopg2.connect(self.db_url, sslmode="require")
        return psycopg2.connect(self.db_url)

    def _load_pipeline_input(self, connection, job: dict[str, Any]) -> tuple[str, str, str | None]:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT p.full_name, p.branch, u.github_access_token_encrypted
                FROM projects p
                JOIN users u ON u.id = p.user_id
                WHERE p.id = %s AND p.user_id = %s
                """,
                (job["project_id"], job["user_id"]),
            )
            project = cursor.fetchone()
        if not project:
            raise RuntimeError("The deployment project is no longer available to this worker.")

        clone_token = None
        encrypted_token = project.get("github_access_token_encrypted")
        if encrypted_token:
            clone_token = github_oauth.decrypt_token(encrypted_token)
        return project["full_name"], project["branch"], clone_token

    def _mark_job(self, connection, job_id: str, *, status: str, failure_reason: str | None = None) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE deployment_jobs
                SET status = %s,
                    failure_reason = %s,
                    completed_at = CASE WHEN %s IN ('completed', 'failed') THEN NOW() ELSE completed_at END,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (status, failure_reason, status, job_id),
            )

    def execute_job(self, job: dict[str, Any]) -> bool:
        """Execute one queue item and mirror the verified pipeline outcome."""
        deployment_id = job.get("deployment_id")
        if not deployment_id:
            raise RuntimeError("Deployment job has no deployment identifier.")

        connection = self._get_connection()
        connection.autocommit = True
        try:
            self._mark_job(connection, str(job["id"]), status="running")
            repository, branch, clone_token = self._load_pipeline_input(connection, job)

            asyncio.run(
                pipeline.run_deployment_pipeline(
                    str(deployment_id),
                    repository,
                    branch,
                    clone_token,
                )
            )

            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT status, failure_reason FROM deployments WHERE id = %s", (deployment_id,))
                deployment = cursor.fetchone()
            if not deployment or deployment["status"] != "running":
                reason = (deployment or {}).get("failure_reason") or "The deployment pipeline did not verify a running application."
                self._mark_job(connection, str(job["id"]), status="failed", failure_reason=reason)
                return False

            self._mark_job(connection, str(job["id"]), status="completed")
            return True
        except Exception as error:
            self._mark_job(connection, str(job["id"]), status="failed", failure_reason=str(error))
            return False
        finally:
            connection.close()
