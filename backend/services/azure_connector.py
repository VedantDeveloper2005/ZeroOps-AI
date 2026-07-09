import os
import logging
from typing import Optional, Dict, Any, List
import uuid
import gc

# Azure Identity and Key Vault
from azure.identity import ClientSecretCredential
# Azure SDK Resource Management
from azure.mgmt.resource.resources import ResourceManagementClient
from azure.mgmt.containerservice import ContainerServiceClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.core.exceptions import AzureError

from sqlalchemy.future import select

try:
    from backend.services import vault
    from backend import config, models
except ImportError:
    import vault
    import config
    import models

logger = logging.getLogger("zeroops.azure_connector")

# ──────────────────────────────────────────────
# MOCK CLIENTS FOR TESTING/DEV
# ──────────────────────────────────────────────

class MockResourceGroupsOperations:
    def __init__(self, resource_group: str):
        self.resource_group = resource_group
    def get(self, resource_group_name: str, **kwargs):
        if resource_group_name == "fail":
            from azure.core.exceptions import ResourceNotFoundError
            raise ResourceNotFoundError("Resource group not found")
        class MockResourceGroup:
            def __init__(self, name):
                self.id = f"/subscriptions/mock-sub/resourceGroups/{name}"
                self.name = name
                self.location = "eastus"
        return MockResourceGroup(resource_group_name)

class MockResourcesOperations:
    def list_by_resource_group(self, resource_group_name: str, **kwargs):
        class MockResource:
            def __init__(self, name, resource_type):
                self.id = f"/subscriptions/mock-sub/resourceGroups/{resource_group_name}/providers/{resource_type}/{name}"
                self.name = name
                self.type = resource_type
        return [
            MockResource("mock-aks", "Microsoft.ContainerService/managedClusters"),
            MockResource("mock-vnet", "Microsoft.Network/virtualNetworks"),
            MockResource("mock-storage", "Microsoft.Storage/storageAccounts")
        ]
    
    def begin_delete_by_id(self, resource_id: str, **kwargs):
        class MockLROPoller:
            def result(self):
                return None
        return MockLROPoller()

class MockResourceManagementClient:
    def __init__(self, subscription_id: str, resource_group: str):
        self.resource_groups = MockResourceGroupsOperations(resource_group)
        self.resources = MockResourcesOperations()
        self.subscription_id = subscription_id

class MockAgentPoolsOperations:
    def begin_create_or_update(self, resource_group_name: str, resource_name: str, agent_pool_name: str, parameters: Any, **kwargs):
        class MockLROPoller:
            def result(self):
                class MockAgentPool:
                    id = f"/subscriptions/mock-sub/resourceGroups/{resource_group_name}/providers/Microsoft.ContainerService/managedClusters/{resource_name}/agentPools/{agent_pool_name}"
                    name = agent_pool_name
                    count = parameters.get("count", 1) if isinstance(parameters, dict) else (getattr(parameters, "count", 1))
                return MockAgentPool()
        return MockLROPoller()

class MockManagedClustersOperations:
    def begin_create_or_update(self, resource_group_name: str, resource_name: str, parameters: Any, **kwargs):
        class MockLROPoller:
            def result(self):
                class MockCluster:
                    id = f"/subscriptions/mock-sub/resourceGroups/{resource_group_name}/providers/Microsoft.ContainerService/managedClusters/{resource_name}"
                    name = resource_name
                    location = "eastus"
                    provisioning_state = "Succeeded"
                return MockCluster()
        return MockLROPoller()

    def get(self, resource_group_name: str, resource_name: str, **kwargs):
        class MockCluster:
            id = f"/subscriptions/mock-sub/resourceGroups/{resource_group_name}/providers/Microsoft.ContainerService/managedClusters/{resource_name}"
            name = resource_name
            location = "eastus"
            provisioning_state = "Succeeded"
        return MockCluster()

    def begin_delete(self, resource_group_name: str, resource_name: str, **kwargs):
        class MockLROPoller:
            def result(self):
                return None
        return MockLROPoller()

class MockContainerServiceClient:
    def __init__(self, subscription_id: str):
        self.managed_clusters = MockManagedClustersOperations()
        self.agent_pools = MockAgentPoolsOperations()

