provider "azurerm" {
  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id
  # Provider registration is a separate subscription-level change and must
  # never happen implicitly during validation or planning.
  resource_provider_registrations = "none"

  features {
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }

    resource_group {
      prevent_deletion_if_contains_resources = true
    }
  }
}

provider "azapi" {
  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id
}
