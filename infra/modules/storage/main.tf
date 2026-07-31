locals {
  delete_retention_days = max(var.retention_days, 7)
}

resource "azurerm_storage_account" "artifacts" {
  name                              = var.account_names.artifacts
  location                          = var.location
  resource_group_name               = var.resource_group_name
  account_tier                      = "Standard"
  account_replication_type          = var.artifact_redundancy
  account_kind                      = "StorageV2"
  min_tls_version                   = "TLS1_2"
  shared_access_key_enabled         = false
  default_to_oauth_authentication   = true
  allow_nested_items_to_be_public   = false
  cross_tenant_replication_enabled  = false
  public_network_access_enabled     = !var.enable_private_endpoints
  infrastructure_encryption_enabled = true
  tags                              = var.tags

  blob_properties {
    versioning_enabled            = true
    change_feed_enabled           = true
    change_feed_retention_in_days = local.delete_retention_days

    delete_retention_policy {
      days = local.delete_retention_days
    }

    container_delete_retention_policy {
      days = local.delete_retention_days
    }
  }

  network_rules {
    default_action = var.enable_private_endpoints ? "Deny" : "Allow"
    bypass         = ["AzureServices"]
  }
}

resource "azurerm_storage_account" "executor" {
  name                              = var.account_names.executor
  location                          = var.location
  resource_group_name               = var.resource_group_name
  account_tier                      = "Standard"
  account_replication_type          = var.executor_redundancy
  account_kind                      = "StorageV2"
  min_tls_version                   = "TLS1_2"
  shared_access_key_enabled         = false
  default_to_oauth_authentication   = true
  allow_nested_items_to_be_public   = false
  cross_tenant_replication_enabled  = false
  public_network_access_enabled     = !var.enable_private_endpoints
  infrastructure_encryption_enabled = true
  tags                              = var.tags

  blob_properties {
    versioning_enabled  = true
    change_feed_enabled = true

    delete_retention_policy {
      days = local.delete_retention_days
    }

    container_delete_retention_policy {
      days = local.delete_retention_days
    }
  }

  network_rules {
    default_action = var.enable_private_endpoints ? "Deny" : "Allow"
    bypass         = ["AzureServices"]
  }
}

resource "azurerm_storage_account" "analysis_host" {
  name                              = var.account_names.analysis_host
  location                          = var.location
  resource_group_name               = var.resource_group_name
  account_tier                      = "Standard"
  account_replication_type          = var.host_redundancy
  account_kind                      = "StorageV2"
  min_tls_version                   = "TLS1_2"
  shared_access_key_enabled         = false
  default_to_oauth_authentication   = true
  allow_nested_items_to_be_public   = false
  cross_tenant_replication_enabled  = false
  public_network_access_enabled     = !var.enable_private_endpoints
  infrastructure_encryption_enabled = true
  tags                              = var.tags

  blob_properties {
    delete_retention_policy {
      days = 7
    }

    container_delete_retention_policy {
      days = 7
    }
  }

  network_rules {
    default_action = var.enable_private_endpoints ? "Deny" : "Allow"
    bypass         = ["AzureServices"]
  }
}

resource "azurerm_storage_account" "tfgen_host" {
  name                              = var.account_names.tfgen_host
  location                          = var.location
  resource_group_name               = var.resource_group_name
  account_tier                      = "Standard"
  account_replication_type          = var.host_redundancy
  account_kind                      = "StorageV2"
  min_tls_version                   = "TLS1_2"
  shared_access_key_enabled         = false
  default_to_oauth_authentication   = true
  allow_nested_items_to_be_public   = false
  cross_tenant_replication_enabled  = false
  public_network_access_enabled     = !var.enable_private_endpoints
  infrastructure_encryption_enabled = true
  tags                              = var.tags

  blob_properties {
    delete_retention_policy {
      days = 7
    }

    container_delete_retention_policy {
      days = 7
    }
  }

  network_rules {
    default_action = var.enable_private_endpoints ? "Deny" : "Allow"
    bypass         = ["AzureServices"]
  }
}

resource "azurerm_storage_account" "history_host" {
  name                              = var.account_names.history_host
  location                          = var.location
  resource_group_name               = var.resource_group_name
  account_tier                      = "Standard"
  account_replication_type          = var.host_redundancy
  account_kind                      = "StorageV2"
  min_tls_version                   = "TLS1_2"
  shared_access_key_enabled         = false
  default_to_oauth_authentication   = true
  allow_nested_items_to_be_public   = false
  cross_tenant_replication_enabled  = false
  public_network_access_enabled     = !var.enable_private_endpoints
  infrastructure_encryption_enabled = true
  tags                              = var.tags

  blob_properties {
    delete_retention_policy {
      days = 7
    }

    container_delete_retention_policy {
      days = 7
    }
  }

  network_rules {
    default_action = var.enable_private_endpoints ? "Deny" : "Allow"
    bypass         = ["AzureServices"]
  }
}

locals {
  queue_logging_accounts = {
    artifacts = {
      id             = azurerm_storage_account.artifacts.id
      retention_days = local.delete_retention_days
    }
    executor = {
      id             = azurerm_storage_account.executor.id
      retention_days = local.delete_retention_days
    }
    analysis_host = {
      id             = azurerm_storage_account.analysis_host.id
      retention_days = 7
    }
    tfgen_host = {
      id             = azurerm_storage_account.tfgen_host.id
      retention_days = 7
    }
    history_host = {
      id             = azurerm_storage_account.history_host.id
      retention_days = 7
    }
  }
}

