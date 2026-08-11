import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.services import repository_checks


_SOURCE_REVISION = "a" * 40
_SOURCE_DIGEST = "b" * 64


def _which(name: str) -> str:
    return f"/tools/{name}"


def _success_runner(command, cwd, timeout, attestation):
    assert isinstance(command, list)
    assert timeout > 0
    assert not attestation.worker_filesystem_access
    assert not attestation.database_access
    assert not attestation.key_vault_access
    assert not attestation.imds_access
    return repository_checks.CommandExecution(returncode=0, stdout="success")


class _AttestedExecutor:
    def __init__(self, *, runner=_success_runner, which=_which, attestation_factory=None):
        self.runner = runner
        self.which = which
        self.attestation_factory = attestation_factory
        self.attest_requests = []
        self.resolve_calls = []
        self.executions = []

    def attest(self, request):
        self.attest_requests.append(request)
        now = datetime.now(timezone.utc)
        network_policy = "restricted" if request.stage == "dependency_installation" else "none"
        attestation = repository_checks.RepositoryIsolationAttestation(
            isolation_id="sandbox-test-0001",
            stage=request.stage,
            source_revision=request.source_revision,
            source_digest=request.source_digest,
            issued_at=now,
            expires_at=now + timedelta(seconds=2_000),
            disposable=True,
            fresh_source=True,
            worker_filesystem_access=False,
            database_access=False,
            key_vault_access=False,
            imds_access=False,
            network_policy=network_policy,
            allowed_network_destinations=("registry.example.com",) if network_policy == "restricted" else (),
        )
        return self.attestation_factory(attestation, request) if self.attestation_factory else attestation

    def resolve_tool(self, tool, *, attestation):
        self.resolve_calls.append((tool, attestation.isolation_id))
        return self.which(tool)

    def execute(self, command, *, relative_cwd, timeout_seconds, attestation):
        self.executions.append((list(command), relative_cwd, timeout_seconds, attestation.isolation_id))
        return self.runner(command, relative_cwd, timeout_seconds, attestation)


def _run_check(stage, repo_path, *, executor=None, runner=_success_runner, which=_which, **kwargs):
    selected_executor = executor or _AttestedExecutor(runner=runner, which=which)
    return repository_checks.run_repository_check(
        stage,
        repo_path,
        executor=selected_executor,
        source_revision=_SOURCE_REVISION,
        source_digest=_SOURCE_DIGEST,
        **kwargs,
    )


def _run_checks(repo_path, *, executor=None, runner=_success_runner, which=_which, **kwargs):
    selected_executor = executor or _AttestedExecutor(runner=runner, which=which)
    return repository_checks.run_repository_checks(
        repo_path,
        executor=selected_executor,
        source_revision=_SOURCE_REVISION,
        source_digest=_SOURCE_DIGEST,
        **kwargs,
    )


def test_inspection_finds_bounded_node_and_python_components(tmp_path: Path):
    (tmp_path / "package.json").write_text(json.dumps({
        "scripts": {"lint": "eslint .", "typecheck": "tsc --noEmit", "build": "next build"},
        "dependencies": {"next": "1.0.0"},
    }), encoding="utf-8")
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "requirements.txt").write_text("fastapi==1.0.0\n", encoding="utf-8")
    (backend / "tests").mkdir()

    facts = repository_checks.inspect_repository(tmp_path)

    assert facts.errors == ()
    assert [(item.ecosystem, item.relative_path) for item in facts.components] == [
        ("node", "."),
        ("python", "backend"),
    ]
    assert facts.components[0].package_manager == "npm"
    assert facts.components[1].test_tool == "pytest"
    assert "root_path" not in facts.to_dict()


def test_inspection_supports_named_python_requirement_sets(tmp_path: Path):
    worker = tmp_path / "worker"
    worker.mkdir()
    (worker / "requirements.worker.txt").write_text("pytest==9.0.0\n", encoding="utf-8")

    facts = repository_checks.inspect_repository(tmp_path)

    assert len(facts.components) == 1
    assert facts.components[0].relative_path == "worker"
    assert facts.components[0].dependency_files == ("requirements.worker.txt",)


