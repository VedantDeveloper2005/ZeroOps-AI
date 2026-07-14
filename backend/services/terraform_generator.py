"""Internal-only Terraform artifact generation.

No endpoint returns this source.  The user reviews architecture choices through
``InfrastructurePlan`` instead.  The artifact contains no credentials or
secret values and is created only after an approved plan starts a deployment.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from backend import config
except ImportError:
    import config


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9-]", "-", value.lower()).strip("-")[:40] or "zeroops-app"


def _resource_kinds(plan: dict[str, Any]) -> list[str]:
    services = {str(item.get("service") or "") for item in plan.get("components", [])}
    kinds = ["azurerm_linux_web_app"] if "Azure App Service" in services else []
    if "Azure Container Apps" in services:
        kinds.extend(["azurerm_container_app_environment", "azurerm_container_app"])
    if "Azure Blob Storage" in services:
        kinds.append("azurerm_storage_account")
    if "Azure Key Vault" in services:
        kinds.append("azurerm_key_vault")
    if "Application Insights" in services:
        kinds.append("azurerm_application_insights")
    if "Virtual Network" in services:
        kinds.append("azurerm_virtual_network")
    if "Azure Database for PostgreSQL Flexible Server" in services:
        kinds.append("azurerm_postgresql_flexible_server")
    return kinds


def _render_internal_hcl(plan: dict[str, Any], project_name: str) -> str:
    """Render a non-secret Terraform entrypoint for the approved architecture.

    Provider authentication and customer-specific resource identifiers are
    supplied only by the deployment worker through its secure environment.
    """
    # The artifact needs resource decisions only. Scanner evidence (including
    # environment-variable names and findings) stays in the database plan and
    # must not be copied into generated deployment files.
    artifact_plan = {
        "cloud": plan.get("cloud"),
        "region": plan.get("region_label"),
        "revision": plan.get("revision"),
        "components": [
            {
                "id": component.get("id"),
                "service": component.get("service"),
                "tier": component.get("tier"),
            }
            for component in plan.get("components", [])
            if isinstance(component, dict)
        ],
    }
    encoded_plan = json.dumps(artifact_plan, sort_keys=True, separators=(",", ":"))
    services = {str(item.get("service") or "") for item in plan.get("components", [])}
    blocks: list[str] = []

    if "Azure App Service" in services:
        blocks.append('''data "azurerm_service_plan" "application" {
  name                = var.app_service_plan_name
  resource_group_name = var.resource_group_name
}

resource "azurerm_linux_web_app" "application" {
  name                = "${local.project_slug}-${var.deployment_suffix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  service_plan_id     = data.azurerm_service_plan.application.id
  https_only          = true

  identity { type = "SystemAssigned" }
  site_config {}
}''')

    if "Azure Container Apps" in services:
        blocks.append('''resource "azurerm_container_app_environment" "application" {
  name                = "${local.project_slug}-${var.deployment_suffix}-env"
  location            = var.location
  resource_group_name = var.resource_group_name
}

resource "azurerm_container_app" "application" {
  name                         = "${local.project_slug}-${var.deployment_suffix}"
  container_app_environment_id = azurerm_container_app_environment.application.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"

  identity { type = "SystemAssigned" }
  template {
    container {
      name   = "application"
      image  = var.container_image
      cpu    = 0.5
      memory = "1Gi"
    }
  }
}''')

    if "Azure Blob Storage" in services:
        blocks.append('''resource "azurerm_storage_account" "application" {
  name                     = substr(replace("st${local.project_slug}${var.deployment_suffix}", "-", ""), 0, 24)
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"
}''')

    if "Azure Key Vault" in services:
        blocks.append('''data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "application" {
  name                       = substr("kv-${local.project_slug}-${var.deployment_suffix}", 0, 24)
  location                   = var.location
  resource_group_name        = var.resource_group_name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  soft_delete_retention_days = 7
  purge_protection_enabled   = true
}''')

    if "Application Insights" in services:
        blocks.append('''resource "azurerm_application_insights" "application" {
  name                = "${local.project_slug}-${var.deployment_suffix}-insights"
  location            = var.location
  resource_group_name = var.resource_group_name
  application_type    = "web"
}''')

    if "Virtual Network" in services:
        blocks.append('''resource "azurerm_virtual_network" "application" {
  name                = "${local.project_slug}-${var.deployment_suffix}-vnet"
  location            = var.location
  resource_group_name = var.resource_group_name
  address_space       = ["10.0.0.0/16"]
}''')

    if "Azure Database for PostgreSQL Flexible Server" in services:
        blocks.append('''resource "azurerm_postgresql_flexible_server" "application" {
  name                   = "${local.project_slug}-${var.deployment_suffix}-postgres"
  resource_group_name    = var.resource_group_name
  location               = var.location
  version                = "16"
  administrator_login    = var.postgresql_administrator_login
  administrator_password = var.postgresql_administrator_password
  sku_name               = "B_Standard_B1ms"
  storage_mb             = 32768
}''')

    return f'''# Generated by ZeroOps internal deployment engine. Never expose through the API.
terraform {{
  required_providers {{
    azurerm = {{
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }}
  }}
}}

provider "azurerm" {{
  features {{}}
}}

variable "resource_group_name" {{ type = string }}
variable "location" {{ type = string }}
variable "app_service_plan_name" {{ type = string }}
variable "deployment_suffix" {{ type = string }}
variable "container_image" {{
  type    = string
  default = null
}}
variable "postgresql_administrator_login" {{
  type    = string
  default = "zeroopsadmin"
}}
variable "postgresql_administrator_password" {{
  type      = string
  sensitive = true
  default   = null
}}

locals {{
  project_slug = "{_slug(project_name)}"
  architecture = jsondecode(<<PLAN
{encoded_plan}
PLAN
  )
}}

# This artifact intentionally carries no credentials, connection strings, or
# secret values. Authentication and sensitive inputs are supplied only by the
# authenticated deployment worker.

{chr(10).join(blocks)}
'''


def generate_internal_artifact(*, plan: dict[str, Any], project_id: str, project_name: str) -> dict[str, Any]:
    """Write an internal artifact and return non-sensitive execution metadata."""
    root = Path(config.WORKSPACE_DIR) / "internal-iac" / _slug(project_id)
    root.mkdir(parents=True, exist_ok=True)
    terraform_source = _render_internal_hcl(plan, project_name)
    artifact_path = root / "main.tf"
    artifact_path.write_text(terraform_source, encoding="utf-8")
    digest = hashlib.sha256(terraform_source.encode("utf-8")).hexdigest()
    return {
        "engine": "terraform",
        "status": "generated",
        "artifact_sha256": digest,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "resource_kinds": _resource_kinds(plan),
        "plan_revision": plan.get("revision"),
    }
