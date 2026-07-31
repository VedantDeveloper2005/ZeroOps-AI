output "account_ids" {
  value = {
    artifacts     = azurerm_storage_account.artifacts.id
    executor      = azurerm_storage_account.executor.id
    analysis_host = azurerm_storage_account.analysis_host.id
    tfgen_host    = azurerm_storage_account.tfgen_host.id
    history_host  = azurerm_storage_account.history_host.id
  }
}

output "audited_data_service_ids" {
  description = "Data-plane services that carry tenant artifacts, state, and saved plans."
  value = {
    artifacts_blob  = "${azurerm_storage_account.artifacts.id}/blobServices/default"
    artifacts_queue = "${azurerm_storage_account.artifacts.id}/queueServices/default"
    executor_blob   = "${azurerm_storage_account.executor.id}/blobServices/default"
    executor_queue  = "${azurerm_storage_account.executor.id}/queueServices/default"
  }
}

output "artifact_account_id" {
  value = azurerm_storage_account.artifacts.id
}

output "artifact_account_name" {
  value = azurerm_storage_account.artifacts.name
}

output "tenant_artifact_container_name" {
  value = azurerm_storage_container.tenant_artifacts.name
}

output "workflow_history_container_name" {
  value = azurerm_storage_container.workflow_history.name
}

output "executor_account_id" {
  value = azurerm_storage_account.executor.id
}

output "executor_account_name" {
  value = azurerm_storage_account.executor.name
}

output "executor_state_container_id" {
  value = azurerm_storage_container.executor_state.id
}

output "executor_state_container_name" {
  value = azurerm_storage_container.executor_state.name
}

output "executor_plan_container_id" {
  value = azurerm_storage_container.executor_plans.id
}

output "executor_plan_container_name" {
  value = azurerm_storage_container.executor_plans.name
}

output "analysis_host_account_id" {
  value = azurerm_storage_account.analysis_host.id
}

output "analysis_host_account_name" {
  value = azurerm_storage_account.analysis_host.name
}

output "analysis_deployment_container_name" {
  value = azurerm_storage_container.analysis_deployment.name
}

output "tfgen_host_account_id" {
  value = azurerm_storage_account.tfgen_host.id
}

output "tfgen_host_account_name" {
  value = azurerm_storage_account.tfgen_host.name
}

output "tfgen_deployment_container_name" {
  value = azurerm_storage_container.tfgen_deployment.name
}

output "history_host_account_id" {
  value = azurerm_storage_account.history_host.id
}

output "history_host_account_name" {
  value = azurerm_storage_account.history_host.name
}

output "history_deployment_container_name" {
  value = azurerm_storage_container.history_deployment.name
}
