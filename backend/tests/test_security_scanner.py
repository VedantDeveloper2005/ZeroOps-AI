import base64
import json
from pathlib import Path

from backend.services import security_scanner


def _which(name: str) -> str:
    return f"/tools/{name}"


def test_required_missing_scanner_is_unavailable_and_blocks(tmp_path: Path):
    result = security_scanner.run_scan("sast", tmp_path, which=lambda _name: None)

    assert result.status == "unavailable"
    assert result.blocking is True
    assert result.required is True


def test_semgrep_result_is_parsed_without_retaining_source(tmp_path: Path):
    payload = """{
      "results": [{
        "check_id": "python.lang.security.audit.exec-used",
        "path": "src/app.py",
        "start": {"line": 12},
        "extra": {
          "message": "Use of exec",
          "severity": "ERROR",
          "lines": "exec(user_input)",
          "fingerprint": "finding-1"
        }
      }]
    }"""

    def runner(command, cwd, timeout):
        if command[-1] == "--version":
            return security_scanner._ToolExecution(0, "semgrep 1.2.3", "")
        assert command[:4] == ["/tools/semgrep", "scan", "--config", "auto"]
        assert "--error" in command
        assert "--metrics=off" in command
        assert cwd == str(tmp_path.resolve())
        return security_scanner._ToolExecution(1, payload, "")

    result = security_scanner.run_scan("sast", tmp_path, runner=runner, which=_which)

    assert result.status == "warning"
    assert result.blocking is False
    assert result.findings[0].path == "src/app.py"
    assert result.findings[0].line == 12
    assert "exec(user_input)" not in str(result.to_dict())
    assert result.evidence["output_retained"] is False


def test_gitleaks_discards_secret_and_blocks(tmp_path: Path):
    def runner(command, cwd, timeout):
        if command[-1] == "--version":
            return security_scanner._ToolExecution(0, "gitleaks 9", "")
        report_path = Path(command[command.index("--report-path") + 1])
        report_path.write_text(
            json.dumps([{
                "RuleID": "generic-api-key",
                "Description": "API key",
                "File": "config.py",
                "StartLine": 4,
                "Secret": "sk-live-secret",
                "Match": "API_KEY=sk-live-secret",
                "Fingerprint": "safe-fingerprint",
            }]),
            encoding="utf-8",
        )
        return security_scanner._ToolExecution(1, "", "")

    result = security_scanner.run_scan("secrets", tmp_path, runner=runner, which=_which)

    serialized = str(result.to_dict())
    assert result.status == "blocked"
    assert result.blocking is True
    assert "sk-live-secret" not in serialized
    assert result.findings[0].fingerprint == "safe-fingerprint"


def test_malformed_required_output_never_passes(tmp_path: Path):
    def runner(command, cwd, timeout):
        if command[-1] == "--version":
            return security_scanner._ToolExecution(0, "trivy 1", "")
        return security_scanner._ToolExecution(0, "not-json", "")

    result = security_scanner.run_scan("dependencies", tmp_path, runner=runner, which=_which)

    assert result.status == "unavailable"
    assert result.blocking is True


def test_structurally_valid_but_incomplete_output_never_passes(tmp_path: Path):
    def runner(command, cwd, timeout):
        if command[-1] == "--version":
            return security_scanner._ToolExecution(0, "trivy 1", "")
        return security_scanner._ToolExecution(0, "{}", "")

    result = security_scanner.run_scan("dependencies", tmp_path, runner=runner, which=_which)

    assert result.status == "unavailable"
    assert result.blocking is True


def test_tool_error_with_partial_findings_never_passes(tmp_path: Path):
    payload = '{"results":[{"check_id":"rule","extra":{"severity":"WARNING"}}]}'

    def runner(command, cwd, timeout):
        if command[-1] == "--version":
            return security_scanner._ToolExecution(0, "semgrep 1", "")
        return security_scanner._ToolExecution(2, payload, "configuration failed")

    result = security_scanner.run_scan("sast", tmp_path, runner=runner, which=_which)

    assert result.status == "unavailable"
    assert result.blocking is True