@pytest.mark.parametrize(
    "stage",
    ["dependency_installation", "code_quality", "unit_tests", "build"],
)
def test_irrelevant_stage_is_explicitly_skipped(tmp_path: Path, stage: str):
    result = _run_check(
        stage,
        tmp_path,
        runner=lambda *_args: pytest.fail("irrelevant stages must not execute commands"),
        which=lambda _name: pytest.fail("irrelevant stages must not resolve tools"),
    )

    assert result.status == "skipped"
    assert result.blocking is False
    assert result.reason == "The stage is not relevant to the inspected repository facts."


def _write_build_repository(path: Path) -> None:
    (path / "package.json").write_text(
        json.dumps({"scripts": {"build": "next build"}}),
        encoding="utf-8",
    )


def test_public_default_fails_closed_without_resolving_or_executing(monkeypatch, tmp_path: Path):
    _write_build_repository(tmp_path)
    monkeypatch.setattr(
        repository_checks.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("the private local runner must be unreachable"),
    )

    result = repository_checks.run_repository_check(
        "build",
        tmp_path,
        source_revision=_SOURCE_REVISION,
        source_digest=_SOURCE_DIGEST,
    )

    assert result.status == "unavailable"
    assert result.blocking is True
    assert result.commands == ()
    assert result.reason == "No trusted repository isolation executor is configured."


def test_legacy_runner_injection_fails_closed_without_invocation(tmp_path: Path):
    _write_build_repository(tmp_path)
    calls = []

    result = repository_checks.run_repository_check(
        "build",
        tmp_path,
        source_revision=_SOURCE_REVISION,
        source_digest=_SOURCE_DIGEST,
        runner=lambda *_args: calls.append("execute"),
        which=lambda _tool: calls.append("resolve"),
    )

    assert result.status == "unavailable"
    assert result.blocking is True
    assert calls == []
    assert "Direct runner" in (result.reason or "")


def test_expired_attestation_fails_before_tool_resolution(tmp_path: Path):
    _write_build_repository(tmp_path)

    def expired(attestation, _request):
        now = datetime.now(timezone.utc)
        return replace(
            attestation,
            issued_at=now - timedelta(minutes=2),
            expires_at=now - timedelta(seconds=1),
        )

    executor = _AttestedExecutor(attestation_factory=expired)
    result = _run_check("build", tmp_path, executor=executor)

    assert result.status == "unavailable"
    assert result.blocking is True
    assert result.reason == "The isolation attestation has expired."
    assert executor.resolve_calls == []
    assert executor.executions == []


@pytest.mark.parametrize(
    ("attribute", "expected_reason"),
    [
        ("source_revision", "different source revision"),
        ("source_digest", "different repository content"),
    ],
)
def test_mismatched_source_attestation_fails_before_tool_resolution(
    tmp_path: Path,
    attribute: str,
    expected_reason: str,
):
    _write_build_repository(tmp_path)

    def mismatched(attestation, _request):
        replacement = "c" * (40 if attribute == "source_revision" else 64)
        return replace(attestation, **{attribute: replacement})

    executor = _AttestedExecutor(attestation_factory=mismatched)
    result = _run_check("build", tmp_path, executor=executor)

    assert result.status == "unavailable"
    assert result.blocking is True
    assert expected_reason in (result.reason or "")
    assert executor.resolve_calls == []
    assert executor.executions == []


@pytest.mark.parametrize(
    ("attribute", "access_name"),
    [
        ("worker_filesystem_access", "deployment-worker filesystem"),
        ("database_access", "database"),
        ("key_vault_access", "Key Vault"),
        ("imds_access", "instance metadata service"),
    ],
)
def test_access_enabled_attestation_fails_before_tool_resolution(
    tmp_path: Path,
    attribute: str,
    access_name: str,
):
    _write_build_repository(tmp_path)
    executor = _AttestedExecutor(
        attestation_factory=lambda attestation, _request: replace(
            attestation,
            **{attribute: True},
        )
    )

    result = _run_check("build", tmp_path, executor=executor)

    assert result.status == "unavailable"
    assert result.blocking is True
    assert access_name in (result.reason or "")
    assert executor.resolve_calls == []
    assert executor.executions == []


def test_non_dependency_stage_rejects_restricted_network_before_resolution(tmp_path: Path):
    _write_build_repository(tmp_path)
    executor = _AttestedExecutor(
        attestation_factory=lambda attestation, _request: replace(
            attestation,
            network_policy="restricted",
            allowed_network_destinations=("registry.example.com",),
        )
    )

    result = _run_check("build", tmp_path, executor=executor)

    assert result.status == "unavailable"
    assert result.blocking is True
    assert result.reason == "The build stage must run with network access disabled."
    assert executor.resolve_calls == []
    assert executor.executions == []


