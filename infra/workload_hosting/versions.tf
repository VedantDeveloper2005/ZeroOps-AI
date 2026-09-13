terraform {
  required_version = "= 1.15.8"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "= 4.81.0"
    }
  }

  backend "azurerm" {
    resource_group_name  = "zeroops-tfstate-rg"
    storage_account_name = "zeroopstfstate7abb"
    container_name       = "platform-tfstate"
    key                  = "workload-hosting.tfstate"
    subscription_id      = "7abbc9d1-585e-452a-9f6d-a137a0015959"
    tenant_id            = "4df935fe-ee7e-4b05-9701-bf58fd1fd854"
    use_azuread_auth     = true
  }
}

provider "azurerm" {
  subscription_id                 = "7abbc9d1-585e-452a-9f6d-a137a0015959"
  tenant_id                       = "4df935fe-ee7e-4b05-9701-bf58fd1fd854"
  resource_provider_registrations = "none"

  features {}
}
