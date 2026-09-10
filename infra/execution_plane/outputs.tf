output "execution_resource_group_id" {
  value = azurerm_resource_group.execution.id
}

output "demo_workload_resource_group_id" {
  value = azurerm_resource_group.workload.id
}

output "executor_identity" {
  value = {
    id           = azurerm_user_assigned_identity.executor.id
    client_id    = azurerm_user_assigned_identity.executor.client_id
    principal_id = azurerm_user_assigned_identity.executor.principal_id
  }
}

output "service_bus" {
  value = {
    namespace = "${azurerm_servicebus_namespace.execution.name}.servicebus.windows.net"
    queue_ids = { for key, queue in azurerm_servicebus_queue.queues : key => queue.id }
  }
}

output "artifact_storage_account_url" {
  value = azurerm_storage_account.artifacts.primary_blob_endpoint
}

output "executor_storage_account_name" {
  value = azurerm_storage_account.executor.name
}

output "registry_login_server" {
  value = azurerm_container_registry.runner.login_server
}

output "vmss_id" {
  value = try(azurerm_linux_virtual_machine_scale_set.runner[0].id, null)
}