def test_missing_source_binding_fails_before_tool_resolution(tmp_path: Path):
    _write_build_repository(tmp_path)
    executor = _AttestedExecutor()

    result = repository_checks.run_repository_check("build", tmp_path, executor=executor)

    assert result.status == "unavailable"
    assert result.blocking is True
    assert result.reason == "The expected source revision is not an immutable Git object ID."
    assert executor.resolve_calls == []
    assert executor.executions == []


def test_attested_executor_receives_only_relative_workspace_paths(tmp_path: Path):
    _write_build_repository(tmp_path)
    executor = _AttestedExecutor()

    result = _run_check("build", tmp_path, executor=executor)

    assert result.status == "passed"
    assert executor.attest_requests == [
        repository_checks.RepositoryIsolationRequest(
            stage="build",
            source_revision=_SOURCE_REVISION,
            source_digest=_SOURCE_DIGEST,
        )
    ]
    assert executor.executions[0][1] == "."
    assert str(tmp_path.resolve()) not in repr(executor.executions)
    assert result.facts["isolation"]["source_digest"] == _SOURCE_DIGEST
    assert result.facts["isolation"]["network_policy"] == "none"


def test_node_install_uses_lockfile_command_and_no_shell_string(tmp_path: Path):
    (tmp_path / "package.json").write_text(json.dumps({
        "dependencies": {"react": "19.0.0"},
    }), encoding="utf-8")
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    observed = []

    def runner(command, cwd, timeout, environment):
        observed.append((command, cwd, environment))
        return repository_checks.CommandExecution(0, stdout="installed")

    result = _run_check(
        "dependency_installation",
        tmp_path,
        runner=runner,
        which=_which,
    )

    assert result.status == "passed"
    assert observed[0][0] == ["/tools/npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"]
    assert observed[0][1] == "."
    assert result.commands[0].command == ("npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund")
    assert result.commands[0].diagnostic_excerpt is None


def test_declared_node_dependencies_without_lock_are_unavailable(tmp_path: Path):
    (tmp_path / "package.json").write_text(json.dumps({
        "dependencies": {"react": "19.0.0"},
    }), encoding="utf-8")

    result = _run_check(
        "dependency_installation",
        tmp_path,
        runner=lambda *_args: pytest.fail("ambiguous installs must not execute"),
        which=_which,
    )

    assert result.status == "unavailable"
    assert result.blocking is True
    assert "lockfile" in (result.reason or "")


def test_required_missing_tool_is_unavailable_and_blocks(tmp_path: Path):
    (tmp_path / "package.json").write_text(json.dumps({
        "scripts": {"lint": "eslint ."},
    }), encoding="utf-8")

    result = _run_check(
        "code_quality",
        tmp_path,
        which=lambda _name: None,
    )

    assert result.status == "unavailable"
    assert result.blocking is True
    assert result.commands[0].status == "unavailable"


def test_node_quality_runs_only_known_scripts_in_fixed_order(tmp_path: Path):
    (tmp_path / "package.json").write_text(json.dumps({
        "scripts": {
            "custom": "do-not-run",
            "typecheck": "tsc --noEmit",
            "lint": "eslint .",
        },
    }), encoding="utf-8")
    observed = []

    def runner(command, cwd, timeout, environment):
        observed.append(command)
        return repository_checks.CommandExecution(0)

    result = _run_check(
        "code_quality",
        tmp_path,
        runner=runner,
        which=_which,
    )

    assert result.status == "passed"
    assert observed == [
        ["/tools/npm", "run", "lint"],
        ["/tools/npm", "run", "typecheck"],
    ]


def test_failure_diagnostic_is_redacted_and_bounded(tmp_path: Path):
    (tmp_path / "package.json").write_text(json.dumps({
        "scripts": {"build": "next build"},
    }), encoding="utf-8")
    secret = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
    noisy_output = "x" * 2_000 + f"\nAPI_KEY={secret}\n"

    result = _run_check(
        "build",
        tmp_path,
        diagnostic_chars=256,
        runner=lambda *_args: repository_checks.CommandExecution(
            1,
            stderr=noisy_output,
            stderr_truncated=True,
        ),
        which=_which,
    )

    assert result.status == "failed"
    assert result.blocking is True
    command = result.commands[0]
    assert command.diagnostic_excerpt is not None
    assert len(command.diagnostic_excerpt) <= 256
    assert secret not in command.diagnostic_excerpt
    assert "<REDACTED>" in command.diagnostic_excerpt
    assert command.output_truncated is True


