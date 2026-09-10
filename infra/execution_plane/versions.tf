terraform {
  required_version = "= 1.15.8"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.81"
    }
  }

  # The backend settings are supplied from ignored backend.hcl after the
  # dedicated state account is bootstrapped. State never belongs on a laptop.
  backend "azurerm" {
    use_azuread_auth = true
  }
}