class MockVirtualNetworksOperations:
    def begin_create_or_update(self, resource_group_name: str, virtual_network_name: str, parameters: Any, **kwargs):
        class MockLROPoller:
            def result(self):
                class MockVnet:
                    id = f"/subscriptions/mock-sub/resourceGroups/{resource_group_name}/providers/Microsoft.Network/virtualNetworks/{virtual_network_name}"
                    name = virtual_network_name
                return MockVnet()
        return MockLROPoller()

class MockNetworkManagementClient:
    def __init__(self, subscription_id: str):
        self.virtual_networks = MockVirtualNetworksOperations()

class MockStorageAccountsOperations:
    def begin_create(self, resource_group_name: str, account_name: str, parameters: Any, **kwargs):
        class MockLROPoller:
            def result(self):
                class MockStorage:
                    id = f"/subscriptions/mock-sub/resourceGroups/{resource_group_name}/providers/Microsoft.Storage/storageAccounts/{account_name}"
                    name = account_name
                return MockStorage()
        return MockLROPoller()

class MockStorageManagementClient:
    def __init__(self, subscription_id: str):
        self.storage_accounts = MockStorageAccountsOperations()

def get_mock_clients(subscription_id: str, resource_group: str) -> Dict[str, Any]:
    return {
        "resource": MockResourceManagementClient(subscription_id, resource_group),
        "containerservice": MockContainerServiceClient(subscription_id),
        "network": MockNetworkManagementClient(subscription_id),
        "storage": MockStorageManagementClient(subscription_id),
        "subscription_id": subscription_id,
        "resource_group": resource_group,
        "is_mock": True
    }

# ──────────────────────────────────────────────
# CREDENTIAL STORAGE
# ──────────────────────────────────────────────

def _get_kv_secret_name(user_id: uuid.UUID) -> str:
    return f"zo-byos-sp-{str(user_id)}".replace("_", "-").lower()

def store_credential_in_vault(user_id: uuid.UUID, client_secret: str) -> bool:
    """Store customer Service Principal client secret in vault and zero from memory."""
    secret_name = _get_kv_secret_name(user_id)
    success = False
    
    if vault.HAS_AZURE_KV:
        try:
            vault.kv_client.set_secret(secret_name, client_secret)
            success = True
        except Exception as e:
            logger.error(f"Failed to store SP secret in Azure Key Vault: {e}. Falling back to mock vault.")
            
    if not success:
        # Fallback to mock vault file
        try:
            mock_vault = vault.read_mock_vault()
            if "byos_credentials" not in mock_vault:
                mock_vault["byos_credentials"] = {}
            mock_vault["byos_credentials"][str(user_id)] = client_secret
            vault.write_mock_vault(mock_vault)
            success = True
        except Exception as e:
            logger.error(f"Failed to write mock vault: {e}")
            success = False
            
    # Zero/delete reference from memory
    del client_secret
    gc.collect()
    return success

def get_credential_secret(user_id: uuid.UUID) -> Optional[str]:
    """Retrieve SP client secret from Key Vault or mock fallback."""
    secret_name = _get_kv_secret_name(user_id)
    
    if vault.HAS_AZURE_KV:
        try:
            secret = vault.kv_client.get_secret(secret_name)
            return secret.value
        except Exception as e:
            logger.debug(f"Azure Key Vault get_secret failed: {e}. Checking mock vault.")
            
    # Try mock vault
    try:
        mock_vault = vault.read_mock_vault()
        return mock_vault.get("byos_credentials", {}).get(str(user_id))
    except Exception as e:
        logger.error(f"Failed to read from mock vault: {e}")
        return None

def delete_credential_from_vault(user_id: uuid.UUID) -> bool:
    """Remove SP client secret from Key Vault and mock vault."""
    secret_name = _get_kv_secret_name(user_id)
    success = False
    
    if vault.HAS_AZURE_KV:
        try:
            vault.kv_client.begin_delete_secret(secret_name)
            success = True
        except Exception as e:
            logger.debug(f"Azure Key Vault delete_secret failed: {e}")
            
    try:
        mock_vault = vault.read_mock_vault()
        if "byos_credentials" in mock_vault and str(user_id) in mock_vault["byos_credentials"]:
            del mock_vault["byos_credentials"][str(user_id)]
            vault.write_mock_vault(mock_vault)
            success = True
    except Exception as e:
        logger.error(f"Failed to delete from mock vault: {e}")
        
    return success

