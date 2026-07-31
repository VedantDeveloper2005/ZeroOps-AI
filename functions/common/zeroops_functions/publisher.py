"""Managed-identity Service Bus publishing for workflow transitions."""

from __future__ import annotations

from typing import Any

from azure.servicebus import ServiceBusClient, ServiceBusMessage

from .contracts import WorkflowEventV1
from .security import canonical_json_bytes


class ServiceBusPublisher:
    def __init__(self, fully_qualified_namespace: str, credential: Any):
        namespace = fully_qualified_namespace.strip()
        if not namespace.endswith(".servicebus.windows.net"):
            raise ValueError("Service Bus namespace is invalid")
        self._client = ServiceBusClient(
            fully_qualified_namespace=namespace,
            credential=credential,
        )

    def send_json(
        self,
        queue_name: str,
        value: dict[str, Any],
        *,
        message_id: str,
        correlation_id: str,
        subject: str,
        session_id: str | None = None,
    ) -> None:
        body = canonical_json_bytes(value)
        message = ServiceBusMessage(
            body,
            content_type="application/json",
            message_id=message_id,
            correlation_id=correlation_id,
            subject=subject,
            session_id=session_id,
        )
        with self._client.get_queue_sender(queue_name=queue_name) as sender:
            sender.send_messages(message)

    def send_event(self, queue_name: str, event: WorkflowEventV1) -> None:
        self.send_json(
            queue_name,
            event.model_dump(mode="json"),
            message_id=event.event_id,
            correlation_id=event.correlation_id,
            subject=event.event_type,
            session_id=str(event.run_id),
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ServiceBusPublisher":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
