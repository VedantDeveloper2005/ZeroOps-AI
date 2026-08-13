"""Real Azure access helpers used by the approval gateway and deployment worker."""

from __future__ import annotations

import gc
import json
import logging
import os
import re
import uuid
from collections.abc import Mapping
from typing import Any, Optional

from azure.identity import ClientSecretCredential
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.resource.resources import ResourceManagementClient
from azure.mgmt.storage import StorageManagementClient
from sqlalchemy.future import select

try:
    from backend import models
    from backend.services import vault
except ImportError:
    import models
    from services import vault

logger = logging.getLogger("zeroops.azure_connector")

ACR_RESOURCE_API_VERSION = "2023-07-01"
APP_SERVICE_PLAN_API_VERSION = "2023-12-01"
_ACR_LOGIN_SERVER = re.compile(r"^(?P<name>[a-z0-9]{5,50})\.azurecr\.io$")
_ARM_RESOURCE_NAME = re.compile(r"^[A-Za-z0-9._()\-]{1,90}$")


class AzureTargetValidationError(ValueError):
    """A redacted, user-actionable Azure deployment-target validation error."""


def _resource_properties(resource: Any) -> dict[str, Any]:
    properties = getattr(resource, "properties", None)
    if isinstance(properties, Mapping):
        return dict(properties)
    if properties is None:
        return {}
    return {
        name: getattr(properties, name)
        for name in dir(properties)
        if not name.startswith("_") and not callable(getattr(properties, name))
    }


def _property(properties: dict[str, Any], name: str) -> Any:
    expected = name.casefold()
    return next(
        (value for key, value in properties.items() if str(key).casefold() == expected),
        None,
    )


