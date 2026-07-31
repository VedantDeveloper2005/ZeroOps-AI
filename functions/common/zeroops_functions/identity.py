"""Deterministic Azure credentials for local and hosted workers."""

from __future__ import annotations

import os

from azure.identity import DefaultAzureCredential, ManagedIdentityCredential


def workload_credential():
    """Return a credential without enabling interactive authentication.

    Hosted production Functions use their configured user-assigned identity
    directly. Local development can use Azure CLI/developer credentials through
    DefaultAzureCredential.
    """

    app_env = os.getenv("APP_ENV", "development").strip().lower()
    client_id = os.getenv("AZURE_CLIENT_ID", "").strip() or None
    if app_env == "production":
        if not client_id:
            raise RuntimeError("AZURE_CLIENT_ID is required in production")
        return ManagedIdentityCredential(client_id=client_id)
    return DefaultAzureCredential(
        managed_identity_client_id=client_id,
        exclude_interactive_browser_credential=True,
    )
