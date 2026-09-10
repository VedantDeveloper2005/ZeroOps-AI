from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend import config
from backend.services import workflow_outbox


def test_production_rejects_partial_cross_tenant_servicebus_configuration():
    for target_tenant_id, multitenant_app_client_id in (
        ("target-tenant", ""),
        ("", "multitenant-app"),
    ):
        with pytest.raises(RuntimeError, match="must be configured together"):
            config._validate_cross_tenant_servicebus_settings(
                is_production=True,
                target_tenant_id=target_tenant_id,
                multitenant_app_client_id=multitenant_app_client_id,
            )

    config._validate_cross_tenant_servicebus_settings(
        is_production=False,
        target_tenant_id="target-tenant",
        multitenant_app_client_id="",
    )


def test_publisher_rejects_partial_cross_tenant_configuration():
    with pytest.raises(ValueError, match="requires both"):
        workflow_outbox.ManagedIdentityServiceBusPublisher(
            fully_qualified_namespace="zeroops.servicebus.windows.net",
            target_tenant_id="target-tenant",
        )


def test_publisher_from_config_keeps_same_tenant_configuration(monkeypatch):
    monkeypatch.setattr(config, "IS_PRODUCTION", True)
    monkeypatch.setattr(config, "SERVICEBUS_FULLY_QUALIFIED_NAMESPACE", "zeroops.servicebus.windows.net")
    monkeypatch.setattr(config, "SERVICEBUS_MANAGED_IDENTITY_CLIENT_ID", "source-managed-identity")
    monkeypatch.setattr(config, "SERVICEBUS_TARGET_TENANT_ID", "")
    monkeypatch.setattr(config, "SERVICEBUS_MULTITENANT_APP_CLIENT_ID", "")

    publisher = workflow_outbox.publisher_from_config()

    assert publisher.namespace == "zeroops.servicebus.windows.net"
    assert publisher.managed_identity_client_id == "source-managed-identity"
    assert publisher.target_tenant_id is None
    assert publisher.multitenant_app_client_id is None


def test_publisher_from_config_selects_cross_tenant_configuration(monkeypatch):
    monkeypatch.setattr(config, "IS_PRODUCTION", True)
    monkeypatch.setattr(config, "SERVICEBUS_FULLY_QUALIFIED_NAMESPACE", "zeroops.servicebus.windows.net")
    monkeypatch.setattr(config, "SERVICEBUS_MANAGED_IDENTITY_CLIENT_ID", "source-managed-identity")
    monkeypatch.setattr(config, "SERVICEBUS_TARGET_TENANT_ID", "target-tenant")
    monkeypatch.setattr(config, "SERVICEBUS_MULTITENANT_APP_CLIENT_ID", "multitenant-app")

    publisher = workflow_outbox.publisher_from_config()

    assert publisher.managed_identity_client_id == "source-managed-identity"
    assert publisher.target_tenant_id == "target-tenant"
    assert publisher.multitenant_app_client_id == "multitenant-app"


def _patch_servicebus_sdk(monkeypatch, *, sender_error: Exception | None = None):
    import azure.identity
    import azure.identity.aio
    import azure.servicebus
    import azure.servicebus.aio

    state = SimpleNamespace(
        assertion_sources=[],
        assertion_credentials=[],
        managed_identity_credentials=[],
        messages=[],
        clients=[],
    )

    class AssertionSourceManagedIdentityCredential:
        def __init__(self, *, client_id=None):
            self.client_id = client_id
            self.scopes = []
            self.closed = False
            state.assertion_sources.append(self)

        def get_token(self, *scopes):
            self.scopes.append(scopes)
            return SimpleNamespace(token="managed-identity-assertion")

        def close(self):
            self.closed = True

    class ClientAssertionCredential:
        def __init__(self, *, tenant_id, client_id, func):
            self.tenant_id = tenant_id
            self.client_id = client_id
            self.assertion = func()
            self.closed = False
            state.assertion_credentials.append(self)

        async def close(self):
            self.closed = True

    class AsyncManagedIdentityCredential:
        def __init__(self, *, client_id=None):
            self.client_id = client_id
            self.closed = False
            state.managed_identity_credentials.append(self)

        async def close(self):
            self.closed = True

    class DefaultAzureCredential:
        def __init__(self, **_kwargs):
            raise AssertionError("same-tenant managed identity should be selected")

    class ServiceBusMessage:
        def __init__(self, body, **kwargs):
            self.body = body
            self.kwargs = kwargs

    class Sender:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def send_messages(self, message):
            if sender_error is not None:
                raise sender_error
            state.messages.append(message)

    class ServiceBusClient:
        def __init__(self, *, fully_qualified_namespace, credential, logging_enable):
            self.namespace = fully_qualified_namespace
            self.credential = credential
            self.logging_enable = logging_enable
            self.queue_name = None
            state.clients.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def get_queue_sender(self, *, queue_name):
            self.queue_name = queue_name
            return Sender()

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
    monkeypatch.setattr(azure.servicebus, "ServiceBusMessage", ServiceBusMessage)
    monkeypatch.setattr(azure.servicebus.aio, "ServiceBusClient", ServiceBusClient)
    return state


