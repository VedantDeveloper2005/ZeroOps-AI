"""Transactional Service Bus outbox for workflow commands."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import re
from typing import Any, Protocol
import uuid

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

try:
    from backend import config, models
    from backend.contracts.workflow import canonical_digest, canonical_json_bytes
except ImportError:  # pragma: no cover - backend-directory execution
    import config, models
    from contracts.workflow import canonical_digest, canonical_json_bytes


QUEUE_NAMES = frozenset({"repo-analysis", "terraform-generation", "terraform-apply"})
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TOKEN_EXCHANGE_SCOPE = "api://AzureADTokenExchange/.default"


class WorkflowPublisher(Protocol):
    async def send(
        self,
        *,
        queue_name: str,
        body: bytes,
        message_id: str,
        correlation_id: str,
        session_id: str | None,
    ) -> None: ...


class ManagedIdentityServiceBusPublisher:
    """Publish with Entra authentication; connection strings are unsupported."""

    def __init__(
        self,
        *,
        fully_qualified_namespace: str,
        managed_identity_client_id: str | None = None,
        target_tenant_id: str | None = None,
        multitenant_app_client_id: str | None = None,
    ) -> None:
        namespace = fully_qualified_namespace.strip().lower()
        if (
            not namespace
            or "/" in namespace
            or ":" in namespace
            or not namespace.endswith(".servicebus.windows.net")
        ):
            raise ValueError("Service Bus namespace must be a fully qualified Azure hostname.")
        self.namespace = namespace
        self.managed_identity_client_id = (managed_identity_client_id or "").strip() or None
        self.target_tenant_id = (target_tenant_id or "").strip() or None
        self.multitenant_app_client_id = (multitenant_app_client_id or "").strip() or None
        if bool(self.target_tenant_id) != bool(self.multitenant_app_client_id):
            raise ValueError(
                "Cross-tenant Service Bus publishing requires both a target tenant "
                "and multitenant application client ID."
            )

    async def send(
        self,
        *,
        queue_name: str,
        body: bytes,
        message_id: str,
        correlation_id: str,
        session_id: str | None,
    ) -> None:
        from azure.identity.aio import (
            ClientAssertionCredential,
            DefaultAzureCredential,
            ManagedIdentityCredential,
        )
        from azure.servicebus import ServiceBusMessage
        from azure.servicebus.aio import ServiceBusClient

        credential = None
        assertion_credential = None
        try:
            if self.target_tenant_id:
                if not self.multitenant_app_client_id:
                    raise RuntimeError(
                        "Cross-tenant Service Bus publishing requires a multitenant application client ID."
                    )
                # The async ClientAssertionCredential accepts a synchronous
                # assertion callback. The source managed identity is therefore
                # intentionally the synchronous Azure Identity credential; the
                # Service Bus client and target-tenant credential remain async.
                from azure.identity import (
                    ManagedIdentityCredential as AssertionManagedIdentityCredential,
                )

                assertion_credential = AssertionManagedIdentityCredential(
                    client_id=self.managed_identity_client_id,
                )
                credential = ClientAssertionCredential(
                    tenant_id=self.target_tenant_id,
                    client_id=self.multitenant_app_client_id,
                    func=lambda: assertion_credential.get_token(_TOKEN_EXCHANGE_SCOPE).token,
                )
            elif self.managed_identity_client_id:
                credential = ManagedIdentityCredential(client_id=self.managed_identity_client_id)
            else:
                credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
            async with ServiceBusClient(
                fully_qualified_namespace=self.namespace,
                credential=credential,
                logging_enable=False,
            ) as client:
                async with client.get_queue_sender(queue_name=queue_name) as sender:
                    message = ServiceBusMessage(
                        body,
                        content_type="application/json",
                        message_id=message_id,
                        correlation_id=correlation_id,
                        session_id=session_id,
                    )
                    await sender.send_messages(message)
        finally:
            if credential is not None:
                await credential.close()
            if assertion_credential is not None:
                assertion_credential.close()


def _validate_identifier(value: str, *, field: str) -> str:
    normalized = str(value or "").strip()
    if not _IDENTIFIER.fullmatch(normalized):
        raise ValueError(f"{field} is invalid.")
    return normalized


async def enqueue(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    operation_run_id: uuid.UUID,
    queue_name: str,
    payload: dict[str, Any],
    message_id: str,
    correlation_id: str,
    session_id: str | None = None,
) -> models.WorkflowOutboxMessage:
    """Add one immutable command in the caller's database transaction."""

    if queue_name not in QUEUE_NAMES:
        raise ValueError("Workflow queue is not approved.")
    normalized_message_id = _validate_identifier(message_id, field="message_id")
    normalized_correlation_id = _validate_identifier(correlation_id, field="correlation_id")
    normalized_session_id = (
        _validate_identifier(session_id, field="session_id") if session_id is not None else None
    )
    if queue_name == "terraform-apply" and normalized_session_id is None:
        raise ValueError("Terraform apply messages require a workflow session.")
    if queue_name != "terraform-apply" and normalized_session_id is not None:
        raise ValueError("Only the Terraform apply queue accepts a backend session ID.")

    digest = canonical_digest(payload)
    existing_result = await db.execute(
        select(models.WorkflowOutboxMessage).where(
            models.WorkflowOutboxMessage.tenant_id == tenant_id,
            models.WorkflowOutboxMessage.operation_run_id == operation_run_id,
            models.WorkflowOutboxMessage.queue_name == queue_name,
        )
    )
    existing = existing_result.scalars().first()
    if existing is not None:
        if (
            existing.message_id != normalized_message_id
            or existing.correlation_id != normalized_correlation_id
            or existing.session_id != normalized_session_id
            or existing.payload_digest != digest
            or existing.payload != payload
        ):
            raise ValueError("Workflow command idempotency key is bound to different content.")
        return existing

    message = models.WorkflowOutboxMessage(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        operation_run_id=operation_run_id,
        queue_name=queue_name,
        message_id=normalized_message_id,
        correlation_id=normalized_correlation_id,
        session_id=normalized_session_id,
        payload=payload,
        payload_digest=digest,
        status="pending",
        attempt_count=0,
        next_attempt_at=datetime.now(timezone.utc),
    )
    db.add(message)
    await db.flush()
    return message


