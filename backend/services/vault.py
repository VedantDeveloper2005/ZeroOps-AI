import os
import json

# Local mock storage path for fallback (stored statefully in workspace directory)
<<<<<<< HEAD
try:
    from backend.config import WORKSPACE_DIR
except ImportError:
    from config import WORKSPACE_DIR
=======
from backend.config import WORKSPACE_DIR
>>>>>>> 7a8a49ab91a776be547d07446a274f5d8f0822b2
VAULT_MOCK_FILE = os.path.join(WORKSPACE_DIR, "vault_secrets.json")

# Ensure initial file exists
if not os.path.exists(VAULT_MOCK_FILE):
    with open(VAULT_MOCK_FILE, "w") as f:
        json.dump({}, f)

def read_mock_vault() -> dict:
    try:
        with open(VAULT_MOCK_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def write_mock_vault(data: dict):
    try:
        with open(VAULT_MOCK_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Failed to write to mock vault: {e}")

# Try to import Azure SDK, fall back to mock if not installed or vault URL is empty
AZURE_KEYVAULT_URL = os.getenv("AZURE_KEYVAULT_URL", "")

HAS_AZURE_KV = False
if AZURE_KEYVAULT_URL:
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
        
        credential = DefaultAzureCredential()
        kv_client = SecretClient(vault_url=AZURE_KEYVAULT_URL, credential=credential)
        HAS_AZURE_KV = True
        print(f"Azure Key Vault client successfully initialized at: {AZURE_KEYVAULT_URL}")
    except Exception as e:
        print(f"Azure Key Vault initialization failed: {e}. Falling back to mock vault.")

def set_project_secret(project_id: str, key: str, value: str) -> bool:
    """Store a secret for a project."""
    # Enforce safe DNS-like names for AKV secret names (only alphanumeric and dashes are allowed)
    # Format the secret name as: zo-{project_id}-{key}
    akv_secret_name = f"zo-{project_id}-{key}".replace("_", "-").replace(" ", "-").lower()
    
    if HAS_AZURE_KV:
        try:
            kv_client.set_secret(akv_secret_name, value)
            return True
        except Exception as e:
            print(f"Azure Key Vault set_secret failed: {e}. Saving to mock vault instead.")
            
    # Save to mock vault
    vault = read_mock_vault()
    if project_id not in vault:
        vault[project_id] = {}
    vault[project_id][key] = value
    write_mock_vault(vault)
    return True

def get_project_secrets(project_id: str) -> dict:
    """Retrieve all secrets for a project (key-value pairs)."""
    secrets = {}
    
    # Read from mock vault
    vault = read_mock_vault()
    if project_id in vault:
        secrets.update(vault[project_id])
        
    # Read from Azure Key Vault if available (overwriting mock values if keys overlap)
    if HAS_AZURE_KV:
        try:
            prefix = f"zo-{project_id}-".replace("_", "-").replace(" ", "-").lower()
            secret_properties = kv_client.list_properties_of_secrets()
            for secret_property in secret_properties:
                if secret_property.name.startswith(prefix):
                    key_part = secret_property.name[len(prefix):].replace("-", "_").upper()
                    try:
                        secret = kv_client.get_secret(secret_property.name)
                        secrets[key_part] = secret.value
                    except Exception as err:
                        print(f"Failed to fetch secret value for {secret_property.name}: {err}")
        except Exception as e:
            print(f"Azure Key Vault list/get secrets failed: {e}")
            
    return secrets

def delete_project_secret(project_id: str, key: str) -> bool:
    """Delete a secret for a project."""
    akv_secret_name = f"zo-{project_id}-{key}".replace("_", "-").replace(" ", "-").lower()
    success = False
    
    if HAS_AZURE_KV:
        try:
            kv_client.begin_delete_secret(akv_secret_name)
            success = True
        except Exception as e:
            print(f"Azure Key Vault delete_secret failed: {e}")
            
    # Delete from mock vault
    vault = read_mock_vault()
    if project_id in vault and key in vault[project_id]:
        del vault[project_id][key]
        write_mock_vault(vault)
        success = True
        
    return success
