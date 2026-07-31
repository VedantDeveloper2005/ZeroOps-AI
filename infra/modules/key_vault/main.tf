resource "azurerm_key_vault" "analysis" {
  name                          = var.analysis_vault_name
  location                      = var.location
  resource_group_name           = var.resource_group_name
  tenant_id                     = var.tenant_id
  sku_name                      = "standard"
  rbac_authorization_enabled    = true
  purge_protection_enabled      = true
  soft_delete_retention_days    = 90
  public_network_access_enabled = !var.enable_private_endpoints
  tags                          = var.tags

  network_acls {
    bypass         = "AzureServices"
    default_action = var.enable_private_endpoints ? "Deny" : "Allow"
  }
}

resource "azurerm_key_vault" "terraform_generation" {
  name                          = var.terraform_vault_name
  location                      = var.location
  resource_group_name           = var.resource_group_name
  tenant_id                     = var.tenant_id
  sku_name                      = "standard"
  rbac_authorization_enabled    = true
  purge_protection_enabled      = true
  soft_delete_retention_days    = 90
  public_network_access_enabled = !var.enable_private_endpoints
  tags                          = var.tags

  network_acls {
    bypass         = "AzureServices"
    default_action = var.enable_private_endpoints ? "Deny" : "Allow"
  }
}

locals {
  vaults = {
    analysis             = azurerm_key_vault.analysis.id
    terraform_generation = azurerm_key_vault.terraform_generation.id
  }
}

resource "azurerm_private_endpoint" "this" {
  for_each = var.enable_private_endpoints ? local.vaults : {}

  name                = "${each.key}-key-vault-pe"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.private_endpoint_subnet_id
  tags                = var.tags

  private_service_connection {
    name                           = "${each.key}-key-vault-connection"
    private_connection_resource_id = each.value
    subresource_names              = ["vault"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "key-vault"
    private_dns_zone_ids = [var.private_dns_zone_id]
  }
}
