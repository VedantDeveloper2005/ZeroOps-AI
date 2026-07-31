"""Scale-to-zero Service Bus worker for Terraform plan/apply jobs."""

from __future__ import annotations

import os
import signal
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from azure.identity import ManagedIdentityCredential
from azure.servicebus import (
    AutoLockRenewer,
    NEXT_AVAILABLE_SESSION,
    ServiceBusClient,
    ServiceBusReceiveMode,
)
from azure.servicebus.exceptions import ServiceBusError

from worker.azure_adapters import (
    AzureBlobArtifactStore,
    AzureBlobStateLeaseFactory,
    ServiceBusEventSink,
    VmssScaleInProtection,
)
from worker.contracts import ContractError, ExecutionEnvelope
from worker.execution_gate import ExecutionGateError, decode_envelope_json
from worker.health import WorkerHealth, start_health_server
from worker.terraform_executor import TerraformExecutionError, TerraformExecutor


keep_running = True


def _stop(_signum, _frame) -> None:
    global keep_running
    keep_running = False


def _required_environment(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required runner setting {name} is missing.")
    return value


@dataclass(frozen=True)
class RunnerConfig:
    client_id: str
    service_bus_namespace: str
    plan_queue: str
    apply_queue: str
    event_queue: str
    artifact_account: str
    executor_account: str
    private_plan_container: str
    state_container: str
    health_port: int = 8085
    poll_seconds: int = 10

    @classmethod
    def from_environment(cls) -> "RunnerConfig":
        return cls(
            client_id=_required_environment("AZURE_CLIENT_ID"),
            service_bus_namespace=_required_environment(
                "ZEROOPS_SERVICE_BUS_NAMESPACE"
            ),
            plan_queue=_required_environment("ZEROOPS_PLAN_QUEUE"),
            apply_queue=_required_environment("ZEROOPS_APPLY_QUEUE"),
            event_queue=_required_environment("ZEROOPS_EVENT_QUEUE"),
            artifact_account=_required_environment("ZEROOPS_ARTIFACT_ACCOUNT"),
            executor_account=_required_environment("ZEROOPS_EXECUTOR_ACCOUNT"),
            private_plan_container=_required_environment(
                "ZEROOPS_PRIVATE_PLAN_CONTAINER"
            ),
            state_container=_required_environment("ZEROOPS_STATE_CONTAINER"),
            health_port=int(os.getenv("ZEROOPS_HEALTH_PORT", "8085")),
            poll_seconds=int(os.getenv("ZEROOPS_POLL_SECONDS", "10")),
        )


def _message_bytes(message) -> bytes:
    return b"".join(
        chunk if isinstance(chunk, bytes) else bytes(chunk)
        for chunk in message.body
    )


def _safe_failure(envelope: ExecutionEnvelope, category: str) -> dict[str, Any]:
    return {
        **envelope.safe_context(),
        "status": "failed",
        "failure_category": category,
    }


def _process_message(
    *,
    receiver,
    message,
    expected_operation: str,
    store: AzureBlobArtifactStore,
    lease_factory: AzureBlobStateLeaseFactory,
    protection: VmssScaleInProtection,
    event_sink: ServiceBusEventSink,
    executor: TerraformExecutor,
    health: WorkerHealth,
) -> None:
    envelope: ExecutionEnvelope | None = None
    protected = False
    try:
        envelope = decode_envelope_json(_message_bytes(message))
        if envelope.operation != expected_operation:
            raise ContractError("Queue and operation do not match.")
        health.mark_ready(active_job=envelope.job_id)

        if store.was_completed(envelope):
            receiver.complete_message(message)
            return

        protection.protect()
        protected = True
        with lease_factory.for_envelope(envelope) as lease:
            with tempfile.TemporaryDirectory(
                prefix=f"zeroops-{envelope.job_id}-",
                dir="/work",
            ) as temporary:
                with AutoLockRenewer(
                    max_lock_renewal_duration=7_200
                ) as lock_renewer:
                    lock_renewer.register(
                        receiver,
                        message,
                        max_lock_renewal_duration=7_200,
                    )
                    result = executor.execute(
                        envelope,
                        job_directory=Path(temporary),
                    )
                    lease.assert_current()

            event_sink.publish(envelope, result)
            store.mark_completed(envelope, result)
            receiver.complete_message(message)
    except (ContractError, ExecutionGateError) as error:
        if envelope is not None:
            event_sink.publish(envelope, _safe_failure(envelope, type(error).__name__))
        receiver.dead_letter_message(
            message,
            reason="zeroops-safety-gate",
            error_description=type(error).__name__,
        )
    except TerraformExecutionError as error:
        delivery_count = int(getattr(message, "delivery_count", 0) or 0)
        if delivery_count >= 4:
            if envelope is not None:
                event_sink.publish(
                    envelope,
                    _safe_failure(envelope, f"tool:{error.phase}"),
                )
            receiver.dead_letter_message(
                message,
                reason="terraform-execution-failed",
                error_description=error.phase[:256],
            )
        else:
            receiver.abandon_message(message)
    except Exception:
        receiver.abandon_message(message)
    finally:
        release_failed = False
        if protected:
            try:
                protection.release()
            except Exception:
                release_failed = True
                health.mark_error(
                    "Scale-in protection release failed; operator reconciliation required.",
                    active_job=envelope.job_id if envelope else None,
                )
        if not release_failed:
            health.mark_ready()


def _poll_queue(
    *,
    client: ServiceBusClient,
    queue_name: str,
    operation: str,
    handler_kwargs: dict[str, Any],
) -> bool:
    try:
        with client.get_queue_receiver(
            queue_name=queue_name,
            session_id=NEXT_AVAILABLE_SESSION,
            receive_mode=ServiceBusReceiveMode.PEEK_LOCK,
            prefetch_count=1,
            max_wait_time=5,
        ) as receiver:
            messages = receiver.receive_messages(
                max_message_count=1,
                max_wait_time=5,
            )
            if not messages:
                return False
            _process_message(
                receiver=receiver,
                message=messages[0],
                expected_operation=operation,
                **handler_kwargs,
            )
            return True
    except ServiceBusError:
        return False


def main() -> int:
    global keep_running
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    try:
        config = RunnerConfig.from_environment()
    except (RuntimeError, ValueError):
        return 1

    health = WorkerHealth()
    health_server = start_health_server(health, port=config.health_port)
    credential = ManagedIdentityCredential(client_id=config.client_id)
    service_bus = ServiceBusClient(
        fully_qualified_namespace=config.service_bus_namespace,
        credential=credential,
        logging_enable=False,
    )
    store = AzureBlobArtifactStore(
        credential=credential,
        artifact_account_name=config.artifact_account,
        executor_account_name=config.executor_account,
        plan_container_name=config.private_plan_container,
    )
    lease_factory = AzureBlobStateLeaseFactory(
        credential=credential,
        executor_account_name=config.executor_account,
        state_container_name=config.state_container,
    )
    handler_kwargs = {
        "store": store,
        "lease_factory": lease_factory,
        "protection": VmssScaleInProtection(credential),
        "event_sink": ServiceBusEventSink(service_bus, config.event_queue),
        "executor": TerraformExecutor(
            store=store,
            executor_storage_account=config.executor_account,
            state_container=config.state_container,
            managed_identity_client_id=config.client_id,
        ),
        "health": health,
    }

    try:
        while keep_running:
            handled = _poll_queue(
                client=service_bus,
                queue_name=config.apply_queue,
                operation="apply",
                handler_kwargs=handler_kwargs,
            )
            handled = _poll_queue(
                client=service_bus,
                queue_name=config.plan_queue,
                operation="plan",
                handler_kwargs=handler_kwargs,
            ) or handled
            health.mark_ready()
            if not handled:
                time.sleep(config.poll_seconds)
        return 0
    finally:
        service_bus.close()
        credential.close()
        health_server.shutdown()
        health_server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