def test_findings_exit_code_without_findings_never_passes(tmp_path: Path):
    def runner(command, cwd, timeout):
        if command[-1] == "--version":
            return security_scanner._ToolExecution(0, "trivy 1", "")
        return security_scanner._ToolExecution(1, '{"Results":[]}', "")

    result = security_scanner.run_scan("dependencies", tmp_path, runner=runner, which=_which)

    assert result.status == "unavailable"
    assert result.blocking is True


def test_required_scan_requires_verifiable_tool_version(tmp_path: Path):
    def runner(command, cwd, timeout):
        if command[-1] == "--version":
            return security_scanner._ToolExecution(1, "", "version failed")
        return security_scanner._ToolExecution(0, '{"Results":[]}', "")

    result = security_scanner.run_scan("dependencies", tmp_path, runner=runner, which=_which)

    assert result.status == "unavailable"
    assert result.blocking is True
    assert "version" in result.summary


def test_semgrep_partial_scan_errors_never_pass(tmp_path: Path):
    def runner(command, cwd, timeout):
        if command[-1] == "--version":
            return security_scanner._ToolExecution(0, "semgrep 1", "")
        return security_scanner._ToolExecution(
            0,
            '{"results":[],"errors":[{"message":"parse failure"}]}',
            "",
        )

    result = security_scanner.run_scan("sast", tmp_path, runner=runner, which=_which)

    assert result.status == "unavailable"
    assert result.blocking is True


def test_finding_paths_cannot_escape_repository(tmp_path: Path):
    payload = {
        "results": [{
            "check_id": "rule",
            "path": "../../outside.py",
            "start": {"line": 1},
            "extra": {"severity": "WARNING"},
        }],
    }

    def runner(command, cwd, timeout):
        if command[-1] == "--version":
            return security_scanner._ToolExecution(0, "semgrep 1", "")
        return security_scanner._ToolExecution(1, json.dumps(payload), "")

    result = security_scanner.run_scan("sast", tmp_path, runner=runner, which=_which)

    assert result.findings[0].path is None


def test_truncation_retains_blocking_severity(tmp_path: Path):
    results = [
        {"check_id": f"low-{index}", "extra": {"severity": "INFO"}}
        for index in range(security_scanner._MAX_FINDINGS)
    ]
    results.append({"check_id": "critical-last", "extra": {"severity": "CRITICAL"}})

    def runner(command, cwd, timeout):
        if command[-1] == "--version":
            return security_scanner._ToolExecution(0, "semgrep 1", "")
        return security_scanner._ToolExecution(1, json.dumps({"results": results}), "")

    result = security_scanner.run_scan("sast", tmp_path, runner=runner, which=_which)

    assert result.status == "blocked"
    assert len(result.findings) == security_scanner._MAX_FINDINGS
    assert result.findings[0].rule_id == "critical-last"
    assert result.evidence["result_count"] == security_scanner._MAX_FINDINGS + 1


def test_default_runner_does_not_forward_cloud_credentials(tmp_path: Path, monkeypatch):
    captured = {}

    def fake_run(*args, **kwargs):
        captured.update(kwargs)
        return type("Completed", (), {"returncode": 0, "stdout": "{}", "stderr": ""})()

    monkeypatch.setenv("AZURE_CLIENT_SECRET", "must-not-leak")
    monkeypatch.setattr(security_scanner.subprocess, "run", fake_run)

    security_scanner._default_runner(["scanner"], str(tmp_path), 1)

    assert "AZURE_CLIENT_SECRET" not in captured["env"]
    assert captured["env"]["NO_COLOR"] == "1"
    assert captured["env"]["HOME"] != str(Path.home())


