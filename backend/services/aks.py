"""Deployment adapter for an existing Azure Kubernetes Service cluster.

The adapter intentionally does not provision clusters.  It obtains a
non-admin cluster-user kubeconfig with Microsoft Entra credentials, isolates
that kubeconfig per deployment, validates a narrow namespace-scoped workload
allowlist, applies the rendered manifests, and verifies rollout/endpoints.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import urlsplit

import yaml
from yaml.tokens import AliasToken, AnchorToken

try:
    from azure.identity import ClientSecretCredential
    from azure.mgmt.containerservice import ContainerServiceClient
    from backend.services import security_scanner
    from backend.services.redaction import is_sensitive_key, redact_sensitive_text
except ImportError:  # pragma: no cover - worker-style imports
    from azure.identity import ClientSecretCredential
    from azure.mgmt.containerservice import ContainerServiceClient
    from services import security_scanner
    from services.redaction import is_sensitive_key, redact_sensitive_text


_NAMESPACE_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_RESOURCE_NAME_PATTERN = re.compile(r"^[a-z0-9](?:[-a-z0-9.]{0,251}[a-z0-9])?$")
_IMAGE_DIGEST_PATTERN = re.compile(
    r"^(?=.{1,1024}$)[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[0-9]+)?"
    r"(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+@sha256:[0-9a-f]{64}$"
)
_LABEL_KEY = "zeroops.ai/release"
_MANAGED_BY_KEY = "app.kubernetes.io/managed-by"
_MANAGED_BY_VALUE = "zeroops"
_AKS_AAD_SCOPE = "6dae42f8-4368-4678-94ff-3960e28e3630/.default"
_MAX_KUBECONFIG_BYTES = 1_000_000
_MAX_MANIFEST_BYTES = 2_000_000
_MAX_MANIFEST_FILES = 200
_MAX_MANIFEST_DOCUMENTS = 500
_ALLOWED_KINDS = {
    "ConfigMap",
    "DaemonSet",
    "Deployment",
    "HorizontalPodAutoscaler",
    "Ingress",
    "NetworkPolicy",
    "PodDisruptionBudget",
    "Service",
    "StatefulSet",
}
_ROLLOUT_KINDS = {"DaemonSet", "Deployment", "StatefulSet"}
_BLOCKED_KINDS = {
    "ClusterRole",
    "ClusterRoleBinding",
    "CustomResourceDefinition",
    "Namespace",
    "Node",
    "PersistentVolume",
    "Role",
    "RoleBinding",
    "Secret",
    "ServiceAccount",
}
_DISCOVERY_DIRS = {"k8s", "kubernetes", "manifests"}
_DISCOVERY_FILES = {
    "deployment.yaml",
    "deployment.yml",
    "service.yaml",
    "service.yml",
    "ingress.yaml",
    "ingress.yml",
    "kustomization.yaml",
    "kustomization.yml",
}


class AksDeploymentError(RuntimeError):
    """A safe failure that can be persisted and shown to the project owner."""


@dataclass(frozen=True)
class KubernetesAssets:
    manifest_files: tuple[str, ...] = ()
    chart_directories: tuple[str, ...] = ()
    kustomization_files: tuple[str, ...] = ()

    @property
    def detected(self) -> bool:
        return bool(self.manifest_files or self.chart_directories or self.kustomization_files)


@dataclass(frozen=True)
class AksRelease:
    cluster: str
    namespace: str
    workloads: tuple[str, ...]
    image_digest: str
    deployment_revision: str | None
    service_endpoint: str | None
    rollout_status: str
    pod_status: dict[str, int] = field(default_factory=dict)
    workload_status: dict[str, dict[str, int | str]] = field(default_factory=dict)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[[Sequence[str], str, dict[str, str], int], CommandResult]
ScanRunner = Callable[..., security_scanner.SecurityScanResult]


_SAFE_ENVIRONMENT_KEYS = {
    "COMSPEC",
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
    "WINDIR",
}


def _run(command: Sequence[str], cwd: str, env: dict[str, str], timeout: int) -> CommandResult:
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as error:
        raise AksDeploymentError(f"Kubernetes command exceeded its {timeout}s limit.") from error
    return CommandResult(
        completed.returncode,
        redact_sensitive_text(completed.stdout, maximum_length=100_000),
        redact_sensitive_text(completed.stderr, maximum_length=20_000),
    )


def _isolated_environment(temp: Path, kubeconfig: Path) -> dict[str, str]:
    """Build a per-deployment CLI environment without cloud credentials."""

    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in _SAFE_ENVIRONMENT_KEYS
    }
    locations = {
        "HOME": temp / "home",
        "USERPROFILE": temp / "home",
        "XDG_CONFIG_HOME": temp / "xdg-config",
        "XDG_CACHE_HOME": temp / "xdg-cache",
        "AZURE_CONFIG_DIR": temp / "azure-cli",
        "HELM_CACHE_HOME": temp / "helm-cache",
        "HELM_CONFIG_HOME": temp / "helm-config",
        "HELM_DATA_HOME": temp / "helm-data",
    }
    for location in set(locations.values()):
        location.mkdir(mode=0o700, parents=True, exist_ok=True)
    environment.update({key: str(value) for key, value in locations.items()})
    environment.update({
        "CI": "true",
        "KUBECONFIG": str(kubeconfig),
        "NO_COLOR": "1",
    })
    return environment


def _required(
    runner: CommandRunner,
    command: Sequence[str],
    cwd: str,
    env: dict[str, str],
    *,
    timeout: int = 300,
    action: str,
) -> CommandResult:
    result = runner(command, cwd, env, timeout)
    if result.returncode != 0:
        raise AksDeploymentError(f"{action} failed. Review the sanitized deployment evidence.")
    return result


def normalize_namespace(value: str) -> str:
    namespace = re.sub(r"[^a-z0-9-]+", "-", str(value or "").lower())
    namespace = re.sub(r"-+", "-", namespace).strip("-")[:63].rstrip("-")
    if not namespace or not _NAMESPACE_PATTERN.fullmatch(namespace):
        raise AksDeploymentError("The generated Kubernetes namespace is invalid.")
    return namespace


def normalize_release_name(value: str) -> str:
    return normalize_namespace(value)


def detect_kubernetes_assets(repo_path: str | os.PathLike[str]) -> KubernetesAssets:
    root = Path(repo_path).resolve(strict=True)
    if not root.is_dir():
        raise AksDeploymentError("The Kubernetes source must be a repository directory.")
    manifests: set[str] = set()
    charts: set[str] = set()
    kustomizations: set[str] = set()
    ignored = {".git", ".next", "dist", "build", "node_modules", ".venv", "venv"}

    for current, directories, files in os.walk(root):
        directories[:] = [name for name in directories if name not in ignored]
        current_path = Path(current)
        relative_dir = current_path.relative_to(root)
        parts = {part.lower() for part in relative_dir.parts}
        if "chart.yaml" in {name.lower() for name in files}:
            charts.add(str(relative_dir).replace("\\", "/") or ".")
        for filename in files:
            lower = filename.lower()
            relative = (relative_dir / filename).as_posix()
            if lower in {"kustomization.yaml", "kustomization.yml"}:
                kustomizations.add(relative)
            if lower not in _DISCOVERY_FILES and not parts.intersection(_DISCOVERY_DIRS):
                continue
            if lower.endswith((".yaml", ".yml")) and lower not in {"chart.yaml", "values.yaml", "values.yml"}:
                manifests.add(relative)
    chart_paths = tuple(Path(path) for path in charts)
    kustomize_paths = tuple(Path(path).parent for path in kustomizations)
    manifests = {
        path
        for path in manifests
        if Path(path).name.lower() not in {"kustomization.yaml", "kustomization.yml"}
        and not any(Path(path).is_relative_to(chart_path) for chart_path in chart_paths)
        and not any(Path(path).is_relative_to(kustomize_path) for kustomize_path in kustomize_paths)
    }
    return KubernetesAssets(
        manifest_files=tuple(sorted(manifests)),
        chart_directories=tuple(sorted(charts)),
        kustomization_files=tuple(sorted(kustomizations)),
    )


def _workload_pod_spec(document: dict[str, Any]) -> dict[str, Any] | None:
    kind = document.get("kind")
    spec = document.get("spec") if isinstance(document.get("spec"), dict) else {}
    if kind in _ROLLOUT_KINDS:
        template = spec.get("template") if isinstance(spec.get("template"), dict) else {}
        return template.get("spec") if isinstance(template.get("spec"), dict) else None
    return None


def _reject_secret_references(container: dict[str, Any], workload: str) -> None:
    env_from = container.get("envFrom") or []
    if not isinstance(env_from, list):
        raise AksDeploymentError(f"Kubernetes workload {workload} has invalid envFrom configuration.")
    if any(isinstance(item, dict) and item.get("secretRef") for item in env_from):
        raise AksDeploymentError(
            f"Kubernetes workload {workload} references a Kubernetes Secret. Use Key Vault CSI instead."
        )
    environment = container.get("env") or []
    if not isinstance(environment, list):
        raise AksDeploymentError(f"Kubernetes workload {workload} has invalid environment configuration.")
    for item in environment:
        if not isinstance(item, dict):
            raise AksDeploymentError(f"Kubernetes workload {workload} has an invalid environment entry.")
        value_from = item.get("valueFrom") if isinstance(item.get("valueFrom"), dict) else {}
        if value_from.get("secretKeyRef"):
            raise AksDeploymentError(
                f"Kubernetes workload {workload} references a Kubernetes Secret. Use Key Vault CSI instead."
            )
        if is_sensitive_key(item.get("name")) and "value" in item:
            raise AksDeploymentError(
                f"Kubernetes workload {workload} embeds a secret-looking environment value. Use Key Vault CSI instead."
            )


def _validate_container_security(container: dict[str, Any], workload: str) -> None:
    security_context = container.get("securityContext")
    if security_context is None:
        security_context = {}
    if not isinstance(security_context, dict):
        raise AksDeploymentError(f"Kubernetes workload {workload} has an invalid container security context.")
    if security_context.get("privileged") is True:
        raise AksDeploymentError(f"Kubernetes workload {workload} requests a privileged container.")
    if security_context.get("allowPrivilegeEscalation") is True:
        raise AksDeploymentError(f"Kubernetes workload {workload} allows privilege escalation.")
    if security_context.get("runAsNonRoot") is False or security_context.get("runAsUser") == 0:
        raise AksDeploymentError(f"Kubernetes workload {workload} explicitly requests a root container.")
    if security_context.get("procMount") == "Unmasked":
        raise AksDeploymentError(f"Kubernetes workload {workload} requests an unmasked host proc filesystem.")
    capabilities = security_context.get("capabilities")
    if isinstance(capabilities, dict) and capabilities.get("add"):
        raise AksDeploymentError(f"Kubernetes workload {workload} adds Linux capabilities.")
    seccomp = security_context.get("seccompProfile")
    if isinstance(seccomp, dict) and seccomp.get("type") == "Unconfined":
        raise AksDeploymentError(f"Kubernetes workload {workload} disables seccomp confinement.")
    windows = security_context.get("windowsOptions")
    if isinstance(windows, dict) and windows.get("hostProcess") is True:
        raise AksDeploymentError(f"Kubernetes workload {workload} requests a Windows host process.")
    ports = container.get("ports") or []
    if not isinstance(ports, list):
        raise AksDeploymentError(f"Kubernetes workload {workload} has invalid container ports.")
    for item in ports:
        if not isinstance(item, dict):
            raise AksDeploymentError(f"Kubernetes workload {workload} has an invalid container port.")
        if item.get("hostPort") not in {None, 0, "0"}:
            raise AksDeploymentError(f"Kubernetes workload {workload} requests a host port.")
    _reject_secret_references(container, workload)


def _validate_pod_spec(pod_spec: dict[str, Any], workload: str) -> list[dict[str, Any]]:
    if pod_spec.get("hostNetwork") or pod_spec.get("hostPID") or pod_spec.get("hostIPC"):
        raise AksDeploymentError(f"Kubernetes workload {workload} requests blocked host access.")
    if pod_spec.get("serviceAccountName") not in {None, "", "default"}:
        raise AksDeploymentError(f"Kubernetes workload {workload} selects a non-default service account.")
    if pod_spec.get("automountServiceAccountToken") is True:
        raise AksDeploymentError(f"Kubernetes workload {workload} requests a Kubernetes API token.")
    if pod_spec.get("imagePullSecrets"):
        raise AksDeploymentError(f"Kubernetes workload {workload} references a Kubernetes image-pull Secret.")
    if pod_spec.get("initContainers") or pod_spec.get("ephemeralContainers"):
        raise AksDeploymentError(
            f"Kubernetes workload {workload} cannot include init or ephemeral containers in automatic mode."
        )
    pod_security = pod_spec.get("securityContext")
    if pod_security is not None and not isinstance(pod_security, dict):
        raise AksDeploymentError(f"Kubernetes workload {workload} has an invalid pod security context.")
    if isinstance(pod_security, dict):
        if pod_security.get("runAsNonRoot") is False or pod_security.get("runAsUser") == 0:
            raise AksDeploymentError(f"Kubernetes workload {workload} explicitly requests a root pod.")
        seccomp = pod_security.get("seccompProfile")
        if isinstance(seccomp, dict) and seccomp.get("type") == "Unconfined":
            raise AksDeploymentError(f"Kubernetes workload {workload} disables seccomp confinement.")
    volumes = pod_spec.get("volumes") or []
    if not isinstance(volumes, list):
        raise AksDeploymentError(f"Kubernetes workload {workload} has invalid volumes.")
    for volume in volumes:
        if not isinstance(volume, dict):
            raise AksDeploymentError(f"Kubernetes workload {workload} has an invalid volume.")
        if volume.get("hostPath"):
            raise AksDeploymentError(f"Kubernetes workload {workload} mounts a host path.")
        if volume.get("secret"):
            raise AksDeploymentError(
                f"Kubernetes workload {workload} references a Kubernetes Secret. Use Key Vault CSI instead."
            )
        projected = volume.get("projected") if isinstance(volume.get("projected"), dict) else {}
        sources = projected.get("sources") or []
        if not isinstance(sources, list):
            raise AksDeploymentError(f"Kubernetes workload {workload} has an invalid projected volume.")
        for source in sources:
            if not isinstance(source, dict):
                raise AksDeploymentError(f"Kubernetes workload {workload} has an invalid projected volume source.")
            if source.get("serviceAccountToken"):
                raise AksDeploymentError(f"Kubernetes workload {workload} projects a Kubernetes API token.")
            if source.get("secret"):
                raise AksDeploymentError(
                    f"Kubernetes workload {workload} projects a Kubernetes Secret. Use Key Vault CSI instead."
                )
        csi = volume.get("csi") if isinstance(volume.get("csi"), dict) else {}
        if csi.get("nodePublishSecretRef"):
            raise AksDeploymentError(f"Kubernetes workload {workload} references a Kubernetes CSI Secret.")
    containers = pod_spec.get("containers") if isinstance(pod_spec.get("containers"), list) else []
    if len(containers) != 1 or not isinstance(containers[0], dict):
        raise AksDeploymentError(
            f"Kubernetes workload {workload} must define exactly one application container for automatic image binding."
        )
    _validate_container_security(containers[0], workload)
    pod_spec["automountServiceAccountToken"] = False
    return containers


def validate_and_render_manifests(
    manifest_files: Sequence[str | os.PathLike[str]],
    *,
    repo_path: str | os.PathLike[str],
    namespace: str,
    image_ref: str,
    release_name: str | None = None,
) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
    """Validate scope and render the verified image into workload documents."""
    root = Path(repo_path).resolve(strict=True)
    namespace = normalize_namespace(namespace)
    release = normalize_release_name(release_name or namespace)
    if len(manifest_files) > _MAX_MANIFEST_FILES:
        raise AksDeploymentError("The Kubernetes release contains too many manifest files.")
    documents: list[dict[str, Any]] = []
    workloads: list[str] = []
    total_bytes = 0
    for raw_path in manifest_files:
        unresolved = (root / raw_path) if not Path(raw_path).is_absolute() else Path(raw_path)
        if unresolved.is_symlink():
            raise AksDeploymentError("Kubernetes manifest symlinks are blocked.")
        path = unresolved.resolve(strict=True)
        try:
            path.relative_to(root)
        except ValueError as error:
            raise AksDeploymentError("Kubernetes manifest escaped the repository workspace.") from error
        if not path.is_file():
            raise AksDeploymentError("Kubernetes manifest paths must reference regular files.")
        total_bytes += path.stat().st_size
        if total_bytes > _MAX_MANIFEST_BYTES:
            raise AksDeploymentError("The Kubernetes release exceeds the manifest size limit.")
        try:
            content = path.read_text(encoding="utf-8")
            if any(isinstance(token, (AliasToken, AnchorToken)) for token in yaml.scan(content)):
                raise AksDeploymentError("Kubernetes YAML anchors and aliases are blocked.")
            loaded = list(yaml.safe_load_all(content))
        except (OSError, yaml.YAMLError) as error:
            raise AksDeploymentError(f"Kubernetes YAML validation failed for {path.name}.") from error
        for document in loaded:
            if document is None:
                continue
            if not isinstance(document, dict):
                raise AksDeploymentError(f"Kubernetes document in {path.name} must be an object.")
            if len(documents) >= _MAX_MANIFEST_DOCUMENTS:
                raise AksDeploymentError("The Kubernetes release contains too many manifest documents.")
            kind = str(document.get("kind") or "")
            if kind in _BLOCKED_KINDS:
                if kind == "Secret":
                    raise AksDeploymentError(
                        "Raw Kubernetes Secret manifests are blocked. Use Azure Key Vault with the CSI driver."
                    )
                raise AksDeploymentError(f"Cluster-scoped or privilege-bearing Kubernetes kind {kind} is blocked.")
            if kind not in _ALLOWED_KINDS:
                raise AksDeploymentError(f"Kubernetes kind {kind or 'unknown'} is not in the deployment allowlist.")
            metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
            name = str(metadata.get("name") or "")
            if not _RESOURCE_NAME_PATTERN.fullmatch(name):
                raise AksDeploymentError(f"Kubernetes {kind} has an invalid or missing metadata.name.")
            configured_namespace = str(metadata.get("namespace") or namespace)
            if configured_namespace != namespace:
                raise AksDeploymentError(
                    f"Kubernetes resource {kind}/{name} targets namespace {configured_namespace}, not {namespace}."
                )
            metadata["namespace"] = namespace
            labels = metadata.get("labels") if metadata.get("labels") is not None else {}
            if not isinstance(labels, dict):
                raise AksDeploymentError(f"Kubernetes {kind}/{name} has invalid metadata.labels.")
            labels[_MANAGED_BY_KEY] = _MANAGED_BY_VALUE
            labels[_LABEL_KEY] = release
            metadata["labels"] = labels
            document["metadata"] = metadata

            if kind == "ConfigMap":
                data = document.get("data") or {}
                if not isinstance(data, dict):
                    raise AksDeploymentError(f"Kubernetes ConfigMap/{name} has invalid data.")
                if document.get("binaryData"):
                    raise AksDeploymentError(
                        f"Kubernetes ConfigMap/{name} binaryData is blocked because it cannot be inspected safely."
                    )
                if any(is_sensitive_key(key) for key in data):
                    raise AksDeploymentError(
                        f"Kubernetes ConfigMap/{name} contains a secret-looking key. Use Key Vault CSI instead."
                    )

            pod_spec = _workload_pod_spec(document)
            if pod_spec is not None:
                workload = f"{kind}/{name}"
                containers = _validate_pod_spec(pod_spec, workload)
                containers[0]["image"] = image_ref
                pod_spec["containers"] = containers
                spec = document.get("spec") if isinstance(document.get("spec"), dict) else {}
                template = spec.get("template") if isinstance(spec.get("template"), dict) else {}
                template_metadata = template.get("metadata") if isinstance(template.get("metadata"), dict) else {}
                template_labels = (
                    template_metadata.get("labels")
                    if isinstance(template_metadata.get("labels"), dict)
                    else {}
                )
                template_labels[_MANAGED_BY_KEY] = _MANAGED_BY_VALUE
                template_labels[_LABEL_KEY] = release
                template_metadata["labels"] = template_labels
                template["metadata"] = template_metadata
                spec["template"] = template
                document["spec"] = spec
                workloads.append(f"{kind.lower()}/{name}")
            documents.append(document)

    if not documents:
        raise AksDeploymentError("No deployable Kubernetes manifests were detected.")
    if not workloads:
        raise AksDeploymentError("No Kubernetes workload was found in the validated manifests.")
    return documents, tuple(workloads)


def _decode_kubeconfig(value: Any) -> bytes:
    raw = bytes(value) if isinstance(value, (bytes, bytearray)) else str(value or "").encode("utf-8")
    if not raw or len(raw) > _MAX_KUBECONFIG_BYTES * 2:
        raise AksDeploymentError("Azure returned an invalid cluster-user kubeconfig.")
    if raw.lstrip().startswith((b"apiVersion:", b"---")):
        decoded = raw
    else:
        try:
            decoded = base64.b64decode(raw, validate=True)
        except (ValueError, TypeError) as error:
            raise AksDeploymentError("Azure returned an invalid cluster-user kubeconfig.") from error
    if len(decoded) > _MAX_KUBECONFIG_BYTES:
        raise AksDeploymentError("Azure returned an oversized cluster-user kubeconfig.")
    _load_kubeconfig(decoded)
    return decoded


def _load_kubeconfig(content: bytes) -> dict[str, Any]:
    try:
        decoded = content.decode("utf-8")
        if any(isinstance(token, (AliasToken, AnchorToken)) for token in yaml.scan(decoded)):
            raise AksDeploymentError("Azure returned an invalid cluster-user kubeconfig.")
        configuration = yaml.safe_load(decoded)
    except (UnicodeDecodeError, yaml.YAMLError) as error:
        raise AksDeploymentError("Azure returned an invalid cluster-user kubeconfig.") from error
    if not isinstance(configuration, dict):
        raise AksDeploymentError("Azure returned an invalid cluster-user kubeconfig.")
    if configuration.get("apiVersion") != "v1" or configuration.get("kind") != "Config":
        raise AksDeploymentError("Azure returned an invalid cluster-user kubeconfig.")
    if not isinstance(configuration.get("clusters"), list):
        raise AksDeploymentError("Azure returned an invalid cluster-user kubeconfig.")
    return configuration


def _selected_cluster(configuration: dict[str, Any]) -> dict[str, Any]:
    clusters = configuration.get("clusters") or []
    contexts = configuration.get("contexts") or []
    cluster_name: str | None = None
    current_context = configuration.get("current-context")
    if isinstance(current_context, str) and isinstance(contexts, list):
        for context in contexts:
            if not isinstance(context, dict) or context.get("name") != current_context:
                continue
            details = context.get("context") if isinstance(context.get("context"), dict) else {}
            configured_cluster = details.get("cluster")
            if isinstance(configured_cluster, str):
                cluster_name = configured_cluster
            break
    candidates = [
        item
        for item in clusters
        if isinstance(item, dict) and (cluster_name is None or item.get("name") == cluster_name)
    ]
    if len(candidates) != 1 or not isinstance(candidates[0].get("cluster"), dict):
        raise AksDeploymentError("Azure returned an ambiguous cluster-user kubeconfig.")
    cluster = candidates[0]["cluster"]
    server = cluster.get("server")
    if not isinstance(server, str):
        raise AksDeploymentError("Azure returned a cluster-user kubeconfig without a server.")
    parsed_server = urlsplit(server)
    if (
        parsed_server.scheme != "https"
        or not parsed_server.hostname
        or parsed_server.username
        or parsed_server.password
        or parsed_server.query
        or parsed_server.fragment
    ):
        raise AksDeploymentError("Azure returned an unsafe AKS API server address.")
    if cluster.get("insecure-skip-tls-verify") is True or cluster.get("proxy-url"):
        raise AksDeploymentError("AKS kubeconfig cannot disable or proxy TLS verification.")
    certificate = cluster.get("certificate-authority-data")
    if not isinstance(certificate, str) or not certificate:
        raise AksDeploymentError("Azure returned a cluster-user kubeconfig without certificate authority data.")
    try:
        decoded_certificate = base64.b64decode(certificate, validate=True)
    except (ValueError, TypeError) as error:
        raise AksDeploymentError("Azure returned invalid AKS certificate authority data.") from error
    if not decoded_certificate or len(decoded_certificate) > _MAX_KUBECONFIG_BYTES:
        raise AksDeploymentError("Azure returned invalid AKS certificate authority data.")
    sanitized = {
        "server": server,
        "certificate-authority-data": certificate,
    }
    tls_server_name = cluster.get("tls-server-name")
    if tls_server_name is not None:
        if not isinstance(tls_server_name, str) or not tls_server_name.strip():
            raise AksDeploymentError("Azure returned an invalid AKS TLS server name.")
        sanitized["tls-server-name"] = tls_server_name
    return sanitized


def _tokenized_kubeconfig(source: bytes, token: str) -> bytes:
    if not isinstance(token, str) or not token or len(token) > 32_000:
        raise AksDeploymentError("Azure returned an invalid AKS access token.")
    cluster = _selected_cluster(_load_kubeconfig(source))
    configuration = {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [{"name": "zeroops-aks", "cluster": cluster}],
        "contexts": [{
            "name": "zeroops-aks",
            "context": {"cluster": "zeroops-aks", "user": "zeroops-deployer"},
        }],
        "current-context": "zeroops-aks",
        "users": [{"name": "zeroops-deployer", "user": {"token": token}}],
    }
    return yaml.safe_dump(configuration, sort_keys=True).encode("utf-8")


def _secure_write(path: Path, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, stat.S_IRUSR | stat.S_IWUSR)
    try:
        with os.fdopen(descriptor, "wb") as destination:
            destination.write(content)
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _validate_isolated_kubeconfig(path: Path) -> None:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_KUBECONFIG_BYTES:
        raise AksDeploymentError("The isolated AKS kubeconfig is invalid.")
    if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) & (stat.S_IRWXG | stat.S_IRWXO):
        raise AksDeploymentError("The isolated AKS kubeconfig permissions are too broad.")
    configuration = _load_kubeconfig(path.read_bytes())
    users = configuration.get("users")
    contexts = configuration.get("contexts")
    if not isinstance(users, list) or len(users) != 1 or not isinstance(contexts, list) or len(contexts) != 1:
        raise AksDeploymentError("The isolated AKS kubeconfig is invalid.")
    user = users[0].get("user") if isinstance(users[0], dict) and isinstance(users[0].get("user"), dict) else {}
    if set(user) != {"token"} or not isinstance(user.get("token"), str) or not user["token"]:
        raise AksDeploymentError("AKS kubeconfig must use only a short-lived Entra token.")
    _selected_cluster(configuration)


def _write_cluster_user_kubeconfig(connection: Any, client_secret: str, destination: Path) -> None:
    if not client_secret:
        raise AksDeploymentError("Azure credentials are unavailable. Reconnect Azure and try again.")
    credential = ClientSecretCredential(
        tenant_id=str(connection.tenant_id),
        client_id=str(connection.client_id),
        client_secret=client_secret,
    )
    client: Any = None
    wrote_destination = False
    try:
        client = ContainerServiceClient(credential, str(connection.subscription_id))
        result = client.managed_clusters.list_cluster_user_credentials(
            str(connection.resource_group),
            str(connection.aks_cluster_name),
            format="exec",
        )
        kubeconfigs = list(result.kubeconfigs or [])
        if not kubeconfigs:
            raise AksDeploymentError("Azure returned no cluster-user kubeconfig for the configured AKS cluster.")
        source = _decode_kubeconfig(kubeconfigs[0].value)
        token = credential.get_token(_AKS_AAD_SCOPE).token
        _secure_write(destination, _tokenized_kubeconfig(source, token))
        wrote_destination = True
        _validate_isolated_kubeconfig(destination)
    except AksDeploymentError:
        if wrote_destination:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    except Exception as error:
        if wrote_destination:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                pass
        raise AksDeploymentError("Azure could not issue isolated AKS cluster-user credentials.") from error
    finally:
        close = getattr(client, "close", None) if client is not None else None
        if callable(close):
            try:
                close()
            except Exception:
                pass
        close_credential = getattr(credential, "close", None)
        if callable(close_credential):
            try:
                close_credential()
            except Exception:
                pass


def _tool(name: str, *, required: bool = True) -> str | None:
    executable = shutil.which(name)
    if required and not executable:
        raise AksDeploymentError(f"{name} is unavailable in the deployment worker; AKS deployment is blocked.")
    return executable


def _extract_endpoint(payload: dict[str, Any], *, release_name: str | None = None) -> str | None:
    items = payload.get("items")
    if not isinstance(items, list):
        raise AksDeploymentError("AKS returned invalid service endpoint metadata.")
    for item in items:
        if not isinstance(item, dict):
            raise AksDeploymentError("AKS returned invalid service endpoint metadata.")
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        labels = metadata.get("labels") if isinstance(metadata.get("labels"), dict) else {}
        if release_name and labels.get(_LABEL_KEY) != release_name:
            continue
        kind = item.get("kind")
        status = item.get("status") if isinstance(item.get("status"), dict) else {}
        if kind == "Ingress":
            spec = item.get("spec") if isinstance(item.get("spec"), dict) else {}
            scheme = "https" if spec.get("tls") else "http"
            ingress = status.get("loadBalancer", {}).get("ingress", []) if isinstance(status.get("loadBalancer"), dict) else []
            for endpoint in ingress:
                host = endpoint.get("hostname") or endpoint.get("ip") if isinstance(endpoint, dict) else None
                if isinstance(host, str) and host and not any(character.isspace() for character in host):
                    formatted = f"[{host}]" if ":" in host and not host.startswith("[") else host
                    return f"{scheme}://{formatted}"
        if kind == "Service":
            spec = item.get("spec") if isinstance(item.get("spec"), dict) else {}
            ports = spec.get("ports") if isinstance(spec.get("ports"), list) else []
            uses_tls = any(
                isinstance(port, dict)
                and (
                    port.get("port") == 443
                    or str(port.get("name") or "").lower() == "https"
                    or str(port.get("appProtocol") or "").lower() == "https"
                )
                for port in ports
            )
            ingress = status.get("loadBalancer", {}).get("ingress", []) if isinstance(status.get("loadBalancer"), dict) else []
            for endpoint in ingress:
                host = endpoint.get("hostname") or endpoint.get("ip") if isinstance(endpoint, dict) else None
                if isinstance(host, str) and host and not any(character.isspace() for character in host):
                    formatted = f"[{host}]" if ":" in host and not host.startswith("[") else host
                    return f"{'https' if uses_tls else 'http'}://{formatted}"
    return None


def _pod_counts(payload: dict[str, Any], *, release_name: str) -> dict[str, int]:
    items = payload.get("items")
    if not isinstance(items, list):
        raise AksDeploymentError("AKS returned invalid pod health metadata.")
    counts = {
        "total": 0,
        "ready": 0,
        "not_ready": 0,
        "pending": 0,
        "failed": 0,
        "succeeded": 0,
        "terminating": 0,
        "restarts": 0,
    }
    seen: set[str] = set()
    for pod in items:
        if not isinstance(pod, dict):
            raise AksDeploymentError("AKS returned invalid pod health metadata.")
        metadata = pod.get("metadata") if isinstance(pod.get("metadata"), dict) else {}
        labels = metadata.get("labels") if isinstance(metadata.get("labels"), dict) else {}
        if labels.get(_LABEL_KEY) != release_name:
            continue
        uid = str(metadata.get("uid") or metadata.get("name") or "")
        if not uid or uid in seen:
            continue
        seen.add(uid)
        if metadata.get("deletionTimestamp"):
            counts["terminating"] += 1
            continue
        status = pod.get("status") if isinstance(pod.get("status"), dict) else {}
        phase = str(status.get("phase") or "Unknown").lower()
        if phase in counts:
            counts[phase] += 1
        conditions = status.get("conditions") if isinstance(status.get("conditions"), list) else []
        container_statuses = status.get("containerStatuses")
        if not isinstance(container_statuses, list) or not container_statuses:
            raise AksDeploymentError("AKS returned incomplete container health metadata.")
        pod_ready = phase == "running" and any(
            isinstance(condition, dict)
            and condition.get("type") == "Ready"
            and condition.get("status") == "True"
            for condition in conditions
        ) and all(
            isinstance(container_status, dict) and container_status.get("ready") is True
            for container_status in container_statuses
        )
        counts["total"] += 1
        counts["ready" if pod_ready else "not_ready"] += 1
        status_groups = [
            status.get("initContainerStatuses") or [],
            container_statuses,
            status.get("ephemeralContainerStatuses") or [],
        ]
        for statuses in status_groups:
            if not isinstance(statuses, list):
                raise AksDeploymentError("AKS returned invalid container health metadata.")
            for container_status in statuses:
                if not isinstance(container_status, dict):
                    raise AksDeploymentError("AKS returned invalid container health metadata.")
                restart_count = container_status.get("restartCount") or 0
                if not isinstance(restart_count, int) or restart_count < 0:
                    raise AksDeploymentError("AKS returned invalid container restart metadata.")
                counts["restarts"] += restart_count
    return counts


def _json_object(result: CommandResult, *, action: str, allow_empty: bool = False) -> dict[str, Any] | None:
    raw = result.stdout.strip()
    if not raw and allow_empty:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise AksDeploymentError(f"AKS returned invalid {action} metadata.") from error
    if not isinstance(payload, dict):
        raise AksDeploymentError(f"AKS returned invalid {action} metadata.")
    return payload


def _workload_health(workload: str, payload: dict[str, Any]) -> tuple[dict[str, int | str], str]:
    expected_kind, expected_name = workload.split("/", 1)
    kind = str(payload.get("kind") or "").lower()
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    if kind != expected_kind or metadata.get("name") != expected_name:
        raise AksDeploymentError(f"AKS returned mismatched rollout metadata for {workload}.")
    spec = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
    status = payload.get("status") if isinstance(payload.get("status"), dict) else {}

    def count(value: Any, *, default: int = 0) -> int:
        if value is None:
            return default
        if not isinstance(value, int) or value < 0:
            raise AksDeploymentError(f"AKS returned invalid rollout counts for {workload}.")
        return value

    generation = count(metadata.get("generation"), default=0)
    observed = count(status.get("observedGeneration"), default=0)
    if expected_kind == "daemonset":
        desired = count(status.get("desiredNumberScheduled"))
        ready = count(status.get("numberReady"))
        updated = count(status.get("updatedNumberScheduled"))
        available = count(status.get("numberAvailable"), default=ready)
        unavailable = count(status.get("numberUnavailable"), default=max(desired - available, 0))
    else:
        desired = count(spec.get("replicas"), default=1)
        ready = count(status.get("readyReplicas"))
        updated = count(status.get("updatedReplicas"), default=ready)
        available = count(status.get("availableReplicas"), default=ready)
        unavailable = count(status.get("unavailableReplicas"), default=max(desired - available, 0))
    if generation <= 0 or observed < generation or desired <= 0:
        raise AksDeploymentError(f"AKS rollout metadata for {workload} is incomplete.")
    if ready < desired or updated < desired or available < desired or unavailable:
        raise AksDeploymentError(f"AKS reports that {workload} is not fully available.")
    revision = status.get("updateRevision") or status.get("currentRevision")
    if not isinstance(revision, str) or not revision:
        uid = metadata.get("uid")
        if not isinstance(uid, str) or not uid:
            raise AksDeploymentError(f"AKS rollout metadata for {workload} has no resource identity.")
        revision = f"{uid}:{generation}"
    return ({
        "desired": desired,
        "ready": ready,
        "updated": updated,
        "available": available,
        "unavailable": unavailable,
        "generation": generation,
        "observed_generation": observed,
        "revision": revision,
    }, revision)


def _release_revision(revisions: Sequence[str]) -> str:
    material = "\n".join(sorted(set(revisions)))
    if not material:
        raise AksDeploymentError("AKS returned no rollout revision metadata.")
    return "aks-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _reject_source_symlinks(source: Path, root: Path) -> None:
    resolved = source.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise AksDeploymentError("Kubernetes deployment source escaped the repository workspace.") from error
    if source.is_symlink() or any(path.is_symlink() for path in source.rglob("*")):
        raise AksDeploymentError("Kubernetes deployment source symlinks are blocked.")


def _select_kustomization(root: Path, files: Sequence[str]) -> Path:
    candidates: list[Path] = []
    for relative in files:
        unresolved = root / relative
        if unresolved.is_symlink():
            raise AksDeploymentError("Kustomize source symlinks are blocked.")
        candidate = unresolved.resolve(strict=True)
        try:
            candidate.relative_to(root)
        except ValueError as error:
            raise AksDeploymentError("Kustomize source escaped the repository workspace.") from error
        candidates.append(candidate)
    candidate_directories = sorted(set(path.parent for path in candidates), key=lambda path: len(path.parts))
    roots = [
        directory
        for directory in candidate_directories
        if all(other == directory or other.is_relative_to(directory) for other in candidate_directories)
    ]
    if len(roots) != 1:
        raise AksDeploymentError("Automatic AKS deployment requires one unambiguous Kustomize root.")
    root_files = [path for path in candidates if path.parent == roots[0]]
    if len(root_files) != 1:
        raise AksDeploymentError("The Kustomize root contains an ambiguous configuration.")
    _reject_source_symlinks(roots[0], root)
    return root_files[0]


def _render_assets(
    *,
    root: Path,
    assets: KubernetesAssets,
    temp: Path,
    namespace: str,
    release_name: str,
    runner: CommandRunner,
    environment: dict[str, str],
    kubectl: str,
    helm: str | None,
) -> tuple[list[str | os.PathLike[str]], Path]:
    source_count = sum(bool(group) for group in (
        assets.manifest_files,
        assets.chart_directories,
        assets.kustomization_files,
    ))
    if source_count != 1:
        raise AksDeploymentError(
            "Automatic AKS deployment requires exactly one source type: manifests, one Helm chart, or Kustomize."
        )
    if assets.manifest_files:
        return list(assets.manifest_files), root
    if assets.chart_directories:
        if len(assets.chart_directories) != 1 or not helm:
            raise AksDeploymentError("Automatic AKS deployment currently supports one Helm chart per project.")
        unresolved_chart = root / assets.chart_directories[0]
        _reject_source_symlinks(unresolved_chart, root)
        chart = unresolved_chart.resolve(strict=True)
        output = temp / "helm-rendered"
        _required(
            runner,
            [
                helm,
                "template",
                release_name,
                str(chart),
                "--namespace",
                namespace,
                "--output-dir",
                str(output),
            ],
            str(root),
            environment,
            action="Helm template rendering",
        )
        files = sorted(path for path in output.rglob("*.yaml") if path.is_file())
        if not files:
            raise AksDeploymentError("Helm did not render any Kubernetes manifests.")
        return files, temp
    kustomization = _select_kustomization(root, assets.kustomization_files)
    output = temp / "kustomize-rendered.yaml"
    _required(
        runner,
        [
            kubectl,
            "kustomize",
            str(kustomization.parent),
            "--load-restrictor=LoadRestrictionsRootOnly",
            "--enable-alpha-plugins=false",
            "--network=false",
            "--output",
            str(output),
        ],
        str(root),
        environment,
        action="Kustomize rendering",
    )
    if not output.is_file():
        raise AksDeploymentError("Kustomize did not render a Kubernetes manifest.")
    return [output], temp


def _ensure_namespace(
    *,
    runner: CommandRunner,
    kubectl: str,
    cwd: str,
    environment: dict[str, str],
    temp: Path,
    namespace: str,
    release_name: str,
) -> None:
    result = _required(
        runner,
        [kubectl, "get", "namespace", namespace, "--ignore-not-found", "-o", "json"],
        cwd,
        environment,
        timeout=60,
        action="Kubernetes namespace inspection",
    )
    existing = _json_object(result, action="namespace", allow_empty=True)
    if existing is not None:
        metadata = existing.get("metadata") if isinstance(existing.get("metadata"), dict) else {}
        labels = metadata.get("labels") if isinstance(metadata.get("labels"), dict) else {}
        if (
            existing.get("kind") != "Namespace"
            or metadata.get("name") != namespace
            or labels.get(_MANAGED_BY_KEY) != _MANAGED_BY_VALUE
            or labels.get(_LABEL_KEY) != release_name
        ):
            raise AksDeploymentError("The target namespace is not exclusively owned by this ZeroOps release.")
        return
    namespace_manifest = temp / "namespace.json"
    namespace_manifest.write_text(json.dumps({
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {
            "name": namespace,
            "labels": {
                _MANAGED_BY_KEY: _MANAGED_BY_VALUE,
                _LABEL_KEY: release_name,
            },
        },
    }), encoding="utf-8")
    _required(
        runner,
        [kubectl, "create", "-f", str(namespace_manifest)],
        cwd,
        environment,
        timeout=60,
        action="Kubernetes namespace creation",
    )


def deploy_existing_cluster(
    *,
    connection: Any,
    client_secret: str,
    repo_path: str | os.PathLike[str],
    namespace: str,
    image_ref: str,
    release_name: str,
    runner: CommandRunner = _run,
    kubeconfig_writer: Callable[[Any, str, Path], None] = _write_cluster_user_kubeconfig,
    scanner: ScanRunner = security_scanner.run_scan,
) -> AksRelease:
    """Validate, deploy, and verify a release on a configured existing AKS cluster."""
    root = Path(repo_path).resolve(strict=True)
    namespace = normalize_namespace(namespace)
    release_name = normalize_release_name(release_name)
    cluster = str(getattr(connection, "aks_cluster_name", "") or "").strip()
    if not cluster:
        raise AksDeploymentError("An existing AKS cluster is not configured.")
    if not _IMAGE_DIGEST_PATTERN.fullmatch(str(image_ref or "")):
        raise AksDeploymentError("AKS deployment requires an immutable sha256 image digest.")
    registry = str(getattr(connection, "acr_login_server", "") or "").strip().lower().rstrip("/")
    if registry.startswith("https://"):
        registry = registry.removeprefix("https://")
    if not registry or not image_ref.lower().startswith(registry + "/"):
        raise AksDeploymentError("AKS deployment image must come from the connected Azure Container Registry.")
    assets = detect_kubernetes_assets(root)
    if not assets.detected:
        raise AksDeploymentError("No Kubernetes manifests, Helm chart, or Kustomize configuration was detected.")

    kubectl = _tool("kubectl")
    kubeconform = _tool("kubeconform")
    _tool("trivy")
    helm = _tool("helm", required=bool(assets.chart_directories))

    with tempfile.TemporaryDirectory(prefix="zeroops-aks-") as temp_dir:
        temp = Path(temp_dir)
        kubeconfig = temp / "kubeconfig"
        environment = _isolated_environment(temp, kubeconfig)
        manifest_files, validation_root = _render_assets(
            root=root,
            assets=assets,
            temp=temp,
            namespace=namespace,
            release_name=release_name,
            runner=runner,
            environment=environment,
            kubectl=str(kubectl),
            helm=str(helm) if helm else None,
        )

        documents, workloads = validate_and_render_manifests(
            manifest_files,
            repo_path=validation_root,
            namespace=namespace,
            image_ref=image_ref,
            release_name=release_name,
        )
        validated = temp / "validated"
        validated.mkdir(mode=0o700)
        rendered = validated / "rendered.yaml"
        rendered.write_text(yaml.safe_dump_all(documents, sort_keys=False), encoding="utf-8")

        _required(
            runner,
            [str(kubeconform), "-strict", "-summary", str(rendered)],
            str(root),
            environment,
            action="Kubernetes schema validation",
        )
        scan = scanner(
            "kubernetes",
            validated,
            required=True,
            policy=security_scanner.ScanPolicy(block_critical=True, block_high=True),
        )
        if scan.blocking or scan.status in {"failed", "blocked", "unavailable"}:
            raise AksDeploymentError(f"Kubernetes security validation blocked deployment: {scan.summary}")

        kubeconfig_writer(connection, client_secret, kubeconfig)
        _validate_isolated_kubeconfig(kubeconfig)
        _ensure_namespace(
            runner=runner,
            kubectl=str(kubectl),
            cwd=str(root),
            environment=environment,
            temp=temp,
            namespace=namespace,
            release_name=release_name,
        )
        _required(
            runner,
            [
                str(kubectl),
                "apply",
                "--server-side=true",
                "--field-manager=zeroops",
                "--validate=strict",
                "--dry-run=server",
                "--namespace",
                namespace,
                "-f",
                str(rendered),
            ],
            str(root),
            environment,
            action="Kubernetes server-side dry run",
        )
        _required(
            runner,
            [
                str(kubectl),
                "apply",
                "--server-side=true",
                "--field-manager=zeroops",
                "--validate=strict",
                "--namespace",
                namespace,
                "-f",
                str(rendered),
            ],
            str(root),
            environment,
            action="AKS manifest deployment",
        )
        for workload in workloads:
            _required(
                runner,
                [str(kubectl), "rollout", "status", workload, "--namespace", namespace, "--timeout=10m"],
                str(root),
                environment,
                timeout=660,
                action=f"AKS rollout verification for {workload}",
            )

        workload_status: dict[str, dict[str, int | str]] = {}
        revisions: list[str] = []
        for workload in workloads:
            result = _required(
                runner,
                [str(kubectl), "get", workload, "--namespace", namespace, "-o", "json"],
                str(root),
                environment,
                timeout=60,
                action=f"AKS rollout metadata inspection for {workload}",
            )
            payload = _json_object(result, action=f"rollout for {workload}")
            assert payload is not None
            status, revision = _workload_health(workload, payload)
            workload_status[workload] = status
            revisions.append(revision)

        resources = _required(
            runner,
            [
                str(kubectl),
                "get",
                "service,ingress",
                "--namespace",
                namespace,
                "--selector",
                f"{_LABEL_KEY}={release_name}",
                "-o",
                "json",
            ],
            str(root),
            environment,
            timeout=60,
            action="AKS service endpoint inspection",
        )
        pods = _required(
            runner,
            [
                str(kubectl),
                "get",
                "pods",
                "--namespace",
                namespace,
                "--selector",
                f"{_LABEL_KEY}={release_name}",
                "-o",
                "json",
            ],
            str(root),
            environment,
            timeout=60,
            action="AKS pod health inspection",
        )
        endpoint_payload = _json_object(resources, action="service endpoint")
        pod_payload = _json_object(pods, action="pod health")
        assert endpoint_payload is not None and pod_payload is not None
        pod_status = _pod_counts(pod_payload, release_name=release_name)
        expected_pods = sum(int(status["desired"]) for status in workload_status.values())
        if pod_status["ready"] < expected_pods or pod_status["not_ready"] or pod_status["failed"]:
            raise AksDeploymentError("AKS rollout completed but one or more application pods are not ready.")
        return AksRelease(
            cluster=cluster,
            namespace=namespace,
            workloads=workloads,
            image_digest=image_ref,
            deployment_revision=_release_revision(revisions),
            service_endpoint=_extract_endpoint(endpoint_payload, release_name=release_name),
            rollout_status="healthy",
            pod_status=pod_status,
            workload_status=workload_status,
        )
