from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from worker.vmss_main import RunnerConfig


class PlanOnlyVmssEntrypointTests(unittest.TestCase):
    def test_runner_configuration_does_not_require_an_apply_queue(self) -> None:
        environment = {
            "AZURE_CLIENT_ID": "11111111-1111-4111-8111-111111111111",
            "ZEROOPS_SERVICE_BUS_NAMESPACE": "zeroops.servicebus.windows.net",
            "ZEROOPS_PLAN_QUEUE": "terraform-plan",
            "ZEROOPS_EVENT_QUEUE": "workflow-events",
            "ZEROOPS_ARTIFACT_ACCOUNT": "artifactaccount",
            "ZEROOPS_EXECUTOR_ACCOUNT": "executoraccount",
            "ZEROOPS_PRIVATE_PLAN_CONTAINER": "saved-plans-private",
            "ZEROOPS_STATE_CONTAINER": "terraform-state",
        }

        with patch.dict(os.environ, environment, clear=True):
            config = RunnerConfig.from_environment()

        self.assertEqual(config.plan_queue, "terraform-plan")
        self.assertFalse(hasattr(config, "apply_queue"))


if __name__ == "__main__":
    unittest.main()
