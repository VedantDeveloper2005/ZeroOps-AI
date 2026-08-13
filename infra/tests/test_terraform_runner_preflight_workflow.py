from __future__ import annotations

import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = (
    REPOSITORY_ROOT
    / ".github"
    / "workflows"
    / "terraform-runner-preflight.yml"
)


class TerraformRunnerPreflightWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_is_manual_main_only_and_least_privilege(self) -> None:
        trigger = re.search(
            r"(?ms)^on:\s*\n(?P<body>.*?)(?=^permissions:)",
            self.workflow,
        )
        self.assertIsNotNone(trigger)
        assert trigger is not None
        self.assertEqual(trigger.group("body").strip(), "workflow_dispatch:")

        self.assertIn("permissions: {}", self.workflow)
        self.assertIn("contents: read", self.workflow)
        self.assertIn("id-token: write", self.workflow)
        self.assertIn(
            "if: github.event_name == 'workflow_dispatch' "
            "&& github.ref == 'refs/heads/main'",
            self.workflow,
        )
        for forbidden_trigger in ("push:", "pull_request:", "schedule:"):
            self.assertNotIn(forbidden_trigger, trigger.group("body"))

    def test_actions_are_pinned_and_oidc_uses_only_generic_secrets(self) -> None:
        self.assertIn(
            "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
            self.workflow,
        )
        self.assertIn(
            "azure/login@8216e11d8cd9b42fe925c852af8e76311ff067ac",
            self.workflow,
        )
        self.assertIn(
            "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
            self.workflow,
        )
        for action in re.findall(r"uses:\s*[^@\s]+@([^\s]+)", self.workflow):
            self.assertRegex(action, r"^[0-9a-f]{40}$")

        secret_names = set(re.findall(r"secrets\.([A-Z0-9_]+)", self.workflow))
        self.assertEqual(
            secret_names,
            {"AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID"},
        )
        self.assertNotIn("set -x", self.workflow)
        self.assertIn("AZURE_CORE_OUTPUT: none", self.workflow)

    def test_target_and_all_required_read_only_checks_are_fixed(self) -> None:
        for expected in (
            "TARGET_RESOURCE_GROUP: zeroops-rg",
            "TARGET_LOCATION: centralindia",
            "TARGET_VM_SIZE: Standard_D2ads_v5",
            "Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest",
            "TARGET_VNET_CIDR: 10.72.0.0/16",
            "REQUIRED_VCPUS: \"2\"",
            'resource_group_location,,}" == "${TARGET_LOCATION,,}',
            "--size \"${TARGET_VM_SIZE}\" --all",
            ".restrictions // [] | length",
            "selected_target_restriction_count",
            '.restrictionInfo.zones // [])[]?; . == "1" or . == "2"',
            "az vm image show",
            "az vm list-usage",
            "regional_free",
            "family_free",
            "compute-quota.json",
            "candidate-skus.json",
            'candidate_skus_path="${RUNNER_TEMP}/terraform-runner-candidate-skus.json"',
            'with open(sku_path, encoding="utf-8")',
            "Standard_B2s",
            "Standard_D2as_v5",
            '"viable": (',
            "az provider show",
            "az resource list",
            "az network vnet list",
            "ipaddress.ip_network",
            "prefix.overlaps(planned)",
        ):
            self.assertIn(expected, self.workflow)

        for namespace in (
            "Microsoft.App",
            "Microsoft.Authorization",
            "Microsoft.Compute",
            "Microsoft.ContainerRegistry",
            "Microsoft.DBforPostgreSQL",
            "Microsoft.Insights",
            "Microsoft.KeyVault",
            "Microsoft.ManagedIdentity",
            "Microsoft.Network",
            "Microsoft.OperationalInsights",
            "Microsoft.ServiceBus",
            "Microsoft.Storage",
            "Microsoft.Web",
            "Microsoft.Quota",
        ):
            self.assertIn(namespace, self.workflow)

        for resource_name in (
            "ASP-zeroopsrg-8559",
            "zeroopsai",
            "zeroops-backend",
            "zeroops-db-prod",
            "zeroops-kv-prod",
            "zeroops-backend-id-96a7",
        ):
            self.assertIn(resource_name, self.workflow)

    def test_azure_cli_commands_are_strictly_read_only(self) -> None:
        allowed_commands = {
            "account show",
            "group show",
            "network vnet",
            "provider show",
            "resource list",
            "vm image",
            "vm list-skus",
            "vm list-usage",
        }
        commands = {
            " ".join(match)
            for match in re.findall(
                r"\baz\s+([a-z-]+)\s+([a-z-]+)",
                self.workflow,
                flags=re.IGNORECASE,
            )
        }
        self.assertEqual(commands, allowed_commands)

        self.assertIsNone(
            re.search(
                r"\baz\s+[^\n]*(?:\s|^)(?:create|delete|update|set|register|"
                r"unregister|assign|remove|start|stop|restart)(?:\s|$)",
                self.workflow,
                flags=re.IGNORECASE,
            )
        )
        self.assertIsNone(
            re.search(
                r"(?m)^\s*(?:terraform|tofu)\s+(?:plan|apply|destroy|import)",
                self.workflow,
                flags=re.IGNORECASE,
            )
        )
        self.assertNotIn("az provider register", self.workflow.lower())
        self.assertNotIn("az deployment", self.workflow.lower())

    def test_artifacts_are_sanitized_and_do_not_contain_raw_responses(self) -> None:
        self.assertIn(
            "{name, type, location}",
            self.workflow,
        )
        self.assertIn(
            "{name, resourceGroup, addressPrefixes:",
            self.workflow,
        )
        self.assertIn(
            "contains no access tokens, credentials, resource IDs, or raw Azure responses",
            self.workflow,
        )
        for raw_name in (
            "account.json",
            "sku.json",
            "image.json",
            "usage.json",
            "sku-candidates-raw.json",
        ):
            self.assertNotIn(raw_name, self.workflow)


if __name__ == "__main__":
    unittest.main()
