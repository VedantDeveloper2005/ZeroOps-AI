#!/usr/bin/env python3
"""ZeroOps AI - Demo Readiness Pre-Flight Verification Script.

Non-destructively checks backend, database, GitHub, Azure, worker, and security
tool readiness for the university demo on September 17, 2026.
"""

import asyncio
import os
import sys
import shutil
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_env_files():
    """Load key-value pairs from .env or .env.local without overriding active environment."""
    # Ensure demo development environment defaults unless explicitly overridden in process environment
    if "APP_ENV" not in os.environ:
        os.environ["APP_ENV"] = "development"
    if "ZEROOPS_DEMO_EXECUTOR" not in os.environ:
        os.environ["ZEROOPS_DEMO_EXECUTOR"] = "true"

    # Refresh PATH with standard user tool installation directories
    home = Path.home()
    for extra_path in (
        home / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links",
        home / "AppData" / "Roaming" / "Python" / "Python314" / "Scripts",
        home / "AppData" / "Local" / "Programs" / "Python" / "Python313" / "Scripts",
        home / ".local" / "bin",
    ):
        if extra_path.is_dir() and str(extra_path) not in os.environ.get("PATH", ""):
            os.environ["PATH"] = str(extra_path) + os.pathsep + os.environ.get("PATH", "")

    for filename in [".env", ".env.local"]:
        env_file = PROJECT_ROOT / filename
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k not in os.environ:
                        os.environ[k] = v


