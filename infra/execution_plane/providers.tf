provider "azurerm" {
  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id

  # Registration is a deliberate subscription-level action, never an implicit
  # side effect of plan or apply.
  resource_provider_registrations = "none"

  features {
    resource_group {
      prevent_deletion_if_contains_resources = true
    }

    # The execution storage accounts deliberately reject shared-key access.
    # No queue or static-website data-plane resources are declared here, so
    # disable AzureRM's incompatible shared-key data-plane probe.
    storage {
      data_plane_available = false
    }
  }
}
