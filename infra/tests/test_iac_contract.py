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
            "AI_REPOSITORY_FALLBACK_API_KEY",
            "AI_TERRAFORM_API_KEY",
            "AI_TERRAFORM_FALLBACK_API_KEY",
            "POSTGRES_ENTRA_USER",
        ):
            self.assertIn(setting, root)
        self.assertIn('module "history_function"', root)
        self.assertIn('version = "3.13"', function_module)

    def test_model_routes_use_separate_vaults_and_explicit_groq_fallbacks(self) -> None:
        root = (INFRA_ROOT / "main.tf").read_text(encoding="utf-8")
        rbac = (INFRA_ROOT / "rbac.tf").read_text(encoding="utf-8")
        function_module = (
            INFRA_ROOT / "modules" / "function_flex" / "main.tf"
        ).read_text(encoding="utf-8")

        self.assertIn('resource "azurerm_user_assigned_identity" "analysis"', root)
        self.assertIn(
            'resource "azurerm_user_assigned_identity" "terraform_generation"',
            root,
        )
        for value in (
            "AI_REPOSITORY_API_KEY",
            "ai-repository-api-key",
            "AI_REPOSITORY_FALLBACK_API_KEY",
            "ai-repository-fallback-api-key",
            "AI_TERRAFORM_API_KEY",
            "ai-terraform-api-key",
            "AI_TERRAFORM_FALLBACK_API_KEY",
            "ai-terraform-fallback-api-key",
        ):
            self.assertIn(value, root)
        self.assertRegex(
            root,
            r"model_key_vault_uri\s*=\s*module\.model_key_vaults\.analysis_vault_uri",
        )
        self.assertRegex(
            root,
            r"model_key_vault_uri\s*=\s*module\.model_key_vaults\.terraform_vault_uri",
        )
        self.assertEqual(
            len(re.findall(r'AI_REPOSITORY_PROVIDER\s*=\s*"nvidia"', root)),
            1,
        )
        self.assertEqual(
            len(re.findall(r'AI_TERRAFORM_PROVIDER\s*=\s*"nvidia"', root)),
            1,
        )
        self.assertEqual(
            root.count('https://integrate.api.nvidia.com/v1'),
            2,
        )
        self.assertEqual(root.count('z-ai/glm-5.2'), 2)
        self.assertEqual(
            len(re.findall(r'AI_REPOSITORY_FALLBACK_PROVIDER\s*=\s*"groq"', root)),
            1,
        )
        self.assertEqual(
            len(re.findall(r'AI_TERRAFORM_FALLBACK_PROVIDER\s*=\s*"groq"', root)),
            1,
        )
        self.assertEqual(root.count('https://api.groq.com/openai/v1'), 2)
        self.assertEqual(root.count('openai/gpt-oss-120b'), 2)
        self.assertIn('AI_REPOSITORY_FALLBACK_MAX_INPUT_CHARS   = "14000"', root)
        self.assertIn('AI_REPOSITORY_FALLBACK_MAX_OUTPUT_TOKENS = "800"', root)
        self.assertIn('AI_TERRAFORM_FALLBACK_MAX_INPUT_CHARS   = "14000"', root)
        self.assertIn('AI_TERRAFORM_FALLBACK_MAX_OUTPUT_TOKENS = "1000"', root)
        self.assertNotIn('model_api_key_setting_name = "NVIDIA_API_KEY"', root)
        self.assertNotIn("GROQ_API_KEY", root)
        self.assertNotIn("GROQ_API_KEY", function_module)
        self.assertIn(
            "secrets/${var.fallback_model_api_key_secret_name}",
            function_module,
        )
        self.assertIn(
            "scope              = module.model_key_vaults.analysis_vault_id",
            rbac,
        )

        analysis_block, remainder = root.split(
            'module "terraform_generation_function"',
            maxsplit=1,
        )
        terraform_block = remainder.split('module "history_function"', maxsplit=1)[0]
        self.assertIn("AI_REPOSITORY_FALLBACK_API_KEY", analysis_block)
        self.assertNotIn("AI_TERRAFORM_FALLBACK_API_KEY", analysis_block)
        self.assertIn("AI_TERRAFORM_FALLBACK_API_KEY", terraform_block)
        self.assertNotIn("AI_REPOSITORY_FALLBACK_API_KEY", terraform_block)
        self.assertIn(
            "scope              = module.model_key_vaults.terraform_vault_id",
            rbac,
        )


if __name__ == "__main__":
    unittest.main()
