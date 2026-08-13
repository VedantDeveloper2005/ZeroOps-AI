data "azurerm_resource_group" "platform" {
  name = var.resource_group_name
}

data "azurerm_service_plan" "existing" {
  name                = var.existing_service_plan_name
  resource_group_name = data.azurerm_resource_group.platform.name
}

data "azurerm_linux_web_app" "frontend" {
  name                = var.existing_frontend_app_name
  resource_group_name = data.azurerm_resource_group.platform.name
}

data "azurerm_linux_web_app" "backend" {
  name                = var.existing_backend_app_name
  resource_group_name = data.azurerm_resource_group.platform.name
}

data "azurerm_postgresql_flexible_server" "existing" {
  name                = var.existing_postgresql_server_name
  resource_group_name = data.azurerm_resource_group.platform.name
}

data "azurerm_key_vault" "control" {
  name                = var.existing_control_key_vault_name
  resource_group_name = data.azurerm_resource_group.platform.name
}

data "azurerm_user_assigned_identity" "backend" {
  name                = var.existing_backend_identity_name
  resource_group_name = data.azurerm_resource_group.platform.name
}

resource "azurerm_user_assigned_identity" "analysis" {
  name                = local.names.analysis_identity
  location            = data.azurerm_resource_group.platform.location
  resource_group_name = data.azurerm_resource_group.platform.name
  tags                = local.standard_tags
}

resource "azurerm_user_assigned_identity" "terraform_generation" {
  name                = local.names.terraform_identity
  location            = data.azurerm_resource_group.platform.location
  resource_group_name = data.azurerm_resource_group.platform.name
  tags                = local.standard_tags
}

resource "azurerm_user_assigned_identity" "executor" {
  name                = local.names.executor_identity
  location            = data.azurerm_resource_group.platform.location
  resource_group_name = data.azurerm_resource_group.platform.name
  tags                = local.standard_tags
}

resource "azurerm_user_assigned_identity" "history" {
  name                = local.names.history_identity
  location            = data.azurerm_resource_group.platform.location
  resource_group_name = data.azurerm_resource_group.platform.name
  tags                = local.standard_tags
}

module "network" {
  source = "./modules/network"

  name                    = local.names.network
  nat_gateway_name        = local.names.nat_gateway
  location                = data.azurerm_resource_group.platform.location
  resource_group_name     = data.azurerm_resource_group.platform.name
  address_space           = var.vnet_address_space
  subnet_address_prefixes = var.subnet_address_prefixes
  private_dns_zones       = local.private_dns_zones
  enable_private_dns      = var.enable_private_endpoints
  tags                    = local.standard_tags
}

module "storage" {
  source = "./modules/storage"

  location                   = data.azurerm_resource_group.platform.location
  resource_group_name        = data.azurerm_resource_group.platform.name
  account_names              = local.storage_names
  artifact_redundancy        = var.artifact_storage_redundancy
  executor_redundancy        = var.state_storage_redundancy
  host_redundancy            = var.host_storage_redundancy
  retention_days             = var.artifact_retention_days
  enable_private_endpoints   = var.enable_private_endpoints
  private_endpoint_subnet_id = module.network.subnet_ids.private_endpoints
  private_dns_zone_ids = {
    blob  = try(module.network.private_dns_zone_ids.blob, null)
    queue = try(module.network.private_dns_zone_ids.queue, null)
    table = try(module.network.private_dns_zone_ids.table, null)
  }
  tags = local.standard_tags
}

module "model_key_vaults" {
  source = "./modules/key_vault"

  location                   = data.azurerm_resource_group.platform.location
  resource_group_name        = data.azurerm_resource_group.platform.name
  tenant_id                  = var.tenant_id
  analysis_vault_name        = local.names.analysis_key_vault
  terraform_vault_name       = local.names.terraform_key_vault
  enable_private_endpoints   = var.enable_private_endpoints
  private_endpoint_subnet_id = module.network.subnet_ids.private_endpoints
  private_dns_zone_id        = try(module.network.private_dns_zone_ids.key_vault, null)
  tags                       = local.standard_tags
}

module "service_bus" {
  source = "./modules/service_bus"

