output "github_configuration" {
  description = "Non-secret IDs to configure as GitHub repository/environment variables."
  value = {
    azure_subscription_id    = var.subscription_id
    azure_tenant_id          = var.tenant_id
    azure_plan_client_id     = azurerm_user_assigned_identity.plan.client_id
    azure_apply_client_id    = azurerm_user_assigned_identity.apply.client_id
    azure_apply_principal_id = azurerm_user_assigned_identity.apply.principal_id
    tf_state_resource_group  = data.azurerm_resource_group.state.name
    tf_state_storage_account = data.azurerm_storage_account.state.name
    tf_state_container       = var.state_container_name
    tf_plan_container        = var.plan_container_name
    github_apply_environment = var.github_apply_environment
  }
}

output "authority_boundaries" {
  value = {
    plan  = "Reader on the platform resource group; Blob Data Contributor only on state and saved-plan containers"
    apply = "Contributor and RBAC Administrator on the platform resource group; optional RBAC Administrator on one customer scope; Blob Data Contributor only on state and saved-plan containers"
  }
}
