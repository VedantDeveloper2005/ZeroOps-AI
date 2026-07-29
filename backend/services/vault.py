"""Azure Key Vault access for ZeroOps configuration and customer secrets.

The vault URL is the sole secret-store bootstrap setting. Values are read
directly through a managed identity (or another ``DefaultAzureCredential``
source); production never falls back to a local file or process environment.
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
from typing import Final


AZURE_KEYVAULT_URL = os.environ.get("AZURE_KEYVAULT_URL", "").strip().rstrip("/")
HAS_AZURE_KV = False
kv_client = None
_application_settings: dict[str, str] = {}
_settings_lock = threading.Lock()

# Preserve the names already documented for existing production vaults while
# using the standard convention for every other application setting.
_LEGACY_SETTING_NAMES: Final[dict[str, tuple[str, ...]]] = {
    "OPENAI_API_KEY": ("zeroops-ai-api-key", "zeroops-openai-api-key"),
    "GITHUB_TOKEN": ("zeroops-github-server-token", "zeroops-github-token"),
}


class KeyVaultConfigurationError(RuntimeError):
    """Raised when a required application setting cannot be retrieved."""


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
        # Never log credential, token, or connection details during import.
        HAS_AZURE_KV = False


def _application_secret_names(name: str) -> tuple[str, ...]:
    normalized = re.sub(r"[^a-z0-9-]", "-", name.lower().replace("_", "-"))
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    if not normalized:
        raise ValueError("Azure Key Vault setting names cannot be empty.")
    return _LEGACY_SETTING_NAMES.get(name.upper(), (f"zeroops-{normalized}",))


def _is_not_found(error: Exception) -> bool:
    return getattr(error, "status_code", None) == 404 or error.__class__.__name__ == "ResourceNotFoundError"


def get_application_setting(name: str, *, default: str = "", required: bool = False) -> str:
    """Read and cache one control-plane setting from Azure Key Vault.

    ``required`` makes startup fail closed when the value or vault access is
    unavailable. Local development may use documented defaults only when no
    vault is configured; it never reads application values from ``.env``.
    """
    setting_name = name.upper()
    with _settings_lock:
        if setting_name in _application_settings:
            return _application_settings[setting_name]

    if not HAS_AZURE_KV or kv_client is None:
        if required:
            raise KeyVaultConfigurationError(
                f"Azure Key Vault is required to load {setting_name}, but no vault client is available."
            )
        return default

    for secret_name in _application_secret_names(setting_name):
        try:
            value = kv_client.get_secret(secret_name).value
        except Exception as error:
            if _is_not_found(error):
                continue
            raise KeyVaultConfigurationError(
                f"Azure Key Vault could not load {setting_name}."
            ) from error
        if value is not None:
            with _settings_lock:
                _application_settings[setting_name] = value
            return value

    if required:
        raise KeyVaultConfigurationError(
            f"Azure Key Vault does not contain the required setting {setting_name}."
        )
    return default


def clear_application_setting_cache() -> None:
    """Clear the in-process cache; intended for test isolation only."""
    with _settings_lock:
        _application_settings.clear()


def _secret_name(project_id: str, key: str) -> str:
    project_value = str(project_id).lower()
    if not re.fullmatch(r"[0-9a-f-]{36}", project_value):
        raise ValueError("Project secret names require a canonical project UUID.")
    if key and not re.fullmatch(r"[A-Z][A-Z0-9_]{0,254}", key):
        raise ValueError("Environment variable keys must use uppercase letters, digits, and underscores.")

    prefix = f"zo-{project_value}-"
    normalized_key = key.lower().replace("_", "-")
    value = f"{prefix}{normalized_key}".rstrip("-")
    if len(value) <= 127:
        return value

    # Preserve readable names while preventing the truncation collisions that
    # would otherwise make two long environment keys overwrite one another.
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    readable_length = 127 - len(prefix) - len(digest) - 1
    readable_key = normalized_key[:readable_length].rstrip("-")
    return f"{prefix}{readable_key}-{digest}"


def _require_client():
    if not HAS_AZURE_KV or kv_client is None:
        raise RuntimeError("Azure Key Vault is not configured or unavailable.")
    return kv_client


def set_project_secret(project_id: str, key: str, value: str) -> bool:
    client = _require_client()
    secret_name = _secret_name(project_id, key)
    try:
        client.set_secret(secret_name, value)
    except Exception as error:
        # Key Vault soft-delete reserves a name. Recovering it before writing a
        # new version lets a user intentionally recreate a deleted variable.
        is_conflict = (
            getattr(error, "status_code", None) == 409
            or error.__class__.__name__ == "ResourceExistsError"
        )
        if not is_conflict:
            raise
        client.begin_recover_deleted_secret(secret_name).result()
        client.set_secret(secret_name, value)
    return True


def get_project_secret(project_id: str, key: str) -> str | None:
    try:
        return _require_client().get_secret(_secret_name(project_id, key)).value
    except Exception:
        return None


def get_project_secrets(project_id: str) -> dict[str, str]:
    """Return project secrets without persisting values outside Key Vault."""
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
    _require_client().begin_delete_secret(_secret_name(project_id, key)).result()
    return True
