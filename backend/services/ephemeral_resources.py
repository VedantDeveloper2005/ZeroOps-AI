"""
Ephemeral Cloud Sandboxes & Self-Service Resources Service
==========================================================
Manages the lifecycle of on-demand, temporary Azure resources (Linux/Windows VMs,
PostgreSQL/MySQL databases, containers, storage, redis) for testing, staging, and QA.
Enforces strict Time-To-Live (TTL) with automated background teardown.
"""

from __future__ import annotations

import asyncio
import copy
import hmac
import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from typing import Any, Dict, List, Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from backend import models, schemas
    from backend.services.cost_engine import calculate_custom_subtotal
    from backend.services.deployment_targets import configuration_fingerprint
except ImportError:
    import models
    import schemas
    from services.cost_engine import calculate_custom_subtotal
    from services.deployment_targets import configuration_fingerprint

try:
    from backend.services import azure_connector
except ImportError:  # Azure SDKs are optional for template validation/unit tests.
    try:
        from services import azure_connector
    except ImportError:
        azure_connector = None

logger = logging.getLogger("zeroops.ephemeral_resources")

# ──────────────────────────────────────────────
# RESOURCE CATALOG DEFINITIONS
# ──────────────────────────────────────────────

RESOURCE_CATALOG = {
    "custom_arm": {
        "title": "Custom Azure Resource Template",
        "description": "Deploy a reviewed Azure Resource Manager template into your verified resource group.",
        "icon": "layers",
        "category": "custom",
        "default_sku": "Custom",
        "skus": [],
        "distros": [],
        "default_ports": [],
    },
}
REGIONS = [
    {"id": "eastus", "label": "East US (Virginia)"},
    {"id": "eastus2", "label": "East US 2 (Virginia)"},
    {"id": "westeurope", "label": "West Europe (Netherlands)"},
    {"id": "northeurope", "label": "North Europe (Ireland)"},
    {"id": "centralus", "label": "Central US (Iowa)"},
    {"id": "westus2", "label": "West US 2 (Washington)"},
]


_ARM_TYPE = re.compile(r"^Microsoft\.[A-Za-z0-9.]+/(?:[A-Za-z0-9._-]+/)*[A-Za-z0-9._-]+$")
_ARM_API_VERSION = re.compile(r"^20\d\d-\d\d-\d\d(?:-preview)?$")
_ARM_SENSITIVE_KEY = re.compile(r"(?:password|passwd|secret|token|api.?key|private.?key|client.?credential)", re.IGNORECASE)
_ARM_DENIED_TYPES = (
    "microsoft.authorization/",
    "microsoft.resources/deployments",
    "microsoft.resources/deploymentscripts",
    "microsoft.managedidentity/",
)
_ARM_DENIED_KEYS = frozenset({"scope", "subscriptionid", "resourcegroup", "copy"})
_MAX_ARM_TEMPLATE_BYTES = 512 * 1024
_MAX_ARM_RESOURCE_COUNT = 25


class AzureResourceProvisioningError(RuntimeError):
    """A redacted error raised when the customer's Azure deployment fails."""


