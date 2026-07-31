resource "azurerm_log_analytics_workspace" "this" {
  name                       = var.workspace_name
  location                   = var.location
  resource_group_name        = var.resource_group_name
  sku                        = "PerGB2018"
  retention_in_days          = var.retention_days
  daily_quota_gb             = 1
  internet_ingestion_enabled = true
  internet_query_enabled     = true
  tags                       = var.tags
}

resource "azurerm_application_insights" "this" {
  for_each = toset(["frontend", "backend", "analysis", "terraform-generation", "history"])

  name                         = "${var.workspace_name}-${each.key}-appi"
  location                     = var.location
  resource_group_name          = var.resource_group_name
  workspace_id                 = azurerm_log_analytics_workspace.this.id
  application_type             = "web"
  local_authentication_enabled = false
  internet_ingestion_enabled   = true
  internet_query_enabled       = true
  retention_in_days            = var.retention_days
  tags                         = var.tags
}

resource "azurerm_monitor_action_group" "operations" {
  name                = var.action_group_name
  resource_group_name = var.resource_group_name
  short_name          = "zeroopsops"
  enabled             = true
  tags                = var.tags

  dynamic "email_receiver" {
    for_each = nonsensitive(var.alert_email_receivers)

    content {
      name                    = email_receiver.key
      email_address           = email_receiver.value
      use_common_alert_schema = true
    }
  }
}

resource "azurerm_monitor_diagnostic_setting" "service_bus" {
  name                       = "send-to-zeroops-law"
  target_resource_id         = var.service_bus_namespace_id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id

  enabled_log {
    category_group = "allLogs"
  }

  enabled_metric {
    category = "AllMetrics"
  }
}

resource "azurerm_monitor_diagnostic_setting" "storage" {
  for_each = var.storage_account_ids

  name                       = "send-to-zeroops-law"
  target_resource_id         = each.value
  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id

  enabled_metric {
    category = "Transaction"
  }
}

resource "azurerm_monitor_diagnostic_setting" "storage_data_plane" {
  for_each = var.storage_data_service_ids

  name                           = "send-audit-to-zeroops-law"
  target_resource_id             = each.value
  log_analytics_workspace_id     = azurerm_log_analytics_workspace.this.id
  log_analytics_destination_type = "Dedicated"

  enabled_log {
    category_group = "audit"
  }

  enabled_metric {
    category = "Transaction"
  }
}

resource "azurerm_monitor_metric_alert" "dead_letters" {
  name                = "${var.workspace_name}-servicebus-deadletters"
  resource_group_name = var.resource_group_name
  scopes              = [var.service_bus_namespace_id]
  description         = "A workflow queue has dead-lettered messages and needs operator attention."
  severity            = 1
  frequency           = "PT5M"
  window_size         = "PT15M"
  auto_mitigate       = true
  enabled             = true
  tags                = var.tags

  criteria {
    metric_namespace = "Microsoft.ServiceBus/namespaces"
    metric_name      = "DeadletteredMessages"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 0
  }

  action {
    action_group_id = azurerm_monitor_action_group.operations.id
  }
}
