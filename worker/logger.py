import os
import requests

class WorkerLogger:
    def __init__(self, deploy_id: str, backend_url: str = None):
        self.deploy_id = deploy_id
        self.backend_url = backend_url or os.getenv("BACKEND_URL", "http://localhost:8000")
        self.line_number = 0

    def log(self, message: str, level: str = "INFO"):
        self.line_number += 1
        level = level.upper()
        # Print locally
        print(f"[{level}] {message}", flush=True)
        
        # Post callback to FastAPI events endpoint
        if self.deploy_id:
            try:
                payload = {
                    "type": "log",
                    "text": message,
                    "lineType": level.lower(),
                    "line_number": self.line_number
                }
                requests.post(
                    f"{self.backend_url}/api/deployments/{self.deploy_id}/events",
                    json=payload,
                    timeout=5
                )
            except Exception as e:
                print(f"[Logger Exception] Failed to send log callback: {e}", flush=True)

    def update_stage(self, stage_id: int, status: str, duration: str = "", label: str = ""):
        # Status can be: completed, active, pending
        # Send stage progress update callback to FastAPI
        if self.deploy_id:
            try:
                payload = {
                    "type": "stage",
                    "id": stage_id,
                    "status": status,
                    "duration": duration,
                    "label": label
                }
                requests.post(
                    f"{self.backend_url}/api/deployments/{self.deploy_id}/events",
                    json=payload,
                    timeout=5
                )
            except Exception as e:
                print(f"[Logger Exception] Failed to send stage callback: {e}", flush=True)

    def update_status(self, status: str, failure_reason: str = None):
        # status can be: running, failed, etc.
        if self.deploy_id:
            try:
                payload = {
                    "type": "status",
                    "status": status,
                    "failure_reason": failure_reason
                }
                requests.post(
                    f"{self.backend_url}/api/deployments/{self.deploy_id}/events",
                    json=payload,
                    timeout=5
                )
            except Exception as e:
                print(f"[Logger Exception] Failed to send status callback: {e}", flush=True)
