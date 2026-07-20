import time
import signal
import sys
import uuid
import socket
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from worker.queue import PostgresJobQueue
from worker.terraform_runner import TerraformRunner
from worker.azure import is_azure_cli_available, check_azure_login
from worker.health import start_health_server

try:
    from backend import config
except ImportError:
    import config

# Global keep_running flag for graceful shutdown
keep_running = True

def handle_sigterm(signum, frame):
    global keep_running
    print("\n[Worker] Termination signal received. Shutting down gracefully...", flush=True)
    keep_running = False

def main():
    global keep_running
    # Register signal handlers
    signal.signal(signal.SIGINT, handle_sigterm)
    signal.signal(signal.SIGTERM, handle_sigterm)
    
    db_url = config.DATABASE_URL
    poll_interval = config.WORKER_POLL_INTERVAL_SECONDS
    
    # Generate unique Worker ID
    worker_id = f"worker-{socket.gethostname()}-{uuid.uuid4().hex[:6]}"
    
    print("=" * 60)
    print(f"ZeroOps AI Decoupled Terraform Worker {worker_id} Starting...")
    print("=" * 60)
    
    if not db_url:
        print("[Worker Fatal] DATABASE_URL is not configured in Azure Key Vault. Exiting.")
        return

    # Check Azure CLI availability
    if not is_azure_cli_available():
        print("[Worker Warning] Terraform worker requires 'az' CLI on PATH for subscription deployments.")
    else:
        print("[Worker Info] Azure CLI detected.")
        if check_azure_login():
            print("[Worker Info] Azure session is logged in.")
        else:
            print("[Worker Warning] No active Azure CLI session. Run 'az login' to authenticate.")

    # Start health server
    start_health_server(port=8085)

    # Initialize queue and runner
    queue = PostgresJobQueue(database_url=db_url)
    runner = TerraformRunner(db_url=db_url, worker_id=worker_id)

    print(f"[Worker] Polling queue for jobs (every {poll_interval}s)...", flush=True)
    
    try:
        while keep_running:
            # Check for next job
            # Pass worker_id to queue so we lock the job under this worker
            job = queue.pop_job(worker_id=worker_id)
            if job:
                print(f"[Worker] Picked up deployment job: {job['id']}")
                try:
                    runner.execute_job(job)
                except Exception as e:
                    print(f"[Worker Exception] Job {job['id']} execution failed: {e}")
            else:
                # Wait poll_interval seconds before polling again, checking shutdown flag
                for _ in range(poll_interval):
                    if not keep_running:
                        break
                    time.sleep(1)
        print("[Worker] Loop stopped cleanly.")
    except Exception as e:
        print(f"[Worker Fatal] Unexpected loop crash: {e}")

if __name__ == "__main__":
    main()