def publisher_from_config() -> ManagedIdentityServiceBusPublisher:
    if config.IS_PRODUCTION and not config.SERVICEBUS_MANAGED_IDENTITY_CLIENT_ID:
        raise RuntimeError("Production workflow publishing requires an explicit managed identity.")
    return ManagedIdentityServiceBusPublisher(
        fully_qualified_namespace=config.SERVICEBUS_FULLY_QUALIFIED_NAMESPACE,
        managed_identity_client_id=config.SERVICEBUS_MANAGED_IDENTITY_CLIENT_ID or None,
        target_tenant_id=config.SERVICEBUS_TARGET_TENANT_ID or None,
        multitenant_app_client_id=config.SERVICEBUS_MULTITENANT_APP_CLIENT_ID or None,
    )


async def dispatch_pending(
    db: AsyncSession,
    *,
    publisher: WorkflowPublisher,
    batch_size: int | None = None,
    now: datetime | None = None,
) -> int:
    """Publish a bounded batch and retain failed rows for durable retry.

    Rows remain transaction-locked until their send result is recorded.  A
    crash after Service Bus accepts a message can cause a duplicate delivery;
    stable message IDs and namespace duplicate detection make that replay safe.
    """

    checked_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    result = await db.execute(
        select(models.WorkflowOutboxMessage)
        .where(
            models.WorkflowOutboxMessage.status == "pending",
            or_(
                models.WorkflowOutboxMessage.next_attempt_at.is_(None),
                models.WorkflowOutboxMessage.next_attempt_at <= checked_at,
            ),
        )
        .order_by(models.WorkflowOutboxMessage.created_at, models.WorkflowOutboxMessage.id)
        .limit(batch_size or config.WORKFLOW_OUTBOX_BATCH_SIZE)
        .with_for_update(skip_locked=True)
    )
    rows = list(result.scalars().all())
    sent = 0
    for row in rows:
        try:
            await publisher.send(
                queue_name=row.queue_name,
                body=canonical_json_bytes(row.payload),
                message_id=row.message_id,
                correlation_id=row.correlation_id,
                session_id=row.session_id,
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            row.attempt_count += 1
            delay_seconds = min(300, 2 ** min(row.attempt_count, 8))
            row.next_attempt_at = checked_at + timedelta(seconds=delay_seconds)
            row.last_error_code = type(error).__name__[:96]
            continue
        row.status = "sent"
        row.attempt_count += 1
        row.sent_at = checked_at
        row.next_attempt_at = checked_at
        row.last_error_code = None
        sent += 1
    if rows:
        await db.commit()
    return sent


__all__ = [
    "ManagedIdentityServiceBusPublisher",
    "WorkflowPublisher",
    "dispatch_pending",
    "enqueue",
    "publisher_from_config",
]
