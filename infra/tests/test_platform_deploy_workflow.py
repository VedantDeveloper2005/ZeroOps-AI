from __future__ import annotations

import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
INFRA_ROOT = REPOSITORY_ROOT / "infra"
WORKFLOW = (
    REPOSITORY_ROOT / ".github" / "workflows" / "platform-deploy.yml"
).read_text(encoding="utf-8")


class PlatformDeployWorkflowTests(unittest.TestCase):
    def test_is_manual_main_only_and_uses_protected_apply_environment(self) -> None:
        trigger = re.search(
            r"(?ms)^on:\s*\n(?P<body>.*?)(?=^permissions:)", WORKFLOW
        )
        self.assertIsNotNone(trigger)
        assert trigger is not None
        self.assertIn("workflow_dispatch:", trigger.group("body"))
        for forbidden in ("push:", "pull_request:", "schedule:"):
            self.assertNotIn(forbidden, trigger.group("body"))
        self.assertIn("if: github.ref == 'refs/heads/main'", WORKFLOW)
        self.assertEqual(WORKFLOW.count("environment: azure-test-apply"), 2)
        self.assertIn("cancel-in-progress: false", WORKFLOW)

    def test_uses_oidc_without_client_secrets(self) -> None:
        self.assertIn('ARM_USE_OIDC: "true"', WORKFLOW)
        self.assertIn("id-token: write", WORKFLOW)
        self.assertIn("AZURE_PLAN_CLIENT_ID", WORKFLOW)
        self.assertIn("AZURE_APPLY_CLIENT_ID", WORKFLOW)
        for forbidden in (
            "AZURE_CLIENT_SECRET",
            "client-secret",
            "ARM_CLIENT_SECRET",
            "access_key",
            "sas_token",
            "publish-profile",
        ):
            self.assertNotIn(forbidden, WORKFLOW)

    def test_saved_plan_is_exact_commit_bound_single_use_and_not_artifact(self) -> None:
        for expected in (
            "plan-foundation",
            "plan-runner",
            "apply-saved-plan",
            "sha256sum",
            "git_commit=",
            "az storage blob upload",
            "az storage blob download",
            "az storage blob delete",
            "terraform -chdir=infra apply -input=false -auto-approve",
        ):
            self.assertIn(expected, WORKFLOW)
        self.assertIn(
            '[[ "$(jq -r \'.git_commit // ""\' <<< "${metadata}")" == "${GITHUB_SHA}" ]]',
            WORKFLOW,
        )
        artifact_block = WORKFLOW.split(
            "Retain versioned Function release artifact", maxsplit=1
        )[1].split("Deploy Function packages", maxsplit=1)[0]
        self.assertNotIn("tfplan", artifact_block.lower())

    def test_release_resolves_real_runner_digest_and_uses_function_one_deploy(self) -> None:
        for expected in (
            "docker push",
            "az acr repository show",
            "@${digest}",
            "az functionapp deployment source config-zip",
            "--build-remote true",
            "zeroops-function-release-${{ github.sha }}",
        ):
            self.assertIn(expected, WORKFLOW)
        self.assertNotIn("sha256:0000000000000000", WORKFLOW)

    def test_actions_are_commit_pinned(self) -> None:
        action_refs = re.findall(r"uses:\s*[^@\s]+@([^\s]+)", WORKFLOW)
        self.assertTrue(action_refs)
        for reference in action_refs:
            self.assertRegex(reference, r"^[0-9a-f]{40}$")


class DeploymentBootstrapTests(unittest.TestCase):
    def test_bootstrap_separates_plan_and_apply_authority(self) -> None:
        bootstrap = (INFRA_ROOT / "bootstrap" / "main.tf").read_text(
            encoding="utf-8"
        )
        provider = (INFRA_ROOT / "bootstrap" / "versions.tf").read_text(
            encoding="utf-8"
        )
        self.assertIn('resource_provider_registrations = "none"', provider)
        self.assertIn('resource "azurerm_user_assigned_identity" "plan"', bootstrap)
        self.assertIn('resource "azurerm_user_assigned_identity" "apply"', bootstrap)
        self.assertIn("ref:refs/heads/main", bootstrap)
        self.assertIn("environment:${var.github_apply_environment}", bootstrap)
        self.assertIn("plan_platform_reader", bootstrap)
        self.assertIn("apply_platform_contributor", bootstrap)
        self.assertIn("apply_platform_rbac", bootstrap)
        self.assertIn("plan_execution_reader", bootstrap)
        self.assertIn("apply_execution_rbac", bootstrap)
        self.assertIn("customer_scope_is_not_control_plane", bootstrap)
        self.assertNotIn("/subscriptions/${var.subscription_id}\"", bootstrap)

    def test_state_bootstrap_disables_shared_keys_and_never_registers_provider(self) -> None:
        script = (INFRA_ROOT / "bootstrap" / "bootstrap-state.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("--allow-shared-key-access', 'false", script)
        self.assertIn("--allow-blob-public-access', 'false", script)
        self.assertIn("--enable-versioning', 'true", script)
        self.assertIn("expire-saved-deployment-plans", script)
        self.assertIn("$previousNativeCommandPreference", script)
        self.assertIn("$storageShowExitCode", script)
        self.assertIn("$containerShowExitCode", script)
        self.assertNotIn("provider', 'register", script)
        self.assertNotIn("provider register", script)

    def test_lock_files_include_registry_checksums_for_both_platforms(self) -> None:
        for lock_path in (
            INFRA_ROOT / ".terraform.lock.hcl",
            INFRA_ROOT / "bootstrap" / ".terraform.lock.hcl",
        ):
            lock = lock_path.read_text(encoding="utf-8")
            self.assertGreaterEqual(lock.count('"zh:'), 10)


if __name__ == "__main__":
    unittest.main()
