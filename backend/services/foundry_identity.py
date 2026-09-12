"""Acquire Foundry tokens in the resource tenant without storing client secrets."""

from backend import config


def foundry_credential():
    from azure.identity import ClientAssertionCredential, DefaultAzureCredential, ManagedIdentityCredential

    if config.FOUNDRY_TARGET_TENANT_ID:
        identity = ManagedIdentityCredential(client_id=config.FOUNDRY_MANAGED_IDENTITY_CLIENT_ID)
        return ClientAssertionCredential(
            tenant_id=config.FOUNDRY_TARGET_TENANT_ID,
            client_id=config.FOUNDRY_MULTITENANT_APP_CLIENT_ID,
            func=lambda: identity.get_token("api://AzureADTokenExchange/.default").token,
        )
    return DefaultAzureCredential(exclude_interactive_browser_credential=True)
