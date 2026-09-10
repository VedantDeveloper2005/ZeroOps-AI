from __future__ import annotations

import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from worker.terraform_executor import TerraformExecutor
from worker.vmss_main import RunnerConfig


class VmssEntrypointTests(unittest.TestCase):
    def test_runner_configuration_requires_separate_plan_and_apply_queues(self) -> None:
        environment = {
            "AZURE_CLIENT_ID": "11111111-1111-4111-8111-111111111111",
            "ZEROOPS_SERVICE_BUS_NAMESPACE": "zeroops.servicebus.windows.net",
            "ZEROOPS_PLAN_QUEUE": "terraform-plan",
            "ZEROOPS_APPLY_QUEUE": "terraform-apply",
            "ZEROOPS_EVENT_QUEUE": "workflow-events",
            "ZEROOPS_ARTIFACT_ACCOUNT": "artifactaccount",
            "ZEROOPS_EXECUTOR_ACCOUNT": "executoraccount",
            "ZEROOPS_PRIVATE_PLAN_CONTAINER": "saved-plans-private",
            "ZEROOPS_STATE_CONTAINER": "terraform-state",
        }

        with patch.dict(os.environ, environment, clear=True):
            config = RunnerConfig.from_environment()

        self.assertEqual(config.plan_queue, "terraform-plan")
        self.assertEqual(config.apply_queue, "terraform-apply")

    def test_executor_uses_writable_tflint_plugin_directory(self) -> None:
        executor = TerraformExecutor(
            store=object(),
            executor_storage_account="executoraccount",
            state_container="terraform-state",
            managed_identity_client_id="11111111-1111-4111-8111-111111111111",
        )
        envelope = SimpleNamespace(
            target_subscription_id="22222222-2222-4222-8222-222222222222",
            target_tenant_id="33333333-3333-4333-8333-333333333333",
        )

        with patch.dict(
            os.environ,
            {"HOME": "/home/zeroops", "PATH": "/usr/local/bin"},
            clear=True,
        ):
            environment = executor._environment(envelope)

        self.assertEqual(environment["HOME"], "/home/zeroops")
        self.assertEqual(
            environment["TFLINT_PLUGIN_DIR"],
            "/work/.tflint.d/plugins",
        )


if __name__ == "__main__":
    unittest.main()
