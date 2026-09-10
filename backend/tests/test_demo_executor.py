"""Tests for DemoRepositoryCheckExecutor."""

import os
from pathlib import Path
import tempfile
import pytest

from backend import config
from backend.services.demo_executor import DemoRepositoryCheckExecutor
from backend.services.repository_checks import RepositoryIsolationRequest, verify_isolation_attestation


def test_demo_executor_fails_closed_in_production(monkeypatch):
    monkeypatch.setattr(config, "IS_PRODUCTION", True)
    monkeypatch.setattr(config, "ZEROOPS_DEMO_EXECUTOR", True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        with pytest.raises(RuntimeError, match="cannot be instantiated when APP_ENV=production"):
            DemoRepositoryCheckExecutor(tmp_dir)


def test_demo_executor_requires_explicit_flag(monkeypatch):
    monkeypatch.setattr(config, "IS_PRODUCTION", False)
    monkeypatch.setattr(config, "ZEROOPS_DEMO_EXECUTOR", False)

    with tempfile.TemporaryDirectory() as tmp_dir:
        with pytest.raises(RuntimeError, match="requires ZEROOPS_DEMO_EXECUTOR=true"):
            DemoRepositoryCheckExecutor(tmp_dir)


def test_demo_executor_attestation_verifies(monkeypatch):
    monkeypatch.setattr(config, "IS_PRODUCTION", False)
    monkeypatch.setattr(config, "ZEROOPS_DEMO_EXECUTOR", True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        executor = DemoRepositoryCheckExecutor(tmp_dir)
        request = RepositoryIsolationRequest(
            stage="unit_tests",
            source_revision="a" * 40,
            source_digest="b" * 64,
        )
        attestation = executor.attest(request)
        verification = verify_isolation_attestation(attestation, request)

        assert verification.valid is True
        assert "verified" in verification.reason.lower()
        assert attestation.disposable is True
        assert attestation.fresh_source is True
        assert attestation.worker_filesystem_access is False
        assert attestation.database_access is False
        assert attestation.key_vault_access is False
        assert attestation.network_policy == "none"


def test_demo_executor_tool_resolution(monkeypatch):
    monkeypatch.setattr(config, "IS_PRODUCTION", False)
    monkeypatch.setattr(config, "ZEROOPS_DEMO_EXECUTOR", True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        executor = DemoRepositoryCheckExecutor(tmp_dir)
        request = RepositoryIsolationRequest(
            stage="unit_tests",
            source_revision="a" * 40,
            source_digest="b" * 64,
        )
        attestation = executor.attest(request)

        # Allowlisted tools
        assert executor.resolve_tool("python", attestation=attestation) is not None
        # Disallowed dangerous tools
        assert executor.resolve_tool("bash", attestation=attestation) is None
        assert executor.resolve_tool("curl", attestation=attestation) is None
        assert executor.resolve_tool("powershell", attestation=attestation) is None


def test_demo_executor_executes_allowlisted_command_and_sanitizes_env(monkeypatch):
    monkeypatch.setattr(config, "IS_PRODUCTION", False)
    monkeypatch.setattr(config, "ZEROOPS_DEMO_EXECUTOR", True)
    monkeypatch.setenv("AZURE_SECRET_LEAK", "should_not_reach_child")
    monkeypatch.setenv("JWT_SECRET_LEAK", "should_not_reach_child")

    with tempfile.TemporaryDirectory() as tmp_dir:
        executor = DemoRepositoryCheckExecutor(tmp_dir)
        request = RepositoryIsolationRequest(
            stage="unit_tests",
            source_revision="a" * 40,
            source_digest="b" * 64,
        )
        attestation = executor.attest(request)

        result = executor.execute(
            ["python", "-c", "import os; print('ENV_KEYS:' + ','.join(os.environ.keys()))"],
            relative_cwd=".",
            timeout_seconds=30,
            attestation=attestation,
        )

        assert result.returncode == 0
        assert "ENV_KEYS:" in result.stdout
        assert "AZURE_SECRET_LEAK" not in result.stdout
        assert "JWT_SECRET_LEAK" not in result.stdout


def test_demo_executor_captures_failure_exit_code(monkeypatch):
    monkeypatch.setattr(config, "IS_PRODUCTION", False)
    monkeypatch.setattr(config, "ZEROOPS_DEMO_EXECUTOR", True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        executor = DemoRepositoryCheckExecutor(tmp_dir)
        request = RepositoryIsolationRequest(
            stage="unit_tests",
            source_revision="a" * 40,
            source_digest="b" * 64,
        )
        attestation = executor.attest(request)

        result = executor.execute(
            ["python", "-c", "import sys; sys.stderr.write('AssertionError: test failed\\n'); sys.exit(1)"],
            relative_cwd=".",
            timeout_seconds=30,
            attestation=attestation,
        )

        assert result.returncode == 1
        assert "AssertionError: test failed" in result.stderr


def test_demo_executor_blocks_directory_escape(monkeypatch):
    monkeypatch.setattr(config, "IS_PRODUCTION", False)
    monkeypatch.setattr(config, "ZEROOPS_DEMO_EXECUTOR", True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        executor = DemoRepositoryCheckExecutor(tmp_dir)
        request = RepositoryIsolationRequest(
            stage="unit_tests",
            source_revision="a" * 40,
            source_digest="b" * 64,
        )
        attestation = executor.attest(request)

        result = executor.execute(
            ["python", "-c", "print('hello')"],
            relative_cwd="../escaped_directory",
            timeout_seconds=30,
            attestation=attestation,
        )

        assert result.returncode == 1
        assert "escaped the repository root" in result.stderr
