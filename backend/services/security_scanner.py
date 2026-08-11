"""Deterministic DevSecOps scanner orchestration.

This module is deliberately independent from the deployment database.  It
executes one configured scanner at a time, returns a bounded/sanitized result,
and treats missing or malformed required tooling as unavailable rather than as
a successful scan.  Pipeline persistence and policy decisions are handled by
the caller.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Sequence

try:
    from backend.services.redaction import redact_sensitive_text, redact_sensitive_values
except ImportError:  # pragma: no cover - worker-style imports
    from services.redaction import redact_sensitive_text, redact_sensitive_values


ScanKind = Literal[
    "sast",
    "dependencies",
    "secrets",
    "container",
    "iac",
    "kubernetes",
    "sbom",
]
ScanStatus = Literal["passed", "warning", "failed", "blocked", "unavailable"]
Severity = Literal["critical", "high", "medium", "low", "info", "unknown"]

_MAX_OUTPUT_CHARS = 250_000
_MAX_FINDINGS = 500
_SEVERITY_ORDER = {
    "unknown": 0,
    "info": 1,
    "low": 2,
    "medium": 3,
    "high": 4,
    "critical": 5,
}
_TOOL_EXIT_CODES: dict[str, frozenset[int]] = {
    "semgrep": frozenset({0, 1}),
    "trivy": frozenset({0, 1}),
    "gitleaks": frozenset({0, 1}),
    "checkov": frozenset({0, 1}),
    "syft": frozenset({0}),
    "tflint": frozenset({0, 2}),
}
_FINDING_EXIT_CODES: dict[str, frozenset[int]] = {
    "semgrep": frozenset({1}),
    "trivy": frozenset({1}),
    "gitleaks": frozenset({1}),
    "checkov": frozenset({1}),
    "syft": frozenset(),
    "tflint": frozenset({2}),
}
_SAFE_ENVIRONMENT_KEYS = {
    "COMSPEC",
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "PATHEXT",
    "SSL_CERT_DIR",
    "SSL_CERT_FILE",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "TMPDIR",
    "USERPROFILE",
    "WINDIR",
}


@dataclass(frozen=True)
class ScanPolicy:
    """Small policy surface with secure production defaults."""

    block_critical: bool = True
    block_high: bool = False


@dataclass(frozen=True)
class SecurityFinding:
    rule_id: str
    severity: Severity
    title: str
    path: str | None = None
    line: int | None = None
    fingerprint: str | None = None


@dataclass(frozen=True)
class SecurityScanResult:
    kind: ScanKind
    tool: str
    status: ScanStatus
    required: bool
    blocking: bool
    summary: str
    findings: list[SecurityFinding] = field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""
    tool_version: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return redact_sensitive_values(asdict(self))


@dataclass(frozen=True)
class _ToolExecution:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[Sequence[str], str, int], _ToolExecution]
Which = Callable[[str], str | None]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded(value: str) -> str:
    return redact_sensitive_text(str(value or ""), maximum_length=_MAX_OUTPUT_CHARS)


def _scanner_environment(home: Path | None = None) -> dict[str, str]:
    """Return the minimum host environment needed to launch scanner CLIs.

    Deployment credentials are intentionally not inherited by repository
    scanners.  The worker image is responsible for installing scanners on a
    trusted PATH; the repository itself is never added to PATH.
    """

    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in _SAFE_ENVIRONMENT_KEYS
    }
    environment.update({"CI": "true", "NO_COLOR": "1"})
    if home is not None:
        environment.update({
            "HOME": str(home),
            "USERPROFILE": str(home),
            "XDG_CACHE_HOME": str(home / "cache"),
            "XDG_CONFIG_HOME": str(home / "config"),
            "TEMP": str(home / "tmp"),
            "TMP": str(home / "tmp"),
            "TMPDIR": str(home / "tmp"),
        })
    return environment


def _default_runner(command: Sequence[str], cwd: str, timeout_seconds: int) -> _ToolExecution:
    try:
        with tempfile.TemporaryDirectory(prefix="zeroops-scanner-home-") as temp_home:
            home = Path(temp_home)
            (home / "cache").mkdir(mode=0o700)
            (home / "config").mkdir(mode=0o700)
            (home / "tmp").mkdir(mode=0o700)
            completed = subprocess.run(
                list(command),
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                check=False,
                shell=False,
                env=_scanner_environment(home),
            )
    except subprocess.TimeoutExpired as error:
        raise TimeoutError(f"Scanner exceeded its {timeout_seconds}s execution limit.") from error
    return _ToolExecution(
        returncode=completed.returncode,
        stdout=_bounded(completed.stdout),
        stderr=_bounded(completed.stderr),
    )


def _registry_authenticated_runner(
    registry_server: str,
    username: str,
    access_token: str,
) -> Runner:
    """Build an in-memory runner for one exact private-registry credential.

    Docker-compatible credentials exist only in a mode-0600 file below the
    scanner's isolated temporary HOME. They are never placed in argv, process
    environment variables, scanner evidence, or persistent worker storage.
    """

    encoded_auth = base64.b64encode(
        f"{username}:{access_token}".encode("utf-8")
    ).decode("ascii")

    def bounded_registry_output(value: str) -> str:
        # Treat the child process as an untrusted log source. Registry clients
        # should not echo credentials, but an error from a remote registry or
        # future tool version must not be able to cross the evidence boundary
        # with either the bearer token or Docker's base64 auth payload intact.
        sanitized = str(value or "")
        for secret_value in (access_token, encoded_auth):
            sanitized = sanitized.replace(secret_value, "[REDACTED]")
        return _bounded(sanitized)

    def run(command: Sequence[str], cwd: str, timeout_seconds: int) -> _ToolExecution:
        try:
            with tempfile.TemporaryDirectory(prefix="zeroops-registry-scan-") as temp_home:
                home = Path(temp_home)
                for directory in (home / "cache", home / "config", home / "tmp", home / ".docker"):
                    directory.mkdir(mode=0o700)
                docker_config = json.dumps(
                    {"auths": {registry_server: {"auth": encoded_auth}}},
                    separators=(",", ":"),
                ).encode("utf-8")
                config_path = home / ".docker" / "config.json"
                descriptor = os.open(
                    config_path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
                try:
                    os.write(descriptor, docker_config)
                finally:
                    os.close(descriptor)
                completed = subprocess.run(
                    list(command),
                    cwd=cwd,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout_seconds,
                    check=False,
                    shell=False,
                    env=_scanner_environment(home),
                )
        except subprocess.TimeoutExpired as error:
            raise TimeoutError(
                f"Scanner exceeded its {timeout_seconds}s execution limit."
            ) from error
        return _ToolExecution(
            returncode=completed.returncode,
            stdout=bounded_registry_output(completed.stdout),
            stderr=bounded_registry_output(completed.stderr),
        )

    return run


def _safe_repo_path(repo_path: str | os.PathLike[str]) -> str:
    path = Path(repo_path).resolve(strict=True)
    if not path.is_dir():
        raise ValueError("The scanner target must be a repository directory.")
    return str(path)


def _severity(value: Any) -> Severity:
    normalized = str(value or "unknown").strip().lower()
    aliases = {"error": "high", "warning": "medium", "warn": "medium", "negligible": "low"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in _SEVERITY_ORDER:
        return "unknown"
    return normalized  # type: ignore[return-value]


def _safe_relative_path(value: Any, repo_path: str) -> str | None:
    if not value:
        return None
    root = Path(repo_path).resolve(strict=True)
    candidate = Path(str(value).replace("\\", "/"))
    try:
        resolved = candidate.resolve(strict=False) if candidate.is_absolute() else (root / candidate).resolve(strict=False)
        relative = resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    normalized = relative.as_posix()
    if not normalized or normalized == ".":
        return None
    return normalized[:500]


def _finding(
    *,
    rule_id: Any,
    severity: Any,
    title: Any,
    repo_path: str,
    path: Any = None,
    line: Any = None,
    fingerprint: Any = None,
) -> SecurityFinding:
    line_number = int(line) if isinstance(line, int) or str(line or "").isdigit() else None
    if line_number is not None and not 0 < line_number <= 2_147_483_647:
        line_number = None
    return SecurityFinding(
        rule_id=_bounded(str(rule_id or "unclassified"))[:160],
        severity=_severity(severity),
        title=_bounded(str(title or "Security finding"))[:500],
        path=_safe_relative_path(path, repo_path),
        line=line_number,
        fingerprint=_bounded(str(fingerprint))[:160] if fingerprint else None,
    )


def _json_payload(execution: _ToolExecution) -> Any:
    raw = execution.stdout.strip()
    if not raw:
        return []
    return json.loads(raw)


def _parse_semgrep(payload: Any, repo_path: str) -> list[SecurityFinding]:
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("Semgrep JSON did not contain a results array.")
    errors = payload.get("errors", [])
    if not isinstance(errors, list) or errors:
        raise ValueError("Semgrep reported an incomplete scan.")
    results = payload["results"]
    findings: list[SecurityFinding] = []
    for item in results:
        if not isinstance(item, dict):
            raise ValueError("Semgrep returned a malformed result.")
        extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
        metadata = extra.get("metadata") if isinstance(extra.get("metadata"), dict) else {}
        start = item.get("start") if isinstance(item.get("start"), dict) else {}
        findings.append(_finding(
            rule_id=item.get("check_id"),
            severity=extra.get("severity") or metadata.get("severity"),
            # Semgrep messages may interpolate matched source. Retain only the
            # stable rule identifier, never source-derived message text.
            title=item.get("check_id"),
            repo_path=repo_path,
            path=item.get("path"),
            line=start.get("line"),
            fingerprint=extra.get("fingerprint"),
        ))
    return findings


def _parse_gitleaks(payload: Any, repo_path: str) -> list[SecurityFinding]:
    if not isinstance(payload, list):
        raise ValueError("Gitleaks JSON was not an array.")
    results = payload
    findings: list[SecurityFinding] = []
    for item in results:
        if not isinstance(item, dict):
            raise ValueError("Gitleaks returned a malformed result.")
        # Never retain Match, Secret, or Entropy fields from Gitleaks.
        findings.append(_finding(
            rule_id=item.get("RuleID"),
            severity="critical",
            title=item.get("Description") or "Potential committed credential",
            repo_path=repo_path,
            path=item.get("File"),
            line=item.get("StartLine"),
            fingerprint=item.get("Fingerprint"),
        ))
    return findings


def _parse_trivy(payload: Any, repo_path: str) -> list[SecurityFinding]:
    if not isinstance(payload, dict) or not isinstance(payload.get("Results"), list):
        raise ValueError("Trivy JSON did not contain a Results array.")
    results = payload["Results"]
    findings: list[SecurityFinding] = []
    for result in results:
        if not isinstance(result, dict):
            raise ValueError("Trivy returned a malformed result.")
        target = result.get("Target")
        vulnerabilities = result.get("Vulnerabilities") or []
        misconfigurations = result.get("Misconfigurations") or []
        if not isinstance(vulnerabilities, list) or not isinstance(misconfigurations, list):
            raise ValueError("Trivy returned malformed finding arrays.")
        for item in [*vulnerabilities, *misconfigurations]:
            if not isinstance(item, dict):
                raise ValueError("Trivy returned a malformed finding.")
            findings.append(_finding(
                rule_id=item.get("VulnerabilityID") or item.get("ID") or item.get("AVDID"),
                severity=item.get("Severity"),
                title=item.get("Title") or item.get("Message") or item.get("PkgName"),
                repo_path=repo_path,
                path=item.get("CauseMetadata", {}).get("Resource")
                if isinstance(item.get("CauseMetadata"), dict)
                else target,
                line=(item.get("CauseMetadata") or {}).get("StartLine")
                if isinstance(item.get("CauseMetadata"), dict)
                else None,
                fingerprint=item.get("PrimaryURL") or item.get("VulnerabilityID"),
            ))
    return findings


def _parse_checkov(payload: Any, repo_path: str) -> list[SecurityFinding]:
    if not isinstance(payload, (dict, list)):
        raise ValueError("Checkov JSON was not an object or array.")
    reports = payload if isinstance(payload, list) else [payload]
    if not reports:
        raise ValueError("Checkov returned no framework report.")
    findings: list[SecurityFinding] = []
    for report in reports:
        if not isinstance(report, dict):
            raise ValueError("Checkov returned a malformed framework report.")
        results = report.get("results")
        if not isinstance(results, dict) or not isinstance(results.get("failed_checks"), list):
            raise ValueError("Checkov JSON did not contain failed_checks.")
        failed = results["failed_checks"]
        for item in failed:
            if not isinstance(item, dict):
                raise ValueError("Checkov returned a malformed finding.")
            file_line = item.get("file_line_range") or []
            findings.append(_finding(
                rule_id=item.get("check_id"),
                severity=(item.get("severity") or "high"),
                title=item.get("check_name") or item.get("check_id"),
                repo_path=repo_path,
                path=item.get("file_path"),
                line=file_line[0] if file_line else None,
                fingerprint=item.get("bc_check_id") or item.get("check_id"),
            ))
    return findings


def _parse_tflint(payload: Any, repo_path: str) -> list[SecurityFinding]:
    if not isinstance(payload, dict) or not isinstance(payload.get("issues"), list):
        raise ValueError("TFLint JSON did not contain an issues array.")
    errors = payload.get("errors", [])
    if errors and isinstance(errors, list):
        raise ValueError("TFLint reported an execution error.")
    if errors and not isinstance(errors, list):
        raise ValueError("TFLint returned malformed errors.")
    issues = payload["issues"]
    findings: list[SecurityFinding] = []
    for item in issues:
        if not isinstance(item, dict):
            raise ValueError("TFLint returned a malformed issue.")
        rule = item.get("rule") if isinstance(item.get("rule"), dict) else {}
        location = item.get("range", {}).get("start", {}) if isinstance(item.get("range"), dict) else {}
        findings.append(_finding(
            rule_id=rule.get("name"),
            severity=rule.get("severity"),
            title=item.get("message"),
            repo_path=repo_path,
            path=item.get("range", {}).get("filename") if isinstance(item.get("range"), dict) else None,
            line=location.get("line"),
        ))
    return findings


def _parse_syft(payload: Any, _repo_path: str) -> list[SecurityFinding]:
    if not isinstance(payload, dict):
        raise ValueError("Syft JSON was not an object.")
    if payload.get("bomFormat") != "CycloneDX" or not isinstance(payload.get("components"), list):
        raise ValueError("Syft did not return a valid CycloneDX document.")
    return []


def _retained_findings(findings: list[SecurityFinding]) -> list[SecurityFinding]:
    """Retain the highest severities so truncation can never hide a blocker."""

    return sorted(
        findings,
        key=lambda item: _SEVERITY_ORDER[item.severity],
        reverse=True,
    )[:_MAX_FINDINGS]


def _status_for(findings: list[SecurityFinding], policy: ScanPolicy) -> tuple[ScanStatus, bool]:
    critical = any(item.severity == "critical" for item in findings)
    high = any(item.severity == "high" for item in findings)
    blocking = (critical and policy.block_critical) or (high and policy.block_high)
    if blocking:
        return "blocked", True
    if findings:
        return "warning", False
    return "passed", False


def _version(tool: str, executable: str, repo_path: str, runner: Runner) -> str | None:
    try:
        execution = runner([executable, "--version"], repo_path, 15)
    except (OSError, TimeoutError):
        return None
    if execution.returncode != 0:
        return None
    output = (execution.stdout or execution.stderr).splitlines()
    return _bounded(output[0])[:200] if output else None


def _unavailable(kind: ScanKind, tool: str, required: bool, started_at: str, reason: str) -> SecurityScanResult:
    return SecurityScanResult(
        kind=kind,
        tool=tool,
        status="unavailable",
        required=required,
        blocking=required,
        summary=reason,
        started_at=started_at,
        completed_at=_utc_now(),
        evidence={"result_count": 0, "output_retained": False},
    )


def run_scan(
    kind: ScanKind,
    repo_path: str | os.PathLike[str],
    *,
    image_ref: str | None = None,
    required: bool = True,
    policy: ScanPolicy | None = None,
    timeout_seconds: int = 300,
    runner: Runner = _default_runner,
    which: Which = shutil.which,
) -> SecurityScanResult:
    """Run one deterministic scan and return only safe, bounded evidence."""

    started_at = _utc_now()
    repository = _safe_repo_path(repo_path)
    scan_policy = policy or ScanPolicy()
    tool_by_kind = {
        "sast": "semgrep",
        "dependencies": "trivy",
        "secrets": "gitleaks",
        "container": "trivy",
        "iac": "checkov",
        "kubernetes": "trivy",
        "sbom": "syft",
    }
    tool = tool_by_kind[kind]
    executable = which(tool)
    if not executable:
        return _unavailable(kind, tool, required, started_at, f"{tool} is not installed in the deployment worker.")

    parser: Callable[[Any, str], list[SecurityFinding]]
    output_file: str | None = None
    temporary_directory: tempfile.TemporaryDirectory[str] | None = None
    if kind == "sast":
        command = [
            executable,
            "scan",
            "--config",
            "auto",
            "--json",
            "--quiet",
            "--error",
            "--metrics=off",
            ".",
        ]
        parser = _parse_semgrep
    elif kind == "dependencies":
        command = [executable, "fs", "--scanners", "vuln", "--format", "json", "--exit-code", "1", "."]
        parser = _parse_trivy
    elif kind == "secrets":
        temporary_directory = tempfile.TemporaryDirectory(prefix="zeroops-gitleaks-")
        output_file = str(Path(temporary_directory.name) / "findings.json")
        command = [
            executable,
            "detect",
            "--source",
            ".",
            "--no-git",
            "--redact",
            "--exit-code",
            "1",
            "--report-format",
            "json",
            "--report-path",
            output_file,
        ]
        parser = _parse_gitleaks
    elif kind == "container":
        if not image_ref or image_ref.startswith("-") or any(character.isspace() for character in image_ref):
            return _unavailable(kind, tool, required, started_at, "A verified image reference is required for container scanning.")
        command = [
            executable,
            "image",
            "--scanners",
            "vuln",
            "--format",
            "json",
            "--exit-code",
            "1",
            "--",
            image_ref,
        ]
        parser = _parse_trivy
    elif kind == "iac":
        command = [executable, "-d", ".", "-o", "json", "--compact"]
        parser = _parse_checkov
    elif kind == "kubernetes":
        command = [executable, "config", "--format", "json", "--exit-code", "1", "."]
        parser = _parse_trivy
    else:
        command = [executable, ".", "-o", "cyclonedx-json"]
        parser = _parse_syft

    try:
        execution = runner(command, repository, timeout_seconds)
        raw_payload = execution.stdout
        if len(raw_payload) > _MAX_OUTPUT_CHARS:
            return _unavailable(
                kind,
                tool,
                required,
                started_at,
                f"{tool} returned more evidence than ZeroOps can validate safely.",
            )
        if output_file and Path(output_file).is_file():
            with Path(output_file).open("r", encoding="utf-8", errors="replace") as report:
                raw_payload = report.read(_MAX_OUTPUT_CHARS + 1)
            if len(raw_payload) > _MAX_OUTPUT_CHARS:
                return _unavailable(
                    kind,
                    tool,
                    required,
                    started_at,
                    f"{tool} returned more evidence than ZeroOps can validate safely.",
                )
        try:
            payload = json.loads(raw_payload) if raw_payload.strip() else []
            all_findings = parser(payload, repository)
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            return _unavailable(
                kind,
                tool,
                required,
                started_at,
                f"{tool} returned output that ZeroOps could not validate: {type(error).__name__}.",
            )

        # Each command explicitly configures its findings exit code. Other
        # exit codes are execution failures even if partial JSON was emitted.
        if execution.returncode not in _TOOL_EXIT_CODES[tool]:
            return _unavailable(
                kind,
                tool,
                required,
                started_at,
                f"{tool} did not complete successfully (exit code {execution.returncode}).",
            )
        if execution.returncode in _FINDING_EXIT_CODES[tool] and not all_findings:
            return _unavailable(
                kind,
                tool,
                required,
                started_at,
                f"{tool} returned a findings exit code without validated findings.",
            )

        tool_version = _version(tool, executable, repository, runner)
        if required and not tool_version:
            return _unavailable(kind, tool, required, started_at, f"{tool} version could not be verified.")

        status, blocking = _status_for(all_findings, scan_policy)
        findings = _retained_findings(all_findings)
        counts = {severity: 0 for severity in _SEVERITY_ORDER}
        for finding in all_findings:
            counts[finding.severity] += 1
        summary = "No findings detected." if not all_findings else f"{len(all_findings)} validated finding(s) detected."
        additional_evidence: dict[str, Any] = {}
        if kind == "sbom" and isinstance(payload, dict):
            additional_evidence["component_count"] = len(payload.get("components", []))
        return SecurityScanResult(
            kind=kind,
            tool=tool,
            status=status,
            required=required,
            blocking=blocking,
            summary=summary,
            findings=findings,
            started_at=started_at,
            completed_at=_utc_now(),
            tool_version=tool_version,
            evidence={
                "result_count": len(all_findings),
                "retained_findings": len(findings),
                "severity_counts": counts,
                "output_retained": False,
                "secrets_forwarded_to_ai": False,
                **additional_evidence,
            },
        )
    except (OSError, TimeoutError) as error:
        return _unavailable(kind, tool, required, started_at, _bounded(str(error))[:500])
    finally:
        if temporary_directory is not None:
            temporary_directory.cleanup()


def run_authenticated_container_scan(
    repo_path: str | os.PathLike[str],
    *,
    image_ref: str,
    registry_server: str,
    username: str,
    access_token: str,
    required: bool = True,
    policy: ScanPolicy | None = None,
    timeout_seconds: int = 300,
    which: Which = shutil.which,
) -> SecurityScanResult:
    """Scan one immutable image using a short-lived, exact-registry login."""

    started_at = _utc_now()
    registry = str(registry_server or "").strip().lower().rstrip("/")
    immutable_image = str(image_ref or "").strip()
    image_match = re.fullmatch(
        r"(?P<registry>[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?)/"
        r"[a-z0-9](?:[a-z0-9._/-]*[a-z0-9])?@sha256:[0-9a-f]{64}",
        immutable_image,
    )
    if (
        not registry
        or len(registry) > 253
        or "://" in registry
        or "/" in registry
        or "\\" in registry
        or any(character.isspace() for character in registry)
        or image_match is None
        or image_match.group("registry").lower() != registry
    ):
        return _unavailable(
            "container",
            "trivy",
            required,
            started_at,
            "Container scanning requires an immutable digest from the exact configured registry.",
        )
    if (
        not username
        or len(username) > 256
        or ":" in username
        or any(ord(character) < 32 for character in username)
        or not access_token
        or len(access_token) > 16_384
        or any(ord(character) < 32 for character in access_token)
    ):
        return _unavailable(
            "container",
            "trivy",
            required,
            started_at,
            "A valid short-lived registry credential is required for private image scanning.",
        )

    runner = _registry_authenticated_runner(registry, username, access_token)
    return run_scan(
        "container",
        repo_path,
        image_ref=immutable_image,
        required=required,
        policy=policy,
        timeout_seconds=timeout_seconds,
        runner=runner,
        which=which,
    )


def run_tflint(
    repo_path: str | os.PathLike[str],
    *,
    required: bool = True,
    policy: ScanPolicy | None = None,
    timeout_seconds: int = 300,
    runner: Runner = _default_runner,
    which: Which = shutil.which,
) -> SecurityScanResult:
    """Run TFLint separately so IaC validation can expose both tools."""

    started_at = _utc_now()
    repository = _safe_repo_path(repo_path)
    executable = which("tflint")
    if not executable:
        return _unavailable("iac", "tflint", required, started_at, "tflint is not installed in the deployment worker.")
    try:
        execution = runner([executable, "--format", "json", "--recursive"], repository, timeout_seconds)
        try:
            findings = _parse_tflint(_json_payload(execution), repository)
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            return _unavailable("iac", "tflint", required, started_at, f"tflint output was invalid: {type(error).__name__}.")
        if execution.returncode not in _TOOL_EXIT_CODES["tflint"]:
            return _unavailable(
                "iac",
                "tflint",
                required,
                started_at,
                f"tflint did not complete successfully (exit code {execution.returncode}).",
            )
        if execution.returncode in _FINDING_EXIT_CODES["tflint"] and not findings:
            return _unavailable(
                "iac",
                "tflint",
                required,
                started_at,
                "tflint returned a findings exit code without validated findings.",
            )
        tool_version = _version("tflint", executable, repository, runner)
        if required and not tool_version:
            return _unavailable("iac", "tflint", required, started_at, "tflint version could not be verified.")
        status, blocking = _status_for(findings, policy or ScanPolicy())
        retained = _retained_findings(findings)
        return SecurityScanResult(
            kind="iac",
            tool="tflint",
            status=status,
            required=required,
            blocking=blocking,
            summary="No findings detected." if not findings else f"{len(findings)} validated finding(s) detected.",
            findings=retained,
            started_at=started_at,
            completed_at=_utc_now(),
            tool_version=tool_version,
            evidence={
                "result_count": len(findings),
                "retained_findings": len(retained),
                "output_retained": False,
            },
        )
    except (OSError, TimeoutError) as error:
        return _unavailable("iac", "tflint", required, started_at, _bounded(str(error))[:500])
