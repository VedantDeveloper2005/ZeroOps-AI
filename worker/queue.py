"""PostgreSQL-backed deployment queue with bounded, renewable worker leases."""

from __future__ import annotations

import os
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import psycopg2
from psycopg2.extras import Json, RealDictCursor


class QueueUnavailableError(RuntimeError):
    """Raised when queue state cannot be read or changed safely."""


def postgres_connection_kwargs(
    *,
    ssl_enabled: bool,
    ssl_verify: bool,
    ssl_root_cert: str | None,
) -> dict[str, str]:
    """Translate the shared database TLS policy to libpq parameters."""

    if not ssl_enabled:
        return {"sslmode": "disable"}
    kwargs = {"sslmode": "verify-full" if ssl_verify else "require"}
    if ssl_verify:
        root_cert = ssl_root_cert
        if not root_cert:
            root_cert = next(
                (
                    candidate
                    for candidate in (
                        "/etc/ssl/certs/ca-certificates.crt",
                        "/etc/pki/tls/certs/ca-bundle.crt",
                    )
                    if os.path.isfile(candidate)
                ),
                None,
            )
        if root_cert:
            kwargs["sslrootcert"] = root_cert
    return kwargs


def stale_job_disposition(
    deployment_status: str | None,
    attempt_count: int | None,
    max_attempts: int,
) -> str:
    """Return the only safe action for an expired worker claim.

    A release that is still queued has not crossed the worker's explicit
    side-effect boundary and can be retried. Once a deployment is building,
    replay is withheld because the previous worker may have changed Azure
    before it stopped heartbeating.
    """

    attempts = max(int(attempt_count or 0), 0)
    if deployment_status == "running":
        return "complete"
    if deployment_status in {"stopped", "rolled_back"}:
        return "cancel"
    if deployment_status == "queued" and attempts < max_attempts:
        return "requeue"
    return "fail"


