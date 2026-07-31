data "azurerm_resource_group" "this" {
  name = var.resource_group_name
}

resource "azurerm_service_plan" "this" {
  name                = var.service_plan_name
  resource_group_name = var.resource_group_name
  location            = var.location
  os_type             = "Linux"
  sku_name            = "FC1"
  tags                = var.tags
}

resource "azurerm_role_assignment" "host_blob_owner" {
  scope                = var.host_storage_account_id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = var.identity_principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "host_queue_contributor" {
  scope                = var.host_storage_account_id
  role_definition_name = "Storage Queue Data Contributor"
  principal_id         = var.identity_principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "host_table_contributor" {
  scope                = var.host_storage_account_id
  role_definition_name = "Storage Table Data Contributor"
  principal_id         = var.identity_principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "application_insights_publisher" {
  scope                = var.app_insights_id
  role_definition_name = "Monitoring Metrics Publisher"
  principal_id         = var.identity_principal_id
  principal_type       = "ServicePrincipal"
}

resource "time_sleep" "rbac_propagation" {
  depends_on = [
    azurerm_role_assignment.host_blob_owner,
    azurerm_role_assignment.host_queue_contributor,
    azurerm_role_assignment.host_table_contributor,
    azurerm_role_assignment.application_insights_publisher,
  ]

  create_duration = "60s"
}

locals {
  common_app_settings = [
    {
      name  = "APP_ENV"
      value = var.app_environment
    },
    {
      name  = "FUNCTIONS_EXTENSION_VERSION"
      value = "~4"
    },
    {
      name  = "FUNCTIONS_WORKER_RUNTIME"
      value = "python"
    },
    {
      name  = "AzureWebJobsFeatureFlags"
      value = "EnableWorkerIndexing"
    },
    {
      name  = "AzureWebJobsStorage__accountName"
      value = var.host_storage_account_name
    },
    {
      name  = "AzureWebJobsStorage__credential"
      value = "managedidentity"
    },
    {
      name  = "AzureWebJobsStorage__clientId"
      value = var.identity_client_id
    },
    {
      name  = "AzureWebJobsStorage__blobServiceUri"
      value = "https://${var.host_storage_account_name}.blob.core.windows.net"
    },
    {
      name  = "AzureWebJobsStorage__queueServiceUri"
      value = "https://${var.host_storage_account_name}.queue.core.windows.net"
    },
    {
      name  = "AzureWebJobsStorage__tableServiceUri"
      value = "https://${var.host_storage_account_name}.table.core.windows.net"
    },
    {
      name  = "ServiceBusConnection__fullyQualifiedNamespace"
      value = var.service_bus_namespace
    },
    {
      name  = "ServiceBusConnection__credential"
      value = "managedidentity"
    },
    {
      name  = "ServiceBusConnection__clientId"
      value = var.identity_client_id
    },
    {
      name  = "SERVICEBUS_FULLY_QUALIFIED_NAMESPACE"
      value = var.service_bus_namespace
    },
    {
      name  = "AZURE_CLIENT_ID"
      value = var.identity_client_id
    },
    {
      name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
      value = var.app_insights_connection
    },
    {
      name  = "APPLICATIONINSIGHTS_AUTHENTICATION_STRING"
      value = "Authorization=AAD;ClientId=${var.identity_client_id}"
    },
  ]

  workload_app_settings = [
    for name, value in var.application_settings : {
      name  = name
      value = value
    }
  ]

  model_api_key_settings = (
    var.model_key_vault_uri == null ||
    var.model_api_key_setting_name == null ||
    var.model_api_key_secret_name == null
    ) ? [] : [
    {
      name  = var.model_api_key_setting_name
      value = "@Microsoft.KeyVault(SecretUri=${var.model_key_vault_uri}secrets/${var.model_api_key_secret_name})"
    }
  ]

  app_settings = concat(
    local.common_app_settings,
    local.workload_app_settings,
    local.model_api_key_settings,
  )
}

# The current Azure Functions template catalog has no Python + Service Bus
# Terraform template. This composes the official FC1 AzAPI base pattern with
# identity-based Service Bus settings; application code is deployed separately.
resource "azapi_resource" "this" {
  type      = "Microsoft.Web/sites@2024-04-01"
  name      = var.name
  location  = var.location
  parent_id = data.azurerm_resource_group.this.id
  tags      = var.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [var.identity_id]
  }

  body = {
    kind = "functionapp,linux"
    properties = {
      serverFarmId              = azurerm_service_plan.this.id
      httpsOnly                 = true
      clientAffinityEnabled     = false
      publicNetworkAccess       = var.enable_private_networking ? "Disabled" : "Enabled"
      virtualNetworkSubnetId    = var.subnet_id
      keyVaultReferenceIdentity = var.identity_id
      siteConfig = {
        alwaysOn              = false
        ftpsState             = "Disabled"
        http20Enabled         = true
        minTlsVersion         = "1.2"
        use32BitWorkerProcess = false
        appSettings           = local.app_settings
      }
      functionAppConfig = {
        runtime = {
          name    = "python"
          version = "3.13"
        }
        scaleAndConcurrency = {
          maximumInstanceCount = var.max_instances
          instanceMemoryMB     = var.instance_memory_mb
        }
        deployment = {
          storage = {
            type  = "blobContainer"
            value = "https://${var.host_storage_account_name}.blob.core.windows.net/${var.deployment_container_name}"
            authentication = {
              type                           = "UserAssignedIdentity"
              userAssignedIdentityResourceId = var.identity_id
            }
          }
        }
      }
    }
  }

  response_export_values = ["properties.defaultHostName"]

  depends_on = [time_sleep.rbac_propagation]
}
