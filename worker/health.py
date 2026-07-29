"""Liveness and readiness endpoints for the deployment worker."""

from __future__ import annotations

import http.server
import json
import threading
from datetime import datetime, timezone


class WorkerHealth:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ready = False
        self._last_error: str | None = "The worker has not completed its first queue poll."
        self._last_queue_poll: str | None = None
        self._active_job: str | None = None

    def mark_ready(self, *, active_job: str | None = None) -> None:
        with self._lock:
            self._ready = True
            self._last_error = None
            self._last_queue_poll = datetime.now(timezone.utc).isoformat()
            self._active_job = active_job

    def mark_error(self, message: str, *, active_job: str | None = None) -> None:
        with self._lock:
            self._ready = False
            self._last_error = message
            self._active_job = active_job

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "status": "ready" if self._ready else "not_ready",
                "last_queue_poll": self._last_queue_poll,
                "active_job": self._active_job,
                "detail": self._last_error,
            }


def start_health_server(
    state: WorkerHealth,
    port: int = 8085,
) -> http.server.ThreadingHTTPServer:
    """Start a lightweight health server in a daemon thread."""

    class HealthHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/health", "/healthz"):
                status_code = 200
                body = {"status": "alive"}
            elif self.path in ("/ready", "/readyz"):
                body = state.snapshot()
                status_code = 200 if body["status"] == "ready" else 503
            else:
                self.send_response(404)
                self.end_headers()
                return

            encoded = json.dumps(body).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, _format, *_args):
            return

    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"[Health Server] Liveness and readiness endpoints are on port {port}.", flush=True)
    return server