class JobQueue(ABC):
    @abstractmethod
    def pop_job(self, worker_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Claim the next queued job under a renewable lease."""

    @abstractmethod
    def heartbeat_job(self, job_id: str, worker_id: str, lease_token: str) -> bool:
        """Renew a claim, returning false when this worker no longer owns it."""

    @abstractmethod
    def recover_stale_jobs(self) -> dict[str, int]:
        """Reconcile a bounded batch of expired claims."""


class PostgresJobQueue(JobQueue):
    _UPDATABLE_FIELDS = {
        "terraform_status",
        "deployment_status",
        "estimated_cost",
        "terraform_path",
        "logs",
        "terraform_plan_output",
        "live_url",
        "failure_reason",
        "worker_id",
        "lease_token",
        "lease_expires_at",
        "heartbeat_at",
        "attempt_count",
        "started_at",
        "completed_at",
    }

    def __init__(
        self,
        database_url: str,
        *,
        lease_seconds: int = 180,
        max_attempts: int = 3,
        recovery_batch_size: int = 25,
        ssl_enabled: bool = False,
        ssl_verify: bool = True,
        ssl_root_cert: str | None = None,
    ):
        cleaned_url = database_url
        if "postgresql+asyncpg://" in cleaned_url:
            cleaned_url = cleaned_url.replace("postgresql+asyncpg://", "postgresql://")
        self.conn_str = cleaned_url
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts
        self.recovery_batch_size = recovery_batch_size
        self.connection_kwargs = postgres_connection_kwargs(
            ssl_enabled=ssl_enabled,
            ssl_verify=ssl_verify,
            ssl_root_cert=ssl_root_cert,
        )

    def _get_connection(self):
        return psycopg2.connect(self.conn_str, **self.connection_kwargs)

    def recover_stale_jobs(self) -> dict[str, int]:
        """Reconcile expired leases without replaying uncertain cloud changes."""

        conn = None
        counts = {"requeued": 0, "completed": 0, "cancelled": 0, "failed": 0}
        try:
            conn = self._get_connection()
            conn.autocommit = False
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT
                        j.id,
                        j.deployment_id,
                        j.attempt_count,
                        d.status AS deployment_status,
                        d.failure_reason AS deployment_failure_reason,
                        d.live_url AS deployment_live_url
                    FROM deployment_jobs AS j
                    LEFT JOIN deployments AS d ON d.id = j.deployment_id
                    WHERE j.status = 'running'
                      AND (
                        j.lease_expires_at < NOW()
                        OR (
                          j.lease_expires_at IS NULL
                          AND COALESCE(j.updated_at, j.started_at, j.created_at, TIMESTAMP 'epoch')
                              < NOW() - (%s * INTERVAL '1 second')
                        )
                      )
                    ORDER BY COALESCE(j.lease_expires_at, j.updated_at, j.started_at, j.created_at) ASC
                    LIMIT %s
                    FOR UPDATE OF j SKIP LOCKED
                    """,
                    (self.lease_seconds, self.recovery_batch_size),
                )
                stale_jobs = cursor.fetchall()

                for job in stale_jobs:
                    job_id = str(job["id"])
                    deployment_id = job.get("deployment_id")
                    disposition = stale_job_disposition(
                        job.get("deployment_status"),
                        job.get("attempt_count"),
                        self.max_attempts,
                    )

                    if disposition == "requeue":
                        cursor.execute(
                            """
                            UPDATE deployment_jobs
                            SET status = 'queued',
                                worker_id = NULL,
                                lease_token = NULL,
                                lease_expires_at = NULL,
                                heartbeat_at = NULL,
                                started_at = NULL,
                                completed_at = NULL,
                                failure_reason = NULL,
                                updated_at = NOW()
                            WHERE id = %s AND status = 'running'
                            """,
                            (job_id,),
                        )
                        counts["requeued"] += cursor.rowcount
                        continue

                    if disposition == "complete":
                        cursor.execute(
                            """
                            UPDATE deployment_jobs
                            SET status = 'completed',
                                deployment_status = 'completed',
                                live_url = %s,
                                worker_id = NULL,
                                lease_token = NULL,
                                lease_expires_at = NULL,
                                heartbeat_at = NULL,
                                completed_at = COALESCE(completed_at, NOW()),
                                failure_reason = NULL,
                                updated_at = NOW()
                            WHERE id = %s AND status = 'running'
                            """,
                            (job.get("deployment_live_url"), job_id),
                        )
                        counts["completed"] += cursor.rowcount
                        continue

                    if disposition == "cancel":
                        cursor.execute(
                            """
                            UPDATE deployment_jobs
                            SET status = 'cancelled',
                                worker_id = NULL,
                                lease_token = NULL,
                                lease_expires_at = NULL,
                                heartbeat_at = NULL,
                                completed_at = COALESCE(completed_at, NOW()),
                                failure_reason = 'The deployment became inactive while its worker lease was stale.',
                                updated_at = NOW()
                            WHERE id = %s AND status = 'running'
                            """,
                            (job_id,),
                        )
                        counts["cancelled"] += cursor.rowcount
                        continue

                    reason = (
                        job.get("deployment_failure_reason")
                        or "The deployment worker lease expired after release processing started. "
                        "Automatic replay was withheld to avoid duplicate Azure changes."
                    )
                    cursor.execute(
                        """
                        UPDATE deployment_jobs
                        SET status = 'failed',
                            worker_id = NULL,
                            lease_token = NULL,
                            lease_expires_at = NULL,
                            heartbeat_at = NULL,
                            completed_at = COALESCE(completed_at, NOW()),
                            failure_reason = %s,
                            updated_at = NOW()
                        WHERE id = %s AND status = 'running'
                        """,
                        (reason, job_id),
                    )
                    counts["failed"] += cursor.rowcount

                    if deployment_id:
                        cursor.execute(
                            """
                            UPDATE deployments
                            SET status = 'failed',
                                failure_reason = COALESCE(failure_reason, %s),
                                completed_at = COALESCE(completed_at, NOW())
                            WHERE id = %s
                              AND status IN ('queued', 'building', 'deploying')
                            """,
                            (reason, str(deployment_id)),
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
                                        "outcome": "Worker lease expired; automatic replay was withheld.",
                                        "reason": reason,
                                    }
                                ),
                                str(deployment_id),
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
                            (str(deployment_id), str(deployment_id)),
                        )

                conn.commit()
                return counts
        except Exception as error:
            if conn:
                conn.rollback()
            raise QueueUnavailableError("Unable to reconcile stale deployment jobs.") from error
        finally:
            if conn:
                conn.close()

    def pop_job(self, worker_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not worker_id:
            raise ValueError("worker_id is required to claim a deployment job.")

        self.recover_stale_jobs()
        conn = None
        try:
            conn = self._get_connection()
            conn.autocommit = False
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT id, user_id, project_id, deployment_id, cloud, region, infrastructure_spec
                    FROM deployment_jobs
                    WHERE status = 'queued' AND attempt_count < %s
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                    """,
                    (self.max_attempts,),
                )
                job = cursor.fetchone()
                if not job:
                    conn.rollback()
                    return None

                lease_token = uuid.uuid4().hex
                cursor.execute(
                    """
                    UPDATE deployment_jobs
                    SET status = 'running',
                        worker_id = %s,
                        lease_token = %s,
                        heartbeat_at = NOW(),
                        lease_expires_at = NOW() + (%s * INTERVAL '1 second'),
                        attempt_count = attempt_count + 1,
                        started_at = NOW(),
                        completed_at = NULL,
                        failure_reason = NULL,
                        updated_at = NOW()
                    WHERE id = %s AND status = 'queued' AND attempt_count < %s
                    RETURNING attempt_count
                    """,
                    (worker_id, lease_token, self.lease_seconds, str(job["id"]), self.max_attempts),
                )
                claim = cursor.fetchone()
                if not claim:
                    conn.rollback()
                    return None

                conn.commit()
                return {
                    "id": str(job["id"]),
                    "user_id": str(job["user_id"]),
                    "project_id": str(job["project_id"]),
                    "deployment_id": str(job["deployment_id"]) if job["deployment_id"] else None,
                    "cloud": job["cloud"],
                    "region": job["region"],
                    "infrastructure_spec": job["infrastructure_spec"],
                    "worker_id": worker_id,
                    "lease_token": lease_token,
                    "attempt_count": int(claim["attempt_count"]),
                }
        except Exception as error:
            if conn:
                conn.rollback()
            raise QueueUnavailableError("Unable to claim a deployment job.") from error
        finally:
            if conn:
                conn.close()

    def heartbeat_job(self, job_id: str, worker_id: str, lease_token: str) -> bool:
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE deployment_jobs
                    SET heartbeat_at = NOW(),
                        lease_expires_at = NOW() + (%s * INTERVAL '1 second'),
                        updated_at = NOW()
                    WHERE id = %s
                      AND status = 'running'
                      AND worker_id = %s
                      AND lease_token = %s
                    """,
                    (self.lease_seconds, job_id, worker_id, lease_token),
                )
                renewed = cursor.rowcount == 1
                conn.commit()
                return renewed
        except Exception as error:
            if conn:
                conn.rollback()
            raise QueueUnavailableError("Unable to renew the deployment job lease.") from error
        finally:
            if conn:
                conn.close()

    def update_job_status(self, job_id: str, status: str, **kwargs) -> None:
        """Administrative update helper; active worker paths use fenced writes."""

        conn = None
        try:
            unsupported_fields = set(kwargs) - self._UPDATABLE_FIELDS
            if unsupported_fields:
                raise ValueError(
                    f"Unsupported deployment job update fields: {', '.join(sorted(unsupported_fields))}"
                )
            conn = self._get_connection()
            with conn.cursor() as cursor:
                fields = ["status = %s", "updated_at = NOW()"]
                params: list[Any] = [status]
                for key, value in kwargs.items():
                    fields.append(f"{key} = %s")
                    params.append(value)
                params.append(job_id)
                cursor.execute(
                    f"UPDATE deployment_jobs SET {', '.join(fields)} WHERE id = %s",
                    tuple(params),
                )
                conn.commit()
        except Exception as error:
            if conn:
                conn.rollback()
            raise QueueUnavailableError(f"Unable to update deployment job {job_id}.") from error
        finally:
            if conn:
                conn.close()
