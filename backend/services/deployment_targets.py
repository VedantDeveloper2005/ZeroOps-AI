from __future__ import annotations

from dataclasses import dataclass
from typing import Any


AKS_RELEASE_BLOCKER = "Hardened AKS Service/Ingress verification"


@dataclass
class TargetStatus:
    provider: str
    label: str
    ready: bool
    missing: list[str]
    region: str | None = None
    plan_name: str | None = None
    registry: str | None = None
    cluster_name: str | None = None


@dataclass
class SelectedTarget:
    provider: str
    label: str
    connection: Any
    reason: str


def _clean(value: Any) -> str:
    return str(value or "").strip()


def azure_missing(connection: Any | None) -> list[str]:
    """Return fields required for a real App Service deployment."""
    if not connection:
        return ["Azure connection"]
    required = {
        "Tenant ID": getattr(connection, "tenant_id", None),
        "Subscription ID": getattr(connection, "subscription_id", None),
        "Client ID": getattr(connection, "client_id", None),
        "Resource group": getattr(connection, "resource_group", None),
        "Container registry": getattr(connection, "acr_login_server", None),
        "Linux App Service plan": getattr(connection, "app_service_plan", None),
    }
    return [label for label, value in required.items() if not _clean(value)]


def aks_missing(connection: Any | None) -> list[str]:
    """Return configuration and runtime gates required for an AKS release."""
    if not connection:
        return ["Azure connection", AKS_RELEASE_BLOCKER]
    required = {
        "Tenant ID": getattr(connection, "tenant_id", None),
        "Subscription ID": getattr(connection, "subscription_id", None),
        "Client ID": getattr(connection, "client_id", None),
        "Resource group": getattr(connection, "resource_group", None),
        "Container registry": getattr(connection, "acr_login_server", None),
        "Existing AKS cluster": getattr(connection, "aks_cluster_name", None),
    }
    missing = [label for label, value in required.items() if not _clean(value)]
    # The adapter is implemented, but the active pipeline must not advertise a
    # deployable target while its required external verification cannot run.
    missing.append(AKS_RELEASE_BLOCKER)
    return missing


def has_kubernetes_evidence(analysis: dict | None) -> bool:
    """Use deterministic repository evidence, never an unsupported AI claim."""
    facts = analysis if isinstance(analysis, dict) else {}
    if any(bool(facts.get(key)) for key in (
        "kubernetes_detected",
        "kubernetes_manifest_detected",
        "helm_detected",
        "kustomize_detected",
    )):
        return True
    manifest = facts.get("kubernetes_manifest")
    if isinstance(manifest, str) and manifest.strip():
        return True
    paths = facts.get("files") or facts.get("files_list") or facts.get("changed_files") or []
    markers = (
        "kubernetes/", "k8s/", "manifests/", "helm/", "/chart.yaml",
        "deployment.yaml", "deployment.yml", "service.yaml", "service.yml",
        "ingress.yaml", "ingress.yml", "kustomization.yaml", "kustomization.yml",
    )
    for raw_path in paths:
        normalized = f"/{str(raw_path).replace(chr(92), '/').lower()}"
        if any(marker in normalized for marker in markers):
            return True
    return False


def target_statuses(azure_connection: Any | None) -> list[TargetStatus]:
    app_service_missing = azure_missing(azure_connection)
    cluster_missing = aks_missing(azure_connection)
    return [
        TargetStatus(
            provider="azure-app-service",
            label="Azure App Service",
            ready=not app_service_missing,
            missing=app_service_missing,
            region=getattr(azure_connection, "region", None) if azure_connection else None,
            plan_name=getattr(azure_connection, "app_service_plan", None) if azure_connection else None,
            registry=getattr(azure_connection, "acr_login_server", None) if azure_connection else None,
        ),
        TargetStatus(
            provider="azure-aks",
            label="Azure Kubernetes Service",
            ready=not cluster_missing,
            missing=cluster_missing,
            region=getattr(azure_connection, "region", None) if azure_connection else None,
            registry=getattr(azure_connection, "acr_login_server", None) if azure_connection else None,
            cluster_name=getattr(azure_connection, "aks_cluster_name", None) if azure_connection else None,
        ),
    ]


def status_payload(azure_connection: Any | None) -> dict:
    statuses = target_statuses(azure_connection)
    return {
        "any_ready": any(status.ready for status in statuses),
        "targets": [status.__dict__ for status in statuses],
    }


def choose_target(
    analysis: dict | None,
    azure_connection: Any | None,
    requested_provider: str | None = "auto",
) -> SelectedTarget:
    """Select App Service or an existing AKS cluster from repository evidence."""
    requested = (requested_provider or "auto").strip().lower()
    if requested not in {
        "auto", "azure", "azure-app-service", "app-service",
        "azure-kubernetes-service", "azure-aks", "aks",
        # Upgrade legacy stored target aliases to the managed App Service path.
        "azure-container-apps", "container-apps",
    }:
        raise ValueError(
            "Supported targets are Azure App Service and an existing Azure Kubernetes Service cluster."
        )

    kubernetes_evidence = has_kubernetes_evidence(analysis)
    wants_aks = requested in {"azure-kubernetes-service", "azure-aks", "aks"} or (
        requested == "auto" and kubernetes_evidence
    )
    if wants_aks:
        if not kubernetes_evidence:
            raise ValueError(
                "AKS requires validated Kubernetes manifests, a Helm chart, or Kustomize configuration."
            )
        missing = aks_missing(azure_connection)
        if missing:
            raise ValueError(
                "AKS deployment is unavailable: " + ", ".join(missing) + "."
            )
        return SelectedTarget(
            "azure-aks",
            "Azure Kubernetes Service",
            azure_connection,
            "Validated Kubernetes deployment configuration was detected and an existing AKS cluster is configured.",
        )

    missing = azure_missing(azure_connection)
    if missing:
        raise ValueError(
            "Azure App Service needs setup before launch: " + ", ".join(missing) + "."
        )
    return SelectedTarget(
        "azure-app-service",
        "Azure App Service",
        azure_connection,
        (
            "Azure App Service is preferred for this managed web workload; "
            "no validated Kubernetes deployment configuration was selected."
        ),
    )


def namespace_prefix(target: SelectedTarget, user_id: Any) -> str:
    """Return a stable per-account app/namespace prefix."""
    existing = _clean(getattr(target.connection, "namespace_prefix", None))
    default = "aks" if target.provider == "azure-aks" else "app"
    return existing or f"{default}-{str(user_id)[:8]}"


def image_ref_for_target(target: SelectedTarget, project_slug: str, version: str) -> str:
    registry = _clean(getattr(target.connection, "acr_login_server", "")).rstrip("/")
    if not registry:
        raise ValueError("Azure container registry is not configured.")
    return f"{registry}/{project_slug}:{version}"


def metadata_for_target(target: SelectedTarget) -> dict:
    metadata = {
        "provider": target.provider,
        "subscription_id": getattr(target.connection, "subscription_id", None),
        "region": getattr(target.connection, "region", None),
        "resource_group": getattr(target.connection, "resource_group", None),
        "acr_login_server": getattr(target.connection, "acr_login_server", None),
        "app_service_plan": getattr(target.connection, "app_service_plan", None),
    }
    if target.provider == "azure-aks":
        metadata["aks_cluster_name"] = getattr(target.connection, "aks_cluster_name", None)
        metadata.pop("app_service_plan", None)
    return metadata