def test_authenticated_container_scan_uses_ephemeral_exact_registry_config(
    tmp_path: Path,
    monkeypatch,
):
    captured: dict[str, object] = {}
    access_token = "short-lived-registry-token"
    username = "00000000-0000-0000-0000-000000000000"
    registry = "example.azurecr.io"

    def fake_run(command, **kwargs):
        environment = kwargs["env"]
        config_path = Path(environment["HOME"]) / ".docker" / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        decoded = base64.b64decode(
            config["auths"][registry]["auth"]
        ).decode("utf-8")
        captured.update(
            {
                "command": list(command),
                "environment": dict(environment),
                "config_path": config_path,
                "decoded": decoded,
            }
        )
        version_call = command[-1] == "--version"
        return type(
            "Completed",
            (),
            {
                "returncode": 0,
                "stdout": "trivy 0.73.0" if version_call else '{"Results": []}',
                "stderr": "",
            },
        )()

    monkeypatch.setattr(security_scanner.subprocess, "run", fake_run)
    result = security_scanner.run_authenticated_container_scan(
        tmp_path,
        image_ref=f"{registry}/team/api@sha256:{'a' * 64}",
        registry_server=registry,
        username=username,
        access_token=access_token,
        which=lambda _tool: "/usr/local/bin/trivy",
    )

    assert result.status == "passed"
    assert captured["decoded"] == f"{username}:{access_token}"
    assert access_token not in " ".join(captured["command"])
    assert access_token not in captured["environment"].values()
    assert not captured["config_path"].exists()


def test_authenticated_container_scan_rejects_registry_or_mutable_image_mismatch(
    tmp_path: Path,
):
    result = security_scanner.run_authenticated_container_scan(
        tmp_path,
        image_ref="other.azurecr.io/team/api:latest",
        registry_server="expected.azurecr.io",
        username="registry-user",
        access_token="short-lived-token",
        which=lambda _tool: "/usr/local/bin/trivy",
    )

    assert result.status == "unavailable"
    assert result.blocking is True
    assert "exact configured registry" in result.summary


def test_authenticated_registry_runner_redacts_token_and_encoded_auth_from_child_output(
    tmp_path: Path,
    monkeypatch,
):
    access_token = "short-lived-registry-token"
    username = "registry-user"
    encoded_auth = base64.b64encode(f"{username}:{access_token}".encode()).decode()

    def fake_run(*_args, **_kwargs):
        return type(
            "Completed",
            (),
            {
                "returncode": 1,
                "stdout": f"remote response included {access_token}",
                "stderr": f"docker auth was {encoded_auth}",
            },
        )()

    monkeypatch.setattr(security_scanner.subprocess, "run", fake_run)
    runner = security_scanner._registry_authenticated_runner(
        "example.azurecr.io",
        username,
        access_token,
    )

    execution = runner(["trivy", "image"], str(tmp_path), 1)

    assert access_token not in execution.stdout
    assert access_token not in execution.stderr
    assert encoded_auth not in execution.stdout
    assert encoded_auth not in execution.stderr
    assert "[REDACTED]" in execution.stdout
    assert "[REDACTED]" in execution.stderr


def test_critical_container_finding_blocks_by_default(tmp_path: Path):
    payload = """{
      "Results": [{
        "Target": "python:3.14",
        "Vulnerabilities": [{
          "VulnerabilityID": "CVE-2099-0001",
          "Severity": "CRITICAL",
          "Title": "Critical package issue",
          "PkgName": "example"
        }]
      }]
    }"""

    def runner(command, cwd, timeout):
        if command[-1] == "--version":
            return security_scanner._ToolExecution(0, "trivy 1", "")
        return security_scanner._ToolExecution(1, payload, "")

    result = security_scanner.run_scan(
        "container",
        tmp_path,
        image_ref="registry.example/app@sha256:" + "a" * 64,
        runner=runner,
        which=_which,
    )

    assert result.status == "blocked"
    assert result.findings[0].severity == "critical"