def validate_custom_arm_template(
    template: Dict[str, Any],
    region: str,
    resource_id: str,
    custom_tags: Optional[Dict[str, str]] = None,
) -> tuple[Dict[str, Any], List[Dict[str, str]]]:
    """Validate a bounded, single-resource-group ARM deployment and track its resources."""
    if not isinstance(template, dict):
        raise ValueError("Enter a valid ARM template object.")
    try:
        import json

        if len(json.dumps(template, separators=(",", ":"), ensure_ascii=False).encode("utf-8")) > _MAX_ARM_TEMPLATE_BYTES:
            raise ValueError("The ARM template is too large (maximum 512 KB).")
    except (TypeError, UnicodeError) as error:
        raise ValueError("The ARM template must contain JSON-compatible values.") from error

    resources = template.get("resources")
    if not isinstance(resources, list) or not resources or len(resources) > _MAX_ARM_RESOURCE_COUNT:
        raise ValueError(f"The ARM template must declare between 1 and {_MAX_ARM_RESOURCE_COUNT} top-level resources.")
    normalized = copy.deepcopy(template)
    normalized.setdefault("$schema", "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#")
    normalized.setdefault("contentVersion", "1.0.0.0")
    resource_manifest: List[Dict[str, str]] = []
    declared_parameters = normalized.get("parameters") or {}
    if not isinstance(declared_parameters, dict) or len(declared_parameters) > 50:
        raise ValueError("ARM template parameters must be an object with at most 50 entries.")
    if custom_tags is not None:
        if not isinstance(custom_tags, dict) or len(custom_tags) > 50:
            raise ValueError("Resource tags must be an object with at most 50 entries.")
        for key, value in custom_tags.items():
            if (
                not isinstance(key, str)
                or not key.strip()
                or len(key) > 128
                or _ARM_SENSITIVE_KEY.search(key)
                or not isinstance(value, str)
                or len(value) > 256
            ):
                raise ValueError("Tags need plain-text names and values; sensitive tag names are not allowed.")
    for parameter_name, definition in declared_parameters.items():
        if not isinstance(definition, dict):
            raise ValueError("Each ARM parameter declaration must be a JSON object.")
        if _ARM_SENSITIVE_KEY.search(str(parameter_name)):
            parameter_type = str(definition.get("type") or "").casefold()
            if parameter_type not in {"securestring", "secureobject"} or "defaultValue" in definition:
                raise ValueError("Credential parameters must use secureString/secureObject and cannot have a template default.")

    outputs = normalized.get("outputs") or {}
    if not isinstance(outputs, dict):
        raise ValueError("ARM template outputs must be a JSON object.")
    for output_name, output in outputs.items():
        if _ARM_SENSITIVE_KEY.search(str(output_name)) or (
            isinstance(output, dict) and str(output.get("type") or "").casefold() in {"securestring", "secureobject"}
        ):
            raise ValueError("ARM template outputs cannot include credentials or other sensitive values.")

    variables = normalized.get("variables") or {}
    if not isinstance(variables, dict):
        raise ValueError("ARM template variables must be a JSON object.")

    def inspect(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                key_lower = str(key).casefold()
                if key_lower in _ARM_DENIED_KEYS:
                    raise ValueError(f"ARM template property '{key}' is not allowed in a tenant resource deployment.")
                if _ARM_SENSITIVE_KEY.search(str(key)):
                    parameter_reference = isinstance(child, str) and bool(re.fullmatch(r"\[parameters\('[A-Za-z0-9_.-]+'\)\]", child.strip(), re.IGNORECASE))
                    if not parameter_reference:
                        raise ValueError(f"Sensitive ARM value '{key}' must use a secureString or secureObject parameter.")
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)

    for item in normalized["resources"]:
        if not isinstance(item, dict):
            raise ValueError("Each ARM resource must be a JSON object.")
        inspect(item)
        resource_type = str(item.get("type") or "")
        api_version = str(item.get("apiVersion") or "")
        name = str(item.get("name") or "")
        if not _ARM_TYPE.fullmatch(resource_type) or not _ARM_API_VERSION.fullmatch(api_version):
            raise ValueError("Every resource needs a full Microsoft.* type and a dated apiVersion.")
        if any(resource_type.casefold().startswith(prefix) for prefix in _ARM_DENIED_TYPES):
            raise ValueError(f"Resource type '{resource_type}' is blocked by ZeroOps tenant-scope guardrails.")
        if not name or len(name) > 180 or "[" in name or "]" in name:
            raise ValueError("Resource names must be literal strings (maximum 180 characters).")
        if "resources" in item:
            raise ValueError("Declare each resource at the template root so ZeroOps can track and remove it safely.")
        tags = item.get("tags")
        if tags is not None and not isinstance(tags, dict):
            raise ValueError("Resource tags must be a JSON object.")
        if tags is not None:
            stamped_tags = dict(tags)
            if custom_tags:
                stamped_tags.update(custom_tags)
            stamped_tags.update({"zeroops-managed": "true", "zeroops-resource-id": resource_id})
            item["tags"] = stamped_tags
        # Global Azure resources have no regional location. Leave absent location
        # properties alone, and normalize literal regional locations to the choice.
        if "location" in item:
            location = item["location"]
            if not isinstance(location, str) or "[" in location or "]" in location:
                raise ValueError("Resource locations must be literal region names or 'global'.")
            if location.casefold() != "global":
                item["location"] = region
        resource_manifest.append({
            "id_suffix": f"providers/{resource_type}/{name}",
            "api_version": api_version,
        })

    # Variables are part of the submitted template too; prevent credentials from
    # being embedded there under innocuous-looking variable names.
    inspect(variables)

    return normalized, resource_manifest