  name                       = local.names.service_bus
  location                   = data.azurerm_resource_group.platform.location
  resource_group_name        = data.azurerm_resource_group.platform.name
  sku                        = var.service_bus_sku
  capacity                   = var.service_bus_capacity
  queue_names                = local.queue_names
  enable_private_endpoint    = var.enable_private_endpoints
  private_endpoint_subnet_id = module.network.subnet_ids.private_endpoints
  private_dns_zone_id        = try(module.network.private_dns_zone_ids.servicebus, null)
  tags                       = local.standard_tags
}

module "observability" {
  source = "./modules/observability"

  location                 = data.azurerm_resource_group.platform.location
  resource_group_name      = data.azurerm_resource_group.platform.name
  workspace_name           = local.names.log_analytics
  action_group_name        = local.names.action_group
  retention_days           = var.audit_log_retention_days
  alert_email_receivers    = var.alert_email_receivers
  service_bus_namespace_id = module.service_bus.namespace_id
  storage_account_ids      = module.storage.account_ids
  storage_data_service_ids = module.storage.audited_data_service_ids
  tags                     = local.standard_tags
}

module "analysis_function" {
  source = "./modules/function_flex"

  name                                = local.names.analysis_function
  service_plan_name                   = local.names.analysis_function_plan
  location                            = data.azurerm_resource_group.platform.location
  resource_group_name                 = data.azurerm_resource_group.platform.name
  identity_id                         = azurerm_user_assigned_identity.analysis.id
  identity_client_id                  = azurerm_user_assigned_identity.analysis.client_id
  identity_principal_id               = azurerm_user_assigned_identity.analysis.principal_id
  host_storage_account_id             = module.storage.analysis_host_account_id
  host_storage_account_name           = module.storage.analysis_host_account_name
  deployment_container_name           = module.storage.analysis_deployment_container_name
  subnet_id                           = module.network.subnet_ids.analysis_function
  service_bus_namespace               = module.service_bus.fully_qualified_namespace
  model_key_vault_uri                 = module.model_key_vaults.analysis_vault_uri
  model_api_key_setting_name          = "AI_REPOSITORY_API_KEY"
  model_api_key_secret_name           = "ai-repository-api-key"
  fallback_model_api_key_setting_name = "AI_REPOSITORY_FALLBACK_API_KEY"
  fallback_model_api_key_secret_name  = "ai-repository-fallback-api-key"
  app_insights_connection             = module.observability.application_insights_connection_strings.analysis
  app_insights_id                     = module.observability.application_insights_ids.analysis
  max_instances                       = var.analysis_function_max_instances
  instance_memory_mb                  = var.function_instance_memory_mb
  enable_private_networking           = var.enable_private_endpoints
  app_environment                     = "production"
  application_settings = {
    REPOSITORY_ANALYSIS_QUEUE_NAME           = local.queue_names.repo_analysis
    WORKFLOW_EVENTS_QUEUE_NAME               = local.queue_names.workflow_events
    ARTIFACT_STORAGE_ACCOUNT_URL             = "https://${module.storage.artifact_account_name}.blob.core.windows.net"
    AI_REPOSITORY_PROVIDER                   = "nvidia"
    AI_REPOSITORY_ENDPOINT                   = "https://integrate.api.nvidia.com/v1"
    AI_REPOSITORY_MODEL                      = "z-ai/glm-5.2"
    AI_REPOSITORY_PROMPT_VERSION             = "repository-analysis.v1"
    AI_REPOSITORY_FALLBACK_PROVIDER          = "groq"
    AI_REPOSITORY_FALLBACK_ENDPOINT          = "https://api.groq.com/openai/v1"
    AI_REPOSITORY_FALLBACK_MODEL             = "openai/gpt-oss-120b"
    AI_REPOSITORY_FALLBACK_PROMPT_VERSION    = "repository-analysis.v1"
    AI_REPOSITORY_FALLBACK_MAX_INPUT_CHARS   = "14000"
    AI_REPOSITORY_FALLBACK_MAX_OUTPUT_TOKENS = "800"
    AI_REPOSITORY_FALLBACK_TIMEOUT_SECONDS   = "30"
  }
  tags = local.standard_tags

  depends_on = [
    azurerm_role_assignment.analysis_repo_receiver,
    azurerm_role_assignment.analysis_event_sender,
    azurerm_role_assignment.analysis_artifacts,
    azurerm_role_assignment.analysis_model_key,
  ]
}

