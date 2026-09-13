output "resource_group_name" {
  description = "Existing resource group used by the approved workload hosting resources."
  value       = data.azurerm_resource_group.workload.name
}

output "region" {
  description = "Azure region for the approved workload hosting resources."
  value       = "centralindia"
}

output "app_service_plan_name" {
  description = "Name of the approved Linux App Service plan."
  value       = azurerm_service_plan.workloads.name
}

output "acr_login_server" {
  description = "Login server for the approved Azure Container Registry."
  value       = azurerm_container_registry.workloads.login_server
}
