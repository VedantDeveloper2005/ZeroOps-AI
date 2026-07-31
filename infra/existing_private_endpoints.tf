# These endpoints are additive references to existing services. This root does
# not change their public-network flags, application settings, SKU, or lifecycle.
locals {
  existing_private_endpoint_targets = var.enable_private_endpoints ? {
    backend = {
      resource_id = data.azurerm_linux_web_app.backend.id
      subresource = "sites"
      dns_zone_id = try(module.network.private_dns_zone_ids.web, null)
    }
    control_key_vault = {
      resource_id = data.azurerm_key_vault.control.id
      subresource = "vault"
      dns_zone_id = try(module.network.private_dns_zone_ids.key_vault, null)
    }
    postgresql = {
      resource_id = data.azurerm_postgresql_flexible_server.existing.id
      subresource = "postgresqlServer"
      dns_zone_id = try(module.network.private_dns_zone_ids.postgres, null)
    }
  } : {}
}

resource "azurerm_private_endpoint" "existing" {
  for_each = local.existing_private_endpoint_targets

  name                = "${local.prefix}-${replace(each.key, "_", "-")}-pe-${var.name_suffix}"
  location            = data.azurerm_resource_group.platform.location
  resource_group_name = data.azurerm_resource_group.platform.name
  subnet_id           = module.network.subnet_ids.private_endpoints
  tags                = local.standard_tags

  private_service_connection {
    name                           = "${each.key}-connection"
    private_connection_resource_id = each.value.resource_id
    subresource_names              = [each.value.subresource]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = each.key
    private_dns_zone_ids = [each.value.dns_zone_id]
  }
}