def test_timeout_is_a_failed_required_check(tmp_path: Path):
    (tmp_path / "package.json").write_text(json.dumps({
        "scripts": {"test": "vitest"},
    }), encoding="utf-8")

    result = _run_check(
        "unit_tests",
        tmp_path,
        timeout_seconds=7,
        runner=lambda *_args: repository_checks.CommandExecution(-1, timed_out=True),
        which=_which,
    )

    assert result.status == "failed"
    assert result.commands[0].summary == "The command exceeded its 7s execution limit."


def test_python_conventions_produce_install_quality_test_and_build_commands(tmp_path: Path):
    (tmp_path / "requirements.txt").write_text("pytest==9.0.0\nruff==1.0.0\n", encoding="utf-8")
    (tmp_path / "ruff.toml").write_text("line-length = 100\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "app.py").write_text("value = 1\n", encoding="utf-8")
    observed = []

    def runner(command, cwd, timeout, environment):
        observed.append(command)
        return repository_checks.CommandExecution(0)

    report = _run_checks(
        tmp_path,
        runner=runner,
        which=_which,
    )

    assert report.blocking is False
    assert [item.status for item in report.checks] == ["passed", "passed", "passed", "passed"]
    assert observed[0][:5] == ["/tools/python", "-m", "pip", "install", "--disable-pip-version-check"]
    assert observed[1] == ["/tools/ruff", "check", "."]
    assert observed[2] == ["/tools/pytest", "-q"]
    assert observed[3][0:4] == ["/tools/python", "-m", "compileall", "-q"]


def test_malformed_manifest_fails_closed(tmp_path: Path):
    (tmp_path / "package.json").write_text("not-json", encoding="utf-8")

    result = _run_check(
        "build",
        tmp_path,
        runner=lambda *_args: pytest.fail("invalid metadata must not execute"),
        which=_which,
    )

    assert result.status == "unavailable"
    assert result.blocking is True
    assert "valid UTF-8 JSON" in (result.reason or "")


def test_all_stage_runner_skips_descendants_after_blocking_failure(tmp_path: Path):
    (tmp_path / "package.json").write_text(json.dumps({
        "scripts": {"lint": "eslint", "test": "vitest", "build": "next build"},
        "dependencies": {"react": "19.0.0"},
    }), encoding="utf-8")
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

    report = _run_checks(
        tmp_path,
        runner=lambda *_args: repository_checks.CommandExecution(1, stderr="install failed"),
        which=_which,
    )

    assert report.blocking is True
    assert [item.status for item in report.checks] == ["failed", "skipped", "skipped", "skipped"]
    assert "dependency_installation" in report.checks[1].summary


def test_default_runner_sets_shell_false_and_bounds_streams(monkeypatch, tmp_path: Path):
    captured = {}

    class Stream:
        def __init__(self, chunks):
            self._chunks = list(chunks)

        def read(self, _size):
            return self._chunks.pop(0) if self._chunks else b""

        def close(self):
            return None

    class Process:
        pid = 123
        returncode = 0
        stdout = Stream([b"a" * 40_000])
        stderr = Stream([])

        def wait(self, timeout):
            return 0

        def kill(self):
            return None

    def popen(command, **kwargs):
        captured.update(kwargs)
        return Process()

    monkeypatch.setattr(repository_checks.subprocess, "Popen", popen)
    result = repository_checks._default_runner(
        ["tool", "arg"],
        str(tmp_path),
        10,
        {"PATH": "safe"},
    )

    assert captured["shell"] is False
    assert captured["stdin"] is repository_checks.subprocess.DEVNULL
    assert len(result.stdout.encode("utf-8")) == repository_checks._MAX_CAPTURE_BYTES
    assert result.stdout_truncated is True


def test_timeout_and_diagnostic_limits_are_validated(tmp_path: Path):
    with pytest.raises(ValueError, match="timeout_seconds"):
        _run_check("build", tmp_path, timeout_seconds=0)
    with pytest.raises(ValueError, match="diagnostic_chars"):
        _run_check("build", tmp_path, diagnostic_chars=10)