# ──────────────────────────────────────────────
# CREDENTIAL VALIDATION
# ──────────────────────────────────────────────

def validate_credential(tenant_id: str, client_id: str, client_secret: str, subscription_id: str, resource_group: str) -> dict:
    """Validate credentials with a read-only SDK call."""
    # Strict secret sanitization logic
    t_id = tenant_id.strip() if tenant_id else ""
    c_id = client_id.strip() if client_id else ""
    s_id = subscription_id.strip() if subscription_id else ""
    rg = resource_group.strip() if resource_group else ""
    sec = client_secret.strip() if client_secret else ""
    
    if not t_id or not c_id or not s_id or not rg or not sec:
        return {"success": False, "error": "All connection fields are required."}
        
    if t_id == "mock" or c_id == "mock" or sec == "mock":
        if rg == "fail":
            return {"success": False, "error": "Validation failed for mock resource group 'fail'."}
        return {"success": True, "detail": "Mock credential validation succeeded."}
        
    try:
        credential = ClientSecretCredential(tenant_id=t_id, client_id=c_id, client_secret=sec)
        resource_client = ResourceManagementClient(credential, s_id)
        # Execute basic read-only validation check on resource group
        rg_details = resource_client.resource_groups.get(rg)
        return {"success": True, "detail": f"Connected successfully. Resource Group: {rg_details.name}"}
    except Exception as e:
        logger.error(f"Credential validation failed: {e}")
        return {"success": False, "error": str(e)}

# ──────────────────────────────────────────────
# SDK CLIENT INITIALIZATION
# ──────────────────────────────────────────────

async def get_azure_clients_async(user_id: uuid.UUID, db) -> Optional[Dict[str, Any]]:
    """Retrieve active connection and initialize Azure SDK clients."""
    result = await db.execute(
        select(models.UserAzureConnection)
        .filter(models.UserAzureConnection.user_id == user_id, models.UserAzureConnection.connection_status == "connected")
    )
    conn = result.scalars().first()
    if not conn:
        logger.error(f"No connected Azure connection found for user {user_id}")
        return None
        
    client_secret = get_credential_secret(user_id)
    if not client_secret:
        logger.error(f"Could not retrieve client secret for user {user_id}")
        return None
        
    if conn.tenant_id == "mock" or conn.client_id == "mock" or client_secret == "mock":
        return get_mock_clients(conn.subscription_id, conn.resource_group)
        
    try:
        credential = ClientSecretCredential(
            tenant_id=conn.tenant_id,
            client_id=conn.client_id,
            client_secret=client_secret
        )
        
        resource_client = ResourceManagementClient(credential, conn.subscription_id)
        containerservice_client = ContainerServiceClient(credential, conn.subscription_id)
        network_client = NetworkManagementClient(credential, conn.subscription_id)
        storage_client = StorageManagementClient(credential, conn.subscription_id)
        
        return {
            "resource": resource_client,
            "containerservice": containerservice_client,
            "network": network_client,
            "storage": storage_client,
            "subscription_id": conn.subscription_id,
            "resource_group": conn.resource_group,
            "is_mock": False
        }
    except Exception as e:
        logger.error(f"Failed to initialize Azure SDK clients: {e}")
        return None

# ──────────────────────────────────────────────
# WRAPPER METHODS (All structured errors, no exceptions)
# ──────────────────────────────────────────────

