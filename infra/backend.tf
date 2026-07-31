terraform {
  # Supply resource_group_name, storage_account_name, container_name, and key
  # at init time through a local backend.hcl file. Never commit backend.hcl.
  backend "azurerm" {
    use_azuread_auth = true
  }
}

