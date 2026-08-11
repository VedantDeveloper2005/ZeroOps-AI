"""Bounded, deterministic repository checks for deployment pipelines.

Repository code is untrusted executable code.  Public check entry points only
dispatch commands through an explicit :class:`RepositoryCheckExecutor` after
validating a fresh, source-bound disposable-isolation attestation.  The
credentialed deployment worker is never the default command-execution venue.

The private local subprocess helper exists solely for its low-level unit test;
it is deliberately unreachable from :func:`run_repository_check` and
:func:`run_repository_checks`.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Protocol, Sequence

try:
    import tomllib
except ImportError:  # pragma: no cover - Python 3.11+ is required in production
    tomllib = None  # type: ignore[assignment]

try:
    from backend.services.redaction import REDACTED, redact_sensitive_text, redact_sensitive_values
except ImportError:  # pragma: no cover - worker-style imports
    from services.redaction import REDACTED, redact_sensitive_text, redact_sensitive_values


CheckStage = Literal["dependency_installation", "code_quality", "unit_tests", "build"]
CheckStatus = Literal["passed", "failed", "skipped", "unavailable"]
CommandStatus = Literal["passed", "failed", "unavailable"]
Ecosystem = Literal["node", "python"]
NetworkPolicy = Literal["none", "restricted"]

_STAGE_ORDER: tuple[CheckStage, ...] = (
    "dependency_installation",
    "code_quality",
    "unit_tests",
    "build",
)
_MAX_MANIFEST_BYTES = 1_000_000
_MAX_COMPONENTS = 32
_MAX_DISCOVERY_DIRECTORIES = 2_000
_MAX_DISCOVERY_ENTRIES = 50_000
_MAX_DISCOVERY_DEPTH = 3
_MAX_COMMANDS_PER_STAGE = 64
_MAX_CAPTURE_BYTES = 32_000
_DEFAULT_DIAGNOSTIC_CHARS = 12_000
_MAX_TIMEOUT_SECONDS = 1_800
_MAX_ATTESTATION_AGE_SECONDS = 120
_MAX_ATTESTATION_CLOCK_SKEW_SECONDS = 5
_MAX_ATTESTATION_LIFETIME_SECONDS = _MAX_TIMEOUT_SECONDS + 300
_IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".next",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "venv",
}
_QUALITY_SCRIPTS = ("lint", "typecheck", "check", "format:check")
_TEST_SCRIPTS = ("test:unit", "test:ci", "test")
_LOCK_FILES = {
    "npm": ("package-lock.json", "npm-shrinkwrap.json"),
    "pnpm": ("pnpm-lock.yaml",),
    "yarn": ("yarn.lock",),
    "bun": ("bun.lock", "bun.lockb"),
}
_KNOWN_SECRET_PATTERN = re.compile(
    r"(?i)\b(?:"
    r"AKIA[0-9A-Z]{16}|"
    r"gh[pousr]_[A-Za-z0-9]{20,}|"
    r"sk-[A-Za-z0-9_-]{16,}|"
    r"xox[baprs]-[A-Za-z0-9-]{16,}"
    r")\b"
)
_JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_PEM_PATTERN = re.compile(
    r"-----BEGIN [^-\r\n]+-----[\s\S]*?-----END [^-\r\n]+-----",
    re.IGNORECASE,
)
_ANSI_PATTERN = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_REQUIREMENTS_FILE_PATTERN = re.compile(r"^requirements(?:[._-][A-Za-z0-9_.-]{1,100})?\.txt$")
_SOURCE_REVISION_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")
_CONTENT_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ISOLATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$")
_NETWORK_DESTINATION_PATTERN = re.compile(
    r"^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?(?::[1-9][0-9]{0,4})?$"
)
_FORBIDDEN_NETWORK_DESTINATIONS = {
    "169.254.169.254",
    "localhost",
    "metadata.azure.internal",
}


@dataclass(frozen=True)
class RepositoryComponent:
    """Non-sensitive facts for one Node or Python component."""

    ecosystem: Ecosystem
    relative_path: str
    manifests: tuple[str, ...] = ()
    package_manager: str | None = None
    package_manager_variant: str | None = None
    package_manager_root: str | None = None
    scripts: tuple[str, ...] = ()
    quality_tools: tuple[str, ...] = ()
    test_tool: str | None = None
    build_kind: str | None = None
    dependency_files: tuple[str, ...] = ()
    has_declared_dependencies: bool = False
    dependency_issue: str | None = None


@dataclass(frozen=True)
class RepositoryFacts:
    """Bounded repository inspection result.

    ``root_path`` is needed for execution but is deliberately omitted from
    ``to_dict`` so persisted evidence does not disclose worker filesystem
    layout.
    """

    root_path: str = field(repr=False)
    components: tuple[RepositoryComponent, ...] = ()
    errors: tuple[str, ...] = ()
    inspected_directories: int = 0

    def to_dict(self) -> dict[str, Any]:
        return redact_sensitive_values({
            "components": [asdict(component) for component in self.components],
            "errors": list(self.errors),
            "inspected_directories": self.inspected_directories,
        })


@dataclass(frozen=True)
class CommandExecution:
    """Bounded command result returned by an isolation executor."""

    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    stdout_truncated: bool = False
    stderr_truncated: bool = False


@dataclass(frozen=True)
class RepositoryIsolationRequest:
    """Exact source and stage an executor must materialize in isolation."""

    stage: CheckStage
    source_revision: str
    source_digest: str


@dataclass(frozen=True)
class RepositoryIsolationAttestation:
    """Security properties asserted by a trusted isolation executor.

    Attestations are process-local capability objects, not portable bearer
    tokens.  A configured executor is the trust boundary and must obtain these
    facts from its sandbox control plane rather than repository-controlled
    input.
    """

    isolation_id: str
    stage: CheckStage
    source_revision: str
    source_digest: str
    issued_at: datetime
    expires_at: datetime
    disposable: bool
    fresh_source: bool
    worker_filesystem_access: bool
    database_access: bool
    key_vault_access: bool
    imds_access: bool
    network_policy: NetworkPolicy
    allowed_network_destinations: tuple[str, ...] = ()


@dataclass(frozen=True)
class IsolationVerification:
    valid: bool
    reason: str


class RepositoryCheckExecutor(Protocol):
    """Trusted boundary for a pre-materialized disposable source sandbox.

    Implementations must not interpret ``relative_cwd`` on the deployment
    worker.  Resolution and execution happen inside the attested sandbox.
    """

    def attest(self, request: RepositoryIsolationRequest) -> RepositoryIsolationAttestation:
        ...

    def resolve_tool(
        self,
        tool: str,
        *,
        attestation: RepositoryIsolationAttestation,
    ) -> str | None:
        ...

    def execute(
        self,
        command: Sequence[str],
        *,
        relative_cwd: str,
        timeout_seconds: int,
        attestation: RepositoryIsolationAttestation,
    ) -> CommandExecution:
        ...


@dataclass(frozen=True)
class CheckCommandResult:
    label: str
    tool: str
    command: tuple[str, ...]
    working_directory: str
    status: CommandStatus
    exit_code: int | None
    duration_ms: int
    summary: str
    diagnostic_excerpt: str | None = None
    output_truncated: bool = False


@dataclass(frozen=True)
class RepositoryCheckResult:
    stage: CheckStage
    status: CheckStatus
    required: bool
    blocking: bool
    summary: str
    reason: str | None = None
    commands: tuple[CheckCommandResult, ...] = ()
    facts: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return redact_sensitive_values(asdict(self))


@dataclass(frozen=True)
class RepositoryCheckReport:
    facts: RepositoryFacts
    checks: tuple[RepositoryCheckResult, ...]
    blocking: bool

    def to_dict(self) -> dict[str, Any]:
        return redact_sensitive_values({
            "facts": self.facts.to_dict(),
            "checks": [check.to_dict() for check in self.checks],
            "blocking": self.blocking,
        })


@dataclass(frozen=True)
class _CommandPlan:
    label: str
    tool: str
    arguments: tuple[str, ...]
    relative_cwd: str


Runner = Callable[[Sequence[str], str, int, Mapping[str, str]], CommandExecution]
Which = Callable[[str], str | None]


def _aware_utc(value: datetime) -> datetime | None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(timezone.utc)


def _network_destination_reason(destination: str) -> str | None:
    normalized = destination.strip().lower()
    host = normalized.rsplit(":", 1)[0] if normalized.count(":") == 1 else normalized
    if (
        normalized != destination
        or not _NETWORK_DESTINATION_PATTERN.fullmatch(normalized)
        or "*" in normalized
    ):
        return "Restricted-network destinations must be exact lowercase host names with optional ports."
    if (
        host in _FORBIDDEN_NETWORK_DESTINATIONS
        or host.startswith("127.")
        or host.startswith("169.254.")
        or host.endswith(".local")
    ):
        return "Restricted-network destinations must not include local or instance-metadata endpoints."
    if ":" in normalized and int(normalized.rsplit(":", 1)[1]) > 65_535:
        return "Restricted-network destination ports must be valid TCP ports."
    return None


def verify_isolation_attestation(
    attestation: RepositoryIsolationAttestation,
    request: RepositoryIsolationRequest,
    *,
    now: datetime | None = None,
    minimum_validity_seconds: int = 1,
) -> IsolationVerification:
    """Validate an executor assertion without trusting repository-controlled data."""

    if not isinstance(attestation, RepositoryIsolationAttestation):
        return IsolationVerification(False, "The isolation executor returned an unsupported attestation.")
    if not _SOURCE_REVISION_PATTERN.fullmatch(request.source_revision):
        return IsolationVerification(False, "The expected source revision is not an immutable Git object ID.")
    if not _CONTENT_DIGEST_PATTERN.fullmatch(request.source_digest):
        return IsolationVerification(False, "The expected repository content digest is not a SHA-256 digest.")
    if (
        not isinstance(attestation.isolation_id, str)
        or not _ISOLATION_ID_PATTERN.fullmatch(attestation.isolation_id)
    ):
        return IsolationVerification(False, "The isolation attestation has an invalid isolation identifier.")
    if attestation.stage != request.stage:
        return IsolationVerification(False, "The isolation attestation is bound to a different repository-check stage.")
    if (
        not isinstance(attestation.source_revision, str)
        or attestation.source_revision != request.source_revision
    ):
        return IsolationVerification(False, "The isolation attestation is bound to a different source revision.")
    if (
        not isinstance(attestation.source_digest, str)
        or attestation.source_digest != request.source_digest
    ):
        return IsolationVerification(False, "The isolation attestation is bound to different repository content.")

    issued_at = _aware_utc(attestation.issued_at)
    expires_at = _aware_utc(attestation.expires_at)
    current_time = _aware_utc(now or datetime.now(timezone.utc))
    if issued_at is None or expires_at is None or current_time is None:
        return IsolationVerification(False, "Isolation attestation timestamps must be timezone-aware UTC instants.")
    if expires_at <= issued_at:
        return IsolationVerification(False, "The isolation attestation validity interval is invalid.")
    if expires_at - issued_at > timedelta(seconds=_MAX_ATTESTATION_LIFETIME_SECONDS):
        return IsolationVerification(False, "The isolation attestation lifetime exceeds the allowed execution lease.")
    if issued_at > current_time + timedelta(seconds=_MAX_ATTESTATION_CLOCK_SKEW_SECONDS):
        return IsolationVerification(False, "The isolation attestation was issued in the future.")
    if expires_at <= current_time:
        return IsolationVerification(False, "The isolation attestation has expired.")
    if current_time - issued_at > timedelta(seconds=_MAX_ATTESTATION_AGE_SECONDS):
        return IsolationVerification(False, "The isolation attestation is not fresh.")
    if minimum_validity_seconds < 1 or (
        expires_at < current_time + timedelta(seconds=minimum_validity_seconds)
    ):
        return IsolationVerification(
            False,
            "The isolation attestation expires before the command execution lease ends.",
        )

    if attestation.disposable is not True:
        return IsolationVerification(False, "Repository checks require a disposable isolation environment.")
    if attestation.fresh_source is not True:
        return IsolationVerification(False, "The isolation environment did not verify a fresh exact-source materialization.")
    denied_access = [
        label
        for enabled, label in (
            (attestation.worker_filesystem_access is not False, "deployment-worker filesystem"),
            (attestation.database_access is not False, "database"),
            (attestation.key_vault_access is not False, "Key Vault"),
            (attestation.imds_access is not False, "instance metadata service"),
        )
        if enabled
    ]
    if denied_access:
        return IsolationVerification(
            False,
            f"The isolation environment exposes forbidden access to {', '.join(denied_access)}.",
        )
    if (
        not isinstance(attestation.network_policy, str)
        or attestation.network_policy not in {"none", "restricted"}
    ):
        return IsolationVerification(False, "The isolation environment has no enforceable network policy.")
    if not isinstance(attestation.allowed_network_destinations, tuple):
        return IsolationVerification(False, "The isolation network allowlist must be an immutable tuple.")
    if attestation.network_policy == "none" and attestation.allowed_network_destinations:
        return IsolationVerification(False, "A network-disabled isolation cannot declare allowed destinations.")
    if attestation.network_policy == "restricted":
        if request.stage != "dependency_installation":
            return IsolationVerification(
                False,
                f"The {request.stage} stage must run with network access disabled.",
            )
        if not attestation.allowed_network_destinations:
            return IsolationVerification(False, "Restricted network access requires an exact destination allowlist.")
        if len(attestation.allowed_network_destinations) > 32:
            return IsolationVerification(False, "The restricted-network destination allowlist is too large.")
        for destination in attestation.allowed_network_destinations:
            if not isinstance(destination, str):
                return IsolationVerification(False, "Restricted-network destinations must be strings.")
            reason = _network_destination_reason(destination)
            if reason:
                return IsolationVerification(False, reason)
    return IsolationVerification(True, "Disposable repository isolation is verified.")


class _TailCapture:
    """Drain a process stream while retaining only a fixed-size tail."""

    def __init__(self, maximum_bytes: int = _MAX_CAPTURE_BYTES):
        self._maximum_bytes = maximum_bytes
        self._data = bytearray()
        self.total_bytes = 0
        self._lock = threading.Lock()

    def append(self, chunk: bytes) -> None:
        with self._lock:
            self.total_bytes += len(chunk)
            self._data.extend(chunk)
            overflow = len(self._data) - self._maximum_bytes
            if overflow > 0:
                del self._data[:overflow]

    def text(self) -> str:
        with self._lock:
            return bytes(self._data).decode("utf-8", errors="replace")

    @property
    def truncated(self) -> bool:
        return self.total_bytes > self._maximum_bytes


def _drain_stream(stream: Any, capture: _TailCapture) -> None:
    try:
        while True:
            chunk = stream.read(8_192)
            if not chunk:
                break
            capture.append(chunk)
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _kill_process(process: subprocess.Popen[bytes]) -> None:
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except (OSError, ProcessLookupError):
        pass


def _default_runner(
    command: Sequence[str],
    cwd: str,
    timeout_seconds: int,
    environment: Mapping[str, str],
) -> CommandExecution:
    """Run an argv command with bounded in-memory output and no shell."""

    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        list(command),
        cwd=cwd,
        env=dict(environment),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        close_fds=True,
        start_new_session=os.name == "posix",
        creationflags=creation_flags,
    )
    stdout_capture = _TailCapture()
    stderr_capture = _TailCapture()
    stdout_thread = threading.Thread(
        target=_drain_stream,
        args=(process.stdout, stdout_capture),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_drain_stream,
        args=(process.stderr, stderr_capture),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    timed_out = False
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_process(process)
        process.wait(timeout=10)
    finally:
        stdout_thread.join(timeout=10)
        stderr_thread.join(timeout=10)

    return CommandExecution(
        returncode=process.returncode if process.returncode is not None else -1,
        stdout=stdout_capture.text(),
        stderr=stderr_capture.text(),
        timed_out=timed_out,
        stdout_truncated=stdout_capture.truncated,
        stderr_truncated=stderr_capture.truncated,
    )


def _relative_path(path: Path, root: Path) -> str:
    relative = path.relative_to(root)
    return "." if not relative.parts else relative.as_posix()


def _safe_repository(repo_path: str | os.PathLike[str]) -> Path:
    root = Path(repo_path).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Repository checks require a directory.")
    return root


def _safe_manifest(path: Path, root: Path) -> bytes:
    if path.is_symlink():
        raise ValueError(f"{_relative_path(path, root)} must not be a symbolic link.")
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError("Repository metadata resolves outside the repository.") from error
    if not resolved.is_file():
        raise ValueError(f"{_relative_path(path, root)} must be a regular file.")
    size = resolved.stat().st_size
    if size > _MAX_MANIFEST_BYTES:
        raise ValueError(f"{_relative_path(path, root)} exceeds the metadata size limit.")
    with resolved.open("rb") as handle:
        content = handle.read(_MAX_MANIFEST_BYTES + 1)
    if len(content) > _MAX_MANIFEST_BYTES:
        raise ValueError(f"{_relative_path(path, root)} changed beyond the metadata size limit.")
    return content


def _read_json(path: Path, root: Path) -> dict[str, Any]:
    try:
        payload = json.loads(_safe_manifest(path, root).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{_relative_path(path, root)} is not valid UTF-8 JSON.") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{_relative_path(path, root)} must contain a JSON object.")
    return payload


def _read_toml(path: Path, root: Path) -> dict[str, Any]:
    if tomllib is None:
        raise ValueError("Python TOML inspection is unavailable in this worker runtime.")
    try:
        payload = tomllib.loads(_safe_manifest(path, root).decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f"{_relative_path(path, root)} is not valid UTF-8 TOML.") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{_relative_path(path, root)} must contain a TOML table.")
    return payload


def _discover_directories(root: Path) -> tuple[list[tuple[Path, tuple[str, ...]]], int, list[str]]:
    directories: list[tuple[Path, tuple[str, ...]]] = []
    errors: list[str] = []
    inspected = 0
    inspected_entries = 0
    pending: list[tuple[Path, int]] = [(root, 0)]
    while pending:
        current_path, depth = pending.pop(0)
        inspected += 1
        if inspected > _MAX_DISCOVERY_DIRECTORIES:
            errors.append("Repository discovery exceeded the directory limit.")
            break
        try:
            entries: list[os.DirEntry[str]] = []
            with os.scandir(current_path) as iterator:
                for entry in iterator:
                    inspected_entries += 1
                    if inspected_entries > _MAX_DISCOVERY_ENTRIES:
                        errors.append("Repository discovery exceeded the filesystem-entry limit.")
                        return directories, inspected, errors
                    entries.append(entry)
        except OSError as error:
            errors.append(f"Could not inspect {_relative_path(current_path, root)}: {type(error).__name__}.")
            continue
        entries.sort(key=lambda entry: entry.name)
        file_names = {
            entry.name
            for entry in entries
            if entry.is_file(follow_symlinks=True)
        }
        has_node = "package.json" in file_names
        has_python = bool(file_names & {
            "pyproject.toml",
            "requirements.txt",
            "requirements-dev.txt",
            "requirements-test.txt",
            "poetry.lock",
            "uv.lock",
            "Pipfile",
            "Pipfile.lock",
            "setup.py",
            "setup.cfg",
        }) or any(_REQUIREMENTS_FILE_PATTERN.fullmatch(name) for name in file_names)
        if current_path == root and not has_python:
            has_python = any(name.endswith(".py") for name in file_names)
        if has_node or has_python:
            directories.append((current_path, tuple(sorted(file_names))))
        if depth < _MAX_DISCOVERY_DEPTH:
            child_directories = [
                current_path / entry.name
                for entry in entries
                if entry.name not in _IGNORED_DIRECTORIES
                and not entry.name.startswith(".")
                and not entry.is_symlink()
                and entry.is_dir(follow_symlinks=False)
            ]
            pending.extend((child, depth + 1) for child in child_directories)
    return directories, inspected, errors


def _manager_at(path: Path) -> tuple[str | None, str | None]:
    managers = [
        manager
        for manager, lock_files in _LOCK_FILES.items()
        if any((path / filename).is_file() for filename in lock_files)
    ]
    if len(managers) > 1:
        return None, "Multiple Node lockfile formats make dependency installation ambiguous."
    return (managers[0], None) if managers else (None, None)


def _declared_manager(package: Mapping[str, Any]) -> str | None:
    value = package.get("packageManager")
    if not isinstance(value, str) or "@" not in value:
        return None
    name = value.split("@", 1)[0].strip().lower()
    return name if name in _LOCK_FILES else None


def _declared_manager_variant(package: Mapping[str, Any], manager: str, path: Path) -> str | None:
    if manager != "yarn":
        return None
    value = package.get("packageManager")
    if isinstance(value, str) and value.lower().startswith("yarn@"):
        version = value.split("@", 1)[1].split(".", 1)[0]
        if version.isdigit() and int(version) >= 2:
            return "berry"
    return "berry" if (path / ".yarnrc.yml").is_file() else "classic"


def _node_component(path: Path, root: Path) -> RepositoryComponent:
    package = _read_json(path / "package.json", root)
    scripts_payload = package.get("scripts", {})
    if scripts_payload is None:
        scripts_payload = {}
    if not isinstance(scripts_payload, dict):
        raise ValueError(f"{_relative_path(path / 'package.json', root)} scripts must be a JSON object.")
    scripts = tuple(sorted(
        str(name)
        for name, value in scripts_payload.items()
        if isinstance(name, str) and isinstance(value, str)
    ))
    manager: str | None = None
    manager_variant: str | None = None
    manager_root: Path | None = None
    manager_issue: str | None = None
    candidate = path
    while True:
        candidate_manager, candidate_issue = _manager_at(candidate)
        if candidate_issue:
            manager_issue = candidate_issue
            manager_root = candidate
            break
        if candidate_manager:
            manager = candidate_manager
            manager_root = candidate
            break
        if candidate == root:
            break
        candidate = candidate.parent

    declared = _declared_manager(package)
    manager_package = package
    if manager_root and manager_root != path and (manager_root / "package.json").is_file():
        manager_package = _read_json(manager_root / "package.json", root)
        root_declared = _declared_manager(manager_package)
        if root_declared:
            declared = root_declared
    if manager and declared and manager != declared:
        manager_issue = f"packageManager declares {declared}, but the selected lockfile requires {manager}."
    if not manager:
        manager = declared or "npm"
        manager_root = path
    manager_variant = _declared_manager_variant(manager_package, manager, manager_root or path)

    dependencies = package.get("dependencies")
    development_dependencies = package.get("devDependencies")
    has_dependencies = bool(dependencies) or bool(development_dependencies)
    if has_dependencies and manager_issue is None and not any(
        (manager_root / filename).is_file()
        for filename in _LOCK_FILES.get(manager, ())
    ):
        manager_issue = "Node dependencies are declared without a supported lockfile."

    manifests = ["package.json"]
    if manager_root == path:
        manifests.extend(
            filename
            for filename in _LOCK_FILES.get(manager, ())
            if (path / filename).is_file()
        )
    for filename in manifests:
        _safe_manifest(path / filename, root)
    if manager_root and manager_root != path:
        for filename in _LOCK_FILES.get(manager, ()):
            lock_path = manager_root / filename
            if lock_path.is_file():
                _safe_manifest(lock_path, root)
    return RepositoryComponent(
        ecosystem="node",
        relative_path=_relative_path(path, root),
        manifests=tuple(manifests),
        package_manager=manager,
        package_manager_variant=manager_variant,
        package_manager_root=_relative_path(manager_root or path, root),
        scripts=scripts,
        has_declared_dependencies=has_dependencies,
        dependency_issue=manager_issue,
        build_kind="package-script" if "build" in scripts else None,
    )


def _nested_table(payload: Mapping[str, Any], *keys: str) -> Mapping[str, Any] | None:
    current: Any = payload
    for key in keys:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current if isinstance(current, Mapping) else None


def _python_component(path: Path, root: Path, discovered_filenames: Sequence[str]) -> RepositoryComponent:
    pyproject_path = path / "pyproject.toml"
    pyproject: dict[str, Any] = _read_toml(pyproject_path, root) if pyproject_path.is_file() else {}
    filenames = set(discovered_filenames)
    metadata_files = filenames & {
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
        "requirements-test.txt",
        "poetry.lock",
        "uv.lock",
        "Pipfile",
        "Pipfile.lock",
        "setup.py",
        "setup.cfg",
        "ruff.toml",
        ".ruff.toml",
        "mypy.ini",
        ".mypy.ini",
        "pyrightconfig.json",
        ".flake8",
        "pytest.ini",
    }
    metadata_files.update(
        filename for filename in filenames if _REQUIREMENTS_FILE_PATTERN.fullmatch(filename)
    )
    for filename in metadata_files:
        _safe_manifest(path / filename, root)
    dependency_files: list[str] = []
    dependency_issue: str | None = None
    manager: str | None = None
    if "uv.lock" in filenames:
        manager = "uv"
        dependency_files = ["uv.lock", "pyproject.toml"]
        if "pyproject.toml" not in filenames:
            dependency_issue = "uv.lock requires pyproject.toml for deterministic installation."
    elif "poetry.lock" in filenames:
        manager = "poetry"
        dependency_files = ["poetry.lock", "pyproject.toml"]
        if "pyproject.toml" not in filenames:
            dependency_issue = "poetry.lock requires pyproject.toml for deterministic installation."
    elif "Pipfile.lock" in filenames:
        manager = "pipenv"
        dependency_files = ["Pipfile.lock", "Pipfile"]
        if "Pipfile" not in filenames:
            dependency_issue = "Pipfile.lock requires Pipfile for deterministic installation."
    else:
        requirements = sorted(
            (filename for filename in filenames if _REQUIREMENTS_FILE_PATTERN.fullmatch(filename)),
            key=lambda filename: (
                filename != "requirements.txt",
                filename not in {"requirements-dev.txt", "requirements-test.txt"},
                filename,
            ),
        )
        if requirements:
            manager = "pip"
            dependency_files = requirements

    project_table = _nested_table(pyproject, "project")
    poetry_table = _nested_table(pyproject, "tool", "poetry")
    has_dependencies = bool(dependency_files)
    if project_table and project_table.get("dependencies"):
        has_dependencies = True
    if poetry_table and poetry_table.get("dependencies"):
        has_dependencies = True
    if has_dependencies and manager is None and dependency_issue is None:
        dependency_issue = "Python dependencies are declared without a supported lockfile or requirements file."

    quality_tools: list[str] = []
    if "ruff.toml" in filenames or ".ruff.toml" in filenames or _nested_table(pyproject, "tool", "ruff"):
        quality_tools.append("ruff")
    if _nested_table(pyproject, "tool", "black"):
        quality_tools.append("black")
    if "mypy.ini" in filenames or ".mypy.ini" in filenames or _nested_table(pyproject, "tool", "mypy"):
        quality_tools.append("mypy")
    if "pyrightconfig.json" in filenames or _nested_table(pyproject, "tool", "pyright"):
        quality_tools.append("pyright")
    if ".flake8" in filenames:
        quality_tools.append("flake8")

    has_tests = any((path / dirname).is_dir() for dirname in ("tests", "test"))
    has_pytest_config = (
        "pytest.ini" in filenames
        or _nested_table(pyproject, "tool", "pytest") is not None
    )
    manifests = sorted(filename for filename in filenames if filename in {
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
        "requirements-test.txt",
        "poetry.lock",
        "uv.lock",
        "Pipfile",
        "Pipfile.lock",
        "setup.py",
        "setup.cfg",
    } or _REQUIREMENTS_FILE_PATTERN.fullmatch(filename))
    return RepositoryComponent(
        ecosystem="python",
        relative_path=_relative_path(path, root),
        manifests=tuple(manifests),
        package_manager=manager,
        package_manager_root=_relative_path(path, root),
        quality_tools=tuple(quality_tools),
        test_tool="pytest" if has_tests or has_pytest_config else None,
        build_kind="compileall",
        dependency_files=tuple(dependency_files),
        has_declared_dependencies=has_dependencies,
        dependency_issue=dependency_issue,
    )


def inspect_repository(repo_path: str | os.PathLike[str]) -> RepositoryFacts:
    """Inspect common Node/Python facts with fixed depth, count, and size limits."""

    root = _safe_repository(repo_path)
    directories, inspected, errors = _discover_directories(root)
    components: list[RepositoryComponent] = []
    for path, filenames in directories:
        if len(components) >= _MAX_COMPONENTS:
            errors.append("Repository inspection exceeded the component limit.")
            break
        try:
            if (path / "package.json").is_file():
                components.append(_node_component(path, root))
            if len(components) >= _MAX_COMPONENTS:
                if any(filename in filenames for filename in {
                    "pyproject.toml", "requirements.txt", "requirements-dev.txt", "requirements-test.txt",
                    "poetry.lock", "uv.lock", "Pipfile", "Pipfile.lock", "setup.py", "setup.cfg",
                }) or any(_REQUIREMENTS_FILE_PATTERN.fullmatch(filename) for filename in filenames):
                    errors.append("Repository inspection exceeded the component limit.")
                break
            python_markers = any((path / marker).is_file() for marker in {
                "pyproject.toml",
                "requirements.txt",
                "requirements-dev.txt",
                "requirements-test.txt",
                "poetry.lock",
                "uv.lock",
                "Pipfile",
                "Pipfile.lock",
                "setup.py",
                "setup.cfg",
            }) or any(_REQUIREMENTS_FILE_PATTERN.fullmatch(filename) for filename in filenames)
            if path == root and not python_markers:
                python_markers = any(filename.endswith(".py") for filename in filenames)
            if python_markers:
                components.append(_python_component(path, root, filenames))
        except (OSError, ValueError) as error:
            errors.append(str(error))
    return RepositoryFacts(
        root_path=str(root),
        components=tuple(components),
        errors=tuple(errors),
        inspected_directories=inspected,
    )


def _node_install_arguments(manager: str, variant: str | None = None) -> tuple[str, ...]:
    if manager == "npm":
        return ("ci", "--ignore-scripts", "--no-audit", "--no-fund")
    if manager == "pnpm":
        return ("install", "--frozen-lockfile", "--ignore-scripts")
    if manager == "yarn":
        if variant == "berry":
            return ("install", "--immutable", "--mode=skip-builds")
        return ("install", "--frozen-lockfile", "--ignore-scripts", "--non-interactive")
    if manager == "bun":
        return ("install", "--frozen-lockfile", "--ignore-scripts")
    raise ValueError("Unsupported Node package manager.")


def _node_script_arguments(manager: str, script: str) -> tuple[str, ...]:
    return ("run", script)


def _dependency_plans(component: RepositoryComponent) -> list[_CommandPlan]:
    if component.dependency_issue:
        return []
    if not component.has_declared_dependencies:
        return []
    cwd = component.package_manager_root or component.relative_path
    if component.ecosystem == "node":
        manager = component.package_manager or "npm"
        return [_CommandPlan(
            label=f"Install Node dependencies ({component.relative_path})",
            tool=manager,
            arguments=_node_install_arguments(manager, component.package_manager_variant),
            relative_cwd=cwd,
        )]
    manager = component.package_manager
    if manager == "uv":
        return [_CommandPlan("Install Python dependencies with uv", "uv", ("sync", "--frozen"), cwd)]
    if manager == "poetry":
        return [_CommandPlan(
            "Install Python dependencies with Poetry",
            "poetry",
            ("install", "--no-interaction", "--no-ansi"),
            cwd,
        )]
    if manager == "pipenv":
        return [_CommandPlan("Install Python dependencies with Pipenv", "pipenv", ("sync", "--dev"), cwd)]
    if manager == "pip":
        plans: list[_CommandPlan] = []
        for filename in component.dependency_files:
            plans.append(_CommandPlan(
                label=f"Install Python dependencies from {filename}",
                tool="python",
                arguments=(
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--no-input",
                    "--requirement",
                    filename,
                ),
                relative_cwd=cwd,
            ))
        return plans
    return []


def _quality_plans(component: RepositoryComponent) -> list[_CommandPlan]:
    cwd = component.relative_path
    if component.ecosystem == "node":
        manager = component.package_manager or "npm"
        return [
            _CommandPlan(
                label=f"Run Node {script} ({component.relative_path})",
                tool=manager,
                arguments=_node_script_arguments(manager, script),
                relative_cwd=cwd,
            )
            for script in _QUALITY_SCRIPTS
            if script in component.scripts
        ]
    arguments = {
        "ruff": ("check", "."),
        "black": ("--check", "."),
        "mypy": ("." ,),
        "pyright": (".",),
        "flake8": (".",),
    }
    return [
        _CommandPlan(
            label=f"Run {tool} ({component.relative_path})",
            tool=tool,
            arguments=arguments[tool],
            relative_cwd=cwd,
        )
        for tool in component.quality_tools
    ]


def _test_plans(component: RepositoryComponent) -> list[_CommandPlan]:
    cwd = component.relative_path
    if component.ecosystem == "node":
        manager = component.package_manager or "npm"
        script = next((candidate for candidate in _TEST_SCRIPTS if candidate in component.scripts), None)
        return [] if script is None else [_CommandPlan(
            label=f"Run Node unit tests ({component.relative_path})",
            tool=manager,
            arguments=_node_script_arguments(manager, script),
            relative_cwd=cwd,
        )]
    if component.test_tool == "pytest":
        return [_CommandPlan(
            label=f"Run Python unit tests ({component.relative_path})",
            tool="pytest",
            arguments=("-q",),
            relative_cwd=cwd,
        )]
    return []


def _build_plans(component: RepositoryComponent) -> list[_CommandPlan]:
    cwd = component.relative_path
    if component.ecosystem == "node" and component.build_kind == "package-script":
        manager = component.package_manager or "npm"
        return [_CommandPlan(
            label=f"Build Node application ({component.relative_path})",
            tool=manager,
            arguments=_node_script_arguments(manager, "build"),
            relative_cwd=cwd,
        )]
    if component.ecosystem == "python" and component.build_kind == "compileall":
        exclusion = r"(^|[\\/])(?:\.git|\.venv|venv|node_modules|__pycache__)(?:[\\/]|$)"
        return [_CommandPlan(
            label=f"Compile Python application ({component.relative_path})",
            tool="python",
            arguments=("-m", "compileall", "-q", "-x", exclusion, "."),
            relative_cwd=cwd,
        )]
    return []


def _plans(stage: CheckStage, facts: RepositoryFacts) -> tuple[list[_CommandPlan], list[str]]:
    planner = {
        "dependency_installation": _dependency_plans,
        "code_quality": _quality_plans,
        "unit_tests": _test_plans,
        "build": _build_plans,
    }[stage]
    issues = list(facts.errors)
    if stage == "dependency_installation":
        issues.extend(
            component.dependency_issue
            for component in facts.components
            if component.dependency_issue
        )
    plans: list[_CommandPlan] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    for component in facts.components:
        for plan in planner(component):
            key = (plan.relative_cwd, plan.tool, plan.arguments)
            if key not in seen:
                seen.add(key)
                plans.append(plan)
    if len(plans) > _MAX_COMMANDS_PER_STAGE:
        issues.append("Repository check planning exceeded the command limit.")
        plans = plans[:_MAX_COMMANDS_PER_STAGE]
    return plans, issues


def _safe_environment(isolated_home: str) -> dict[str, str]:
    allowed = (
        "PATH",
        "PATHEXT",
        "SystemRoot",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "LANG",
        "LC_ALL",
        "TMP",
        "TEMP",
        "TMPDIR",
    )
    environment = {key: os.environ[key] for key in allowed if os.environ.get(key)}
    null_device = os.devnull
    environment.update({
        "CI": "1",
        "NO_COLOR": "1",
        "FORCE_COLOR": "0",
        "HOME": isolated_home,
        "USERPROFILE": isolated_home,
        "XDG_CACHE_HOME": str(Path(isolated_home) / "cache"),
        "NPM_CONFIG_USERCONFIG": null_device,
        "NPM_CONFIG_CACHE": str(Path(isolated_home) / "npm-cache"),
        "NPM_CONFIG_AUDIT": "false",
        "NPM_CONFIG_FUND": "false",
        "PIP_CONFIG_FILE": null_device,
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_NO_INPUT": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": null_device,
        "PYTHONPYCACHEPREFIX": str(Path(isolated_home) / "pycache"),
    })
    return environment


def _sanitize_diagnostic(stdout: str, stderr: str, maximum_chars: int) -> str | None:
    combined = "\n".join(part for part in (stdout, stderr) if part)
    if not combined:
        return None
    combined = _ANSI_PATTERN.sub("", combined)
    combined = _CONTROL_PATTERN.sub("", combined)
    combined = _PEM_PATTERN.sub(REDACTED, combined)
    combined = _KNOWN_SECRET_PATTERN.sub(REDACTED, combined)
    combined = _JWT_PATTERN.sub(REDACTED, combined)
    combined = redact_sensitive_text(combined, maximum_length=_MAX_CAPTURE_BYTES * 2)
    if len(combined) > maximum_chars:
        combined = combined[-maximum_chars:]
    return combined.strip() or None


def _resolve_working_directory(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve(strict=True) if relative != "." else root
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError("A repository check working directory escaped the repository.") from error
    if not candidate.is_dir():
        raise ValueError("A repository check working directory is not a directory.")
    return candidate


def _execute_isolated_plan(
    plan: _CommandPlan,
    *,
    timeout_seconds: int,
    diagnostic_chars: int,
    executor: RepositoryCheckExecutor,
    attestation: RepositoryIsolationAttestation,
) -> CheckCommandResult:
    started = time.monotonic()
    display_command = (plan.tool, *plan.arguments)
    try:
        executable = executor.resolve_tool(plan.tool, attestation=attestation)
    except Exception as error:
        return CheckCommandResult(
            label=plan.label,
            tool=plan.tool,
            command=display_command,
            working_directory=plan.relative_cwd,
            status="unavailable",
            exit_code=None,
            duration_ms=round((time.monotonic() - started) * 1_000),
            summary=f"The isolation executor could not resolve {plan.tool}: {type(error).__name__}.",
        )
    if not executable:
        return CheckCommandResult(
            label=plan.label,
            tool=plan.tool,
            command=display_command,
            working_directory=plan.relative_cwd,
            status="unavailable",
            exit_code=None,
            duration_ms=round((time.monotonic() - started) * 1_000),
            summary=f"Required tool {plan.tool} is not installed in the disposable isolation environment.",
        )
    if (
        not isinstance(executable, str)
        or len(executable) > 1_000
        or any(character in executable for character in ("\x00", "\r", "\n"))
    ):
        return CheckCommandResult(
            label=plan.label,
            tool=plan.tool,
            command=display_command,
            working_directory=plan.relative_cwd,
            status="unavailable",
            exit_code=None,
            duration_ms=round((time.monotonic() - started) * 1_000),
            summary=f"The isolation executor returned an invalid path for {plan.tool}.",
        )
    try:
        execution = executor.execute(
            [executable, *plan.arguments],
            relative_cwd=plan.relative_cwd,
            timeout_seconds=timeout_seconds,
            attestation=attestation,
        )
        if not isinstance(execution, CommandExecution):
            raise TypeError("Isolation executor returned an unsupported result.")
        if (
            type(execution.returncode) is not int
            or not isinstance(execution.stdout, str)
            or not isinstance(execution.stderr, str)
            or type(execution.timed_out) is not bool
            or type(execution.stdout_truncated) is not bool
            or type(execution.stderr_truncated) is not bool
        ):
            raise TypeError("Isolation executor returned malformed command evidence.")
    except Exception as error:
        return CheckCommandResult(
            label=plan.label,
            tool=plan.tool,
            command=display_command,
            working_directory=plan.relative_cwd,
            status="unavailable",
            exit_code=None,
            duration_ms=round((time.monotonic() - started) * 1_000),
            summary=f"The isolation executor could not start {plan.tool}: {type(error).__name__}.",
        )

    duration_ms = round((time.monotonic() - started) * 1_000)
    diagnostic = _sanitize_diagnostic(execution.stdout, execution.stderr, diagnostic_chars)
    truncated = execution.stdout_truncated or execution.stderr_truncated
    if execution.timed_out:
        return CheckCommandResult(
            label=plan.label,
            tool=plan.tool,
            command=display_command,
            working_directory=plan.relative_cwd,
            status="failed",
            exit_code=execution.returncode,
            duration_ms=duration_ms,
            summary=f"The command exceeded its {timeout_seconds}s execution limit.",
            diagnostic_excerpt=diagnostic,
            output_truncated=truncated,
        )
    if execution.returncode != 0:
        return CheckCommandResult(
            label=plan.label,
            tool=plan.tool,
            command=display_command,
            working_directory=plan.relative_cwd,
            status="failed",
            exit_code=execution.returncode,
            duration_ms=duration_ms,
            summary=f"The command exited with code {execution.returncode}.",
            diagnostic_excerpt=diagnostic,
            output_truncated=truncated,
        )
    return CheckCommandResult(
        label=plan.label,
        tool=plan.tool,
        command=display_command,
        working_directory=plan.relative_cwd,
        status="passed",
        exit_code=0,
        duration_ms=duration_ms,
        summary="The command completed successfully.",
        diagnostic_excerpt=None,
        output_truncated=truncated,
    )


def _fact_summary(
    facts: RepositoryFacts,
    *,
    attestation: RepositoryIsolationAttestation | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "component_count": len(facts.components),
        "ecosystems": sorted({component.ecosystem for component in facts.components}),
        "component_paths": sorted({component.relative_path for component in facts.components}),
    }
    if attestation is not None:
        summary["isolation"] = {
            "isolation_id": attestation.isolation_id,
            "stage": attestation.stage,
            "source_revision": attestation.source_revision,
            "source_digest": attestation.source_digest,
            "disposable": attestation.disposable,
            "fresh_source": attestation.fresh_source,
            "network_policy": attestation.network_policy,
            "allowed_network_destination_count": len(attestation.allowed_network_destinations),
            "expires_at": attestation.expires_at.astimezone(timezone.utc).isoformat(),
        }
    return summary


def _isolation_failure(
    stage: CheckStage,
    *,
    required: bool,
    reason: str,
    facts: RepositoryFacts,
    commands: Sequence[CheckCommandResult] = (),
) -> RepositoryCheckResult:
    return RepositoryCheckResult(
        stage=stage,
        status="unavailable",
        required=required,
        blocking=required,
        summary="A verified disposable isolation environment is unavailable for this repository check.",
        reason=reason,
        commands=tuple(commands),
        facts=_fact_summary(facts),
    )


def _attest_executor(
    executor: RepositoryCheckExecutor,
    request: RepositoryIsolationRequest,
    *,
    timeout_seconds: int,
) -> tuple[RepositoryIsolationAttestation | None, str | None]:
    try:
        attestation = executor.attest(request)
    except Exception as error:
        return None, f"The isolation executor could not attest its sandbox: {type(error).__name__}."
    verification = verify_isolation_attestation(
        attestation,
        request,
        minimum_validity_seconds=timeout_seconds,
    )
    if not verification.valid:
        return None, verification.reason
    return attestation, None


def run_repository_check(
    stage: CheckStage,
    repo_path: str | os.PathLike[str],
    *,
    facts: RepositoryFacts | None = None,
    required: bool = True,
    timeout_seconds: int = 600,
    diagnostic_chars: int = _DEFAULT_DIAGNOSTIC_CHARS,
    executor: RepositoryCheckExecutor | None = None,
    source_revision: str | None = None,
    source_digest: str | None = None,
    runner: Runner | None = None,
    which: Which | None = None,
) -> RepositoryCheckResult:
    """Run one stage only through a fresh source-bound isolation executor.

    ``runner`` and ``which`` remain accepted for call compatibility but are
    never invoked.  Their presence without an executor fails closed.
    """

    if stage not in _STAGE_ORDER:
        raise ValueError("Unsupported repository check stage.")
    if not 1 <= timeout_seconds <= _MAX_TIMEOUT_SECONDS:
        raise ValueError(f"timeout_seconds must be between 1 and {_MAX_TIMEOUT_SECONDS}.")
    if not 256 <= diagnostic_chars <= _MAX_CAPTURE_BYTES:
        raise ValueError(f"diagnostic_chars must be between 256 and {_MAX_CAPTURE_BYTES}.")
    root = _safe_repository(repo_path)
    repository_facts = facts or inspect_repository(root)
    if Path(repository_facts.root_path).resolve() != root:
        raise ValueError("Repository facts belong to a different repository.")
    plans, issues = _plans(stage, repository_facts)
    summary_facts = _fact_summary(repository_facts)
    if issues:
        reason = "; ".join(dict.fromkeys(issues))[:1_000]
        return RepositoryCheckResult(
            stage=stage,
            status="unavailable",
            required=required,
            blocking=required,
            summary="Repository metadata could not produce a safe deterministic command plan.",
            reason=reason,
            facts=summary_facts,
        )
    if not plans:
        descriptions = {
            "dependency_installation": "No declared dependencies require installation.",
            "code_quality": "No supported code-quality convention is configured.",
            "unit_tests": "No supported unit-test convention is configured.",
            "build": "No supported application build is applicable.",
        }
        return RepositoryCheckResult(
            stage=stage,
            status="skipped",
            required=required,
            blocking=False,
            summary=descriptions[stage],
            reason="The stage is not relevant to the inspected repository facts.",
            facts=summary_facts,
        )

    if runner is not None or which is not None:
        return _isolation_failure(
            stage,
            required=required,
            reason=(
                "Direct runner and tool-resolver injection is disabled because it can execute "
                "repository code in the credentialed deployment worker."
            ),
            facts=repository_facts,
        )
    if executor is None:
        return _isolation_failure(
            stage,
            required=required,
            reason="No trusted repository isolation executor is configured.",
            facts=repository_facts,
        )
    normalized_revision = str(source_revision or "").strip().lower()
    normalized_digest = str(source_digest or "").strip().lower()
    request = RepositoryIsolationRequest(
        stage=stage,
        source_revision=normalized_revision,
        source_digest=normalized_digest,
    )
    attestation, isolation_reason = _attest_executor(
        executor,
        request,
        timeout_seconds=timeout_seconds,
    )
    if attestation is None:
        return _isolation_failure(
            stage,
            required=required,
            reason=isolation_reason or "The isolation attestation could not be verified.",
            facts=repository_facts,
        )

    command_results: list[CheckCommandResult] = []
    for plan_index, plan in enumerate(plans):
        if plan_index:
            attestation, isolation_reason = _attest_executor(
                executor,
                request,
                timeout_seconds=timeout_seconds,
            )
            if attestation is None:
                return _isolation_failure(
                    stage,
                    required=required,
                    reason=isolation_reason or "The isolation attestation could not be renewed.",
                    facts=repository_facts,
                    commands=command_results,
                )
        result = _execute_isolated_plan(
            plan,
            timeout_seconds=timeout_seconds,
            diagnostic_chars=diagnostic_chars,
            executor=executor,
            attestation=attestation,
        )
        command_results.append(result)
        if result.status != "passed":
            status: CheckStatus = "unavailable" if result.status == "unavailable" else "failed"
            return RepositoryCheckResult(
                stage=stage,
                status=status,
                required=required,
                blocking=required,
                summary=f"{result.label} did not complete successfully.",
                reason=result.summary,
                commands=tuple(command_results),
                facts=_fact_summary(repository_facts, attestation=attestation),
            )
    return RepositoryCheckResult(
        stage=stage,
        status="passed",
        required=required,
        blocking=False,
        summary=f"{len(command_results)} applicable command(s) completed successfully.",
        commands=tuple(command_results),
        facts=_fact_summary(repository_facts, attestation=attestation),
    )


def run_repository_checks(
    repo_path: str | os.PathLike[str],
    *,
    stages: Sequence[CheckStage] = _STAGE_ORDER,
    required: bool = True,
    stop_on_blocking: bool = True,
    timeout_seconds: int = 600,
    diagnostic_chars: int = _DEFAULT_DIAGNOSTIC_CHARS,
    executor: RepositoryCheckExecutor | None = None,
    source_revision: str | None = None,
    source_digest: str | None = None,
    runner: Runner | None = None,
    which: Which | None = None,
) -> RepositoryCheckReport:
    """Run selected stages in order, explicitly skipping blocked descendants."""

    invalid = [stage for stage in stages if stage not in _STAGE_ORDER]
    if invalid:
        raise ValueError("Unsupported repository check stage.")
    requested = set(stages)
    ordered = tuple(stage for stage in _STAGE_ORDER if stage in requested)
    facts = inspect_repository(repo_path)
    checks: list[RepositoryCheckResult] = []
    blocking_stage: CheckStage | None = None
    for stage in ordered:
        if blocking_stage and stop_on_blocking:
            checks.append(RepositoryCheckResult(
                stage=stage,
                status="skipped",
                required=required,
                blocking=False,
                summary=f"Not executed because {blocking_stage} blocked the repository check sequence.",
                reason="An earlier required stage did not pass.",
                facts=_fact_summary(facts),
            ))
            continue
        result = run_repository_check(
            stage,
            repo_path,
            facts=facts,
            required=required,
            timeout_seconds=timeout_seconds,
            diagnostic_chars=diagnostic_chars,
            executor=executor,
            source_revision=source_revision,
            source_digest=source_digest,
            runner=runner,
            which=which,
        )
        checks.append(result)
        if result.blocking:
            blocking_stage = stage
    return RepositoryCheckReport(
        facts=facts,
        checks=tuple(checks),
        blocking=any(check.blocking for check in checks),
    )
