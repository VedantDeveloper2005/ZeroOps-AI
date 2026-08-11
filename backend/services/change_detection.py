"""Deterministic change detection for change-aware deployment pipelines.

The service in this module deliberately performs no Git, database, model, or
cloud-provider calls.  Callers provide the files from a repository snapshot
and, when available, the paths returned by a Git diff.  The resulting values
are safe to persist: repository contents are reduced to SHA-256 digests and
only environment-variable *names* are retained.

Repository AI analysis is intentionally reusable for documentation and normal
application-code changes.  Changes that can alter dependencies, deployment,
infrastructure, Kubernetes resources, security posture, or service topology
require a fresh analysis.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
from pathlib import PurePosixPath
import re
from typing import Iterable, Mapping


CHANGE_DETECTION_VERSION = "change-detection-v1"

# Persistence bounds are part of the classifier contract.  Increasing any of
# them requires a version bump so identical inputs never acquire a different
# persisted representation under the same classifier version.
MAX_SAMPLED_PATHS = 100
MAX_DETECTED_SERVICES = 100
MAX_ENVIRONMENT_VARIABLE_NAMES = 256
MAX_DETECTED_SERVICE_LENGTH = 256
MAX_ENVIRONMENT_VARIABLE_NAME_LENGTH = 256


class ChangeCategory(str, Enum):
    """Stable categories stored with a pipeline's change-detection decision."""

    NO_RELEVANT_CHANGE = "NO_RELEVANT_CHANGE"
    APPLICATION_CODE_CHANGE = "APPLICATION_CODE_CHANGE"
    DEPENDENCY_CHANGE = "DEPENDENCY_CHANGE"
    DEPLOYMENT_CONFIG_CHANGE = "DEPLOYMENT_CONFIG_CHANGE"
    INFRASTRUCTURE_CHANGE = "INFRASTRUCTURE_CHANGE"
    KUBERNETES_CHANGE = "KUBERNETES_CHANGE"
    SECURITY_RELEVANT_CHANGE = "SECURITY_RELEVANT_CHANGE"
    MAJOR_ARCHITECTURE_CHANGE = "MAJOR_ARCHITECTURE_CHANGE"


class AnalysisDecisionReason(str, Enum):
    """Machine-readable reasons for an analysis reuse decision."""

    NO_PREVIOUS_ANALYSIS = "no_previous_analysis"
    NO_DEPLOYMENT_RELEVANT_CHANGE = "no_deployment_relevant_change"
    DEPLOYMENT_RELEVANT_CHANGE = "deployment_relevant_change"


_CATEGORY_PRIORITY = {
    ChangeCategory.MAJOR_ARCHITECTURE_CHANGE: 0,
    ChangeCategory.KUBERNETES_CHANGE: 1,
    ChangeCategory.INFRASTRUCTURE_CHANGE: 2,
    ChangeCategory.DEPLOYMENT_CONFIG_CHANGE: 3,
    ChangeCategory.DEPENDENCY_CHANGE: 4,
    ChangeCategory.SECURITY_RELEVANT_CHANGE: 5,
    ChangeCategory.APPLICATION_CODE_CHANGE: 6,
    ChangeCategory.NO_RELEVANT_CHANGE: 7,
}

_ANALYSIS_TRIGGER_CATEGORIES = frozenset(
    {
        ChangeCategory.DEPENDENCY_CHANGE,
        ChangeCategory.DEPLOYMENT_CONFIG_CHANGE,
        ChangeCategory.INFRASTRUCTURE_CHANGE,
        ChangeCategory.KUBERNETES_CHANGE,
        ChangeCategory.SECURITY_RELEVANT_CHANGE,
        ChangeCategory.MAJOR_ARCHITECTURE_CHANGE,
    }
)

_IGNORED_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".next",
        ".pytest_cache",
        ".ruff_cache",
        ".svn",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "node_modules",
        "target",
        "vendor",
    }
)

_DOCUMENTATION_BASENAMES = frozenset(
    {
        "authors",
        "changelog",
        "code_of_conduct",
        "contributing",
        "contributors",
        "copying",
        "history",
        "license",
        "notice",
        "readme",
    }
)

