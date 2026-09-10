terraform {
  required_version = ">= 1.9.0, < 2.0.0"

  backend "azurerm" {
    use_azuread_auth = true
  }

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "= 4.81.0"
    }
  }
}

provider "azurerm" {
  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id

  # Subscription provider registration is always an explicit prerequisite.
  resource_provider_registrations = "none"

  features {}
}
