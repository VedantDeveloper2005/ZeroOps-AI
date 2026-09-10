from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from azure.servicebus.exceptions import OperationTimeoutError, ServiceBusError

from worker import vmss_main
from worker.health import WorkerHealth


class VmssHealthRecoveryTests(unittest.TestCase):
    def test_release_failure_stops_message_processing_and_preserves_error(self):
        envelope = SimpleNamespace(job_id="job-1", operation="plan")
        protection = MagicMock()
        protection.release.side_effect = RuntimeError("sensitive-provider-diagnostic")
        store = MagicMock()
        store.was_completed.return_value = False
        health = WorkerHealth()

        with (
            patch.object(vmss_main, "decode_envelope_json", return_value=envelope),
            patch.object(vmss_main.tempfile, "TemporaryDirectory") as temporary,
            patch.object(vmss_main, "AutoLockRenewer"),
        ):
            temporary.return_value.__enter__.return_value = "/isolated-test-workspace"
            with self.assertRaisesRegex(RuntimeError, "Scale-in protection release failed"):
                vmss_main._process_message(
                    receiver=MagicMock(), message=SimpleNamespace(body=[b"{}"]),
                    expected_operation="plan", store=store, lease_factory=MagicMock(),
                    protection=protection, event_sink=MagicMock(), executor=MagicMock(), health=health,
                )

        snapshot = health.snapshot()
        self.assertEqual(snapshot["status"], "not_ready")
        self.assertEqual(snapshot["active_job"], "job-1")
        self.assertNotIn("sensitive-provider-diagnostic", str(snapshot))

    def test_queue_connection_failure_is_not_treated_as_empty_queue(self):
        client = MagicMock()
        client.get_queue_receiver.side_effect = ServiceBusError("private-namespace")
        with self.assertRaises(ServiceBusError):
            vmss_main._poll_queue(client=client, queue_name="apply", operation="apply", handler_kwargs={})

    def test_no_available_session_is_an_empty_poll(self):
        client = MagicMock()
        client.get_queue_receiver.return_value.__enter__.side_effect = OperationTimeoutError()
        self.assertFalse(vmss_main._poll_queue(client=client, queue_name="plan", operation="plan", handler_kwargs={}))

    def test_main_remains_unhealthy_when_queue_poll_fails(self):
        health = WorkerHealth()
        config = SimpleNamespace(
            health_port=8085, client_id="identity", service_bus_namespace="namespace",
            artifact_account="artifacts", executor_account="executor", private_plan_container="plans",
            state_container="state", event_queue="events", apply_queue="apply", plan_queue="plan", poll_seconds=1,
        )

        def stop_after_failure(_):
            vmss_main.keep_running = False

        with ExitStack() as stack:
            stack.enter_context(patch.object(vmss_main, "keep_running", True))
            stack.enter_context(patch.object(vmss_main.RunnerConfig, "from_environment", return_value=config))
            stack.enter_context(patch.object(vmss_main, "WorkerHealth", return_value=health))
            stack.enter_context(patch.object(vmss_main.time, "sleep", side_effect=stop_after_failure))
            stack.enter_context(patch.object(vmss_main, "_poll_queue", side_effect=ServiceBusError("private-namespace")))
            for name in ("start_health_server", "ManagedIdentityCredential", "ServiceBusClient", "AzureBlobArtifactStore", "AzureBlobStateLeaseFactory", "VmssScaleInProtection", "ServiceBusEventSink", "TerraformExecutor"):
                stack.enter_context(patch.object(vmss_main, name))
            self.assertEqual(vmss_main.main(), 0)

        self.assertEqual(health.snapshot()["status"], "not_ready")
        self.assertNotIn("private-namespace", str(health.snapshot()))