class DemoReadinessChecker:
    def __init__(self):
        self.results = []
        self.blockers = []
        self.warnings = []

    def record(self, component: str, status: str, detail: str, is_blocker: bool = False):
        self.results.append((component, status, detail))
        if status == "FAIL":
            if is_blocker:
                self.blockers.append(f"{component}: {detail}")
            else:
                self.warnings.append(f"{component}: {detail}")
        elif status == "WARN":
            self.warnings.append(f"{component}: {detail}")

    def check_environment(self):
        app_env = os.getenv("APP_ENV")
        if not app_env:
            self.record("Environment", "FAIL", "APP_ENV is unset. Set APP_ENV=development for demo.", is_blocker=True)
            os.environ["APP_ENV"] = "development"
        elif app_env == "production":
            self.record("Environment", "WARN", "APP_ENV=production. For the demo, set APP_ENV=development and ZEROOPS_DEMO_EXECUTOR=true.")
        else:
            self.record("Environment", "PASS", f"APP_ENV={app_env}")

    async def check_database(self):
        try:
            from backend import config
            db_url = getattr(config, "DATABASE_URL", "")
            if not db_url:
                self.record("Database", "FAIL", "DATABASE_URL is not set in config", is_blocker=True)
                return

            from backend.database import async_engine
            from sqlalchemy import text

            if not async_engine:
                self.record("Database", "FAIL", "SQLAlchemy async engine could not be initialized", is_blocker=True)
                return

            async with asyncio.timeout(4):
                async with async_engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
            self.record("Database", "PASS", "Connected to PostgreSQL database", is_blocker=True)
        except Exception as exc:
            err_msg = str(exc).strip() or repr(exc)
            self.record("Database", "FAIL", f"PostgreSQL connection failed: {err_msg}", is_blocker=True)

    def check_backend(self):
        backend_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000/health")
        try:
            req = urllib.request.Request(backend_url, headers={"User-Agent": "ZeroOps-DemoReadiness/1.0"})
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    self.record("Backend", "PASS", f"Reachable at {backend_url} (HTTP 200)", is_blocker=True)
                else:
                    self.record("Backend", "FAIL", f"HTTP {resp.status} from {backend_url}", is_blocker=True)
        except urllib.error.URLError:
            self.record("Backend", "WARN", f"Local backend server not responding at {backend_url} (start before presentation)")
        except Exception as exc:
            self.record("Backend", "WARN", f"Could not query backend: {exc}")

    def check_worker(self):
        try:
            from backend import config
            if getattr(config, "ZEROOPS_DEMO_EXECUTOR", False):
                self.record("Worker", "PASS", "Demo executor enabled (temporary local directory isolation for development/demo only)")
            else:
                self.record("Worker", "PASS", "Standard worker pipeline configured")
        except Exception as exc:
            self.record("Worker", "FAIL", f"Worker configuration error: {exc}", is_blocker=True)

    def check_github_config(self):
        client_id = os.getenv("GITHUB_CLIENT_ID") or os.getenv("GITHUB_APP_CLIENT_ID")
        client_secret = os.getenv("GITHUB_CLIENT_SECRET") or os.getenv("GITHUB_APP_CLIENT_SECRET")
        webhook_secret = os.getenv("GITHUB_WEBHOOK_SECRET")

        missing = []
        if not client_id:
            missing.append("GITHUB_CLIENT_ID")
        if not client_secret:
            missing.append("GITHUB_CLIENT_SECRET")
        if not webhook_secret:
            missing.append("GITHUB_WEBHOOK_SECRET")

        if not missing:
            self.record("GitHub", "PASS", "OAuth and Webhook secrets configured", is_blocker=True)
        else:
            self.record("GitHub", "WARN", f"Missing environment variables: {', '.join(missing)} (required for live GitHub push demo)")

    def check_azure_auth(self):
        tenant_id = os.getenv("AZURE_TENANT_ID")
        client_id = os.getenv("AZURE_CLIENT_ID")
        client_secret = os.getenv("AZURE_CLIENT_SECRET")
        subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")

        has_env_creds = all([tenant_id, client_id, client_secret, subscription_id])

        if has_env_creds:
            self.record("Azure Auth", "PASS", f"Service Principal configured (Subscription: {subscription_id[:8]}...)", is_blocker=True)
            return

        # Check Azure CLI login if available
        az_cli = shutil.which("az") or shutil.which("az.cmd")
        cli_authenticated = False
        if az_cli:
            try:
                res = subprocess.run(
                    [az_cli, "account", "show", "--query", "id", "-o", "tsv"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=3,
                )
                if res.returncode == 0 and res.stdout.strip():
                    cli_authenticated = True
                    self.record("Azure Auth", "PASS", f"Azure CLI logged in (Subscription: {res.stdout.strip()[:8]}...)", is_blocker=True)
                    return
            except Exception:
                pass

        self.record("Azure Auth", "FAIL", "No Azure Service Principal or az CLI login found", is_blocker=True)

    def check_app_service_target(self):
        rg = os.getenv("AZURE_RESOURCE_GROUP", os.getenv("AZURE_DEFAULT_RESOURCE_GROUP"))
        app_name = os.getenv("AZURE_APP_SERVICE_NAME")
        if rg:
            self.record("App Service Target", "PASS", f"Resource group: {rg}" + (f", App: {app_name}" if app_name else ""))
        else:
            self.record("App Service Target", "WARN", "AZURE_RESOURCE_GROUP not preset (will select from Azure connection in UI)")

    def check_scanners(self):
        from backend.services.security_scanner import _find_executable
        scanners = ["gitleaks", "semgrep", "trivy"]
        for tool in scanners:
            path = _find_executable(tool)
            if path:
                self.record(tool.capitalize(), "PASS", f"Executable found at {path}")
            else:
                self.record(tool.capitalize(), "WARN", f"Executable not on PATH (pipeline will report 'unavailable' without blocking)")

    def check_demo_executor(self):
        from backend import config
        if config.IS_PRODUCTION:
            self.record("Demo Executor", "FAIL", "APP_ENV is production; demo executor is forbidden", is_blocker=True)
        elif config.ZEROOPS_DEMO_EXECUTOR:
            self.record("Demo Executor", "PASS", "ZEROOPS_DEMO_EXECUTOR=true (development mode active)")
        else:
            self.record("Demo Executor", "WARN", "ZEROOPS_DEMO_EXECUTOR=false (set ZEROOPS_DEMO_EXECUTOR=true for presentation)")

    async def run_all(self) -> int:
        load_env_files()

        print("=" * 60)
        print("         ZEROOPS DEMO READINESS PRE-FLIGHT CHECK")
        print("=" * 60)

        self.check_environment()
        await self.check_database()
        self.check_backend()
        self.check_worker()
        self.check_github_config()
        self.check_azure_auth()
        self.check_app_service_target()
        self.check_scanners()
        self.check_demo_executor()

        for comp, status, detail in self.results:
            tag = f"[{status}]"
            print(f"{tag:<8} {comp:<20} - {detail}")

        print("=" * 60)
        if not self.blockers:
            if not self.warnings:
                print("STATUS: READY FOR DEMO")
            else:
                print("STATUS: READY FOR DEMO (with non-blocking warnings)")
            print("=" * 60)
            return 0
        else:
            print("STATUS: BLOCKED")
            print("\nCritical Blockers to resolve before September 17 presentation:")
            for b in self.blockers:
                print(f"  * {b}")
            print("=" * 60)
            return 1


if __name__ == "__main__":
    checker = DemoReadinessChecker()
    exit_code = asyncio.run(checker.run_all())
    sys.exit(exit_code)
