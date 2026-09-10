data "azurerm_resource_group" "state" {
  name = var.state_resource_group_name
}

data "azurerm_resource_group" "platform" {
  name = var.platform_resource_group_name
}

data "azurerm_storage_account" "state" {
  name                = var.state_storage_account_name
  resource_group_name = data.azurerm_resource_group.state.name
}

locals {
  state_container_id = "${data.azurerm_storage_account.state.id}/blobServices/default/containers/${var.state_container_name}"
  plan_container_id  = "${data.azurerm_storage_account.state.id}/blobServices/default/containers/${var.plan_container_name}"

  role_definition_ids = {
    reader             = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/acdd72a7-3385-48ef-bd42-f606fba81ae7"
    contributor        = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/b24988ac-6180-42a0-ab88-20f7382dd24c"
    rbac_administrator = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/f58310d9-a9f6-439a-9e8d-f62e7b41a168"
    blob_contributor   = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/ba92f5b4-2d11-453d-a403-e96b0029c9fe"
  }
}

resource "azurerm_user_assigned_identity" "plan" {
  name                = "zeroops-plan-id-${var.name_suffix}"
  location            = data.azurerm_resource_group.state.location
  resource_group_name = data.azurerm_resource_group.state.name
  tags                = var.tags
}

resource "azurerm_user_assigned_identity" "apply" {
  name                = "zeroops-apply-id-${var.name_suffix}"
  location            = data.azurerm_resource_group.state.location
  resource_group_name = data.azurerm_resource_group.state.name
  tags                = var.tags
}

resource "azurerm_federated_identity_credential" "plan_main" {
  name                = "github-main-plan"
  resource_group_name = data.azurerm_resource_group.state.name
  parent_id           = azurerm_user_assigned_identity.plan.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = "https://token.actions.githubusercontent.com"
  subject             = "repo:${var.github_repository}:ref:refs/heads/main"
}

resource "azurerm_federated_identity_credential" "apply_environment" {
  name                = "github-environment-apply"
  resource_group_name = data.azurerm_resource_group.state.name
  parent_id           = azurerm_user_assigned_identity.apply.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = "https://token.actions.githubusercontent.com"
  subject             = "repo:${var.github_repository}:environment:${var.github_apply_environment}"
}

resource "azurerm_role_assignment" "plan_state" {
  scope              = local.state_container_id
  role_definition_id = local.role_definition_ids.blob_contributor
  principal_id       = azurerm_user_assigned_identity.plan.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "plan_saved_plans" {
  scope              = local.plan_container_id
  role_definition_id = local.role_definition_ids.blob_contributor
  principal_id       = azurerm_user_assigned_identity.plan.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "plan_platform_reader" {
  scope              = data.azurerm_resource_group.platform.id
  role_definition_id = local.role_definition_ids.reader
  principal_id       = azurerm_user_assigned_identity.plan.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "apply_state" {
  scope              = local.state_container_id
  role_definition_id = local.role_definition_ids.blob_contributor
  principal_id       = azurerm_user_assigned_identity.apply.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "apply_saved_plans" {
  scope              = local.plan_container_id
  role_definition_id = local.role_definition_ids.blob_contributor
  principal_id       = azurerm_user_assigned_identity.apply.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "apply_platform_contributor" {
  scope              = data.azurerm_resource_group.platform.id
  role_definition_id = local.role_definition_ids.contributor
  principal_id       = azurerm_user_assigned_identity.apply.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "apply_platform_rbac" {
  scope              = data.azurerm_resource_group.platform.id
  role_definition_id = local.role_definition_ids.rbac_administrator
  principal_id       = azurerm_user_assigned_identity.apply.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "plan_execution_reader" {
  count = var.execution_scope_resource_id == null ? 0 : 1

  scope              = var.execution_scope_resource_id
  role_definition_id = local.role_definition_ids.reader
  principal_id       = azurerm_user_assigned_identity.plan.principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_role_assignment" "apply_execution_rbac" {
  count = var.execution_scope_resource_id == null ? 0 : 1

  scope              = var.execution_scope_resource_id
  role_definition_id = local.role_definition_ids.rbac_administrator
  principal_id       = azurerm_user_assigned_identity.apply.principal_id
  principal_type     = "ServicePrincipal"
}

check "state_and_platform_groups_are_separate" {
  assert {
    condition     = lower(data.azurerm_resource_group.state.id) != lower(data.azurerm_resource_group.platform.id)
    error_message = "Remote state and platform resources must use separate resource groups."
  }
}

check "bootstrap_locations_match" {
  assert {
    condition = (
      lower(replace(data.azurerm_resource_group.state.location, " ", "")) == lower(replace(var.location, " ", "")) &&
      lower(replace(data.azurerm_resource_group.platform.location, " ", "")) == lower(replace(var.location, " ", ""))
    )
    error_message = "State and platform resource groups must match the approved bootstrap location."
  }
}

check "customer_scope_is_not_control_plane" {
  assert {
    condition = (
      var.execution_scope_resource_id == null ||
      (
        lower(var.execution_scope_resource_id) != lower(data.azurerm_resource_group.platform.id) &&
        lower(var.execution_scope_resource_id) != lower(data.azurerm_resource_group.state.id)
      )
    )
    error_message = "The customer execution scope cannot be the platform or remote-state resource group."
  }
}