_DEPENDENCY_BASENAMES = frozenset(
    {
        ".terraform.lock.hcl",
        "build.gradle",
        "build.gradle.kts",
        "cargo.lock",
        "cargo.toml",
        "composer.json",
        "composer.lock",
        "deno.json",
        "deno.lock",
        "directory.packages.props",
        "gemfile",
        "gemfile.lock",
        "go.mod",
        "go.sum",
        "gradle.properties",
        "mix.exs",
        "mix.lock",
        "package-lock.json",
        "package.json",
        "packages.lock.json",
        "pipfile",
        "pipfile.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "pom.xml",
        "pyproject.toml",
        "uv.lock",
        "yarn.lock",
    }
)

_DEPLOYMENT_CONFIG_BASENAMES = frozenset(
    {
        "app.yaml",
        "app.yml",
        "azure.yaml",
        "cloudbuild.yaml",
        "cloudbuild.yml",
        "fly.toml",
        "netlify.toml",
        "nginx.conf",
        "procfile",
        "render.yaml",
        "render.yml",
        "runtime.txt",
        "vercel.json",
    }
)

_ARCHITECTURE_BASENAMES = frozenset(
    {
        "azure.yaml",
        "docker-compose.yaml",
        "docker-compose.yml",
        "lerna.json",
        "nx.json",
        "pnpm-workspace.yaml",
        "serverless.yaml",
        "serverless.yml",
        "turbo.json",
        "workspace.json",
    }
)

_KUBERNETES_BASENAMES = frozenset(
    {
        "chart.yaml",
        "helmfile.yaml",
        "helmfile.yml",
        "kustomization.yaml",
        "kustomization.yml",
    }
)

_SECURITY_CONFIG_BASENAMES = frozenset(
    {
        ".bandit",
        ".snyk",
        "bandit.yaml",
        "bandit.yml",
        "codeowners",
        "dependabot.yaml",
        "dependabot.yml",
        "gitleaks.toml",
        "renovate.json",
        "semgrep.yaml",
        "semgrep.yml",
        "trivy.yaml",
        "trivy.yml",
    }
)

_APPLICATION_EXTENSIONS = frozenset(
    {
        ".c",
        ".cc",
        ".clj",
        ".cpp",
        ".cs",
        ".css",
        ".dart",
        ".ex",
        ".exs",
        ".go",
        ".graphql",
        ".h",
        ".hpp",
        ".html",
        ".java",
        ".js",
        ".jsx",
        ".kt",
        ".kts",
        ".less",
        ".lua",
        ".mjs",
        ".php",
        ".proto",
        ".py",
        ".rb",
        ".rs",
        ".scala",
        ".scss",
        ".sh",
        ".sql",
        ".svelte",
        ".swift",
        ".ts",
        ".tsx",
        ".vue",
    }
)

_IMPORTANT_CONFIG_PATTERNS = (
    re.compile(r"^(?:next|nuxt|vite|webpack|rollup|babel|eslint|prettier)\.config\.[^.]+$"),
    re.compile(r"^(?:tsconfig|jsconfig)(?:\.[^.]+)?\.json$"),
    re.compile(r"^(?:deploy|deployment|release)(?:[-_.].*)?\.(?:ps1|py|sh|yaml|yml)$"),
)

_SECURITY_SOURCE_STEMS = frozenset(
    {
        "auth",
        "authentication",
        "authorization",
        "iam",
        "permissions",
        "rbac",
        "security",
    }
)

_FINGERPRINT_FIELDS = (
    "version",
    "repository_fingerprint",
    "architecture_fingerprint",
    "dependency_files_hash",
    "dockerfile_hash",
    "infrastructure_files_hash",
    "kubernetes_manifests_hash",
    "important_configuration_files_hash",
    "application_framework",
    "detected_services",
    "environment_variable_names",
)

_FIELD_CATEGORY = {
    "version": ChangeCategory.MAJOR_ARCHITECTURE_CHANGE,
    "dependency_files_hash": ChangeCategory.DEPENDENCY_CHANGE,
    "dockerfile_hash": ChangeCategory.DEPLOYMENT_CONFIG_CHANGE,
    "infrastructure_files_hash": ChangeCategory.INFRASTRUCTURE_CHANGE,
    "kubernetes_manifests_hash": ChangeCategory.KUBERNETES_CHANGE,
    "important_configuration_files_hash": ChangeCategory.DEPLOYMENT_CONFIG_CHANGE,
    "application_framework": ChangeCategory.MAJOR_ARCHITECTURE_CHANGE,
    "detected_services": ChangeCategory.MAJOR_ARCHITECTURE_CHANGE,
    "environment_variable_names": ChangeCategory.DEPLOYMENT_CONFIG_CHANGE,
}


