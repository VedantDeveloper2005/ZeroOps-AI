locals {
  normalized_environment = lower(var.environment)
  environment_code       = local.normalized_environment == "production" ? "prod" : "test"
  prefix                 = "zeroops-${local.normalized_environment}"

  names = {
    network                 = "${local.prefix}-vnet-${var.name_suffix}"
    nat_gateway             = "${local.prefix}-nat-${var.name_suffix}"
    service_bus             = "${local.prefix}-sb-${var.name_suffix}"
    analysis_identity       = "${local.prefix}-analysis-id-${var.name_suffix}"
    terraform_identity      = "${local.prefix}-tfgen-id-${var.name_suffix}"
    history_identity        = "${local.prefix}-history-id-${var.name_suffix}"
    executor_identity       = "${local.prefix}-tfexec-id-${var.name_suffix}"
    analysis_key_vault      = "kvzoan${local.normalized_environment}${var.name_suffix}"
    terraform_key_vault     = "kvzotf${local.normalized_environment}${var.name_suffix}"
    analysis_function       = "${local.prefix}-analysis-fn-${var.name_suffix}"
    terraform_function      = "${local.prefix}-tfgen-fn-${var.name_suffix}"
    history_function        = "${local.prefix}-history-fn-${var.name_suffix}"
    analysis_function_plan  = "${local.prefix}-analysis-fc1-${var.name_suffix}"
    terraform_function_plan = "${local.prefix}-tfgen-fc1-${var.name_suffix}"
    history_function_plan   = "${local.prefix}-history-fc1-${var.name_suffix}"
    vmss                    = "${local.prefix}-tfexec-vmss-${var.name_suffix}"
    log_analytics           = "${local.prefix}-law-${var.name_suffix}"
    action_group            = "${local.prefix}-ops-ag-${var.name_suffix}"
    data_collection_rule    = "${local.prefix}-runner-dcr-${var.name_suffix}"
    container_registry      = "crzeroops${local.environment_code}${var.name_suffix}"
  }

  storage_names = {
    artifacts     = substr("stzoart${local.normalized_environment}${var.name_suffix}", 0, 24)
    executor      = substr("stzoexec${local.normalized_environment}${var.name_suffix}", 0, 24)
    analysis_host = substr("stzoan${local.normalized_environment}${var.name_suffix}", 0, 24)
    tfgen_host    = substr("stzotf${local.normalized_environment}${var.name_suffix}", 0, 24)
    history_host  = substr("stzohi${local.normalized_environment}${var.name_suffix}", 0, 24)
  }

  standard_tags = merge({
    application = "ZeroOps AI"
    environment = local.normalized_environment
    managed-by  = "terraform"
    workload    = "ai-infrastructure-automation"
  }, var.tags)

  queue_names = {
    repo_analysis        = "repo-analysis"
    terraform_generation = "terraform-generation"
    terraform_plan       = "terraform-plan"
    terraform_apply      = "terraform-apply"
    workflow_events      = "workflow-events"
  }

  role_definition_ids = {
    service_bus_sender   = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/69a216fc-b8fb-44d8-bc22-1f3c2cd27a39"
    service_bus_receiver = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/4f6d3b9b-027b-4f4c-9142-0e5a2a2247e0"
    blob_contributor     = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/ba92f5b4-2d11-453d-a403-e96b0029c9fe"
    blob_reader          = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/2a2b9908-6ea1-4ae2-8e65-a410df84e7d1"
    blob_owner           = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/b7e6dc6d-f1e8-4753-8033-0f276bb0955b"
    key_vault_secrets    = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/4633458b-17de-408a-b874-0445c86b69e6"
    acr_pull             = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/7f951dda-4ed3-4680-a7ca-43fe172d538d"
    reader               = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/acdd72a7-3385-48ef-bd42-f606fba81ae7"
    contributor          = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/b24988ac-6180-42a0-ab88-20f7382dd24c"
    vm_contributor       = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/9980e02c-c2be-4d73-94e8-173b1dc7cf3c"
  }

  private_dns_zones = {
    blob       = "privatelink.blob.core.windows.net"
    queue      = "privatelink.queue.core.windows.net"
    table      = "privatelink.table.core.windows.net"
    key_vault  = "privatelink.vaultcore.azure.net"
    servicebus = "privatelink.servicebus.windows.net"
    acr        = "privatelink.azurecr.io"
    web        = "privatelink.azurewebsites.net"
    postgres   = "privatelink.postgres.database.azure.com"
  }
}
