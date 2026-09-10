from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend import config
from backend.services import artifacts


_ACCOUNT_URL = "https://artifacts.blob.core.windows.net"
_NAMESPACE_KEY = "zeroops-artifact-test-namespace-key-32"


def _patch_blob_sdk(monkeypatch):
    import azure.identity
    import azure.identity.aio
    import azure.storage.blob.aio

    state = SimpleNamespace(
        assertion_sources=[],
        assertion_credentials=[],
        managed_identity_credentials=[],
        clients=[],
    )

    class AssertionSourceManagedIdentityCredential:
        def __init__(self, *, client_id=None):
            self.client_id = client_id
            self.scopes = []
            state.assertion_sources.append(self)

        def get_token(self, *scopes):
            self.scopes.append(scopes)
            return SimpleNamespace(token="managed-identity-assertion")

    class ClientAssertionCredential:
        def __init__(self, *, tenant_id, client_id, func):
            self.tenant_id = tenant_id
            self.client_id = client_id
            self.assertion = func()
            state.assertion_credentials.append(self)

    class AsyncManagedIdentityCredential:
        def __init__(self, *, client_id=None):
            self.client_id = client_id
            state.managed_identity_credentials.append(self)

    class DefaultAzureCredential:
        def __init__(self, **_kwargs):
            raise AssertionError("an explicit artifact managed identity should be selected")

    class BlobServiceClient:
        def __init__(self, *, account_url, credential):
            self.account_url = account_url
            self.credential = credential
            state.clients.append(self)

    monkeypatch.setattr(
        azure.identity,
        "ManagedIdentityCredential",
        AssertionSourceManagedIdentityCredential,
    )
    monkeypatch.setattr(
        azure.identity.aio,
        "ClientAssertionCredential",
        ClientAssertionCredential,
    )
    monkeypatch.setattr(
        azure.identity.aio,
        "ManagedIdentityCredential",
        AsyncManagedIdentityCredential,
    )
    monkeypatch.setattr(azure.identity.aio, "DefaultAzureCredential", DefaultAzureCredential)
    monkeypatch.setattr(azure.storage.blob.aio, "BlobServiceClient", BlobServiceClient)
    return state


def test_blob_artifact_store_rejects_incomplete_or_implicit_cross_tenant_identity():
    with pytest.raises(ValueError, match="requires both"):
        artifacts.AzureBlobArtifactStore(
            account_url=_ACCOUNT_URL,
            namespace_key=_NAMESPACE_KEY,
            max_download_bytes=1024,
            managed_identity_client_id="artifact-source-identity",
            target_tenant_id="target-tenant",
        )

    with pytest.raises(ValueError, match="explicit user-assigned managed identity"):
        artifacts.AzureBlobArtifactStore(
            account_url=_ACCOUNT_URL,
            namespace_key=_NAMESPACE_KEY,
            max_download_bytes=1024,
            target_tenant_id="target-tenant",
            multitenant_app_client_id="target-app",
        )


def test_get_artifact_store_uses_shared_cross_tenant_federation_for_blob(monkeypatch):
    state = _patch_blob_sdk(monkeypatch)
    artifacts.get_artifact_store.cache_clear()
    monkeypatch.setattr(config, "ARTIFACT_STORAGE_ACCOUNT_URL", _ACCOUNT_URL)
    monkeypatch.setattr(config, "ARTIFACT_STORAGE_NAMESPACE_KEY", _NAMESPACE_KEY)
    monkeypatch.setattr(config, "ARTIFACT_STORAGE_MANAGED_IDENTITY_CLIENT_ID", "artifact-source-identity")
    monkeypatch.setattr(config, "ARTIFACT_STORAGE_MAX_DOWNLOAD_MB", 1)
    monkeypatch.setattr(config, "SERVICEBUS_TARGET_TENANT_ID", "target-tenant")
    monkeypatch.setattr(config, "SERVICEBUS_MULTITENANT_APP_CLIENT_ID", "target-app")

    try:
        store = artifacts.get_artifact_store()
    finally:
        artifacts.get_artifact_store.cache_clear()

    assert store.target_tenant_id == "target-tenant"
    assert store.multitenant_app_client_id == "target-app"
    assert state.assertion_sources[0].client_id == "artifact-source-identity"
    assert state.assertion_sources[0].scopes == [("api://AzureADTokenExchange/.default",)]
    assert state.assertion_credentials[0].tenant_id == "target-tenant"
    assert state.assertion_credentials[0].client_id == "target-app"
    assert state.assertion_credentials[0].assertion == "managed-identity-assertion"
    assert state.clients[0].account_url == _ACCOUNT_URL
    assert state.clients[0].credential is state.assertion_credentials[0]


def test_get_artifact_store_preserves_same_tenant_managed_identity(monkeypatch):
    state = _patch_blob_sdk(monkeypatch)
    artifacts.get_artifact_store.cache_clear()
    monkeypatch.setattr(config, "ARTIFACT_STORAGE_ACCOUNT_URL", _ACCOUNT_URL)
    monkeypatch.setattr(config, "ARTIFACT_STORAGE_NAMESPACE_KEY", _NAMESPACE_KEY)
    monkeypatch.setattr(config, "ARTIFACT_STORAGE_MANAGED_IDENTITY_CLIENT_ID", "artifact-source-identity")
    monkeypatch.setattr(config, "ARTIFACT_STORAGE_MAX_DOWNLOAD_MB", 1)
    monkeypatch.setattr(config, "SERVICEBUS_TARGET_TENANT_ID", "")
    monkeypatch.setattr(config, "SERVICEBUS_MULTITENANT_APP_CLIENT_ID", "")

    try:
        store = artifacts.get_artifact_store()
    finally:
        artifacts.get_artifact_store.cache_clear()

    assert store.target_tenant_id is None
    assert store.multitenant_app_client_id is None
    assert not state.assertion_sources
    assert not state.assertion_credentials
    assert state.managed_identity_credentials[0].client_id == "artifact-source-identity"
    assert state.clients[0].credential is state.managed_identity_credentials[0]
