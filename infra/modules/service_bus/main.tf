resource "azurerm_servicebus_namespace" "this" {
  name                          = var.name
  location                      = var.location
  resource_group_name           = var.resource_group_name
  sku                           = var.sku
  capacity                      = var.sku == "Premium" ? var.capacity : 0
  premium_messaging_partitions  = var.sku == "Premium" ? 1 : 0
  minimum_tls_version           = "1.2"
  local_auth_enabled            = false
  public_network_access_enabled = !var.enable_private_endpoint
  tags                          = var.tags

  identity {
    type = "SystemAssigned"
  }

  lifecycle {
    precondition {
      condition     = !var.enable_private_endpoint || var.sku == "Premium"
      error_message = "Service Bus private endpoints require Premium."
    }
  }
}

resource "azurerm_servicebus_queue" "this" {
  for_each = var.queue_names

  name                                    = each.value
  namespace_id                            = azurerm_servicebus_namespace.this.id
  lock_duration                           = "PT5M"
  max_delivery_count                      = 5
  max_size_in_megabytes                   = 1024
  default_message_ttl                     = "P14D"
  dead_lettering_on_message_expiration    = true
  requires_duplicate_detection            = true
  duplicate_detection_history_time_window = "PT10M"
  requires_session                        = contains(["terraform_plan", "terraform_apply", "workflow_events"], each.key)
  batched_operations_enabled              = true
}

resource "azurerm_private_endpoint" "this" {
  count = var.enable_private_endpoint ? 1 : 0

  name                = "${var.name}-pe"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.private_endpoint_subnet_id
  tags                = var.tags

  private_service_connection {
    name                           = "${var.name}-connection"
    private_connection_resource_id = azurerm_servicebus_namespace.this.id
    subresource_names              = ["namespace"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "service-bus"
    private_dns_zone_ids = [var.private_dns_zone_id]
  }
}
