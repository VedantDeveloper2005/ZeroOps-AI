"""Real Azure access helpers used by the approval gateway and deployment worker."""

from __future__ import annotations

import gc
import json
import logging
import os
import uuid
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
    import vault

logger = logging.getLogger("zeroops.azure_connector")


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
        logger.warning("Azure deployment credential was unavailable for user %s", user_id)
        return None


def delete_credential_from_vault(user_id: uuid.UUID) -> bool:
    try:
        _key_vault_client().begin_delete_secret(_get_kv_secret_name(user_id))
        return True
    except Exception:
        logger.warning("Unable to remove the Azure deployment credential for user %s", user_id)
        return False


def validate_credential(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    subscription_id: str,
    resource_group: str,
) -> dict:
    """Validate an Azure connection with a read-only resource-group lookup."""
    values = [tenant_id, client_id, client_secret, subscription_id, resource_group]
    if not all(str(value or "").strip() for value in values):
        return {"success": False, "error": "All Azure connection fields are required."}
    try:
        credential = ClientSecretCredential(
            tenant_id=tenant_id.strip(),
            client_id=client_id.strip(),
            client_secret=client_secret.strip(),
        )
        resource = ResourceManagementClient(credential, subscription_id.strip())
        resource.resource_groups.get(resource_group.strip())
        return {"success": True, "detail": "Azure connection verified."}
    except Exception:
        logger.exception("Azure connection validation failed")
        return {"success": False, "error": "Azure could not verify these credentials and resource group."}


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
        "error": "Cluster operations are not supported. ZeroOps deploys applications to Azure Container Apps.",
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
