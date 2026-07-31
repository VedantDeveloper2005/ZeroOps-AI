output "referenced_existing_resources" {
  description = "Read-only references; these resources are not imported or managed by this Terraform root."
  value = {
    service_plan_id      = data.azurerm_service_plan.existing.id
    frontend_app_id      = data.azurerm_linux_web_app.frontend.id
    backend_app_id       = data.azurerm_linux_web_app.backend.id
    postgresql_server_id = data.azurerm_postgresql_flexible_server.existing.id
    control_key_vault_id = data.azurerm_key_vault.control.id
  }
}

output "function_apps" {
  value = {
    analysis             = module.analysis_function.function_app_name
    terraform_generation = module.terraform_generation_function.function_app_name
    history_projection   = module.history_function.function_app_name
  }
}

output "service_bus" {
  value = {
    namespace                 = module.service_bus.namespace_name
    fully_qualified_namespace = module.service_bus.fully_qualified_namespace
    queues                    = module.service_bus.queue_names
  }
}

output "storage" {
  description = "Account and container names only; no keys, SAS tokens, state, or saved plan contents."
  value = {
    artifact_account         = module.storage.artifact_account_name
    executor_account         = module.storage.executor_account_name
    executor_state_container = module.storage.executor_state_container_name
    executor_plan_container  = module.storage.executor_plan_container_name
  }
}

output "model_key_vault_uris" {
  description = "Vault endpoints only. API keys are intentionally not provisioned or output by Terraform."
  value = {
    analysis             = module.model_key_vaults.analysis_vault_uri
    terraform_generation = module.model_key_vaults.terraform_vault_uri
  }
}

output "runner" {
  value = {
    vmss_id       = module.runner.vmss_id
    registry_name = module.runner.registry_name
    min_instances = 0
    max_instances = var.vmss_max_instances
  }
}
