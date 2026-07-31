output "function_app_id" {
  value = azapi_resource.this.id
}

output "function_app_name" {
  value = azapi_resource.this.name
}

output "default_hostname" {
  value = try(azapi_resource.this.output.properties.defaultHostName, null)
}

output "service_plan_id" {
  value = azurerm_service_plan.this.id
}