async def create_aks_cluster(user_id: uuid.UUID, params: dict, db) -> dict:
    clients = await get_azure_clients_async(user_id, db)
    if not clients:
        return {"success": False, "error": "Could not initialize Azure clients."}
        
    rg = clients["resource_group"]
    cluster_name = params.get("cluster_name")
    location = params.get("location", "eastus")
    
    cluster_params = {
        "location": location,
        "dns_prefix": params.get("dns_prefix", f"{cluster_name}-dns"),
        "agent_pools": [
            {
                "name": params.get("node_pool_name", "nodepool1"),
                "count": params.get("node_count", 1),
                "vm_size": params.get("vm_size", "Standard_DS2_v2"),
                "mode": "System"
            }
        ]
    }
    
    try:
        cs = clients["containerservice"]
        poller = cs.managed_clusters.begin_create_or_update(rg, cluster_name, cluster_params)
        res = poller.result()
        return {
            "success": True,
            "id": res.id,
            "name": res.name,
            "provisioning_state": getattr(res, "provisioning_state", "Succeeded")
        }
    except Exception as e:
        logger.error(f"create_aks_cluster failed: {e}")
        return {"success": False, "error": str(e)}

async def update_aks_cluster(user_id: uuid.UUID, params: dict, db) -> dict:
    clients = await get_azure_clients_async(user_id, db)
    if not clients:
        return {"success": False, "error": "Could not initialize Azure clients."}
        
    rg = clients["resource_group"]
    cluster_name = params.get("cluster_name")
    location = params.get("location", "eastus")
    
    try:
        cs = clients["containerservice"]
        # In a real cluster update, we might update tags or settings
        # Fetch first, then merge
        existing = cs.managed_clusters.get(rg, cluster_name)
        existing.tags = params.get("tags", {})
        
        poller = cs.managed_clusters.begin_create_or_update(rg, cluster_name, existing)
        res = poller.result()
        return {
            "success": True,
            "id": res.id,
            "name": res.name,
            "provisioning_state": getattr(res, "provisioning_state", "Succeeded")
        }
    except Exception as e:
        logger.error(f"update_aks_cluster failed: {e}")
        return {"success": False, "error": str(e)}

async def scale_aks_nodepool(user_id: uuid.UUID, params: dict, db) -> dict:
    clients = await get_azure_clients_async(user_id, db)
    if not clients:
        return {"success": False, "error": "Could not initialize Azure clients."}
        
    rg = clients["resource_group"]
    cluster_name = params.get("cluster_name")
    pool_name = params.get("node_pool_name", "nodepool1")
    count = params.get("node_count", 1)
    
    try:
        cs = clients["containerservice"]
        # Scale nodepool parameters
        pool_params = {"count": count}
        poller = cs.agent_pools.begin_create_or_update(rg, cluster_name, pool_name, pool_params)
        res = poller.result()
        return {
            "success": True,
            "id": res.id,
            "name": res.name,
            "count": getattr(res, "count", count)
        }
    except Exception as e:
        logger.error(f"scale_aks_nodepool failed: {e}")
        return {"success": False, "error": str(e)}

async def get_aks_cluster(user_id: uuid.UUID, params: dict, db) -> dict:
    clients = await get_azure_clients_async(user_id, db)
    if not clients:
        return {"success": False, "error": "Could not initialize Azure clients."}
        
    rg = clients["resource_group"]
    cluster_name = params.get("cluster_name")
    
    try:
        cs = clients["containerservice"]
        res = cs.managed_clusters.get(rg, cluster_name)
        return {
            "success": True,
            "id": res.id,
            "name": res.name,
            "provisioning_state": getattr(res, "provisioning_state", "Succeeded")
        }
    except Exception as e:
        logger.error(f"get_aks_cluster failed: {e}")
        return {"success": False, "error": str(e)}

async def create_vnet(user_id: uuid.UUID, params: dict, db) -> dict:
    clients = await get_azure_clients_async(user_id, db)
    if not clients:
        return {"success": False, "error": "Could not initialize Azure clients."}
        
    rg = clients["resource_group"]
    vnet_name = params.get("vnet_name")
    location = params.get("location", "eastus")
    
    vnet_params = {
        "location": location,
        "address_space": {"address_prefixes": params.get("address_prefixes", ["10.0.0.0/16"])}
    }
    
    try:
        nw = clients["network"]
        poller = nw.virtual_networks.begin_create_or_update(rg, vnet_name, vnet_params)
        res = poller.result()
        return {
            "success": True,
            "id": res.id,
            "name": res.name
        }
    except Exception as e:
        logger.error(f"create_vnet failed: {e}")
        return {"success": False, "error": str(e)}

