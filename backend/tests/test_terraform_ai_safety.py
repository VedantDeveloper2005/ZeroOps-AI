from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.contracts.ai import TerraformBundle, TerraformGenerationRequest
from backend.services.terraform_ai import TerraformSafetyError, validate_terraform_bundle


PLAN_DIGEST = "a" * 64


def _request(**updates) -> TerraformGenerationRequest:
    payload = {
        "schema_version": "terraform-generation-request.v1",
        "tenant_id": UUID("11111111-1111-1111-1111-111111111111"),
        "project_id": UUID("22222222-2222-2222-2222-222222222222"),
        "plan_id": UUID("33333333-3333-3333-3333-333333333333"),
        "plan_revision": 8,
        "plan_sha256": PLAN_DIGEST,
        "plan_status": "approved",
        "target_cloud": "azure",
        "region": "centralindia",
        "components": [
            {
                "id": "resource-group",
                "service": "Azure Resource Group",
                "tier": None,
                "properties": {"public_network_access": False},
            }
        ],
        "allowed_resource_types": ["azurerm_resource_group"],
        "module_catalog_version": "zeroops-modules.v1",
        "policy_version": "zeroops-policy.v1",
        "constraints": ["Use deterministic names and standard ZeroOps tags."],
        "pricing": None,
    }
    payload.update(updates)
    return TerraformGenerationRequest.model_validate(payload)


def _bundle_payload() -> dict:
    return {
        "schema_version": "terraform-bundle.v1",
        "status": "generated",
        "plan_revision": 8,
        "plan_sha256": PLAN_DIGEST,
        "files": [
            {
                "path": "versions.tf",
                "content": '''
terraform {
  required_version = ">= 1.7, < 2.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
  backend "azurerm" {}
}
''',
            },
            {
                "path": "providers.tf",
                "content": 'provider "azurerm" {\n  features {}\n}\n',
            },
            {
                "path": "variables.tf",
                "content": '''
variable "resource_group_name" {
  type        = string
  description = "Approved resource group name."
}
variable "location" {
  type        = string
  description = "Approved Azure region."
}
''',
            },
            {
                "path": "main.tf",
                "content": '''
resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location
}
''',
            },
            {
                "path": "outputs.tf",
                "content": '''
output "resource_group_name" {
  description = "Created resource group name."
  value       = azurerm_resource_group.main.name
}
''',
            },
        ],
        "variables": [
            {
                "name": "resource_group_name",
                "type": "string",
                "description": "Approved resource group name.",
                "sensitive": False,
                "default": None,
            },
            {
                "name": "location",
                "type": "string",
                "description": "Approved Azure region.",
                "sensitive": False,
                "default": None,
            },
        ],
        "resources": [
            {
                "address": "azurerm_resource_group.main",
                "resource_type": "azurerm_resource_group",
                "component_id": "resource-group",
                "rationale": "Creates the approved deployment boundary.",
                "cost_driver": False,
            }
        ],
        "outputs": [
            {
                "name": "resource_group_name",
                "description": "Created resource group name.",
                "sensitive": False,
            }
        ],
        "assumptions": [],
        "warnings": [],
        "cost_optimizations": [
            {
                "id": "avoid-unapproved-resources",
                "component_id": "resource-group",
                "mechanism": "Generate only the resource explicitly approved by the plan.",
                "expected_impact": "low",
                "tradeoff": "Additional services require a new approved revision.",
                "requires_verified_pricing": True,
            }
        ],
        "validation_requirements": [
            "Run terraform fmt -check.",
            "Run terraform init -backend=false.",
            "Run terraform validate.",
            "Run TFLint.",
            "Run Checkov.",
            "Run terraform plan and compare its JSON with the approved allowlist.",
            "Verify pricing and budget policy.",
            "Require human approval before apply.",
        ],
        "blocked_reasons": [],
    }


def _bundle(**updates) -> TerraformBundle:
    payload = _bundle_payload()
    payload.update(updates)
    return TerraformBundle.model_validate(payload)


