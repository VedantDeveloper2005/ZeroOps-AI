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
    environment_name: str | None = None
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
    """Return only the fields required for a real Container Apps deployment."""
    if not connection:
        return ["Azure connection"]

    required = {
        "Tenant ID": getattr(connection, "tenant_id", None),
        "Subscription ID": getattr(connection, "subscription_id", None),
        "Client ID": getattr(connection, "client_id", None),
        "Resource group": getattr(connection, "resource_group", None),
        "Container registry": getattr(connection, "acr_login_server", None),
        "Application environment": getattr(connection, "container_apps_environment", None),
    }
    return [label for label, value in required.items() if not _clean(value)]


def target_statuses(azure_connection: Any | None) -> list[TargetStatus]:
    missing = azure_missing(azure_connection)
    return [
        TargetStatus(
            provider="azure-container-apps",
            label="Azure application environment",
            ready=not missing,
            missing=missing,
            region=getattr(azure_connection, "region", None) if azure_connection else None,
            environment_name=getattr(azure_connection, "container_apps_environment", None) if azure_connection else None,
            registry=getattr(azure_connection, "acr_login_server", None) if azure_connection else None,
        )
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
    """Select the sole supported target without relying on generated AI hints."""
    requested = (requested_provider or "auto").strip().lower()
    if requested not in {"auto", "azure", "azure-container-apps", "container-apps"}:
        raise ValueError("Only Azure application environments are supported.")

    missing = azure_missing(azure_connection)
    if missing:
        raise ValueError(
            "Azure hosting needs setup before launch: " + ", ".join(missing) + "."
        )

    return SelectedTarget(
        "azure-container-apps",
        "Azure application environment",
        azure_connection,
        "Azure is the configured hosting environment.",
    )


def namespace_prefix(target: SelectedTarget, user_id: Any) -> str:
    """Compatibility helper for stable, per-account application names."""
    existing = _clean(getattr(target.connection, "namespace_prefix", None))
    return existing or f"app-{str(user_id)[:8]}"


def image_ref_for_target(target: SelectedTarget, project_slug: str, version: str) -> str:
    registry = _clean(getattr(target.connection, "acr_login_server", "")).rstrip("/")
    if not registry:
        raise ValueError("Azure container registry is not configured.")
    return f"{registry}/{project_slug}:{version}"


def metadata_for_target(target: SelectedTarget) -> dict:
    return {
        "provider": target.provider,
        "subscription_id": getattr(target.connection, "subscription_id", None),
        "region": getattr(target.connection, "region", None),
        "resource_group": getattr(target.connection, "resource_group", None),
        "acr_login_server": getattr(target.connection, "acr_login_server", None),
        "container_apps_environment": getattr(target.connection, "container_apps_environment", None),
    }