@dataclass(frozen=True)
class FileClassification:
    """Classification of one normalized repository-relative path."""

    path: str
    categories: tuple[ChangeCategory, ...]


@dataclass(frozen=True)
class ChangeClassification:
    """Deterministically ordered classification of a Git change set."""

    categories: tuple[ChangeCategory, ...]
    files: tuple[FileClassification, ...]

    @property
    def primary_category(self) -> ChangeCategory:
        return self.categories[0]

    def to_dict(self) -> dict[str, object]:
        return {
            "categories": [category.value for category in self.categories],
            "primary_category": self.primary_category.value,
            "files": [
                {
                    "path": item.path,
                    "categories": [category.value for category in item.categories],
                }
                for item in self.files
            ],
        }


@dataclass(frozen=True)
class RepositoryFingerprint:
    """Persistable, content-free repository analysis snapshot."""

    commit_sha: str
    repository_fingerprint: str
    architecture_fingerprint: str
    dependency_files_hash: str
    dockerfile_hash: str
    infrastructure_files_hash: str
    kubernetes_manifests_hash: str
    important_configuration_files_hash: str
    application_framework: str | None = None
    detected_services: tuple[str, ...] = ()
    environment_variable_names: tuple[str, ...] = ()
    version: str = CHANGE_DETECTION_VERSION

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class AnalysisReuseDecision:
    """Explainable decision about whether repository AI must run again."""

    requires_repository_analysis: bool
    reuse_previous_analysis: bool
    reason: AnalysisDecisionReason
    message: str
    categories: tuple[ChangeCategory, ...]
    changed_files: tuple[str, ...]
    changed_fingerprint_fields: tuple[str, ...]
    previous_commit_sha: str | None
    current_commit_sha: str
    version: str = CHANGE_DETECTION_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "requires_repository_analysis": self.requires_repository_analysis,
            "reuse_previous_analysis": self.reuse_previous_analysis,
            "reason": self.reason.value,
            "message": self.message,
            "categories": [category.value for category in self.categories],
            "changed_files": list(self.changed_files),
            "changed_fingerprint_fields": list(self.changed_fingerprint_fields),
            "previous_commit_sha": self.previous_commit_sha,
            "current_commit_sha": self.current_commit_sha,
            "version": self.version,
        }