module "terraform_generation_function" {
  source = "./modules/function_flex"

  name                                = local.names.terraform_function
  service_plan_name                   = local.names.terraform_function_plan
  location                            = data.azurerm_resource_group.platform.location
  resource_group_name                 = data.azurerm_resource_group.platform.name
  identity_id                         = azurerm_user_assigned_identity.terraform_generation.id
  identity_client_id                  = azurerm_user_assigned_identity.terraform_generation.client_id
  identity_principal_id               = azurerm_user_assigned_identity.terraform_generation.principal_id
  host_storage_account_id             = module.storage.tfgen_host_account_id
  host_storage_account_name           = module.storage.tfgen_host_account_name
  deployment_container_name           = module.storage.tfgen_deployment_container_name
  subnet_id                           = module.network.subnet_ids.tfgen_function
  service_bus_namespace               = module.service_bus.fully_qualified_namespace
  model_key_vault_uri                 = module.model_key_vaults.terraform_vault_uri
  model_api_key_setting_name          = "AI_TERRAFORM_API_KEY"
  model_api_key_secret_name           = "ai-terraform-api-key"
  fallback_model_api_key_setting_name = "AI_TERRAFORM_FALLBACK_API_KEY"
  fallback_model_api_key_secret_name  = "ai-terraform-fallback-api-key"
  app_insights_connection             = module.observability.application_insights_connection_strings.terraform_generation
  app_insights_id                     = module.observability.application_insights_ids.terraform_generation
  max_instances                       = var.terraform_function_max_instances
  instance_memory_mb                  = var.function_instance_memory_mb
  enable_private_networking           = var.enable_private_endpoints
  app_environment                     = "production"
  application_settings = {
    TERRAFORM_GENERATION_QUEUE_NAME         = local.queue_names.terraform_generation
    TERRAFORM_PLAN_QUEUE_NAME               = local.queue_names.terraform_plan
    WORKFLOW_EVENTS_QUEUE_NAME              = local.queue_names.workflow_events
    ARTIFACT_STORAGE_ACCOUNT_URL            = "https://${module.storage.artifact_account_name}.blob.core.windows.net"
    AI_TERRAFORM_PROVIDER                   = "nvidia"
    AI_TERRAFORM_ENDPOINT                   = "https://integrate.api.nvidia.com/v1"
    AI_TERRAFORM_MODEL                      = "z-ai/glm-5.2"
    AI_TERRAFORM_PROMPT_VERSION             = "terraform-generation.v1"
    AI_TERRAFORM_FALLBACK_PROVIDER          = "groq"
    AI_TERRAFORM_FALLBACK_ENDPOINT          = "https://api.groq.com/openai/v1"
    AI_TERRAFORM_FALLBACK_MODEL             = "openai/gpt-oss-120b"
    AI_TERRAFORM_FALLBACK_PROMPT_VERSION    = "terraform-generation.v1"
    AI_TERRAFORM_FALLBACK_MAX_INPUT_CHARS   = "14000"
    AI_TERRAFORM_FALLBACK_MAX_OUTPUT_TOKENS = "1000"
    AI_TERRAFORM_FALLBACK_TIMEOUT_SECONDS   = "30"
  }
  tags = local.standard_tags

  depends_on = [
    azurerm_role_assignment.tfgen_receiver,
    azurerm_role_assignment.tfgen_plan_sender,
    azurerm_role_assignment.tfgen_event_sender,
    azurerm_role_assignment.tfgen_artifacts,
    azurerm_role_assignment.tfgen_model_key,
  ]
}

module "history_function" {
  source = "./modules/function_flex"

