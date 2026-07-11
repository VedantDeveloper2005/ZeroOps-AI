"""Azure Key Vault access for ZeroOps secrets.

There is deliberately no filesystem fallback.  If Key Vault is unavailable the
operation fails, preventing a customer secret from being written to a local disk
or from a deployment being reported as successful with missing configuration.
"""

from __future__ import annotations

import os
import re

AZURE_KEYVAULT_URL = os.getenv("AZURE_KEYVAULT_URL", "").strip()
HAS_AZURE_KV = False
kv_client = None

if AZURE_KEYVAULT_URL:
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient

        kv_client = SecretClient(
            vault_url=AZURE_KEYVAULT_URL,
            credential=DefaultAzureCredential(exclude_interactive_browser_credential=True),
        )
        HAS_AZURE_KV = True
    except Exception:
        # Do not include connection details or secret material in startup logs.
        HAS_AZURE_KV = False


def _secret_name(project_id: str, key: str) -> str:
    value = re.sub(r"[^0-9a-z-]", "-", f"zo-{project_id}-{key}".lower())
    value = re.sub(r"-+", "-", value).strip("-")
    return value[:127].rstrip("-")


def _require_client():
    if not HAS_AZURE_KV or kv_client is None:
        raise RuntimeError("Azure Key Vault is not configured or unavailable.")
    return kv_client


def set_project_secret(project_id: str, key: str, value: str) -> bool:
    client = _require_client()
    client.set_secret(_secret_name(project_id, key), value)
    return True


def get_project_secret(project_id: str, key: str) -> str | None:
    client = _require_client()
    try:
        return client.get_secret(_secret_name(project_id, key)).value
    except Exception:
        return None


def get_project_secrets(project_id: str) -> dict[str, str]:
    """Return project secrets without ever persisting values outside Key Vault."""
    client = _require_client()
    prefix = _secret_name(project_id, "")
    secrets: dict[str, str] = {}
    for properties in client.list_properties_of_secrets():
        if not properties.name.startswith(prefix):
            continue
        try:
            value = client.get_secret(properties.name).value
        except Exception:
            continue
        key = properties.name[len(prefix):].lstrip("-").replace("-", "_").upper()
        if key:
            secrets[key] = value
    return secrets


def delete_project_secret(project_id: str, key: str) -> bool:
    client = _require_client()
    client.begin_delete_secret(_secret_name(project_id, key))
    return True