@pytest.mark.asyncio
async def test_cross_tenant_publisher_uses_managed_identity_assertion(monkeypatch):
    state = _patch_servicebus_sdk(monkeypatch)
    publisher = workflow_outbox.ManagedIdentityServiceBusPublisher(
        fully_qualified_namespace="zeroops.servicebus.windows.net",
        managed_identity_client_id="source-managed-identity",
        target_tenant_id="target-tenant",
        multitenant_app_client_id="multitenant-app",
    )

    await publisher.send(
        queue_name="terraform-apply",
        body=b'{"job":"approved"}',
        message_id="message-1",
        correlation_id="run-1",
        session_id="session-1",
    )

    source = state.assertion_sources[0]
    target = state.assertion_credentials[0]
    assert source.client_id == "source-managed-identity"
    assert source.scopes == [("api://AzureADTokenExchange/.default",)]
    assert source.closed is True
    assert target.tenant_id == "target-tenant"
    assert target.client_id == "multitenant-app"
    assert target.assertion == "managed-identity-assertion"
    assert target.closed is True
    assert state.clients[0].namespace == "zeroops.servicebus.windows.net"
    assert state.clients[0].queue_name == "terraform-apply"
    assert state.messages[0].body == b'{"job":"approved"}'
    assert state.messages[0].kwargs == {
        "content_type": "application/json",
        "message_id": "message-1",
        "correlation_id": "run-1",
        "session_id": "session-1",
    }


@pytest.mark.asyncio
async def test_cross_tenant_publisher_closes_both_credentials_after_send_error(monkeypatch):
    state = _patch_servicebus_sdk(monkeypatch, sender_error=RuntimeError("send failed"))
    publisher = workflow_outbox.ManagedIdentityServiceBusPublisher(
        fully_qualified_namespace="zeroops.servicebus.windows.net",
        managed_identity_client_id="source-managed-identity",
        target_tenant_id="target-tenant",
        multitenant_app_client_id="multitenant-app",
    )

    with pytest.raises(RuntimeError, match="send failed"):
        await publisher.send(
            queue_name="terraform-apply",
            body=b"{}",
            message_id="message-1",
            correlation_id="run-1",
            session_id="session-1",
        )

    assert state.assertion_sources[0].closed is True
    assert state.assertion_credentials[0].closed is True


@pytest.mark.asyncio
async def test_same_tenant_publisher_uses_existing_async_managed_identity(monkeypatch):
    state = _patch_servicebus_sdk(monkeypatch)
    publisher = workflow_outbox.ManagedIdentityServiceBusPublisher(
        fully_qualified_namespace="zeroops.servicebus.windows.net",
        managed_identity_client_id="same-tenant-managed-identity",
    )

    await publisher.send(
        queue_name="repo-analysis",
        body=b"{}",
        message_id="message-1",
        correlation_id="run-1",
        session_id=None,
    )

    assert not state.assertion_sources
    assert not state.assertion_credentials
    assert state.managed_identity_credentials[0].client_id == "same-tenant-managed-identity"
    assert state.managed_identity_credentials[0].closed is True
