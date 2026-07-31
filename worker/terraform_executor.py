"""Execute Terraform without ever applying an unsaved or unapproved plan."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from worker.contracts import ExecutionEnvelope
from worker.execution_gate import (
    ExecutionGateError,
    require_provider_lockfile,
    safe_extract_zip,
    sha256_file,
    summarize_plan_json,
    validate_saved_plan_gate,
    verify_file_digest,
)
from worker.interfaces import ArtifactStore


class TerraformExecutionError(RuntimeError):
    """A tool failed without exposing its potentially sensitive output."""

    def __init__(self, phase: str, exit_code: int | None = None):
        message = f"{phase} failed"
        if exit_code is not None:
            message += f" with exit code {exit_code}"
        super().__init__(message + ". Review restricted runner telemetry.")
        self.phase = phase
        self.exit_code = exit_code


class TerraformExecutor:
    def __init__(
        self,
        *,
        store: ArtifactStore,
        executor_storage_account: str,
        state_container: str,
        managed_identity_client_id: str,
        terraform_binary: str = "terraform",
        tflint_binary: str = "tflint",
        checkov_binary: str = "checkov",
        command_timeout_seconds: int = 7_200,
    ):
        self.store = store
        self.executor_storage_account = executor_storage_account
        self.state_container = state_container
        self.managed_identity_client_id = managed_identity_client_id
        self.terraform_binary = terraform_binary
        self.tflint_binary = tflint_binary
        self.checkov_binary = checkov_binary
        self.command_timeout_seconds = command_timeout_seconds

    def _environment(self, envelope: ExecutionEnvelope) -> dict[str, str]:
        allowed_names = {
            "PATH",
            "HOME",
            "LANG",
            "LC_ALL",
            "SSL_CERT_FILE",
            "HTTPS_PROXY",
            "HTTP_PROXY",
            "NO_PROXY",
        }
        environment = {
            key: value
            for key, value in os.environ.items()
            if key in allowed_names and isinstance(value, str)
        }
        environment.update(
            {
                "TF_IN_AUTOMATION": "true",
                "TF_INPUT": "false",
                "CHECKPOINT_DISABLE": "1",
                "ARM_USE_MSI": "true",
                "ARM_USE_AZUREAD": "true",
                "ARM_CLIENT_ID": self.managed_identity_client_id,
                "ARM_SUBSCRIPTION_ID": envelope.target_subscription_id,
                "ARM_TENANT_ID": envelope.target_tenant_id,
            }
        )
        return environment

    def _run(
        self,
        args: Sequence[str],
        *,
        cwd: Path,
        environment: dict[str, str],
        phase: str,
        return_stdout: bool = False,
    ) -> bytes:
        if not args or not all(isinstance(argument, str) and argument for argument in args):
            raise TerraformExecutionError(phase)
        executable = shutil.which(args[0], path=environment.get("PATH"))
        if not executable:
            raise TerraformExecutionError(f"{phase} (tool unavailable)")
        safe_args = [executable, *args[1:]]
        try:
            completed = subprocess.run(
                safe_args,
                cwd=cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=self.command_timeout_seconds,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise TerraformExecutionError(phase) from error
        if completed.returncode != 0:
            # Tool output can contain variable values, provider diagnostics, or
            # a rendered plan, so it is deliberately excluded from the error.
            raise TerraformExecutionError(phase, completed.returncode)
        return completed.stdout if return_stdout else b""

    def _terraform_version(
        self,
        *,
        terraform_root: Path,
        environment: dict[str, str],
    ) -> str:
        raw = self._run(
            [self.terraform_binary, "version", "-json"],
            cwd=terraform_root,
            environment=environment,
            phase="Terraform version check",
            return_stdout=True,
        )
        try:
            value = json.loads(raw).get("terraform_version")
        except (AttributeError, json.JSONDecodeError, UnicodeDecodeError) as error:
            raise TerraformExecutionError("Terraform version check") from error
        if not isinstance(value, str):
            raise TerraformExecutionError("Terraform version check")
        return value

    def _initialize(
        self,
        envelope: ExecutionEnvelope,
        terraform_root: Path,
        environment: dict[str, str],
    ) -> None:
        require_provider_lockfile(terraform_root)
        installed_version = self._terraform_version(
            terraform_root=terraform_root,
            environment=environment,
        )
        if installed_version != envelope.terraform_version:
            raise ExecutionGateError(
                "Requested Terraform version does not match the immutable runner image."
            )

        self._run(
            [
                self.terraform_binary,
                "init",
                "-input=false",
                "-no-color",
                "-reconfigure",
                "-lockfile=readonly",
                f"-backend-config=storage_account_name={self.executor_storage_account}",
                f"-backend-config=container_name={self.state_container}",
                f"-backend-config=key={envelope.state_key}",
                "-backend-config=use_azuread_auth=true",
                "-backend-config=use_msi=true",
                f"-backend-config=client_id={self.managed_identity_client_id}",
            ],
            cwd=terraform_root,
            environment=environment,
            phase="Terraform initialization",
        )

    def _static_checks(
        self,
        terraform_root: Path,
        environment: dict[str, str],
    ) -> None:
        checks: list[tuple[str, list[str]]] = [
            (
                "Terraform formatting check",
                [self.terraform_binary, "fmt", "-check", "-recursive", "-no-color"],
            ),
            (
                "Terraform validation",
                [self.terraform_binary, "validate", "-no-color"],
            ),
            (
                "TFLint initialization",
                [self.tflint_binary, "--init"],
            ),
            (
                "TFLint validation",
                [self.tflint_binary, "--recursive", "--format", "compact"],
            ),
            (
                "Checkov policy validation",
                [
                    self.checkov_binary,
                    "-d",
                    str(terraform_root),
                    "--quiet",
                    "--compact",
                    "--framework",
                    "terraform",
                    "--download-external-modules",
                    "false",
                ],
            ),
        ]
        for phase, args in checks:
            self._run(
                args,
                cwd=terraform_root,
                environment=environment,
                phase=phase,
            )

    def _prepare_workspace(
        self,
        envelope: ExecutionEnvelope,
        job_directory: Path,
    ) -> Path:
        bundle_path = job_directory / "bundle.zip"
        source_root = job_directory / "source"
        self.store.download_bundle(envelope.bundle, bundle_path)
        verify_file_digest(bundle_path, envelope.bundle.sha256, label="Terraform bundle")
        if bundle_path.stat().st_size != envelope.bundle.size_bytes:
            raise ExecutionGateError("Terraform bundle size does not match its contract.")
        safe_extract_zip(bundle_path, source_root)
        return source_root

    def execute(
        self,
        envelope: ExecutionEnvelope,
        *,
        job_directory: Path,
    ) -> dict[str, Any]:
        terraform_root = self._prepare_workspace(envelope, job_directory)
        environment = self._environment(envelope)
        self._initialize(envelope, terraform_root, environment)

        if envelope.operation == "plan":
            return self._plan(envelope, terraform_root, job_directory, environment)
        return self._apply(envelope, terraform_root, job_directory, environment)

    def _plan(
        self,
        envelope: ExecutionEnvelope,
        terraform_root: Path,
        job_directory: Path,
        environment: dict[str, str],
    ) -> dict[str, Any]:
        self._static_checks(terraform_root, environment)
        private_directory = job_directory / "private"
        private_directory.mkdir(mode=0o700)
        plan_path = private_directory / "approved-input.tfplan"
        self._run(
            [
                self.terraform_binary,
                "plan",
                "-input=false",
                "-no-color",
                "-lock=true",
                "-lock-timeout=5m",
                f"-out={plan_path}",
            ],
            cwd=terraform_root,
            environment=environment,
            phase="Terraform saved-plan creation",
        )
        if not plan_path.is_file():
            raise TerraformExecutionError("Terraform saved-plan creation")
        os.chmod(plan_path, 0o600)

        raw_plan_json = self._run(
            [self.terraform_binary, "show", "-json", str(plan_path)],
            cwd=terraform_root,
            environment=environment,
            phase="Terraform plan summarization",
            return_stdout=True,
        )
        summary = summarize_plan_json(raw_plan_json)
        del raw_plan_json

        plan_sha256 = sha256_file(plan_path)
        reference = self.store.save_private_plan(
            envelope,
            plan_path,
            plan_sha256,
        )
        history_result = {
            **envelope.safe_context(),
            "status": "planned",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "bundle_sha256": envelope.bundle.sha256,
            "plan_sha256": reference.sha256,
            "summary": summary,
        }
        history_artifact = self.store.save_sanitized_result(
            envelope,
            history_result,
        )
        return {
            **history_result,
            "history_artifact": asdict(history_artifact),
            # This control-plane handle is deliberately added only after the
            # user-visible history document has been persisted.
            "plan_handle": asdict(reference),
        }

    def _apply(
        self,
        envelope: ExecutionEnvelope,
        terraform_root: Path,
        job_directory: Path,
        environment: dict[str, str],
    ) -> dict[str, Any]:
        if envelope.saved_plan is None:
            raise ExecutionGateError("Apply is missing a saved plan.")
        private_directory = job_directory / "private"
        private_directory.mkdir(mode=0o700)
        plan_path = private_directory / "approved-input.tfplan"
        self.store.download_private_plan(envelope.saved_plan, plan_path)
        os.chmod(plan_path, 0o600)
        validate_saved_plan_gate(envelope, plan_path)

        # Supplying the path is mandatory. This runner has no code path that
        # invokes `terraform apply` against a directory or creates a fresh plan.
        self._run(
            [
                self.terraform_binary,
                "apply",
                "-input=false",
                "-no-color",
                "-lock=true",
                "-lock-timeout=5m",
                str(plan_path),
            ],
            cwd=terraform_root,
            environment=environment,
            phase="Terraform saved-plan apply",
        )
        history_result = {
            **envelope.safe_context(),
            "status": "applied",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "bundle_sha256": envelope.bundle.sha256,
            "applied_plan_sha256": envelope.saved_plan.sha256,
            "approval_id": envelope.approval.approval_id if envelope.approval else None,
        }
        history_artifact = self.store.save_sanitized_result(
            envelope,
            history_result,
        )
        return {
            **history_result,
            "history_artifact": asdict(history_artifact),
        }