def _normalized_location(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _resource_id(
    subscription_id: str,
    resource_group: str,
    provider: str,
    resource_type: str,
    name: str,
) -> str:
    return (
        f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
        f"/providers/{provider}/{resource_type}/{name}"
    )


def _validate_resource_identity(resource: Any, *, expected_id: str, expected_type: str) -> None:
    resource_id = str(getattr(resource, "id", "") or "")
    resource_type = str(getattr(resource, "type", "") or "")
    if resource_id.casefold() != expected_id.casefold() or resource_type.casefold() != expected_type.casefold():
        raise AzureTargetValidationError(
            "Azure returned deployment-target metadata that does not match the configured resource group."
        )


def _validate_target_resources(
    resource_client: ResourceManagementClient,
    *,
    subscription_id: str,
    resource_group: str,
    acr_login_server: str,
    app_service_plan: str,
    region: str,
) -> None:
    login_server = acr_login_server.strip().casefold().rstrip("/")
    registry_match = _ACR_LOGIN_SERVER.fullmatch(login_server)
    if registry_match is None:
        raise AzureTargetValidationError(
            "Container registry login server must use the form <registry>.azurecr.io."
        )
    if (
        not _ARM_RESOURCE_NAME.fullmatch(resource_group)
        or resource_group.endswith(".")
        or not _ARM_RESOURCE_NAME.fullmatch(app_service_plan)
        or app_service_plan.endswith(".")
    ):
        raise AzureTargetValidationError(
            "The configured Azure resource group or App Service plan name is invalid."
        )

    registry_name = registry_match.group("name")
    registry_id = _resource_id(
        subscription_id,
        resource_group,
        "Microsoft.ContainerRegistry",
        "registries",
        registry_name,
    )
    plan_id = _resource_id(
        subscription_id,
        resource_group,
        "Microsoft.Web",
        "serverfarms",
        app_service_plan,
    )

    registry = resource_client.resources.get_by_id(registry_id, ACR_RESOURCE_API_VERSION)
    _validate_resource_identity(
        registry,
        expected_id=registry_id,
        expected_type="Microsoft.ContainerRegistry/registries",
    )
    registry_properties = _resource_properties(registry)
    returned_login_server = str(_property(registry_properties, "loginServer") or "").casefold().rstrip("/")
    if returned_login_server != login_server:
        raise AzureTargetValidationError(
            "The configured container registry login server does not match the Azure resource."
        )
    registry_state = str(_property(registry_properties, "provisioningState") or "").casefold()
    if registry_state and registry_state != "succeeded":
        raise AzureTargetValidationError("The configured container registry is not ready.")

    plan = resource_client.resources.get_by_id(plan_id, APP_SERVICE_PLAN_API_VERSION)
    _validate_resource_identity(
        plan,
        expected_id=plan_id,
        expected_type="Microsoft.Web/serverfarms",
    )
    plan_properties = _resource_properties(plan)
    if _property(plan_properties, "reserved") is not True:
        raise AzureTargetValidationError(
            "The configured App Service plan is not a Linux plan."
        )
    plan_state = str(_property(plan_properties, "provisioningState") or "").casefold()
    if plan_state and plan_state != "succeeded":
        raise AzureTargetValidationError("The configured App Service plan is not ready.")
    plan_status = str(_property(plan_properties, "status") or "").casefold()
    if plan_status and plan_status != "ready":
        raise AzureTargetValidationError("The configured App Service plan is not ready.")

    expected_location = _normalized_location(region)
    plan_location = _normalized_location(getattr(plan, "location", None))
    if not expected_location or plan_location != expected_location:
        raise AzureTargetValidationError(
            "The Linux App Service plan must match the configured Azure region."
        )


def _get_kv_secret_name(user_id: uuid.UUID) -> str:
    return f"zo-byos-sp-{str(user_id)}".lower()


def _key_vault_client():
    if not vault.HAS_AZURE_KV or vault.kv_client is None:
        raise RuntimeError("Azure Key Vault must be configured before an Azure connection can be saved.")
    return vault.kv_client


def store_credential_in_vault(user_id: uuid.UUID, client_secret: str) -> bool:
    """Persist a BYOS secret only in Azure Key Vault; never on local disk."""
    try:
        _key_vault_client().set_secret(_get_kv_secret_name(user_id), client_secret)
        return True
    except Exception:
        logger.exception("Unable to store the Azure deployment credential in Key Vault")
        return False
    finally:
        # Remove the local reference promptly. Python cannot guarantee physical
        # memory zeroing for immutable strings, but it must not be retained.
        del client_secret
        gc.collect()


def get_credential_secret(user_id: uuid.UUID) -> Optional[str]:
    try:
        return _key_vault_client().get_secret(_get_kv_secret_name(user_id)).value
    except Exception:
        logger.warning("The Azure deployment credential was unavailable.")
        return None


def delete_credential_from_vault(user_id: uuid.UUID) -> bool:
    try:
        _key_vault_client().begin_delete_secret(_get_kv_secret_name(user_id))
        return True
    except Exception:
        logger.warning("Unable to remove the Azure deployment credential.")
        return False


def validate_credential(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    subscription_id: str,
    resource_group: str,
    acr_login_server: str,
    app_service_plan: str,
    region: str,
) -> dict:
    """Validate credentials and exact, existing App Service target resources.

    All Azure calls are read-only. Deployment permissions such as ACR builds,
    Web App writes, and AcrPull role assignment are exercised only by the
    explicitly approved deployment workflow.
    """
    values = [
        tenant_id,
        client_id,
        client_secret,
        subscription_id,
        resource_group,
        acr_login_server,
        app_service_plan,
        region,
    ]
    if not all(str(value or "").strip() for value in values):
        return {
            "success": False,
            "error": (
                "Tenant, subscription, service-principal, resource group, region, "
                "container registry, and Linux App Service plan fields are required."
            ),
        }
    try:
        credential = ClientSecretCredential(
            tenant_id=tenant_id.strip(),
            client_id=client_id.strip(),
            client_secret=client_secret.strip(),
        )
        resource = ResourceManagementClient(credential, subscription_id.strip())
        resource.resource_groups.get(resource_group.strip())
        _validate_target_resources(
            resource,
            subscription_id=subscription_id.strip(),
            resource_group=resource_group.strip(),
            acr_login_server=acr_login_server,
            app_service_plan=app_service_plan.strip(),
            region=region.strip(),
        )
        return {
            "success": True,
            "detail": (
                "Azure credentials, container registry, and Linux App Service plan "
                "were verified with read-only lookups."
            ),
        }
    except AzureTargetValidationError as error:
        return {"success": False, "error": str(error)}
    except Exception as error:
        # Azure SDK exceptions may contain request context. Keep the log useful
        # without serializing credential input or provider response bodies.
        logger.warning(
            "Azure connection validation failed during a %s exception.",
            type(error).__name__,
        )
        return {
            "success": False,
            "error": (
                "Azure could not read the configured resource group, container registry, "
                "and App Service plan with these credentials."
            ),
        }


async def get_azure_clients_async(user_id: uuid.UUID, db) -> Optional[dict[str, Any]]:
    result = await db.execute(
        select(models.UserAzureConnection).filter(
            models.UserAzureConnection.user_id == user_id,
            models.UserAzureConnection.connection_status == "connected",
        )
    )
    connection = result.scalars().first()
    if not connection:
        return None
    client_secret = get_credential_secret(user_id)
    if not client_secret:
        return None
    try:
        credential = ClientSecretCredential(
            tenant_id=connection.tenant_id,
            client_id=connection.client_id,
            client_secret=client_secret,
        )
        return {
            "resource": ResourceManagementClient(credential, connection.subscription_id),
            "network": NetworkManagementClient(credential, connection.subscription_id),
            "storage": StorageManagementClient(credential, connection.subscription_id),
            "resource_group": connection.resource_group,
        }
    except Exception:
        logger.exception("Azure SDK client initialization failed")
        return None


async def _unsupported_cluster_operation(user_id: uuid.UUID, params: dict, db) -> dict:
    return {
        "success": False,
        "error": "Cluster operations are not supported. ZeroOps deploys applications to Azure App Service.",
    }


create_aks_cluster = _unsupported_cluster_operation
update_aks_cluster = _unsupported_cluster_operation
scale_aks_nodepool = _unsupported_cluster_operation
get_aks_cluster = _unsupported_cluster_operation


async def create_vnet(user_id: uuid.UUID, params: dict, db) -> dict:
    clients = await get_azure_clients_async(user_id, db)
    if not clients:
        return {"success": False, "error": "No verified Azure connection is available."}
    try:
        poller = clients["network"].virtual_networks.begin_create_or_update(
            clients["resource_group"],
            str(params.get("vnet_name") or ""),
            {
                "location": params.get("location", "eastus"),
                "address_space": {"address_prefixes": params.get("address_prefixes", ["10.0.0.0/16"])},
            },
        )
        result = poller.result()
        return {"success": True, "id": result.id, "name": result.name}
    except Exception:
        logger.exception("VNet creation failed")
        return {"success": False, "error": "Azure could not create the network."}


async def create_storage_account(user_id: uuid.UUID, params: dict, db) -> dict:
    clients = await get_azure_clients_async(user_id, db)
    if not clients:
        return {"success": False, "error": "No verified Azure connection is available."}
    try:
        poller = clients["storage"].storage_accounts.begin_create(
            clients["resource_group"],
            str(params.get("account_name") or ""),
            {
                "location": params.get("location", "eastus"),
                "sku": {"name": params.get("sku", "Standard_LRS")},
                "kind": "StorageV2",
            },
        )
        result = poller.result()
        return {"success": True, "id": result.id, "name": result.name}
    except Exception:
        logger.exception("Storage account creation failed")
        return {"success": False, "error": "Azure could not create the storage account."}


async def delete_resource(user_id: uuid.UUID, params: dict, db) -> dict:
    clients = await get_azure_clients_async(user_id, db)
    resource_id = str(params.get("resource_id") or "")
    if not clients or not resource_id:
        return {"success": False, "error": "A verified Azure connection and resource ID are required."}
    try:
        clients["resource"].resources.begin_delete_by_id(resource_id).result()
        return {"success": True, "detail": "Azure resource deleted."}
    except Exception:
        logger.exception("Azure resource deletion failed")
        return {"success": False, "error": "Azure could not delete the resource."}


async def list_resources(user_id: uuid.UUID, params: dict, db) -> dict:
    clients = await get_azure_clients_async(user_id, db)
    if not clients:
        return {"success": False, "error": "No verified Azure connection is available."}
    try:
        resources = clients["resource"].resources.list_by_resource_group(clients["resource_group"])
        return {
            "success": True,
            "resources": [{"id": item.id, "name": item.name, "type": item.type} for item in resources],
        }
    except Exception:
        logger.exception("Azure resource listing failed")
        return {"success": False, "error": "Azure could not list resources."}


async def inject_dependency_impl(user_id: uuid.UUID, params: dict, db) -> dict:
    """Disable unaudited source mutations in the production-style MVP."""
    return {
        "success": False,
        "error": "Automatic source-code edits are disabled. Review and commit code changes in your repository.",
    }
