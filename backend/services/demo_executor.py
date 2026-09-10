"""Safe development-only repository check executor for live demonstrations.

This executor implements the RepositoryCheckExecutor protocol for non-production
demonstrations (e.g. university project presentation). It is strictly gated by
ZEROOPS_DEMO_EXECUTOR=true and APP_ENV != "production". Production environments
always fail closed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Sequence
import uuid

from backend import config
from backend.services.redaction import redact_sensitive_text
from backend.services.repository_checks import (
    CommandExecution,
    RepositoryCheckExecutor,
    RepositoryIsolationAttestation,
    RepositoryIsolationRequest,
)

_ALLOWLISTED_TOOLS = frozenset({
    "python",
    "python3",
    "pytest",
    "node",
    "npm",
    "npx",
    "yarn",
    "pnpm",
    "ruff",
    "flake8",
    "black",
    "eslint",
    "tsc",
})

_SENSITIVE_ENV_PREFIXES = (
    "AZURE_",
    "ARM_",
    "DATABASE_",
    "DB_",
    "JWT_",
    "SECRET_",
    "KEYVAULT_",
    "SMTP_",
    "TWILIO_",
    "STRIPE_",
    "OPENAI_",
    "ANTHROPIC_",
    "GITHUB_ACCESS_TOKEN",
    "WORKER_EVENT_TOKEN",
)

_MAX_CAPTURE_BYTES = 32_000


class DemoRepositoryCheckExecutor:
    """Bounded, safe executor for local and demo repository validation."""

    def __init__(self, repo_path: str | os.PathLike[str]) -> None:
        if config.IS_PRODUCTION:
            raise RuntimeError(
                "DemoRepositoryCheckExecutor cannot be instantiated when APP_ENV=production."
            )
        if not config.ZEROOPS_DEMO_EXECUTOR:
            raise RuntimeError(
                "DemoRepositoryCheckExecutor requires ZEROOPS_DEMO_EXECUTOR=true."
            )
        self.repo_path = Path(repo_path).resolve(strict=True)

    def attest(self, request: RepositoryIsolationRequest) -> RepositoryIsolationAttestation:
        """Issue an in-memory attestation for this check stage."""
        now = datetime.now(timezone.utc)
        return RepositoryIsolationAttestation(
            isolation_id=f"demo-iso-{uuid.uuid4().hex[:16]}",
            stage=request.stage,
            source_revision=request.source_revision,
            source_digest=request.source_digest,
            issued_at=now,
            expires_at=now + timedelta(seconds=600),
            disposable=True,
            fresh_source=True,
            worker_filesystem_access=False,
            database_access=False,
            key_vault_access=False,
            imds_access=False,
            network_policy="none",
            allowed_network_destinations=(),
        )

    def resolve_tool(
        self,
        tool: str,
        *,
        attestation: RepositoryIsolationAttestation,
    ) -> str | None:
        """Resolve allowlisted executables from host environment."""
        normalized = tool.strip().lower()
        if normalized not in _ALLOWLISTED_TOOLS:
            return None

        # Check for exact executable
        found = shutil.which(normalized)
        if found:
            return found

        # If pytest was requested as tool, fallback to python if python is available
        if normalized == "pytest":
            python_path = shutil.which("python") or shutil.which("python3")
            if python_path:
                return python_path

        return None

    def execute(
        self,
        command: Sequence[str],
        *,
        relative_cwd: str,
        timeout_seconds: int,
        attestation: RepositoryIsolationAttestation,
    ) -> CommandExecution:
        """Execute one allowlisted command in the repository workspace."""
        if not command:
            return CommandExecution(returncode=1, stderr="Empty command cannot be executed.")

        raw_tool = Path(command[0]).name.lower()
        # Strip Windows executable extensions (.exe, .cmd, .bat)
        tool_name = re.sub(r"\.(exe|cmd|bat|ps1)$", "", raw_tool)
        if tool_name not in _ALLOWLISTED_TOOLS:
            return CommandExecution(
                returncode=1,
                stderr=f"Tool '{command[0]}' is not in the demo executor allowlist.",
            )

        # Resolve working directory safely within repository
        try:
            cwd_path = (self.repo_path / relative_cwd).resolve()
            if not cwd_path.is_relative_to(self.repo_path):
                return CommandExecution(
                    returncode=1,
                    stderr="Working directory escaped the repository root.",
                )
        except Exception as err:
            return CommandExecution(returncode=1, stderr=f"Invalid working directory: {err}")

        # Build clean execution environment without credentials
        clean_env = {
            key: value
            for key, value in os.environ.items()
            if not any(key.upper().startswith(prefix) for prefix in _SENSITIVE_ENV_PREFIXES)
        }
        clean_env.update({
            "CI": "true",
            "NO_COLOR": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        })

        effective_timeout = max(1, min(timeout_seconds, 180))
        cmd_list = list(command)

        try:
            completed = subprocess.run(
                cmd_list,
                cwd=str(cwd_path),
                env=clean_env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=effective_timeout,
                check=False,
                shell=False,
            )
            raw_stdout = completed.stdout or ""
            raw_stderr = completed.stderr or ""
            stdout_truncated = len(raw_stdout) > _MAX_CAPTURE_BYTES
            stderr_truncated = len(raw_stderr) > _MAX_CAPTURE_BYTES

            safe_stdout = redact_sensitive_text(raw_stdout[:_MAX_CAPTURE_BYTES])
            safe_stderr = redact_sensitive_text(raw_stderr[:_MAX_CAPTURE_BYTES])

            return CommandExecution(
                returncode=completed.returncode,
                stdout=safe_stdout,
                stderr=safe_stderr,
                timed_out=False,
                stdout_truncated=stdout_truncated,
                stderr_truncated=stderr_truncated,
            )
        except subprocess.TimeoutExpired as exc:
            out = redact_sensitive_text(str(exc.stdout or "")[:_MAX_CAPTURE_BYTES])
            err = redact_sensitive_text(str(exc.stderr or "")[:_MAX_CAPTURE_BYTES])
            return CommandExecution(
                returncode=124,
                stdout=out,
                stderr=f"Command timed out after {effective_timeout}s. {err}",
                timed_out=True,
            )
        except Exception as err:
            return CommandExecution(
                returncode=1,
                stderr=redact_sensitive_text(f"Execution error: {err}"),
            )
