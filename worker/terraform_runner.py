"""Run queued releases through the production Azure deployment pipeline.

The old worker manufactured build, health-check, and live-URL success results.
This adapter intentionally delegates to the same pipeline used by the control
plane so a release is only marked running after Azure reports it ready and its
public endpoint has been verified.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from typing import Any, Callable

import psycopg2
from psycopg2.extras import Json, RealDictCursor

try:
    from backend.services import github_oauth, pipeline, terraform_generator
    from backend.services.redaction import redact_sensitive_text
    from worker.queue import postgres_connection_kwargs
except ImportError:
    from services import github_oauth, pipeline, terraform_generator
    from services.redaction import redact_sensitive_text
    from queue import postgres_connection_kwargs


_ARTIFACT_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_GITHUB_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_ALLOWED_RESOURCE_KINDS = {
    "azurerm_application_insights",
    "azurerm_container_app",
    "azurerm_container_app_environment",
    "azurerm_key_vault",
    "azurerm_linux_web_app",
    "azurerm_postgresql_flexible_server",
    "azurerm_storage_account",
    "azurerm_virtual_network",
}


def _pipeline_job_outcome(record: dict[str, Any] | None) -> str:
    """Classify durable pipeline completion without inventing deployment success."""

    if not record:
        return "failed"
    deployment_status = record.get("status")
    pipeline_status = record.get("pipeline_status")
    failure_code = record.get("pipeline_failure_code")
    if deployment_status == "running" and pipeline_status in {None, "succeeded"}:
        return "deployed"
    if deployment_status == "stopped" and pipeline_status == "succeeded":
        return "validation_completed"
    if (
        deployment_status == "stopped"
        and pipeline_status == "blocked"
        and failure_code == "DEPLOYMENT_APPROVAL_REQUIRED"
    ):
        return "approval_required"
    return "failed"


def _safe_internal_iac_metadata(generated: dict[str, Any], queued_spec: dict[str, Any]) -> dict[str, Any]:
    """Allow only non-secret artifact descriptors into deployment metadata."""
    if not isinstance(generated, dict):
        raise RuntimeError("The internal artifact generator returned invalid metadata.")

    digest = generated.get("artifact_sha256")
    if not isinstance(digest, str) or not _ARTIFACT_DIGEST_PATTERN.fullmatch(digest):
        raise RuntimeError("The internal artifact generator returned an invalid digest.")

    generated_at = generated.get("generated_at")
    if not isinstance(generated_at, str):
        raise RuntimeError("The internal artifact generator returned an invalid timestamp.")
    try:
        datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise RuntimeError("The internal artifact generator returned an invalid timestamp.") from error

    resource_kinds = generated.get("resource_kinds") or []
    if not isinstance(resource_kinds, list):
        raise RuntimeError("The internal artifact generator returned invalid resource metadata.")
    safe_resource_kinds = sorted({
        resource_kind
        for resource_kind in resource_kinds
        if isinstance(resource_kind, str) and resource_kind in _ALLOWED_RESOURCE_KINDS
    })

    revision = queued_spec.get("revision")
    if not isinstance(revision, int):
        revision = None

    # Fixed values make the boundary explicit: a file was generated for
    # internal use, while Terraform plan/apply were not invoked.
    return {
        "engine": "terraform",
        "status": "generated",
        "execution": "not_run",
        "artifact_sha256": digest,
        "generated_at": generated_at,
        "resource_kinds": safe_resource_kinds,
        "plan_revision": revision,
    }


class TerraformRunner:
    """Compatibility name for the worker's real deployment-pipeline runner."""

    def __init__(
        self,
        db_url: str,
        worker_id: str | None = None,
        *,
        ssl_enabled: bool = False,
        ssl_verify: bool = True,
        ssl_root_cert: str | None = None,
    ):
        self.db_url = db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        self.worker_id = worker_id
        self.connection_kwargs = postgres_connection_kwargs(
            ssl_enabled=ssl_enabled,
            ssl_verify=ssl_verify,
            ssl_root_cert=ssl_root_cert,
        )

    def _get_connection(self):
        return psycopg2.connect(self.db_url, **self.connection_kwargs)

    @staticmethod
    def _lease_identity(job: dict[str, Any]) -> tuple[str, str]:
        worker_id = job.get("worker_id")
        lease_token = job.get("lease_token")
        if not isinstance(worker_id, str) or not worker_id:
            raise RuntimeError("Deployment job is missing its worker identity.")
        if not isinstance(lease_token, str) or not lease_token:
            raise RuntimeError("Deployment job is missing its lease token.")
        return worker_id, lease_token

    def _load_pipeline_input(
        self,
        connection,
        job: dict[str, Any],
    ) -> tuple[str, str, str, str | None]:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    p.full_name,
                    p.source_type,
                    d.branch,
                    d.commit_sha,
                    u.github_access_token_encrypted
                FROM projects p
                JOIN users u ON u.id = p.user_id
                JOIN deployments d
                  ON d.id = %s
                 AND d.project_id = p.id
                 AND d.user_id = p.user_id
                WHERE p.id = %s AND p.user_id = %s
                """,
                (job["deployment_id"], job["project_id"], job["user_id"]),
            )
            project = cursor.fetchone()
        if not project:
            raise RuntimeError("The deployment project is no longer available to this worker.")
        if project.get("source_type") != "github":
            raise RuntimeError(
                "Isolated deployment workers require durable GitHub source. "
                "Uploaded source is not queueable without shared storage."
            )
        branch = project.get("branch")
        commit_sha = str(project.get("commit_sha") or "").lower()
        if not isinstance(branch, str) or not branch:
            raise RuntimeError("The deployment has no saved source branch.")
        if not _GITHUB_COMMIT_PATTERN.fullmatch(commit_sha):
            raise RuntimeError("The deployment has no verified immutable Git commit.")

        clone_token = None
        encrypted_token = project.get("github_access_token_encrypted")
        if encrypted_token:
            clone_token = github_oauth.decrypt_token(encrypted_token)
        if not clone_token:
            raise RuntimeError("The GitHub connection must be restored before this deployment can run.")
        return project["full_name"], branch, commit_sha, clone_token

    def _mark_job(
        self,
        connection,
        job: dict[str, Any],
        *,
        status: str,
        failure_reason: str | None = None,
        live_url: str | None = None,
        deployment_completed: bool = True,
    ) -> bool:
        worker_id, lease_token = self._lease_identity(job)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE deployment_jobs
                SET status = %s,
                    failure_reason = %s,
                    deployment_status = CASE
                        WHEN %s = 'completed' AND %s THEN 'completed'
                        WHEN %s = 'failed' THEN 'failed'
                        ELSE deployment_status
                    END,
                    live_url = COALESCE(%s, live_url),
                    completed_at = CASE WHEN %s IN ('completed', 'failed') THEN NOW() ELSE completed_at END,
                    worker_id = CASE WHEN %s IN ('completed', 'failed') THEN NULL ELSE worker_id END,
                    lease_token = CASE WHEN %s IN ('completed', 'failed') THEN NULL ELSE lease_token END,
                    lease_expires_at = CASE WHEN %s IN ('completed', 'failed') THEN NULL ELSE lease_expires_at END,
                    heartbeat_at = CASE WHEN %s IN ('completed', 'failed') THEN NULL ELSE heartbeat_at END,
                    updated_at = NOW()
                WHERE id = %s
                  AND status = 'running'
                  AND worker_id = %s
                  AND lease_token = %s
                """,
                (
                    status,
                    failure_reason,
                    status,
                    deployment_completed,
                    status,
                    live_url,
                    status,
                    status,
                    status,
                    status,
                    status,
                    str(job["id"]),
                    worker_id,
                    lease_token,
                ),
            )
            return cursor.rowcount == 1

    def _begin_pipeline(self, connection, job: dict[str, Any]) -> None:
        """Cross the side-effect boundary only while this lease is current."""

        worker_id, lease_token = self._lease_identity(job)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                WITH owned_job AS (
                    SELECT deployment_id
                    FROM deployment_jobs
                    WHERE id = %s
                      AND status = 'running'
                      AND worker_id = %s
                      AND lease_token = %s
                    FOR UPDATE
                )
                UPDATE deployments AS d
                SET status = 'building'
                FROM owned_job
                WHERE d.id = owned_job.deployment_id
                  AND d.id = %s
                  AND d.status = 'queued'
                RETURNING d.id
                """,
                (str(job["id"]), worker_id, lease_token, str(job["deployment_id"])),
            )
            if not cursor.fetchone():
                raise RuntimeError(
                    "The deployment lease was lost or the release already crossed its execution boundary."
                )

    def _persist_internal_iac_metadata(
        self,
        connection,
        job: dict[str, Any],
        artifact_metadata: dict[str, Any],
    ) -> None:
        """Merge a sanitized artifact descriptor into deployment metadata."""
        deployment_id = str(job["deployment_id"])
        worker_id, lease_token = self._lease_identity(job)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "SELECT infrastructure_metadata FROM deployments WHERE id = %s",
                (deployment_id,),
            )
            deployment = cursor.fetchone()
            if not deployment:
                raise RuntimeError("The deployment record is no longer available to this worker.")

            infrastructure_metadata = deployment.get("infrastructure_metadata") or {}
            if isinstance(infrastructure_metadata, str):
                try:
                    infrastructure_metadata = json.loads(infrastructure_metadata)
                except json.JSONDecodeError as error:
                    raise RuntimeError("Deployment infrastructure metadata is invalid.") from error
            if not isinstance(infrastructure_metadata, dict):
                raise RuntimeError("Deployment infrastructure metadata is invalid.")

            updated_metadata = dict(infrastructure_metadata)
            updated_metadata["internal_iac"] = artifact_metadata
            cursor.execute(
                """
                UPDATE deployments AS d
                SET infrastructure_metadata = %s
                WHERE d.id = %s
                  AND d.status = 'queued'
                  AND EXISTS (
                    SELECT 1
                    FROM deployment_jobs AS j
                    WHERE j.id = %s
                      AND j.deployment_id = d.id
                      AND j.status = 'running'
                      AND j.worker_id = %s
                      AND j.lease_token = %s
                  )
                RETURNING d.id
                """,
                (
                    Json(updated_metadata),
                    deployment_id,
                    str(job["id"]),
                    worker_id,
                    lease_token,
                ),
            )
            if not cursor.fetchone():
                raise RuntimeError("The deployment lease was lost before artifact metadata was recorded.")

    def _mark_deployment_failed(
        self,
        connection,
        deployment_id: str,
        failure_reason: str,
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE deployments
                SET status = 'failed',
                    failure_reason = COALESCE(failure_reason, %s),
                    completed_at = COALESCE(completed_at, NOW())
                WHERE id = %s AND status IN ('queued', 'building', 'deploying')
                """,
                (failure_reason, deployment_id),
            )
            cursor.execute(
                """
                UPDATE decision_evaluations
                SET status = 'failed',
                    outcome_metadata = %s
                WHERE deployment_id = %s AND status = 'pending'
                """,
                (
                    Json(
                        {
                            "outcome": "Deployment worker recorded a failed release.",
                            "reason": failure_reason,
                        }
                    ),
                    deployment_id,
                ),
            )
            cursor.execute(
                """
                UPDATE projects AS p
                SET status = 'failed'
                WHERE p.id = (
                    SELECT project_id FROM deployments WHERE id = %s
                )
                  AND p.status = 'deploying'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM deployments AS other
                    WHERE other.project_id = p.id
                      AND other.id <> %s
                      AND other.status IN ('queued', 'building', 'deploying')
                  )
                """,
                (deployment_id, deployment_id),
            )

    def execute_job(
        self,
        job: dict[str, Any],
        *,
        lease_guard: Callable[[], bool] | None = None,
    ) -> bool:
        """Execute one queue item and mirror the verified pipeline outcome."""
        deployment_id = job.get("deployment_id")
        if not deployment_id:
            raise RuntimeError("Deployment job has no deployment identifier.")
        self._lease_identity(job)
        owns_lease = lease_guard or (lambda: True)

        connection = self._get_connection()
        connection.autocommit = True
        try:
            if not owns_lease():
                raise RuntimeError("The deployment lease was lost before execution started.")
            repository, branch, commit_sha, clone_token = self._load_pipeline_input(connection, job)

            queued_spec = job.get("infrastructure_spec")
            if not isinstance(queued_spec, dict):
                raise RuntimeError("Deployment job has no valid approved infrastructure specification.")
            generated_metadata = terraform_generator.generate_internal_artifact(
                plan=queued_spec,
                project_id=str(deployment_id),
                project_name=repository.rsplit("/", 1)[-1],
            )
            artifact_metadata = _safe_internal_iac_metadata(generated_metadata, queued_spec)
            self._persist_internal_iac_metadata(
                connection,
                job,
                artifact_metadata,
            )
            if not owns_lease():
                raise RuntimeError("The deployment lease was lost before cloud execution started.")
            self._begin_pipeline(connection, job)

            asyncio.run(
                pipeline.run_deployment_pipeline(
                    str(deployment_id),
                    repository,
                    branch,
                    clone_token,
                    commit_sha=commit_sha,
                    lease_guard=owns_lease,
                )
            )

            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT
                        status,
                        failure_reason,
                        live_url,
                        pipeline_status,
                        pipeline_failure_code
                    FROM (
                        SELECT
                            d.status,
                            d.failure_reason,
                            d.live_url,
                            latest_pipeline.status AS pipeline_status,
                            latest_pipeline.failure_code AS pipeline_failure_code
                        FROM deployments AS d
                        LEFT JOIN LATERAL (
                            SELECT status, failure_code
                            FROM pipeline_runs
                            WHERE deployment_id = d.id
                            ORDER BY created_at DESC
                            LIMIT 1
                        ) AS latest_pipeline ON TRUE
                        WHERE d.id = %s
                    ) AS pipeline_outcome
                    """,
                    (deployment_id,),
                )
                deployment = cursor.fetchone()
            outcome = _pipeline_job_outcome(deployment)
            if outcome == "failed":
                reason = (deployment or {}).get("failure_reason") or "The deployment pipeline did not verify a running application."
                self._mark_job(connection, job, status="failed", failure_reason=reason)
                return False

            return self._mark_job(
                connection,
                job,
                status="completed",
                live_url=deployment.get("live_url") if outcome == "deployed" else None,
                deployment_completed=outcome == "deployed",
            )
        except Exception as error:
            reason = redact_sensitive_text(str(error), maximum_length=2_000)
            if self._mark_job(connection, job, status="failed", failure_reason=reason):
                self._mark_deployment_failed(connection, str(deployment_id), reason)
            return False
        finally:
            connection.close()