# ──────────────────────────────────────────────
# PROVISIONING ENGINE
# ──────────────────────────────────────────────

async def provision_ephemeral_resource(
    db: AsyncSession,
    user: models.User,
    request: schemas.EphemeralResourceCreateRequest,
    source: str = "catalog_ui",
    source_reference: Optional[str] = None,
) -> models.EphemeralResource:
    """Deploy a reviewed ARM template to the user's verified Azure resource group."""
    now = datetime.now(timezone.utc)
    ttl = max(15, min(request.ttl_minutes or 120, 2880))
    expires_at = now + timedelta(minutes=ttl)
    if request.resource_type != "custom_arm" or request.arm_template is None:
        raise ValueError("Choose Custom Azure Resource and provide a reviewed ARM template. Catalog presets are not yet wired to real Azure templates.")
    if request.estimated_resource_hourly_usd is None:
        raise ValueError("Enter the Azure hourly estimate from your Azure pricing calculator before deployment.")
    if not re.fullmatch(r"[a-z0-9-]{2,50}", request.region.casefold()):
        raise ValueError("Use a valid lowercase Azure region name.")

    subtotal_quote = calculate_custom_subtotal(request.estimated_resource_hourly_usd, ttl)
    resource_uuid = uuid.uuid4()
    clean_name = "".join(ch for ch in request.name.lower() if ch.isalnum() or ch == "-").strip("-")
    res_slug = f"{(clean_name or 'azure-resource')[:42].rstrip('-')}-{secrets.token_hex(3)}"
    normalized_template, resource_manifest = validate_custom_arm_template(
        request.arm_template, request.region, str(resource_uuid), request.tags
    )

    azure_conn_result = await db.execute(
        select(models.UserAzureConnection).filter(
            models.UserAzureConnection.user_id == user.id,
            models.UserAzureConnection.is_active.is_(True),
            models.UserAzureConnection.connection_status == "connected",
        )
    )
    azure_conn = azure_conn_result.scalars().first()
    if not azure_conn or not azure_conn.resource_group:
        raise AzureResourceProvisioningError("Connect and verify an Azure resource group before deploying resources.")
    expected_fingerprint = configuration_fingerprint(azure_conn)
    stored_fingerprint = str(azure_conn.deployment_target_fingerprint or "")
    if (
        azure_conn.deployment_target_verified_at is None
        or not stored_fingerprint
        or not hmac.compare_digest(stored_fingerprint, expected_fingerprint)
    ):
        raise AzureResourceProvisioningError("Reverify the Azure resource group before deploying resources.")
    if azure_connector is None:
        raise AzureResourceProvisioningError("Azure management libraries are unavailable in this runtime.")
    clients = await azure_connector.get_azure_clients_async(user.id, db, azure_conn.id)
    if not clients or not clients.get("resource"):
        raise AzureResourceProvisioningError("A verified Azure deployment credential is unavailable. Reconnect Azure and retry.")
    resource_client = clients["resource"]
    resource_group = str(clients.get("resource_group") or azure_conn.resource_group)
    if (
        resource_group != azure_conn.resource_group
        or clients.get("subscription_id") != azure_conn.subscription_id
    ):
        raise AzureResourceProvisioningError("The verified Azure resource group changed. Reverify the Azure connection.")

    managed_resources: List[Dict[str, str]] = []
    for item in resource_manifest:
        full_id = (
            f"/subscriptions/{azure_conn.subscription_id}/resourceGroups/{resource_group}/"
            f"{item['id_suffix']}"
        )
        managed_resources.append({"id": full_id, "api_version": item["api_version"]})

    # Never let an ARM incremental deployment silently update a pre-existing resource.
    def ensure_names_are_new() -> None:
        for item in managed_resources:
            try:
                    resource_client.resources.get_by_id(item["id"], api_version=item["api_version"])
            except Exception as error:
                if getattr(error, "status_code", None) == 404 or error.__class__.__name__ == "ResourceNotFoundError":
                    continue
                raise AzureResourceProvisioningError("Azure could not verify that the requested resource names are unused.") from error
            raise ValueError("An ARM template resource name already exists in the selected resource group. Change the resource name and retry.")

    await asyncio.to_thread(ensure_names_are_new)

    deployment_name = f"zo-{resource_uuid.hex[:24]}"
    supplied_parameters = request.arm_parameters or {}
    declared_parameters = normalized_template.get("parameters") or {}
    if not isinstance(declared_parameters, dict) or not isinstance(supplied_parameters, dict):
        raise ValueError("ARM parameters must be JSON objects.")
    unknown_parameters = set(supplied_parameters) - set(declared_parameters)
    if unknown_parameters:
        raise ValueError("Every supplied ARM parameter must be declared in the template.")
    deployment_parameters = {key: {"value": value} for key, value in supplied_parameters.items()}
    deployment_payload = {
        "properties": {
            "mode": "Incremental",
            "template": normalized_template,
            "parameters": deployment_parameters,
        }
    }

    first_resource = managed_resources[0]
    portal_url = (
        "https://portal.azure.com/#@/resource/subscriptions/"
        f"{quote(str(azure_conn.subscription_id), safe='')}/resourceGroups/"
        f"{quote(resource_group, safe='')}/overview"
    )
    resource = models.EphemeralResource(
        id=resource_uuid,
        user_id=user.id,
        tenant_id=None,
        name=res_slug,
        resource_type="custom_arm",
        region=request.region,
        sku=request.sku or "Custom",
        status="provisioning",
        source=source,
        source_reference=source_reference,
        ttl_minutes=ttl,
        expires_at=expires_at,
        cost_estimate_hourly=subtotal_quote.hourly_subtotal,
        connection_info={"portal_url": portal_url},
        # Only lifecycle identifiers and a template digest are retained. Parameter
        # values and the submitted template are used for this apply and then dropped.
        configuration={
            "deployment_name": deployment_name,
            "azure_connection_id": str(azure_conn.id),
            "managed_resources": managed_resources,
            "resource_count": len(managed_resources),
            "arm_template_sha256": __import__("hashlib").sha256(
                __import__("json").dumps(normalized_template, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        },
        azure_resource_id=first_resource["id"],
        azure_resource_group=resource_group,
        logs=[{"timestamp": now.isoformat(), "message": f"Azure ARM deployment {deployment_name} started in resource group {resource_group}."}],
        created_at=now,
        updated_at=now,
    )
    db.add(resource)
    await db.commit()
    await db.refresh(resource)

    def deploy() -> Any:
        poller = resource_client.deployments.begin_create_or_update(
            resource_group, deployment_name, deployment_payload
        )
        return poller.result()

    try:
        deployment_result = await asyncio.to_thread(deploy)
    except Exception as error:
        logger.warning("Azure ARM resource deployment failed (%s).", type(error).__name__)
        resource.status = "failed"
        resource.expires_at = now
        resource.logs = [*(resource.logs or []), {"timestamp": datetime.now(timezone.utc).isoformat(), "message": "Azure deployment failed; cleanup of any partially created resources is scheduled."}]
        await db.commit()
        try:
            await destroy_ephemeral_resource(db, resource, reason="Cleanup after failed ARM deployment")
        except AzureResourceProvisioningError:
            logger.warning("Cleanup after a failed Azure ARM deployment remains scheduled.")
        raise AzureResourceProvisioningError("Azure rejected or could not complete this ARM deployment. Check Azure activity before retrying.") from error

    properties = getattr(deployment_result, "properties", None)
    provisioning_state = (
        getattr(properties, "provisioning_state", None)
        or (properties.get("provisioningState") if isinstance(properties, dict) else None)
    )
    if not provisioning_state or str(provisioning_state).casefold() != "succeeded":
        resource.status = "failed"
        resource.expires_at = now
        resource.logs = [*(resource.logs or []), {"timestamp": datetime.now(timezone.utc).isoformat(), "message": "Azure did not confirm success; cleanup of any partially created resources is scheduled."}]
        await db.commit()
        try:
            await destroy_ephemeral_resource(db, resource, reason="Cleanup after unconfirmed ARM deployment")
        except AzureResourceProvisioningError:
            logger.warning("Cleanup after an unconfirmed Azure ARM deployment remains scheduled.")
        raise AzureResourceProvisioningError("Azure did not confirm deployment success. Check Azure activity before retrying.")

    init_logs = [
        {"timestamp": now.isoformat(), "message": f"Azure ARM deployment {deployment_name} completed with state {provisioning_state or 'Succeeded'} in resource group {resource_group}."},
        {"timestamp": now.isoformat(), "message": f"Auto-destroy is scheduled for {expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')} ({ttl} minutes)."},
    ]
    resource.status = "active"
    resource.logs = init_logs
    resource.updated_at = datetime.now(timezone.utc)
    db.add(models.ActivityEvent(
        user_id=user.id,
        action="Ephemeral Azure resources provisioned",
        details=f"ARM deployment {deployment_name} created {len(managed_resources)} resource(s) via {source}; TTL {ttl}m.",
    ))
    await db.commit()
    await db.refresh(resource)
    logger.info("Deployed ARM resource set %s for user %s (TTL: %dm)", resource.id, user.id, ttl)
    return resource


async def extend_ephemeral_resource(
    db: AsyncSession,
    user_id: uuid.UUID,
    resource_id: uuid.UUID,
    extend_minutes: int = 60,
) -> models.EphemeralResource:
    """Extends the Time-To-Live of an active ephemeral resource."""
    res_query = await db.execute(
        select(models.EphemeralResource).filter(
            models.EphemeralResource.id == resource_id,
            models.EphemeralResource.user_id == user_id,
        )
    )
    resource = res_query.scalars().first()
    if not resource:
        raise ValueError("Resource not found.")
    if resource.status != "active":
        raise ValueError(f"Cannot extend resource in '{resource.status}' status.")
    if not (resource.configuration or {}).get("managed_resources"):
        raise ValueError("This legacy resource has no verified Azure identifiers and cannot be extended.")

    now = datetime.now(timezone.utc)
    expires = resource.expires_at.replace(tzinfo=timezone.utc) if resource.expires_at.tzinfo is None else resource.expires_at
    created = resource.created_at.replace(tzinfo=timezone.utc) if resource.created_at.tzinfo is None else resource.created_at
    base_time = expires if expires > now else now
    max_expiration = created + timedelta(hours=48)
    new_expires_at = min(base_time + timedelta(minutes=extend_minutes), max_expiration)

    resource.expires_at = new_expires_at
    resource.ttl_minutes += extend_minutes
    resource.updated_at = now
    
    logs = list(resource.logs or [])
    logs.append({
        "timestamp": now.isoformat(),
        "message": f"TTL extended by +{extend_minutes}m. New auto-destroy scheduled for {new_expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}.",
    })
    resource.logs = logs

    db.add(
        models.ActivityEvent(
            user_id=user_id,
            action="Ephemeral Sandbox Extended",
            details=f"Resource {resource.name} extended by +{extend_minutes}m.",
        )
    )
    await db.commit()
    await db.refresh(resource)
    return resource


async def destroy_ephemeral_resource(
    db: AsyncSession,
    resource: models.EphemeralResource,
    reason: str = "User requested teardown",
) -> models.EphemeralResource:
    """Delete the exact resources recorded from the ARM deployment."""
    now = datetime.now(timezone.utc)
    resource.status = "destroying"
    logs = list(resource.logs or [])
    logs.append({
        "timestamp": now.isoformat(),
        "message": f"Teardown sequence initiated: {reason}.",
    })
    resource.logs = logs
    await db.commit()

    managed_resources = (resource.configuration or {}).get("managed_resources") or []
    if not managed_resources:
        resource.status = "unverified"
        resource.destroyed_at = None
        resource.updated_at = now
        resource.logs = [*logs, {
            "timestamp": now.isoformat(),
            "message": "No Azure resource IDs were recorded, so ZeroOps could not confirm or perform cloud deletion. Verify this legacy resource in Azure manually.",
        }]
        await db.commit()
        await db.refresh(resource)
        return resource

    if managed_resources:
        async def schedule_retry(message: str, user_message: str) -> None:
            resource.status = "active"
            resource.logs = [*logs, {"timestamp": now.isoformat(), "message": message}]
            resource.updated_at = now
            await db.commit()
            raise AzureResourceProvisioningError(user_message)

        if azure_connector is None:
            await schedule_retry(
                "Azure management libraries are unavailable; teardown will retry.",
                "Azure management libraries are unavailable; resource deletion will retry.",
            )

        raw_connection_id = (resource.configuration or {}).get("azure_connection_id")
        try:
            connection_id = uuid.UUID(str(raw_connection_id))
        except (ValueError, TypeError, AttributeError):
            await schedule_retry(
                "The original Azure connection record is unavailable; teardown will retry.",
                "The original Azure connection is unavailable; reconnect and verify it before deleting these resources.",
            )
        connection_result = await db.execute(
            select(models.UserAzureConnection).filter(
                models.UserAzureConnection.id == connection_id,
                models.UserAzureConnection.user_id == resource.user_id,
                models.UserAzureConnection.is_active.is_(True),
                models.UserAzureConnection.connection_status == "connected",
            )
        )
        connection = connection_result.scalars().first()
        if (
            not connection
            or not connection.deployment_target_verified_at
            or not connection.deployment_target_fingerprint
            or not hmac.compare_digest(
                str(connection.deployment_target_fingerprint), configuration_fingerprint(connection)
            )
        ):
            await schedule_retry(
                "The original verified Azure target is unavailable; teardown will retry after reconnection.",
                "Reconnect and verify the original Azure target before deleting these resources.",
            )

        try:
            clients = await azure_connector.get_azure_clients_async(
                resource.user_id, db, connection.id
            )
        except Exception as error:
            logger.warning("Azure credentials could not be loaded for teardown (%s).", type(error).__name__)
            clients = None
        if (
            not clients
            or not clients.get("resource")
            or clients.get("subscription_id") != connection.subscription_id
            or clients.get("resource_group") != resource.azure_resource_group
        ):
            await schedule_retry(
                "The original Azure subscription or resource group is unavailable; teardown will retry.",
                "Reconnect the original Azure target before deleting these resources.",
            )

        def delete_all() -> None:
            pending = list(reversed(managed_resources))
            last_error: Optional[Exception] = None
            while pending:
                next_pending = []
                deleted_any = False
                for item in pending:
                    try:
                        clients["resource"].resources.begin_delete_by_id(
                            item["id"], api_version=item["api_version"]
                        ).result()
                        deleted_any = True
                    except Exception as error:
                        if getattr(error, "status_code", None) == 404 or error.__class__.__name__ == "ResourceNotFoundError":
                            deleted_any = True
                            continue
                        last_error = error
                        next_pending.append(item)
                if not next_pending:
                    break
                if not deleted_any:
                    raise RuntimeError("Azure did not confirm deletion of every managed resource.") from last_error
                pending = next_pending
            deployment_name = str((resource.configuration or {}).get("deployment_name") or "")
            if deployment_name:
                try:
                    clients["resource"].deployments.begin_delete(
                        resource.azure_resource_group, deployment_name
                    ).result()
                except Exception as error:
                    if getattr(error, "status_code", None) != 404 and error.__class__.__name__ != "ResourceNotFoundError":
                        raise

        try:
            await asyncio.to_thread(delete_all)
        except Exception as error:
            logger.warning("Azure ARM resource teardown failed (%s).", type(error).__name__)
            resource.status = "active"
            resource.logs = [*logs, {"timestamp": now.isoformat(), "message": "Azure did not confirm deletion; teardown will retry."}]
            resource.updated_at = now
            await db.commit()
            raise AzureResourceProvisioningError("Azure did not confirm deletion. The resource remains scheduled for teardown retry.") from error
        logs.append({"timestamp": now.isoformat(), "message": f"Azure confirmed deletion of {len(managed_resources)} managed resource(s)."})
    resource.status = "destroyed"
    resource.destroyed_at = now
    resource.updated_at = now
    resource.logs = logs

    db.add(
        models.ActivityEvent(
            user_id=resource.user_id,
            action="Ephemeral Sandbox Destroyed",
            details=f"Resource {resource.name} destroyed ({reason}).",
        )
    )
    await db.commit()
    await db.refresh(resource)
    logger.info("Destroyed ephemeral resource %s (%s)", resource.id, reason)
    return resource


# ──────────────────────────────────────────────
# BACKGROUND TTL EXPIRY DAEMON / REAPER
# ──────────────────────────────────────────────

async def reap_expired_ephemeral_resources(db: AsyncSession) -> int:
    """
    Finds and destroys all active ephemeral resources where expires_at <= utc_now().
    Returns the count of destroyed resources.
    """
    now = datetime.now(timezone.utc)
    expired_query = await db.execute(
        select(models.EphemeralResource).filter(
            models.EphemeralResource.status.in_(["active", "provisioning", "failed"]),
            models.EphemeralResource.expires_at <= now,
        )
    )
    expired_resources = expired_query.scalars().all()
    count = 0

    for res in expired_resources:
        try:
            await destroy_ephemeral_resource(db, res, reason="Auto-destroyed: TTL expired")
            if res.status == "destroyed":
                count += 1
        except Exception as e:
            logger.exception("Error reaping expired resource %s: %s", res.id, e)

    return count