  name                      = local.names.history_function
  service_plan_name         = local.names.history_function_plan
  location                  = data.azurerm_resource_group.platform.location
  resource_group_name       = data.azurerm_resource_group.platform.name
  identity_id               = azurerm_user_assigned_identity.history.id
  identity_client_id        = azurerm_user_assigned_identity.history.client_id
  identity_principal_id     = azurerm_user_assigned_identity.history.principal_id
  host_storage_account_id   = module.storage.history_host_account_id
  host_storage_account_name = module.storage.history_host_account_name
  deployment_container_name = module.storage.history_deployment_container_name
  subnet_id                 = module.network.subnet_ids.history_function
  service_bus_namespace     = module.service_bus.fully_qualified_namespace
  app_insights_connection   = module.observability.application_insights_connection_strings.history
  app_insights_id           = module.observability.application_insights_ids.history
  max_instances             = var.history_function_max_instances
  instance_memory_mb        = var.function_instance_memory_mb
  enable_private_networking = var.enable_private_endpoints
  app_environment           = "production"
  application_settings = {
    WORKFLOW_EVENTS_QUEUE_NAME = local.queue_names.workflow_events
    POSTGRES_HOST              = data.azurerm_postgresql_flexible_server.existing.fqdn
    POSTGRES_PORT              = "5432"
    POSTGRES_DATABASE          = var.postgres_database_name
    POSTGRES_ENTRA_USER        = azurerm_user_assigned_identity.history.name
    POSTGRES_SSL_MODE          = "verify-full"
  }
  tags = local.standard_tags

  depends_on = [
    azurerm_role_assignment.history_event_receiver,
  ]
}

module "runner" {
  source = "./modules/runner"

  name                           = local.names.vmss
  registry_name                  = local.names.container_registry
  location                       = data.azurerm_resource_group.platform.location
  resource_group_name            = data.azurerm_resource_group.platform.name
  subnet_id                      = module.network.subnet_ids.executor_vmss
  identity_id                    = azurerm_user_assigned_identity.executor.id
  identity_client_id             = azurerm_user_assigned_identity.executor.client_id
  service_bus_namespace          = module.service_bus.fully_qualified_namespace
  plan_queue_name                = local.queue_names.terraform_plan
  plan_queue_id                  = module.service_bus.queue_ids.terraform_plan
  event_queue_name               = local.queue_names.workflow_events
  artifact_storage_account_name  = module.storage.artifact_account_name
  executor_storage_account_name  = module.storage.executor_account_name
  executor_plan_container_name   = module.storage.executor_plan_container_name
  executor_state_container_name  = module.storage.executor_state_container_name
  runner_image_reference         = var.runner_image_reference
  admin_username                 = var.runner_admin_username
  admin_ssh_public_key           = var.runner_admin_ssh_public_key
  sku                            = var.vmss_sku
  zones                          = var.vmss_zones
  max_instances                  = var.vmss_max_instances
  log_analytics_workspace_id     = module.observability.workspace_id
  data_collection_rule_name      = local.names.data_collection_rule
  enable_registry_private_access = var.enable_private_endpoints
  private_endpoint_subnet_id     = module.network.subnet_ids.private_endpoints
  private_dns_zone_id            = try(module.network.private_dns_zone_ids.acr, null)
  tags                           = local.standard_tags

  depends_on = [
    azurerm_role_assignment.executor_plan_receiver,
    azurerm_role_assignment.executor_event_sender,
    azurerm_role_assignment.executor_artifacts,
    azurerm_role_assignment.executor_state,
    azurerm_role_assignment.executor_saved_plans,
  ]
}

check "private_service_bus_requires_premium" {
  assert {
    condition     = !var.enable_private_endpoints || var.service_bus_sku == "Premium"
    error_message = "Service Bus private endpoints require the Premium SKU."
  }
}

check "resource_group_region_matches_plan" {
  assert {
    condition     = lower(replace(data.azurerm_resource_group.platform.location, " ", "")) == lower(replace(var.location, " ", ""))
    error_message = "The existing resource group location must match the approved deployment region."
  }
}

check "production_safety_profile" {
  assert {
    condition = var.environment != "production" || (
      var.enable_private_endpoints &&
      var.service_bus_sku == "Premium" &&
      var.vmss_max_instances <= 10
    )
    error_message = "Production requires private endpoints, Premium Service Bus, and a VMSS cap no greater than 10."
  }
}

check "execution_scope_is_not_platform_scope" {
  assert {
    condition = (
      var.execution_scope_resource_id == null ||
      lower(var.execution_scope_resource_id) != lower(data.azurerm_resource_group.platform.id)
    )
    error_message = "The Terraform executor must never receive Contributor on the ZeroOps platform resource group."
  }
}