@dataclass(frozen=True)
class ChangeAnalysisPersistence:
    """Bounded, content-free fields suitable for a ``ChangeAnalysis`` row.

    ``sampled_paths`` contains at most :data:`MAX_SAMPLED_PATHS` normalized
    paths.  The digest and count always cover the complete unique path set;
    file contents are never retained by this adapter.
    """

    changed_paths_digest: str
    change_fingerprint: str
    classifier_version: str
    changed_file_count: int
    application_source_changed: bool
    dependencies_changed: bool
    deployment_config_changed: bool
    infrastructure_changed: bool
    kubernetes_changed: bool
    security_policy_changed: bool
    architecture_changed: bool
    documentation_only: bool
    deployment_relevant: bool
    repository_ai_required: bool
    decision_reason: str
    category_counts: dict[str, int]
    sampled_paths: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return only fields accepted by the persistence model."""

        return {
            "changed_paths_digest": self.changed_paths_digest,
            "change_fingerprint": self.change_fingerprint,
            "classifier_version": self.classifier_version,
            "changed_file_count": self.changed_file_count,
            "application_source_changed": self.application_source_changed,
            "dependencies_changed": self.dependencies_changed,
            "deployment_config_changed": self.deployment_config_changed,
            "infrastructure_changed": self.infrastructure_changed,
            "kubernetes_changed": self.kubernetes_changed,
            "security_policy_changed": self.security_policy_changed,
            "architecture_changed": self.architecture_changed,
            "documentation_only": self.documentation_only,
            "deployment_relevant": self.deployment_relevant,
            "repository_ai_required": self.repository_ai_required,
            "decision_reason": self.decision_reason,
            "category_counts": dict(self.category_counts),
            "sampled_paths": list(self.sampled_paths),
        }


def normalize_repository_path(path: str) -> str:
    """Return a canonical Git-style relative path and reject path traversal."""

    if not isinstance(path, str) or not path.strip():
        raise ValueError("repository path must be a non-empty string")
    if "\x00" in path:
        raise ValueError("repository path must not contain NUL bytes")

    candidate = path.strip().replace("\\", "/")
    if candidate.startswith("/") or re.match(r"^[A-Za-z]:/", candidate):
        raise ValueError("repository path must be relative")

    parts = tuple(part for part in candidate.split("/") if part not in {"", "."})
    if not parts or any(part == ".." for part in parts):
        raise ValueError("repository path must not traverse outside the repository")
    return "/".join(parts)


def _sort_categories(categories: Iterable[ChangeCategory]) -> tuple[ChangeCategory, ...]:
    unique = set(categories)
    if len(unique) > 1:
        unique.discard(ChangeCategory.NO_RELEVANT_CHANGE)
    if not unique:
        unique.add(ChangeCategory.NO_RELEVANT_CHANGE)
    return tuple(sorted(unique, key=_CATEGORY_PRIORITY.__getitem__))


def _is_ignored(path: PurePosixPath) -> bool:
    return any(part.lower() in _IGNORED_DIRECTORY_NAMES for part in path.parts[:-1])


def _is_documentation(path: PurePosixPath) -> bool:
    basename = path.name.lower()
    stem = path.stem.lower()
    return (
        "docs" in {part.lower() for part in path.parts[:-1]}
        or path.suffix.lower() in {".md", ".mdx", ".rst", ".txt"}
        and stem in _DOCUMENTATION_BASENAMES
        or basename in _DOCUMENTATION_BASENAMES
    )


def _is_dependency_file(path: PurePosixPath) -> bool:
    basename = path.name.lower()
    return basename in _DEPENDENCY_BASENAMES or bool(
        re.fullmatch(r"requirements(?:[-_.][a-z0-9_-]+)?\.txt", basename)
    )


def _is_dockerfile(path: PurePosixPath) -> bool:
    basename = path.name.lower()
    return basename == "containerfile" or basename.startswith("dockerfile")


def _is_environment_file(path: PurePosixPath) -> bool:
    basename = path.name.lower()
    return basename == ".env" or basename.startswith(".env.")


def _is_infrastructure_file(path: PurePosixPath) -> bool:
    lowered_parts = {part.lower() for part in path.parts[:-1]}
    basename = path.name.lower()
    suffixes = tuple(suffix.lower() for suffix in path.suffixes)
    return (
        bool(lowered_parts & {"cloudformation", "iac", "infra", "infrastructure", "pulumi", "terraform"})
        or path.suffix.lower() in {".bicep", ".tf", ".tfvars"}
        or suffixes[-2:] in {(".tf", ".json"), (".tfvars", ".json")}
        or basename.startswith("azuredeploy.")
        or basename.startswith("template.") and "cloudformation" in lowered_parts
    )


def _looks_like_kubernetes_manifest(content: str | bytes | None) -> bool:
    if content is None:
        return False
    if isinstance(content, bytes):
        text = content[:64_000].decode("utf-8", errors="ignore")
    elif isinstance(content, str):
        text = content[:64_000]
    else:
        raise TypeError("repository file content must be str or bytes")
    return bool(
        re.search(r"(?m)^\s*apiVersion\s*:\s*\S+", text)
        and re.search(r"(?m)^\s*kind\s*:\s*\S+", text)
    )


def _is_kubernetes_file(path: PurePosixPath, content: str | bytes | None) -> bool:
    lowered_parts = {part.lower() for part in path.parts[:-1]}
    basename = path.name.lower()
    return (
        basename in _KUBERNETES_BASENAMES
        or bool(lowered_parts & {"charts", "helm", "k8s", "kube", "kubernetes"})
        or path.suffix.lower() in {".yaml", ".yml"}
        and _looks_like_kubernetes_manifest(content)
    )


def _is_deployment_config(path: PurePosixPath) -> bool:
    basename = path.name.lower()
    lowered_parts = tuple(part.lower() for part in path.parts[:-1])
    return (
        _is_dockerfile(path)
        or basename in _DEPLOYMENT_CONFIG_BASENAMES
        or basename in _ARCHITECTURE_BASENAMES
        or basename.startswith("docker-compose.")
        or basename.startswith("compose.") and path.suffix.lower() in {".yaml", ".yml"}
        or _is_environment_file(path)
        or lowered_parts[:2] == (".github", "workflows")
        or "deploy" in lowered_parts
        or "deployment" in lowered_parts
        or any(pattern.fullmatch(basename) for pattern in _IMPORTANT_CONFIG_PATTERNS)
    )


def _is_security_relevant(path: PurePosixPath) -> bool:
    basename = path.name.lower()
    lowered_parts = {part.lower() for part in path.parts[:-1]}
    return (
        basename in _SECURITY_CONFIG_BASENAMES
        or basename.startswith(".semgrep")
        or basename.startswith(".gitleaks")
        or bool(lowered_parts & {"auth", "iam", "policies", "rbac", "security"})
        or path.stem.lower() in _SECURITY_SOURCE_STEMS
        or ".github" in lowered_parts
        and ("codeql" in basename or "dependabot" in basename or "security" in basename)
    )


def _is_major_architecture_file(path: PurePosixPath) -> bool:
    basename = path.name.lower()
    return (
        basename in _ARCHITECTURE_BASENAMES
        or basename.startswith("docker-compose.")
        or basename.startswith("compose.") and path.suffix.lower() in {".yaml", ".yml"}
    )


def classify_file(path: str, content: str | bytes | None = None) -> FileClassification:
    """Classify one file without reading it from disk.

    ``content`` is optional and is inspected only to recognize Kubernetes YAML
    stored outside conventional Kubernetes directories.
    """

    normalized = normalize_repository_path(path)
    parsed = PurePosixPath(normalized)
    if _is_ignored(parsed) or _is_documentation(parsed):
        return FileClassification(normalized, (ChangeCategory.NO_RELEVANT_CHANGE,))

    categories: set[ChangeCategory] = set()
    if _is_dependency_file(parsed):
        categories.add(ChangeCategory.DEPENDENCY_CHANGE)
    if _is_infrastructure_file(parsed):
        categories.add(ChangeCategory.INFRASTRUCTURE_CHANGE)
    is_kubernetes = _is_kubernetes_file(parsed, content)
    if is_kubernetes:
        categories.add(ChangeCategory.KUBERNETES_CHANGE)
    if _is_deployment_config(parsed) and not is_kubernetes:
        categories.add(ChangeCategory.DEPLOYMENT_CONFIG_CHANGE)
    if _is_security_relevant(parsed):
        categories.add(ChangeCategory.SECURITY_RELEVANT_CHANGE)
    if _is_major_architecture_file(parsed):
        categories.add(ChangeCategory.MAJOR_ARCHITECTURE_CHANGE)

    structural_categories = {
        ChangeCategory.DEPENDENCY_CHANGE,
        ChangeCategory.DEPLOYMENT_CONFIG_CHANGE,
        ChangeCategory.INFRASTRUCTURE_CHANGE,
        ChangeCategory.KUBERNETES_CHANGE,
        ChangeCategory.MAJOR_ARCHITECTURE_CHANGE,
    }
    if (
        parsed.suffix.lower() in _APPLICATION_EXTENSIONS
        and not structural_categories.intersection(categories)
    ):
        categories.add(ChangeCategory.APPLICATION_CODE_CHANGE)
    if not categories:
        categories.add(ChangeCategory.NO_RELEVANT_CHANGE)

    return FileClassification(normalized, _sort_categories(categories))


def classify_changes(
    changed_files: Iterable[str] | Mapping[str, str | bytes],
) -> ChangeClassification:
    """Classify changed paths in a stable order.

    A mapping may be supplied when file contents are already available.  A
    plain iterable is appropriate for path-only Git/GitHub diff responses.
    Duplicate normalized paths are collapsed.
    """

    if isinstance(changed_files, Mapping):
        raw_items = changed_files.items()
    else:
        if isinstance(changed_files, (str, bytes)):
            raise TypeError("changed_files must be an iterable of paths, not a single path")
        raw_items = ((path, None) for path in changed_files)

    by_path: dict[str, FileClassification] = {}
    for path, content in raw_items:
        item = classify_file(path, content)
        existing = by_path.get(item.path)
        if existing is None:
            by_path[item.path] = item
        else:
            by_path[item.path] = FileClassification(
                path=item.path,
                categories=_sort_categories((*existing.categories, *item.categories)),
            )

    files = tuple(by_path[path] for path in sorted(by_path))
    categories = _sort_categories(
        category for item in files for category in item.categories
    )
    return ChangeClassification(categories=categories, files=files)


def _content_bytes(content: str | bytes) -> bytes:
    if isinstance(content, str):
        return content.encode("utf-8")
    if isinstance(content, bytes):
        return content
    raise TypeError("repository file content must be str or bytes")


def _hash_files(files: Iterable[tuple[str, bytes]]) -> str:
    """Hash named files with length framing to avoid concatenation ambiguity."""

    digest = hashlib.sha256()
    for path, content in sorted(files, key=lambda item: item[0]):
        encoded_path = path.encode("utf-8")
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _hash_canonical_payload(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalized_names(
    values: Iterable[str],
    *,
    label: str,
    max_count: int,
    max_length: int,
) -> tuple[str, ...]:
    """Normalize bounded name evidence, failing instead of truncating it."""

    normalized: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise TypeError(f"{label} must contain strings")
        clean = value.strip()
        if clean:
            if len(clean) > max_length:
                raise ValueError(
                    f"{label} entries must not exceed {max_length} characters"
                )
            if any(character in clean for character in ("\x00", "\r", "\n")):
                raise ValueError(f"{label} entries must not contain control characters")
            normalized.add(clean)
            if len(normalized) > max_count:
                raise ValueError(f"{label} must not contain more than {max_count} names")
    return tuple(sorted(normalized))


def fingerprint_repository(
    files: Mapping[str, str | bytes],
    *,
    commit_sha: str,
    application_framework: str | None = None,
    detected_services: Iterable[str] = (),
    environment_variable_names: Iterable[str] = (),
) -> RepositoryFingerprint:
    """Create a whole-repository hash plus deployment-specific group hashes."""

    normalized_files: dict[str, bytes] = {}
    classifications: dict[str, FileClassification] = {}
    for raw_path, raw_content in files.items():
        normalized_path = normalize_repository_path(raw_path)
        if normalized_path in normalized_files:
            raise ValueError(f"duplicate normalized repository path: {normalized_path}")
        content = _content_bytes(raw_content)
        normalized_files[normalized_path] = content
        classifications[normalized_path] = classify_file(normalized_path, raw_content)

    repository_files: list[tuple[str, bytes]] = []
    dependencies: list[tuple[str, bytes]] = []
    dockerfiles: list[tuple[str, bytes]] = []
    infrastructure: list[tuple[str, bytes]] = []
    kubernetes: list[tuple[str, bytes]] = []
    important_configuration: list[tuple[str, bytes]] = []

    for path, content in normalized_files.items():
        item = classifications[path]
        categories = set(item.categories)
        parsed = PurePosixPath(path)
        # Environment files may contain low-entropy secrets. Even a raw
        # SHA-256 of their content can become an offline guessing oracle, so
        # only separately supplied, normalized variable names may influence
        # a persistable fingerprint.
        is_environment_file = _is_environment_file(parsed)
        if not _is_ignored(parsed) and not is_environment_file:
            repository_files.append((path, content))
        if ChangeCategory.DEPENDENCY_CHANGE in categories:
            dependencies.append((path, content))
        if _is_dockerfile(parsed):
            dockerfiles.append((path, content))
        if ChangeCategory.INFRASTRUCTURE_CHANGE in categories:
            infrastructure.append((path, content))
        if ChangeCategory.KUBERNETES_CHANGE in categories:
            kubernetes.append((path, content))
        if (
            ChangeCategory.DEPLOYMENT_CONFIG_CHANGE in categories
            or ChangeCategory.SECURITY_RELEVANT_CHANGE in categories
            or ChangeCategory.MAJOR_ARCHITECTURE_CHANGE in categories
        ) and not _is_dockerfile(parsed) and not is_environment_file:
            important_configuration.append((path, content))

    framework = application_framework.strip() if isinstance(application_framework, str) else None
    framework = framework or None
    dependency_files_hash = _hash_files(dependencies)
    dockerfile_hash = _hash_files(dockerfiles)
    infrastructure_files_hash = _hash_files(infrastructure)
    kubernetes_manifests_hash = _hash_files(kubernetes)
    important_configuration_files_hash = _hash_files(important_configuration)
    normalized_services = _normalized_names(
        detected_services,
        label="detected_services",
        max_count=MAX_DETECTED_SERVICES,
        max_length=MAX_DETECTED_SERVICE_LENGTH,
    )
    normalized_environment_names = _normalized_names(
        environment_variable_names,
        label="environment_variable_names",
        max_count=MAX_ENVIRONMENT_VARIABLE_NAMES,
        max_length=MAX_ENVIRONMENT_VARIABLE_NAME_LENGTH,
    )
    architecture_fingerprint = _hash_canonical_payload(
        {
            "version": CHANGE_DETECTION_VERSION,
            "dependency_files_hash": dependency_files_hash,
            "dockerfile_hash": dockerfile_hash,
            "infrastructure_files_hash": infrastructure_files_hash,
            "kubernetes_manifests_hash": kubernetes_manifests_hash,
            "important_configuration_files_hash": important_configuration_files_hash,
            "application_framework": framework,
            "detected_services": normalized_services,
            "environment_variable_names": normalized_environment_names,
        }
    )
    return RepositoryFingerprint(
        commit_sha=str(commit_sha or "").strip().lower(),
        repository_fingerprint=_hash_files(repository_files),
        architecture_fingerprint=architecture_fingerprint,
        dependency_files_hash=dependency_files_hash,
        dockerfile_hash=dockerfile_hash,
        infrastructure_files_hash=infrastructure_files_hash,
        kubernetes_manifests_hash=kubernetes_manifests_hash,
        important_configuration_files_hash=important_configuration_files_hash,
        application_framework=framework,
        detected_services=normalized_services,
        environment_variable_names=normalized_environment_names,
    )


def decide_analysis_reuse(
    *,
    previous: RepositoryFingerprint | None,
    current: RepositoryFingerprint,
    changed_files: Iterable[str] | Mapping[str, str | bytes] = (),
) -> AnalysisReuseDecision:
    """Decide whether a previous repository AI analysis remains reusable."""

    path_classification = classify_changes(changed_files)
    if previous is None:
        return AnalysisReuseDecision(
            requires_repository_analysis=True,
            reuse_previous_analysis=False,
            reason=AnalysisDecisionReason.NO_PREVIOUS_ANALYSIS,
            message="Repository AI analysis required because no previous analysis snapshot is available.",
            categories=path_classification.categories,
            changed_files=tuple(item.path for item in path_classification.files),
            changed_fingerprint_fields=(),
            previous_commit_sha=None,
            current_commit_sha=current.commit_sha,
        )

    changed_fields = tuple(
        field for field in _FINGERPRINT_FIELDS if getattr(previous, field) != getattr(current, field)
    )
    inferred_categories = {
        _FIELD_CATEGORY[field] for field in changed_fields if field in _FIELD_CATEGORY
    }
    if (
        "architecture_fingerprint" in changed_fields
        and not any(field in _FIELD_CATEGORY for field in changed_fields)
    ):
        inferred_categories.add(ChangeCategory.MAJOR_ARCHITECTURE_CHANGE)
    if changed_fields == ("repository_fingerprint",) and not path_classification.files:
        inferred_categories.add(ChangeCategory.APPLICATION_CODE_CHANGE)

    categories = _sort_categories((*path_classification.categories, *inferred_categories))
    requires_analysis = bool(_ANALYSIS_TRIGGER_CATEGORIES.intersection(categories))

    if requires_analysis:
        triggering = [
            category.value
            for category in categories
            if category in _ANALYSIS_TRIGGER_CATEGORIES
        ]
        message = (
            "Repository AI analysis required because deployment-relevant changes were detected: "
            + ", ".join(triggering)
            + "."
        )
        reason = AnalysisDecisionReason.DEPLOYMENT_RELEVANT_CHANGE
    else:
        message = (
            "Repository AI analysis skipped because no deployment-relevant architecture "
            "changes were detected."
        )
        reason = AnalysisDecisionReason.NO_DEPLOYMENT_RELEVANT_CHANGE

    return AnalysisReuseDecision(
        requires_repository_analysis=requires_analysis,
        reuse_previous_analysis=not requires_analysis,
        reason=reason,
        message=message,
        categories=categories,
        changed_files=tuple(item.path for item in path_classification.files),
        changed_fingerprint_fields=changed_fields,
        previous_commit_sha=previous.commit_sha,
        current_commit_sha=current.commit_sha,
    )


def build_change_analysis_persistence(
    *,
    previous: RepositoryFingerprint | None,
    current: RepositoryFingerprint,
    changed_files: Iterable[str] | Mapping[str, str | bytes] = (),
) -> ChangeAnalysisPersistence:
    """Build bounded fields for a durable ``ChangeAnalysis`` record.

    The complete normalized path set contributes to both digests, while only
    the first :data:`MAX_SAMPLED_PATHS` lexicographically sorted paths are
    exposed.  Mapping values may contain file contents for classification, but
    values are neither copied into the result nor included directly in either
    digest; only repository snapshot hashes bind content to the decision.
    """

    if isinstance(changed_files, Mapping):
        stable_changed_files: Iterable[str] | Mapping[str, str | bytes] = changed_files
    else:
        if isinstance(changed_files, (str, bytes)):
            raise TypeError("changed_files must be an iterable of paths, not a single path")
        stable_changed_files = tuple(changed_files)

    classification = classify_changes(stable_changed_files)
    decision = decide_analysis_reuse(
        previous=previous,
        current=current,
        changed_files=stable_changed_files,
    )
    normalized_paths = tuple(item.path for item in classification.files)
    changed_paths_digest = _hash_files((path, b"") for path in normalized_paths)

    category_counts = {category.value: 0 for category in ChangeCategory}
    for item in classification.files:
        for category in item.categories:
            category_counts[category.value] += 1

    decision_categories = set(decision.categories)
    deployment_relevant = bool(
        _ANALYSIS_TRIGGER_CATEGORIES.intersection(decision_categories)
    )
    documentation_only = bool(classification.files) and all(
        _is_documentation(PurePosixPath(item.path)) for item in classification.files
    )

    change_fingerprint = _hash_canonical_payload(
        {
            "classifier_version": CHANGE_DETECTION_VERSION,
            "previous_commit_sha": previous.commit_sha if previous else None,
            "current_commit_sha": current.commit_sha,
            "previous_repository_fingerprint": (
                previous.repository_fingerprint if previous else None
            ),
            "current_repository_fingerprint": current.repository_fingerprint,
            "previous_architecture_fingerprint": (
                previous.architecture_fingerprint if previous else None
            ),
            "current_architecture_fingerprint": current.architecture_fingerprint,
            "changed_paths_digest": changed_paths_digest,
            "category_counts": category_counts,
            "categories": [category.value for category in decision.categories],
            "repository_ai_required": decision.requires_repository_analysis,
            "decision_reason": decision.reason.value,
        }
    )

    return ChangeAnalysisPersistence(
        changed_paths_digest=changed_paths_digest,
        change_fingerprint=change_fingerprint,
        classifier_version=CHANGE_DETECTION_VERSION,
        changed_file_count=len(normalized_paths),
        application_source_changed=(
            ChangeCategory.APPLICATION_CODE_CHANGE in decision_categories
        ),
        dependencies_changed=ChangeCategory.DEPENDENCY_CHANGE in decision_categories,
        deployment_config_changed=(
            ChangeCategory.DEPLOYMENT_CONFIG_CHANGE in decision_categories
        ),
        infrastructure_changed=(
            ChangeCategory.INFRASTRUCTURE_CHANGE in decision_categories
        ),
        kubernetes_changed=ChangeCategory.KUBERNETES_CHANGE in decision_categories,
        security_policy_changed=(
            ChangeCategory.SECURITY_RELEVANT_CHANGE in decision_categories
        ),
        architecture_changed=(
            ChangeCategory.MAJOR_ARCHITECTURE_CHANGE in decision_categories
        ),
        documentation_only=documentation_only,
        deployment_relevant=deployment_relevant,
        repository_ai_required=decision.requires_repository_analysis,
        decision_reason=decision.message,
        category_counts=category_counts,
        sampled_paths=normalized_paths[:MAX_SAMPLED_PATHS],
    )


class ChangeDetectionService:
    """Stateless facade suitable for dependency injection into a pipeline."""

    classify_file = staticmethod(classify_file)
    classify_changes = staticmethod(classify_changes)
    fingerprint_repository = staticmethod(fingerprint_repository)
    decide_analysis_reuse = staticmethod(decide_analysis_reuse)
    build_change_analysis_persistence = staticmethod(build_change_analysis_persistence)

    @staticmethod
    def compare(
        *,
        previous: RepositoryFingerprint | None,
        current: RepositoryFingerprint,
        changed_files: Iterable[str] | Mapping[str, str | bytes] = (),
    ) -> AnalysisReuseDecision:
        return decide_analysis_reuse(
            previous=previous,
            current=current,
            changed_files=changed_files,
        )
