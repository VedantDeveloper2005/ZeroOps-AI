"""Evidence-led infrastructure planning for the ZeroOps Cloud Architect.

This module converts repository facts into a customer-readable architecture
plan.  It intentionally does not make cloud calls, return credentials, or
surface Terraform.  A plan is a decision record; provisioning remains a
separate, approved deployment concern.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SUPPORTED_REGIONS = {
    "centralindia": "Central India",
    "eastus": "East US",
    "westeurope": "West Europe",
    "uksouth": "UK South",
    "southeastasia": "Southeast Asia",
}

APPLICATION_SERVICES = {
    "Azure App Service": {
        "deployable": True,
        "tiers": ["Existing Linux App Service plan", "B1", "S1", "P0v3"],
    },
    "Azure Container Apps": {
        "deployable": False,
        "tiers": ["Consumption", "Dedicated"],
    },
    "Azure Kubernetes Service": {
        "deployable": False,
        "tiers": ["Standard"],
    },
    "Azure Functions": {
        "deployable": False,
        "tiers": ["Flex Consumption", "Premium"],
    },
    "Azure Static Web Apps": {
        "deployable": False,
        "tiers": ["Free", "Standard"],
    },
    "Azure Virtual Machines": {
        "deployable": False,
        "tiers": ["B2s", "D2s v5"],
    },
}

DATABASE_SERVICES = {
    "PostgreSQL": "Azure Database for PostgreSQL Flexible Server",
    "MySQL": "Azure Database for MySQL Flexible Server",
    "MongoDB": "Azure Cosmos DB for MongoDB",
    "Redis": "Azure Cache for Redis",
}


def _as_list(value: Any) -> list[str]:
    return [str(item) for item in value if str(item).strip()] if isinstance(value, list) else []


def _component(
    component_id: str,
    category: str,
    service: str,
    tier: str | None,
    reason: str,
    *,
    recommended: bool = True,
    deployable: bool = True,
    available_services: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": component_id,
        "category": category,
        "service": service,
        "tier": tier,
        "reason": reason,
        "recommended": recommended,
        "deployable": deployable,
        "available_services": available_services or [],
    }


def human_region(value: str | None) -> str:
    normalized = str(value or "").strip().lower().replace(" ", "")
    return SUPPORTED_REGIONS.get(normalized, str(value or "East US"))


def normalize_region(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "")
    if normalized not in SUPPORTED_REGIONS:
        raise ValueError("Choose a supported Azure region.")
    return normalized


def build_infrastructure_plan(
    analysis: dict[str, Any] | None,
    *,
    region: str,
    azure_connection: Any | None = None,
) -> dict[str, Any]:
    """Build a truthful plan from scanner evidence and verified workspace state."""
    analysis = analysis or {}
    framework = str(analysis.get("framework") or "the detected application")
    runtime = str(analysis.get("runtime") or "runtime")
    docker_support = bool(analysis.get("docker_support"))
    databases = _as_list(analysis.get("database_dependencies"))
    variables = _as_list(analysis.get("environment_variables"))
    vulnerabilities = _as_list(analysis.get("vulnerabilities"))

    existing_plan = getattr(azure_connection, "app_service_plan", None) if azure_connection else None
    application_tier = str(existing_plan or "Existing Linux App Service plan required")
    application_reason = (
        f"{framework} was detected with {runtime} metadata"
        + (" and a Dockerfile." if docker_support else ".")
        + " App Service is the verified deployment target currently configured by ZeroOps."
    )
    components: list[dict[str, Any]] = [
        _component(
            "application",
            "Application runtime",
            "Azure App Service",
            application_tier,
            application_reason,
            available_services=list(APPLICATION_SERVICES),
        ),
        _component(
            "monitoring",
            "Monitoring",
            "Application Insights",
            "Workspace-linked",
            "Recommended baseline telemetry for release health and diagnostics.",
            deployable=False,
        ),
    ]

    normalized_databases = []
    for dependency in databases:
        canonical = next((name for name in DATABASE_SERVICES if name.lower() in dependency.lower()), None)
        if canonical and canonical not in normalized_databases:
            normalized_databases.append(canonical)

    for database in normalized_databases:
        service = DATABASE_SERVICES[database]
        category = "Cache" if database == "Redis" else "Database"
        components.append(_component(
            "cache" if database == "Redis" else "database",
            category,
            service,
            "Configuration required",
            f"Repository dependencies reference {database}. Confirm connection and data-retention requirements before deployment.",
            deployable=False,
            available_services=(list(DATABASE_SERVICES.values()) if category == "Database" else []),
        ))

    if variables:
        components.append(_component(
            "secrets",
            "Secrets",
            "Azure Key Vault",
            "Managed identity access",
            "Repository configuration references environment values. Values stay in secure storage and are never shown in the plan.",
            deployable=False,
        ))

    storage_terms = ("storage", "blob", "upload", "s3", "bucket")
    if any(term in variable.lower() for variable in variables for term in storage_terms):
        components.append(_component(
            "storage",
            "Storage",
            "Azure Blob Storage",
            "Standard LRS",
            "Source configuration indicates object-storage integration. Confirm lifecycle and data-residency settings.",
            deployable=False,
        ))

    if normalized_databases:
        components.append(_component(
            "networking",
            "Networking",
            "Virtual Network",
            "Private endpoint review",
            "A managed data service needs a network-access decision before production deployment.",
            deployable=False,
        ))

    unresolved = _as_list(analysis.get("unresolved_questions"))
    if not azure_connection:
        readiness_message = "Connect and validate an Azure environment before cost and deployment validation."
    else:
        readiness_message = "Azure connection found. Validate required resources and cost controls before approval."

    return {
        "cloud": "Azure",
        "region_label": human_region(region),
        "application_evidence": {
            "framework": analysis.get("framework"),
            "runtime": analysis.get("runtime"),
            "package_manager": analysis.get("package_manager"),
            "docker_support": docker_support,
            "database_dependencies": databases,
            "environment_variable_names": variables,
        },
        "components": components,
        "cost": {
            "status": "requires_connected_azure_subscription",
            "monthly_estimate": None,
            "message": "A source scan cannot calculate subscription-specific Azure pricing. Connect Cost Management to validate a monthly estimate.",
        },
        "deployment_time": {
            "status": "requires_resource_validation",
            "estimate": None,
            "message": "Deployment timing is calculated only after the Azure target and required services pass validation.",
        },
        "assessment": {
            "security": {"status": "requires_configuration_review", "value": None},
            "performance": {"status": "requires_runtime_telemetry", "value": None},
            "reliability": {"status": "requires_runtime_telemetry", "value": None},
            "source_findings": vulnerabilities,
            "unresolved_questions": unresolved,
            "readiness_message": readiness_message,
        },
        "deployment": {
            "approval_required": True,
            "engine": "Internal infrastructure engine",
            "summary": "Infrastructure definitions are generated internally after approval. Source, credentials, and IaC files are never included in this plan.",
        },
    }


def build_infrastructure_spec(
    analysis: dict[str, Any] | None,
    *,
    region: str,
    azure_connection: Any | None = None,
) -> dict[str, Any]:
    """Build a detailed but evidence-bound specification.

    This intentionally does not manufacture pricing, scores, or deployment
    durations. Those values require a connected Azure subscription and runtime
    telemetry. Component explanations describe the selected architecture only.
    """
    plan = build_infrastructure_plan(analysis, region=region, azure_connection=azure_connection)
    explanations: dict[str, str] = {}
    framework = (analysis or {}).get("framework", "application")
    for comp in plan["components"]:
        comp_id = comp.get("id")
        if comp_id == "application":
            explanations[comp_id] = (
                f"Azure App Service is the deployment target currently implemented for this {framework} app. "
                "The connected subscription must provide a validated Linux App Service plan before deployment."
            )
        elif comp_id == "database":
            explanations[comp_id] = (
                "Repository dependencies indicate a database requirement. This managed-database entry is a proposal only; "
                "availability, backups, retention, and network access still require explicit configuration."
            )
        elif comp_id == "cache":
            explanations[comp_id] = (
                "Repository dependencies reference Redis. The cache is not provisioned by the current deployment workflow "
                "and its capacity, persistence, and network settings remain unresolved."
            )
        elif comp_id == "storage":
            explanations[comp_id] = (
                "Source configuration references object storage. Azure Blob Storage is a proposed dependency, not a "
                "provisioned resource; lifecycle, redundancy, and data-residency settings need review."
            )
        elif comp_id == "secrets":
            explanations[comp_id] = (
                "Source configuration references sensitive values. ZeroOps stores project secrets through its configured "
                "Key Vault integration; access policy and managed-identity permissions must be validated."
            )
        elif comp_id == "monitoring":
            explanations[comp_id] = (
                "Application Insights is shown as a monitoring proposal. ZeroOps does not claim telemetry is available "
                "until a connected source has written runtime metrics."
            )
        elif comp_id == "networking":
            explanations[comp_id] = (
                "A private-network decision is recommended for managed data services. The current workflow does not "
                "provision or verify this network component."
            )

    plan["ai_explanations"] = explanations
    return plan


def clear_unverified_estimates(plan: dict[str, Any]) -> dict[str, Any]:
    """Remove legacy synthetic pricing, scores, and deployment estimates."""
    updated = deepcopy(plan)
    assessment = updated.get("assessment") or {}
    updated["cost"] = {
        "status": "requires_connected_azure_subscription",
        "monthly_estimate": None,
        "message": "A source scan cannot calculate subscription-specific Azure pricing. Connect Cost Management to validate a monthly estimate.",
    }
    updated["deployment_time"] = {
        "status": "requires_resource_validation",
        "estimate": None,
        "message": "Deployment timing is calculated only after the Azure target and required services pass validation.",
    }
    updated["assessment"] = {
        "security": {"status": "requires_configuration_review", "value": None},
        "performance": {"status": "requires_runtime_telemetry", "value": None},
        "reliability": {"status": "requires_runtime_telemetry", "value": None},
        "source_findings": _as_list(assessment.get("source_findings")),
        "unresolved_questions": _as_list(assessment.get("unresolved_questions")),
        "readiness_message": assessment.get("readiness_message") or "Validate the Azure target and runtime telemetry before relying on readiness metrics.",
    }
    return updated


def _find_component(plan: dict[str, Any], component_id: str) -> dict[str, Any]:
    for component in plan.get("components", []):
        if component.get("id") == component_id:
            return component
    raise ValueError("That architecture component is not part of this plan.")


def _set_component_service(component: dict[str, Any], service: str) -> None:
    if component.get("id") != "application":
        allowed = component.get("available_services") or []
        if allowed and service not in allowed:
            raise ValueError("That service is not available for this component.")
        component["service"] = service
        return

    if service not in APPLICATION_SERVICES:
        raise ValueError("Choose one of the supported application hosting options.")
    details = APPLICATION_SERVICES[service]
    component["service"] = service
    component["tier"] = details["tiers"][0]
    component["deployable"] = details["deployable"]
    if not details["deployable"]:
        component["reason"] = f"{service} is saved as an architecture choice, but this workspace currently deploys through Azure App Service only."


def apply_plan_update(plan: dict[str, Any], *, region: str | None, component_id: str | None, service: str | None, tier: str | None) -> dict[str, Any]:
    """Return a revised plan while keeping unsupported choices explicit."""
    updated = deepcopy(plan)
    if region:
        updated["region_label"] = human_region(normalize_region(region))
    if component_id:
        component = _find_component(updated, component_id)
        if service:
            _set_component_service(component, service)
        if tier:
            tier_value = tier.strip()
            if not tier_value:
                raise ValueError("A pricing tier cannot be empty.")
            component["tier"] = tier_value
    elif service or tier:
        raise ValueError("Choose the component you want to modify.")
    return clear_unverified_estimates(updated)


def apply_chat_instruction(plan: dict[str, Any], message: str) -> tuple[dict[str, Any], str | None]:
    """Translate a narrow set of architecture requests into deterministic updates."""
    text = message.lower().strip()
    region_matches = {
        "central india": "centralindia",
        "centralindia": "centralindia",
        "west europe": "westeurope",
        "westeurope": "westeurope",
        "east us": "eastus",
        "eastus": "eastus",
        "uk south": "uksouth",
        "southeast asia": "southeastasia",
    }
    for phrase, region in region_matches.items():
        if phrase in text:
            return apply_plan_update(plan, region=region, component_id=None, service=None, tier=None), f"Region changed to {human_region(region)}."

    service_matches = {
        "container apps": "Azure Container Apps",
        "kubernetes": "Azure Kubernetes Service",
        "aks": "Azure Kubernetes Service",
        "functions": "Azure Functions",
        "static web app": "Azure Static Web Apps",
        "virtual machine": "Azure Virtual Machines",
        "vm": "Azure Virtual Machines",
        "app service": "Azure App Service",
    }
    for phrase, service in service_matches.items():
        if phrase in text:
            return apply_plan_update(plan, region=None, component_id="application", service=service, tier=None), f"Application runtime changed to {service}."

    if "cosmos db" in text or "cosmos database" in text:
        if any(item.get("id") == "database" for item in plan.get("components", [])):
            return apply_plan_update(
                plan,
                region=None,
                component_id="database",
                service="Azure Cosmos DB for MongoDB",
                tier=None,
            ), "Database changed to Azure Cosmos DB for MongoDB."

    if "add redis" in text:
        updated = deepcopy(plan)
        if not any(item.get("id") == "cache" for item in updated.get("components", [])):
            updated.setdefault("components", []).append(_component(
                "cache", "Cache", "Azure Cache for Redis", "Configuration required",
                "Added after your architecture request. Confirm network access and cache usage before approval.",
                deployable=False,
            ))
            return clear_unverified_estimates(updated), "Azure Cache for Redis added to the plan."

    if "reduce cost" in text or "lower cost" in text or "cheap" in text:
        updated = deepcopy(plan)
        changed = False
        for comp in updated.get("components", []):
            if comp.get("id") == "application":
                comp["tier"] = "B1"  # lower basic tier
                comp["reason"] = "Pricing tier reduced to B1 to optimize infrastructure costs."
                changed = True
            elif comp.get("id") == "database":
                comp["tier"] = "Burstable B1ms"
                changed = True
        if changed:
            return clear_unverified_estimates(updated), "Tiers were adjusted to lower-cost options; validate actual Azure pricing before approval."

    if "increase scalability" in text or "scale up" in text or "premium" in text or "high performance" in text:
        updated = deepcopy(plan)
        changed = False
        for comp in updated.get("components", []):
            if comp.get("id") == "application":
                comp["tier"] = "P0v3"  # high performance tier
                comp["reason"] = "Pricing tier scaled up to P0v3 to support high-performance workloads."
                changed = True
            elif comp.get("id") == "database":
                comp["tier"] = "General Purpose"
                changed = True
        if changed:
            return clear_unverified_estimates(updated), "Tiers were adjusted for higher capacity; validate actual Azure pricing and capacity before approval."

    return deepcopy(plan), None
