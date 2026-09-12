from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


INFRA_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = INFRA_ROOT.parent


class InfrastructureContractTests(unittest.TestCase):
    def test_github_deployments_and_oidc_subject_use_main_branch(self) -> None:
        manifest = json.loads(
            (REPOSITORY_ROOT / ".azure" / "federated-credential.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["name"], "github-main")
        self.assertEqual(
            manifest["issuer"], "https://token.actions.githubusercontent.com"
        )
        self.assertEqual(
            manifest["subject"],
            "repo:VedantDeveloper2005/ZeroOps-AI:ref:refs/heads/main",
        )
        self.assertEqual(manifest["audiences"], ["api://AzureADTokenExchange"])

        for workflow_name in ("main_zeroopsai.yml", "main_zeroops-backend.yml"):
            workflow = (
                REPOSITORY_ROOT / ".github" / "workflows" / workflow_name
            ).read_text(encoding="utf-8")
            self.assertNotIn("environment: production", workflow)
            self.assertIn("id-token: write", workflow)
            self.assertIn(
                "if: github.event_name != 'pull_request' "
                "&& github.ref == 'refs/heads/main'",
                workflow,
            )

        oidc_documentation = (
            REPOSITORY_ROOT / "docs" / "github-actions-azure-oidc.md"
        ).read_text(encoding="utf-8")
        self.assertIn('$tenantId = "<Microsoft Entra tenant ID>"', oidc_documentation)
        self.assertIn('$subscriptionId = "<Azure subscription ID>"', oidc_documentation)
        self.assertIn("az login --tenant $tenantId", oidc_documentation)
        self.assertIn(
            "az account set --subscription $subscriptionId", oidc_documentation
        )
        self.assertIsNone(
            re.search(r"az login --tenant [0-9a-fA-F-]{36}", oidc_documentation)
        )
        self.assertIsNone(
            re.search(
                r"az account set --subscription [0-9a-fA-F-]{36}",
                oidc_documentation,
            )
        )

    def test_vmss_is_regular_scale_to_zero_and_capped(self) -> None:
        runner = (INFRA_ROOT / "modules" / "runner" / "main.tf").read_text()
        root = (INFRA_ROOT / "main.tf").read_text(encoding="utf-8")
        network = (INFRA_ROOT / "modules" / "network" / "main.tf").read_text(
            encoding="utf-8"
        )
        self.assertRegex(runner, re.compile(r'priority\s*=\s*"Regular"'))
        self.assertRegex(runner, re.compile(r"instances\s*=\s*0"))
        self.assertIn("maximum = tostring(var.max_instances)", runner)
        self.assertRegex(
            runner,
            re.compile(r'metric_name\s*=\s*"ActiveMessageCount"'),
        )
        self.assertIn("enable_nat_gateway      = var.deploy_runner", root)
        self.assertGreaterEqual(
            network.count("count = var.enable_nat_gateway ? 1 : 0"), 4
        )

    def test_vmss_uses_initial_trusted_launch_and_managed_os_disk(self) -> None:
        runner = (INFRA_ROOT / "modules" / "runner" / "main.tf").read_text(
            encoding="utf-8"
        )
        self.assertIn('resource "azurerm_linux_virtual_machine_scale_set" "this"', runner)
        self.assertIn("secure_boot_enabled", runner)
        self.assertIn("vtpm_enabled", runner)
        self.assertIn('storage_account_type = "StandardSSD_LRS"', runner)
        self.assertNotIn("diff_disk_settings", runner)
        self.assertNotIn("azapi_update_resource", runner)

        cloud_init = (
            INFRA_ROOT / "modules" / "runner" / "cloud-init.yaml.tftpl"
        ).read_text(encoding="utf-8")
        self.assertIn("docker-29.7.1.tgz", cloud_init)
        self.assertIn(
            "0fcea2a8b4d1b54ccc9010e3451b78504a369d414f37eb3bb79300e1b5c22ce6",
            cloud_init,
        )
        self.assertIn("/metadata/identity/oauth2/token", cloud_init)
        self.assertIn("/oauth2/exchange", cloud_init)
        self.assertNotIn("package_update", cloud_init)
        self.assertNotIn("apt-get", cloud_init)
        self.assertNotIn("az acr login", cloud_init)

    def test_vmss_has_queue_scoped_plan_and_apply_authority(self) -> None:
        root = (INFRA_ROOT / "main.tf").read_text(encoding="utf-8")
        rbac = (INFRA_ROOT / "rbac.tf").read_text(encoding="utf-8")
        locals_tf = (INFRA_ROOT / "locals.tf").read_text(encoding="utf-8")
        runner = (
            INFRA_ROOT / "modules" / "runner" / "main.tf"
        ).read_text(encoding="utf-8")
        runner_variables = (
            INFRA_ROOT / "modules" / "runner" / "variables.tf"
        ).read_text(encoding="utf-8")
        cloud_init = (
            INFRA_ROOT / "modules" / "runner" / "cloud-init.yaml.tftpl"
        ).read_text(encoding="utf-8")
        worker_entrypoint = (
            REPOSITORY_ROOT / "worker" / "vmss_main.py"
        ).read_text(encoding="utf-8")

        # Apply is enabled only through its sessioned queue and the same
        # immutable worker. No namespace-wide messaging role is used.
        self.assertIn('terraform_apply      = "terraform-apply"', locals_tf)
        self.assertIn("executor_apply_receiver", rbac)
        self.assertIn("backend_apply_sender", rbac)
        self.assertGreaterEqual(rbac.count("count = var.deploy_runner ? 1 : 0"), 2)
        self.assertIn("module.service_bus.queue_ids.terraform_apply", rbac)
        self.assertIn("apply_queue", root)
        self.assertIn("apply_queue", runner)
        self.assertIn("apply_queue", runner_variables)
        self.assertIn("ZEROOPS_APPLY_QUEUE", cloud_init)

        # Mutation authority is opt-in and limited to one dedicated customer
        # resource group. A root check rejects the platform group itself.
        self.assertIn(
            "role_definition_id = local.role_definition_ids.contributor",
            rbac,
        )
        self.assertIn("execution_scope_is_not_platform_scope", root)

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
        self.assertIn('vmss_sku           = "Standard_B2as_v2"', test_profile)
        self.assertIn('runner_os_image_version = "22.04.202608060"', test_profile)
        self.assertIn("deploy_runner       = false", test_profile)
        self.assertIn("vmss_max_instances = 2", production_profile)
        self.assertIn('vmss_sku           = "Standard_B2as_v2"', production_profile)
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

    def test_model_routes_use_separate_vaults_and_foundry_only(self) -> None:
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
            "AI_TERRAFORM_API_KEY",
            "ai-terraform-api-key",
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
        variables = (INFRA_ROOT / "variables.tf").read_text(encoding="utf-8")
        self.assertIn("AI_REPOSITORY_PROVIDER                   = var.repository_ai_provider", root)
        self.assertIn("AI_TERRAFORM_PROVIDER                   = var.terraform_ai_provider", root)
        self.assertIn("AI_REPOSITORY_ENDPOINT                   = var.repository_ai_endpoint", root)
        self.assertIn("AI_TERRAFORM_ENDPOINT                   = var.terraform_ai_endpoint", root)
        self.assertIn("AI_REPOSITORY_MODEL                      = var.repository_ai_model", root)
        self.assertIn("AI_TERRAFORM_MODEL                      = var.terraform_ai_model", root)
        self.assertIn('default     = "azure-openai"', variables)
        self.assertNotIn("_FALLBACK_", root)
        self.assertNotIn("nvidia", variables)
        self.assertNotIn("api.groq.com", root)
        self.assertNotIn('model_api_key_setting_name = "NVIDIA_API_KEY"', root)
        self.assertNotIn("GROQ_API_KEY", root)
        self.assertNotIn("GROQ_API_KEY", function_module)
        self.assertIn(
            "secrets/${var.model_api_key_secret_name}",
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
        self.assertIn(
            "scope              = module.model_key_vaults.terraform_vault_id",
            rbac,
        )


if __name__ == "__main__":
    unittest.main()
