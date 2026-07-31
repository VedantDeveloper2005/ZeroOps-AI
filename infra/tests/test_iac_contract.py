from __future__ import annotations

import re
import unittest
from pathlib import Path


INFRA_ROOT = Path(__file__).resolve().parents[1]


class InfrastructureContractTests(unittest.TestCase):
    def test_vmss_is_regular_scale_to_zero_and_capped(self) -> None:
        runner = (INFRA_ROOT / "modules" / "runner" / "main.tf").read_text()
        self.assertIn('priority                     = "Regular"', runner)
        self.assertIn("instances                    = 0", runner)
        self.assertIn("maximum = tostring(var.max_instances)", runner)
        self.assertRegex(
            runner,
            re.compile(r'metric_name\s*=\s*"ActiveMessageCount"'),
        )

    def test_executor_only_state_and_plan_containers_exist(self) -> None:
        storage = (INFRA_ROOT / "modules" / "storage" / "main.tf").read_text()
        rbac = (INFRA_ROOT / "rbac.tf").read_text()
        self.assertIn('"terraform-state"', storage)
        self.assertIn('"saved-plans-private"', storage)
        self.assertIn('resource "azurerm_role_assignment" "executor_state"', rbac)
        self.assertIn('resource "azurerm_role_assignment" "backend_artifacts"', rbac)
        self.assertNotIn("backend_executor", rbac)

    def test_no_key_vault_secrets_or_raw_plan_outputs(self) -> None:
        terraform = "\n".join(
            path.read_text(encoding="utf-8")
            for path in INFRA_ROOT.rglob("*.tf")
        )
        self.assertNotIn('resource "azurerm_key_vault_secret"', terraform)
        outputs = (INFRA_ROOT / "outputs.tf").read_text(encoding="utf-8")
        self.assertNotIn("primary_access_key", outputs)
        self.assertNotIn("tfplan", outputs.lower())

    def test_validation_cannot_register_resource_providers_implicitly(self) -> None:
        providers = (INFRA_ROOT / "providers.tf").read_text(encoding="utf-8")
        self.assertIn('resource_provider_registrations = "none"', providers)

    def test_environment_caps(self) -> None:
        test_profile = (
            INFRA_ROOT / "environments" / "test.tfvars.example"
        ).read_text()
        production_profile = (
            INFRA_ROOT / "environments" / "production.tfvars.example"
        ).read_text()
        self.assertIn("vmss_max_instances = 1", test_profile)
        self.assertIn("vmss_max_instances = 10", production_profile)
        self.assertIn('service_bus_sku          = "Premium"', production_profile)
        self.assertIn("enable_private_endpoints = true", production_profile)

    def test_function_contract_settings_and_history_projector(self) -> None:
        root = (INFRA_ROOT / "main.tf").read_text(encoding="utf-8")
        function_module = (
            INFRA_ROOT / "modules" / "function_flex" / "main.tf"
        ).read_text(encoding="utf-8")
        for setting in (
            "REPOSITORY_ANALYSIS_QUEUE_NAME",
            "TERRAFORM_GENERATION_QUEUE_NAME",
            "TERRAFORM_PLAN_QUEUE_NAME",
            "WORKFLOW_EVENTS_QUEUE_NAME",
            "ARTIFACT_STORAGE_ACCOUNT_URL",
            "AI_REPOSITORY_API_KEY",
            "AI_TERRAFORM_API_KEY",
            "POSTGRES_ENTRA_USER",
        ):
            self.assertIn(setting, root)
        self.assertIn('module "history_function"', root)
        self.assertIn('version = "3.13"', function_module)


if __name__ == "__main__":
    unittest.main()
