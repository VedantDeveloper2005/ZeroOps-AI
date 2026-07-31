resource "azurerm_role_assignment" "analysis_repo_receiver" {
  scope              = module.service_bus.queue_ids.repo_analysis
  role_definition_id = local.role_definition_ids.service_bus_receiver
  principal_id       = azurerm_user_assigned_identity.analysis.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "backend_tfgen_sender" {
  scope              = module.service_bus.queue_ids.terraform_generation
  role_definition_id = local.role_definition_ids.service_bus_sender
  principal_id       = data.azurerm_user_assigned_identity.backend.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "analysis_event_sender" {
  scope              = module.service_bus.queue_ids.workflow_events
  role_definition_id = local.role_definition_ids.service_bus_sender
  principal_id       = azurerm_user_assigned_identity.analysis.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "analysis_artifacts" {
  scope              = module.storage.artifact_account_id
  role_definition_id = local.role_definition_ids.blob_contributor
  principal_id       = azurerm_user_assigned_identity.analysis.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "analysis_model_key" {
  scope              = module.model_key_vaults.analysis_vault_id
  role_definition_id = local.role_definition_ids.key_vault_secrets
  principal_id       = azurerm_user_assigned_identity.analysis.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "tfgen_receiver" {
  scope              = module.service_bus.queue_ids.terraform_generation
  role_definition_id = local.role_definition_ids.service_bus_receiver
  principal_id       = azurerm_user_assigned_identity.terraform_generation.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "tfgen_plan_sender" {
  scope              = module.service_bus.queue_ids.terraform_plan
  role_definition_id = local.role_definition_ids.service_bus_sender
  principal_id       = azurerm_user_assigned_identity.terraform_generation.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "tfgen_event_sender" {
  scope              = module.service_bus.queue_ids.workflow_events
  role_definition_id = local.role_definition_ids.service_bus_sender
  principal_id       = azurerm_user_assigned_identity.terraform_generation.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "tfgen_artifacts" {
  scope              = module.storage.artifact_account_id
  role_definition_id = local.role_definition_ids.blob_contributor
  principal_id       = azurerm_user_assigned_identity.terraform_generation.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "tfgen_model_key" {
  scope              = module.model_key_vaults.terraform_vault_id
  role_definition_id = local.role_definition_ids.key_vault_secrets
  principal_id       = azurerm_user_assigned_identity.terraform_generation.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "history_event_receiver" {
  scope              = module.service_bus.queue_ids.workflow_events
  role_definition_id = local.role_definition_ids.service_bus_receiver
  principal_id       = azurerm_user_assigned_identity.history.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "executor_plan_receiver" {
  scope              = module.service_bus.queue_ids.terraform_plan
  role_definition_id = local.role_definition_ids.service_bus_receiver
  principal_id       = azurerm_user_assigned_identity.executor.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "executor_apply_receiver" {
  scope              = module.service_bus.queue_ids.terraform_apply
  role_definition_id = local.role_definition_ids.service_bus_receiver
  principal_id       = azurerm_user_assigned_identity.executor.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "executor_event_sender" {
  scope              = module.service_bus.queue_ids.workflow_events
  role_definition_id = local.role_definition_ids.service_bus_sender
  principal_id       = azurerm_user_assigned_identity.executor.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "executor_artifacts" {
  scope              = module.storage.artifact_account_id
  role_definition_id = local.role_definition_ids.blob_contributor
  principal_id       = azurerm_user_assigned_identity.executor.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "executor_state" {
  scope              = module.storage.executor_state_container_id
  role_definition_id = local.role_definition_ids.blob_owner
  principal_id       = azurerm_user_assigned_identity.executor.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "executor_saved_plans" {
  scope              = module.storage.executor_plan_container_id
  role_definition_id = local.role_definition_ids.blob_owner
  principal_id       = azurerm_user_assigned_identity.executor.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "executor_customer_scope" {
  count = var.execution_scope_resource_id == null ? 0 : 1

  scope              = var.execution_scope_resource_id
  role_definition_id = local.role_definition_ids.contributor
  principal_id       = azurerm_user_assigned_identity.executor.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "backend_repo_sender" {
  scope              = module.service_bus.queue_ids.repo_analysis
  role_definition_id = local.role_definition_ids.service_bus_sender
  principal_id       = data.azurerm_user_assigned_identity.backend.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "backend_apply_sender" {
  scope              = module.service_bus.queue_ids.terraform_apply
  role_definition_id = local.role_definition_ids.service_bus_sender
  principal_id       = data.azurerm_user_assigned_identity.backend.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "backend_artifacts" {
  scope              = module.storage.artifact_account_id
  role_definition_id = local.role_definition_ids.blob_contributor
  principal_id       = data.azurerm_user_assigned_identity.backend.principal_id
  principal_type     = "ServicePrincipal"
}
