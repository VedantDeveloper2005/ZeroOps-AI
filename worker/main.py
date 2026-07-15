import os
import time
from dotenv import load_dotenv
from worker.queue import PostgresJobQueue
from worker.terraform_runner import TerraformRunner
from worker.azure import is_azure_cli_available, check_azure_login
from worker.health import start_health_server

def main():
    # Load environment variables
    # If worker is launched in repository root, load .env
    load_dotenv()
    
    db_url = os.getenv("DATABASE_URL")
    backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")
    
    print("=" * 60)
    print("ZeroOps AI Decoupled Terraform Worker Starting...")
    print("=" * 60)
    
    if not db_url:
        print("[Worker Fatal] DATABASE_URL is not set. Exiting.")
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
    runner = TerraformRunner(db_url=db_url, backend_url=backend_url)

    print("[Worker] Polling queue for jobs...", flush=True)
    
    try:
        while True:
            # Check for next job
            job = queue.pop_job()
            if job:
                print(f"[Worker] Picked up deployment job: {job['id']}")
                try:
                    runner.execute_job(job)
                except Exception as e:
                    print(f"[Worker Exception] Job {job['id']} execution failed: {e}")
            else:
                # Wait 5 seconds before polling again
                time.sleep(5)
    except KeyboardInterrupt:
        print("\n[Worker] KeyboardInterrupt detected. Stopping worker loop.")
    except Exception as e:
        print(f"[Worker Fatal] Unexpected loop crash: {e}")

if __name__ == "__main__":
    main()