async def create_storage_account(user_id: uuid.UUID, params: dict, db) -> dict:
    clients = await get_azure_clients_async(user_id, db)
    if not clients:
        return {"success": False, "error": "Could not initialize Azure clients."}
        
    rg = clients["resource_group"]
    account_name = params.get("account_name")
    location = params.get("location", "eastus")
    
    storage_params = {
        "location": location,
        "sku": {"name": params.get("sku", "Standard_LRS")},
        "kind": "StorageV2"
    }
    
    try:
        st = clients["storage"]
        poller = st.storage_accounts.begin_create(rg, account_name, storage_params)
        res = poller.result()
        return {
            "success": True,
            "id": res.id,
            "name": res.name
        }
    except Exception as e:
        logger.error(f"create_storage_account failed: {e}")
        return {"success": False, "error": str(e)}

async def delete_resource(user_id: uuid.UUID, params: dict, db) -> dict:
    clients = await get_azure_clients_async(user_id, db)
    if not clients:
        return {"success": False, "error": "Could not initialize Azure clients."}
        
    resource_id = params.get("resource_id")
    if not resource_id:
        return {"success": False, "error": "resource_id is required."}
        
    try:
        rm = clients["resource"]
        poller = rm.resources.begin_delete_by_id(resource_id)
        poller.result()
        return {"success": True, "detail": f"Resource {resource_id} deleted successfully."}
    except Exception as e:
        logger.error(f"delete_resource failed: {e}")
        return {"success": False, "error": str(e)}

async def list_resources(user_id: uuid.UUID, params: dict, db) -> dict:
    clients = await get_azure_clients_async(user_id, db)
    if not clients:
        return {"success": False, "error": "Could not initialize Azure clients."}
        
    rg = clients["resource_group"]
    
    try:
        rm = clients["resource"]
        res_list = rm.resources.list_by_resource_group(rg)
        output = []
        for r in res_list:
            output.append({
                "id": r.id,
                "name": r.name,
                "type": r.type
            })
        return {"success": True, "resources": output}
    except Exception as e:
        logger.error(f"list_resources failed: {e}")
        return {"success": False, "error": str(e)}

async def inject_dependency_impl(user_id: uuid.UUID, params: dict, db) -> dict:
    """Commit code changes to package.json or requirements.txt on approved self-healing action."""
    project_id = params.get("project_id")
    package_name = params.get("package_name")
    
    if not project_id or not package_name:
        return {"success": False, "error": "project_id and package_name are required."}
        
    try:
        proj_uuid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        result = await db.execute(select(models.Project).filter(models.Project.id == proj_uuid))
        project = result.scalars().first()
        if not project:
            return {"success": False, "error": f"Project {project_id} not found."}
            
        from backend.services import git
        repo_path = git.get_repo_path(project.full_name)
        if not os.path.exists(repo_path):
            return {"success": False, "error": f"Local repository path {repo_path} does not exist."}
            
        package_json_path = os.path.join(repo_path, "package.json")
        req_txt_path = os.path.join(repo_path, "requirements.txt")
        
        fix_applied = False
        import json
        
        if os.path.exists(package_json_path):
            with open(package_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "dependencies" not in data:
                data["dependencies"] = {}
            data["dependencies"][package_name] = "latest"
            with open(package_json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            fix_applied = True
            
        elif os.path.exists(req_txt_path):
            with open(req_txt_path, "a", encoding="utf-8") as f:
                f.write(f"\n{package_name}\n")
            fix_applied = True
            
        if not fix_applied:
            return {"success": False, "error": "Neither package.json nor requirements.txt found in repository."}
            
        db.add(models.ActivityEvent(
            user_id=user_id,
            project_id=project.id,
            action="AI Auto-Fix: Dependency Injected",
            details=f"Injected package '{package_name}' into dependencies list."
        ))
        await db.commit()
        
        return {"success": True, "detail": f"Successfully injected dependency '{package_name}' into manifest."}
    except Exception as e:
        logger.error(f"inject_dependency_impl failed: {e}")
        return {"success": False, "error": str(e)}

