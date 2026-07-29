"""Long-running deployment worker entry point."""

from __future__ import annotations

import signal
import socket
import sys
import threading
import time
import uuid
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from worker.azure import is_azure_cli_available
from worker.health import WorkerHealth, start_health_server
from worker.queue import PostgresJobQueue, QueueUnavailableError
from worker.terraform_runner import TerraformRunner

try:
    from backend import config
except ImportError:
    import config


keep_running = True


def handle_sigterm(_signum, _frame):
    global keep_running
    print("\n[Worker] Termination signal received. Finishing the active operation.", flush=True)
    keep_running = False


def _interruptible_wait(seconds: int) -> None:
    for _ in range(seconds):
        if not keep_running:
            return
        time.sleep(1)


def main() -> int:
    global keep_running
    signal.signal(signal.SIGINT, handle_sigterm)
    signal.signal(signal.SIGTERM, handle_sigterm)

    worker_id = f"worker-{socket.gethostname()}-{uuid.uuid4().hex[:6]}"
    print("=" * 60)
    print(f"ZeroOps AI deployment worker {worker_id} starting")
    print("=" * 60)

    if not config.DATABASE_URL:
        print("[Worker Fatal] DATABASE_URL is not available from Azure Key Vault.", flush=True)
        return 1
    if not is_azure_cli_available():
        print("[Worker Fatal] Azure CLI is required but is not available on PATH.", flush=True)
        return 1

    health = WorkerHealth()
    health_server = start_health_server(health, port=config.WORKER_HEALTH_PORT)
    queue = PostgresJobQueue(
        database_url=config.DATABASE_URL,
        lease_seconds=config.WORKER_LEASE_SECONDS,
        max_attempts=config.WORKER_MAX_ATTEMPTS,
        recovery_batch_size=config.WORKER_RECOVERY_BATCH_SIZE,
        ssl_enabled=config.DB_SSL_ENABLED,
        ssl_verify=config.DB_SSL_VERIFY,
        ssl_root_cert=config.DB_SSL_ROOT_CERT,
    )
    runner = TerraformRunner(
        db_url=config.DATABASE_URL,
        worker_id=worker_id,
        ssl_enabled=config.DB_SSL_ENABLED,
        ssl_verify=config.DB_SSL_VERIFY,
        ssl_root_cert=config.DB_SSL_ROOT_CERT,
    )

    print(
        f"[Worker] Polling every {config.WORKER_POLL_INTERVAL_SECONDS}s "
        f"with a {config.WORKER_LEASE_SECONDS}s lease.",
        flush=True,
    )

    try:
        while keep_running:
            try:
                job = queue.pop_job(worker_id=worker_id)
                health.mark_ready()
            except QueueUnavailableError as error:
                health.mark_error(str(error))
                print(f"[Worker] Queue unavailable: {error}", flush=True)
                _interruptible_wait(config.WORKER_POLL_INTERVAL_SECONDS)
                continue

            if not job:
                _interruptible_wait(config.WORKER_POLL_INTERVAL_SECONDS)
                continue

            job_id = str(job["id"])
            lease_token = str(job["lease_token"])
            health.mark_ready(active_job=job_id)
            print(
                f"[Worker] Claimed job {job_id} (attempt {job['attempt_count']}).",
                flush=True,
            )

            heartbeat_stop = threading.Event()
            lease_lost = threading.Event()

            def renew_lease() -> None:
                while not heartbeat_stop.wait(config.WORKER_HEARTBEAT_SECONDS):
                    try:
                        renewed = queue.heartbeat_job(job_id, worker_id, lease_token)
                    except QueueUnavailableError as error:
                        lease_lost.set()
                        health.mark_error(str(error), active_job=job_id)
                        print(f"[Worker] Lease heartbeat failed for {job_id}: {error}", flush=True)
                        return
                    if not renewed:
                        lease_lost.set()
                        health.mark_error(
                            "This worker no longer owns the active deployment lease.",
                            active_job=job_id,
                        )
                        print(f"[Worker] Lease ownership was lost for {job_id}.", flush=True)
                        return
                    health.mark_ready(active_job=job_id)

            heartbeat_thread = threading.Thread(
                target=renew_lease,
                name=f"lease-{job_id}",
                daemon=True,
            )
            heartbeat_thread.start()
            try:
                succeeded = runner.execute_job(
                    job,
                    lease_guard=lambda: not lease_lost.is_set(),
                )
                if lease_lost.is_set():
                    print(
                        f"[Worker] Job {job_id} ended after its lease was lost; "
                        "fenced queue writes were ignored.",
                        flush=True,
                    )
                elif not succeeded:
                    print(f"[Worker] Job {job_id} recorded a failed release.", flush=True)
            except Exception as error:
                print(f"[Worker] Unexpected job error for {job_id}: {error}", flush=True)
            finally:
                heartbeat_stop.set()
                heartbeat_thread.join(timeout=max(config.WORKER_HEARTBEAT_SECONDS, 1) + 1)
                if lease_lost.is_set():
                    health.mark_error(
                        "The previous deployment lease was lost; reconciliation is required."
                    )
                else:
                    health.mark_ready()

        print("[Worker] Polling loop stopped cleanly.", flush=True)
        return 0
    finally:
        health_server.shutdown()
        health_server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