resource "azurerm_storage_account_queue_properties" "logging" {
  for_each = local.queue_logging_accounts

  storage_account_id = each.value.id

  logging {
    delete                = true
    read                  = true
    version               = "1.0"
    write                 = true
    retention_policy_days = each.value.retention_days
  }
}

resource "azurerm_storage_container" "tenant_artifacts" {
  name                  = "tenant-artifacts"
  storage_account_id    = azurerm_storage_account.artifacts.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "workflow_history" {
  name                  = "workflow-history"
  storage_account_id    = azurerm_storage_account.artifacts.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "executor_state" {
  name                  = "terraform-state"
  storage_account_id    = azurerm_storage_account.executor.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "executor_plans" {
  name                  = "saved-plans-private"
  storage_account_id    = azurerm_storage_account.executor.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "analysis_deployment" {
  name                  = "function-releases"
  storage_account_id    = azurerm_storage_account.analysis_host.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "tfgen_deployment" {
  name                  = "function-releases"
  storage_account_id    = azurerm_storage_account.tfgen_host.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "history_deployment" {
  name                  = "function-releases"
  storage_account_id    = azurerm_storage_account.history_host.id
  container_access_type = "private"
}

resource "azurerm_storage_management_policy" "artifacts" {
  storage_account_id = azurerm_storage_account.artifacts.id

  rule {
    name    = "tier-historical-artifacts"
    enabled = true

    filters {
      blob_types = ["blockBlob"]
      # Runtime tenant containers are opaque HMAC names prefixed with `t-`.
      # Keep the legacy aggregate prefix during migration.
      prefix_match = ["t-", "tenant-artifacts/", "workflow-history/"]
    }

    actions {
      base_blob {
        tier_to_cool_after_days_since_modification_greater_than = 30
        delete_after_days_since_modification_greater_than       = max(var.retention_days, 30)
      }

      snapshot {
        delete_after_days_since_creation_greater_than = max(var.retention_days, 30)
      }

      version {
        delete_after_days_since_creation = max(var.retention_days, 30)
      }
    }
  }
}

resource "azurerm_storage_management_policy" "executor" {
  storage_account_id = azurerm_storage_account.executor.id

  rule {
    name    = "expire-saved-plans"
    enabled = true

    filters {
      blob_types   = ["blockBlob"]
      prefix_match = ["saved-plans-private/"]
    }

    actions {
      base_blob {
        delete_after_days_since_modification_greater_than = 7
      }

      version {
        delete_after_days_since_creation = 7
      }
    }
  }
}

locals {
  private_endpoint_targets = {
    artifacts_blob = {
      account_id  = azurerm_storage_account.artifacts.id
      subresource = "blob"
      dns_zone_id = var.private_dns_zone_ids.blob
    }
    executor_blob = {
      account_id  = azurerm_storage_account.executor.id
      subresource = "blob"
      dns_zone_id = var.private_dns_zone_ids.blob
    }
    analysis_host_blob = {
      account_id  = azurerm_storage_account.analysis_host.id
      subresource = "blob"
      dns_zone_id = var.private_dns_zone_ids.blob
    }
    analysis_host_queue = {
      account_id  = azurerm_storage_account.analysis_host.id
      subresource = "queue"
      dns_zone_id = var.private_dns_zone_ids.queue
    }
    analysis_host_table = {
      account_id  = azurerm_storage_account.analysis_host.id
      subresource = "table"
      dns_zone_id = var.private_dns_zone_ids.table
    }
    tfgen_host_blob = {
      account_id  = azurerm_storage_account.tfgen_host.id
      subresource = "blob"
      dns_zone_id = var.private_dns_zone_ids.blob
    }
    tfgen_host_queue = {
      account_id  = azurerm_storage_account.tfgen_host.id
      subresource = "queue"
      dns_zone_id = var.private_dns_zone_ids.queue
    }
    tfgen_host_table = {
      account_id  = azurerm_storage_account.tfgen_host.id
      subresource = "table"
      dns_zone_id = var.private_dns_zone_ids.table
    }
    history_host_blob = {
      account_id  = azurerm_storage_account.history_host.id
      subresource = "blob"
      dns_zone_id = var.private_dns_zone_ids.blob
    }
    history_host_queue = {
      account_id  = azurerm_storage_account.history_host.id
      subresource = "queue"
      dns_zone_id = var.private_dns_zone_ids.queue
    }
    history_host_table = {
      account_id  = azurerm_storage_account.history_host.id
      subresource = "table"
      dns_zone_id = var.private_dns_zone_ids.table
    }
  }
}

resource "azurerm_private_endpoint" "storage" {
  for_each = var.enable_private_endpoints ? local.private_endpoint_targets : {}

  name                = "${replace(each.key, "_", "-")}-pe"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.private_endpoint_subnet_id
  tags                = var.tags

  private_service_connection {
    name                           = "${replace(each.key, "_", "-")}-connection"
    private_connection_resource_id = each.value.account_id
    subresource_names              = [each.value.subresource]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = each.value.subresource
    private_dns_zone_ids = [each.value.dns_zone_id]
  }
}
