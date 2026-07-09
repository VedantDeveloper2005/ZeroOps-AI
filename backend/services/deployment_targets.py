from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TargetStatus:
    provider: str
    label: str
    ready: bool
    missing: list[str]
    region: str | None = None
    cluster_name: str | None = None
    registry: str | None = None


@dataclass
class SelectedTarget:
    provider: str
    label: str
    connection: Any
    reason: str


def _clean(value: Any) -> str:
    return str(value or "").strip()


def azure_missing(connection: Any | None) -> list[str]:
    if not connection:
        return ["Azure target"]
    missing = []
    if not _clean(getattr(connection, "tenant_id", None)):
        missing.append("Tenant ID")
    if not _clean(getattr(connection, "subscription_id", None)):
        missing.append("Subscription ID")
    if not _clean(getattr(connection, "acr_login_server", None)):
        missing.append("ACR login server")
    if not _clean(getattr(connection, "aks_cluster_name", None)):
        missing.append("AKS cluster name")
    return missing


def gke_missing(connection: Any | None) -> list[str]:
    if not connection:
        return ["GKE target"]
    missing = []
    if not _clean(getattr(connection, "gcp_project_id", None)):
        missing.append("Google Cloud project ID")
    if not _clean(getattr(connection, "location", None)):
        missing.append("GKE location")
    if not _clean(getattr(connection, "cluster_name", None)):
        missing.append("GKE cluster name")
    if not _clean(getattr(connection, "artifact_registry_host", None)):
        missing.append("Artifact Registry host")
    if not _clean(getattr(connection, "artifact_registry_repository", None)):
        missing.append("Artifact Registry repository")
    return missing


def target_statuses(azure_connection: Any | None, gke_connection: Any | None) -> list[TargetStatus]:
    azure_gaps = azure_missing(azure_connection)
    gke_gaps = gke_missing(gke_connection)
    return [
        TargetStatus(
            provider="azure",
            label="Azure AKS",
            ready=not azure_gaps,
            missing=azure_gaps,
            region=getattr(azure_connection, "region", None) if azure_connection else None,
            cluster_name=getattr(azure_connection, "aks_cluster_name", None) if azure_connection else None,
            registry=getattr(azure_connection, "acr_login_server", None) if azure_connection else None,
        ),
        TargetStatus(
            provider="gke",
            label="Google GKE",
            ready=not gke_gaps,
            missing=gke_gaps,
            region=getattr(gke_connection, "location", None) if gke_connection else None,
            cluster_name=getattr(gke_connection, "cluster_name", None) if gke_connection else None,
            registry=getattr(gke_connection, "artifact_registry_host", None) if gke_connection else None,
        ),
    ]


def status_payload(azure_connection: Any | None, gke_connection: Any | None) -> dict:
    statuses = target_statuses(azure_connection, gke_connection)
    return {
        "any_ready": any(status.ready for status in statuses),
        "targets": [status.__dict__ for status in statuses],
    }


def _analysis_text(analysis: dict | None) -> str:
    if not analysis:
        return ""
    parts = []
    for key in [
        "deployment_target",
        "deployment_strategy",
        "recommended_target",
        "framework",
        "language",
        "runtime",
        "explanation",
    ]:
        value = analysis.get(key)
        if value:
            parts.append(str(value))
    return " ".join(parts).lower()


def _is_kubernetes_ready_workload(analysis: dict | None) -> bool:
    if not analysis:
        return False
    if _clean(analysis.get("kubernetes_manifest")):
        return True
    if bool(analysis.get("docker_support")):
        return True
    framework = _clean(analysis.get("framework")).lower()
    return framework not in {"", "unknown"}


def choose_target(
    analysis: dict | None,
    azure_connection: Any | None,
    gke_connection: Any | None,
    requested_provider: str | None = "auto",
) -> SelectedTarget:
    requested = (requested_provider or "auto").strip().lower()
    azure_ready = not azure_missing(azure_connection)
    gke_ready = not gke_missing(gke_connection)

    if requested in {"azure", "aks"}:
        if not azure_ready:
            raise ValueError("Azure AKS target is incomplete. Add the missing Azure fields before deployment.")
        return SelectedTarget("azure", "Azure AKS", azure_connection, "Azure was selected explicitly.")

    if requested in {"gke", "google", "google-gke"}:
        if not gke_ready:
            raise ValueError("Google GKE target is incomplete. Add the missing GKE fields before deployment.")
        return SelectedTarget("gke", "Google GKE", gke_connection, "GKE was selected explicitly.")

    text = _analysis_text(analysis)
    if any(term in text for term in ["gke", "google kubernetes", "google cloud", "artifact registry"]) and gke_ready:
        return SelectedTarget("gke", "Google GKE", gke_connection, "AI analysis recommended Google/GKE.")

    if any(term in text for term in ["aks", "azure", "acr"]) and azure_ready:
        return SelectedTarget("azure", "Azure AKS", azure_connection, "AI analysis recommended Azure/AKS.")

    if _is_kubernetes_ready_workload(analysis) and azure_ready:
        return SelectedTarget("azure", "Azure AKS", azure_connection, "Kubernetes-ready app and Azure target is configured.")

    if _is_kubernetes_ready_workload(analysis) and gke_ready:
        return SelectedTarget("gke", "Google GKE", gke_connection, "Kubernetes-ready app and GKE target is configured.")

    if azure_ready:
        return SelectedTarget("azure", "Azure AKS", azure_connection, "Azure target is configured.")

    if gke_ready:
        return SelectedTarget("gke", "Google GKE", gke_connection, "GKE target is configured.")

    raise ValueError("No deployment target is ready. Configure Azure AKS or Google GKE before deployment.")


def namespace_prefix(target: SelectedTarget, user_id: Any) -> str:
    existing = _clean(getattr(target.connection, "namespace_prefix", None))
    if existing:
        return existing
    return f"user-{str(user_id)[:8]}"


def image_ref_for_target(target: SelectedTarget, project_slug: str, version: str) -> str:
    if target.provider == "gke":
        host = _clean(getattr(target.connection, "artifact_registry_host", "")).rstrip("/")
        gcp_project_id = _clean(getattr(target.connection, "gcp_project_id", ""))
        repo = _clean(getattr(target.connection, "artifact_registry_repository", "")).strip("/")
        return f"{host}/{gcp_project_id}/{repo}/{project_slug}:{version}"

    acr = _clean(getattr(target.connection, "acr_login_server", "")).rstrip("/")
    return f"{acr}/{project_slug}:{version}"


def metadata_for_target(target: SelectedTarget) -> dict:
    if target.provider == "gke":
        return {
            "provider": "gke",
            "gcp_project_id": getattr(target.connection, "gcp_project_id", None),
            "location": getattr(target.connection, "location", None),
            "cluster_name": getattr(target.connection, "cluster_name", None),
            "artifact_registry_host": getattr(target.connection, "artifact_registry_host", None),
            "artifact_registry_repository": getattr(target.connection, "artifact_registry_repository", None),
        }

    return {
        "provider": "azure",
        "subscription_id": getattr(target.connection, "subscription_id", None),
        "region": getattr(target.connection, "region", None),
        "resource_group": getattr(target.connection, "resource_group", None),
        "acr_login_server": getattr(target.connection, "acr_login_server", None),
        "aks_cluster_name": getattr(target.connection, "aks_cluster_name", None),
    }
