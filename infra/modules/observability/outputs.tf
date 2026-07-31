output "workspace_id" {
  value = azurerm_log_analytics_workspace.this.id
}

output "workspace_customer_id" {
  value = azurerm_log_analytics_workspace.this.workspace_id
}

output "action_group_id" {
  value = azurerm_monitor_action_group.operations.id
}

output "application_insights_ids" {
  value = {
    for key, app in azurerm_application_insights.this : replace(key, "-", "_") => app.id
  }
}

output "application_insights_connection_strings" {
  sensitive = true
  value = {
    frontend             = azurerm_application_insights.this["frontend"].connection_string
    backend              = azurerm_application_insights.this["backend"].connection_string
    analysis             = azurerm_application_insights.this["analysis"].connection_string
    terraform_generation = azurerm_application_insights.this["terraform-generation"].connection_string
    history              = azurerm_application_insights.this["history"].connection_string
  }
}