def test_valid_bundle_matches_approved_plan_and_metadata():
    bundle = _bundle()
    assert validate_terraform_bundle(bundle, _request()) is bundle


def test_generation_request_requires_approved_status_and_azure_resources():
    with pytest.raises(ValidationError):
        _request(plan_status="draft")
    with pytest.raises(ValidationError, match="AzureRM"):
        _request(allowed_resource_types=["aws_instance"])


def test_bundle_rejects_plan_revision_or_digest_mismatch():
    with pytest.raises(TerraformSafetyError, match="approved plan revision"):
        validate_terraform_bundle(_bundle(plan_revision=7), _request())
    with pytest.raises(TerraformSafetyError, match="approved plan revision"):
        validate_terraform_bundle(_bundle(plan_sha256="b" * 64), _request())


def test_bundle_rejects_path_traversal_and_forbidden_execution():
    payload = _bundle_payload()
    payload["files"][4]["path"] = "../outputs.tf"
    with pytest.raises(TerraformSafetyError, match="file path"):
        validate_terraform_bundle(TerraformBundle.model_validate(payload), _request())

    payload = _bundle_payload()
    payload["files"][3]["content"] += '''
resource "azurerm_resource_group" "unsafe" {
  name     = var.resource_group_name
  location = var.location
  provisioner "local-exec" {
    command = "run something"
  }
}
'''
    payload["resources"].append(
        {
            "address": "azurerm_resource_group.unsafe",
            "resource_type": "azurerm_resource_group",
            "component_id": "resource-group",
            "rationale": "Unsafe test resource.",
            "cost_driver": False,
        }
    )
    with pytest.raises(TerraformSafetyError, match="local-exec"):
        validate_terraform_bundle(TerraformBundle.model_validate(payload), _request())


def test_bundle_rejects_hardcoded_secrets_and_unapproved_public_access():
    payload = _bundle_payload()
    payload["files"][3]["content"] += '\nclient_secret = "example-placeholder"\n'
    with pytest.raises(TerraformSafetyError, match="hardcoded secret"):
        validate_terraform_bundle(TerraformBundle.model_validate(payload), _request())

    payload = _bundle_payload()
    payload["files"][3]["content"] += "\npublic_network_access_enabled = true\n"
    with pytest.raises(TerraformSafetyError, match="public access"):
        validate_terraform_bundle(TerraformBundle.model_validate(payload), _request())


def test_bundle_rejects_secret_variable_defaults_and_metadata_drift():
    payload = _bundle_payload()
    payload["files"][2]["content"] += '''
variable "admin_password" {
  type        = string
  description = "Runtime-only database password."
  sensitive   = true
  default     = "not-allowed"
}
'''
    payload["variables"].append(
        {
            "name": "admin_password",
            "type": "string",
            "description": "Runtime-only database password.",
            "sensitive": True,
            "default": "not-allowed",
        }
    )
    with pytest.raises(TerraformSafetyError, match="cannot define defaults"):
        validate_terraform_bundle(TerraformBundle.model_validate(payload), _request())

    payload = _bundle_payload()
    payload["resources"] = []
    with pytest.raises(TerraformSafetyError, match="resource metadata"):
        validate_terraform_bundle(TerraformBundle.model_validate(payload), _request())


def test_blocked_bundle_contains_no_source():
    bundle = TerraformBundle.model_validate(
        {
            "schema_version": "terraform-bundle.v1",
            "status": "blocked",
            "plan_revision": 8,
            "plan_sha256": PLAN_DIGEST,
            "files": [],
            "variables": [],
            "resources": [],
            "outputs": [],
            "assumptions": [],
            "warnings": [],
            "cost_optimizations": [],
            "validation_requirements": [],
            "blocked_reasons": ["The approved resource allowlist is missing required detail."],
        }
    )
    assert validate_terraform_bundle(bundle, _request()) is bundle
