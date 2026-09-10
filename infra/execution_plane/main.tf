resource "azurerm_resource_group" "execution" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.tags
}

resource "azurerm_resource_group" "workload" {
  name     = var.execution_workload_resource_group_name
  location = var.location
  tags     = merge(var.tags, { purpose = "runner-approved-demo-scope" })
}

resource "azurerm_user_assigned_identity" "executor" {
  name                = "id-zops-exec-vmss"
  location            = azurerm_resource_group.execution.location
  resource_group_name = azurerm_resource_group.execution.name
  tags                = var.tags
}

resource "azurerm_virtual_network" "execution" {
  name                = "vnet-zeroops-exec-demo"
  location            = azurerm_resource_group.execution.location
  resource_group_name = azurerm_resource_group.execution.name
  address_space       = ["10.92.0.0/16"]
  tags                = var.tags
}

resource "azurerm_network_security_group" "runner" {
  name                = "nsg-zeroops-exec-runner"
  location            = azurerm_resource_group.execution.location
  resource_group_name = azurerm_resource_group.execution.name
  tags                = var.tags

  # Default NSG rules deny all inbound Internet traffic. This pull-only runner
  # deliberately has no inbound allow rule and no VM public IP.
}

resource "azurerm_subnet" "runner" {
  name                 = "snet-executor-vmss"
  resource_group_name  = azurerm_resource_group.execution.name
  virtual_network_name = azurerm_virtual_network.execution.name
  address_prefixes     = ["10.92.4.0/24"]
}

resource "azurerm_subnet_network_security_group_association" "runner" {
  subnet_id                 = azurerm_subnet.runner.id
  network_security_group_id = azurerm_network_security_group.runner.id
}

resource "azurerm_public_ip" "nat" {
  name                = "pip-zeroops-exec-nat"
  location            = azurerm_resource_group.execution.location
  resource_group_name = azurerm_resource_group.execution.name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = var.tags
}

resource "azurerm_nat_gateway" "runner" {
  name                = "nat-zeroops-exec-runner"
  location            = azurerm_resource_group.execution.location
  resource_group_name = azurerm_resource_group.execution.name
  sku_name            = "Standard"
  tags                = var.tags
}

resource "azurerm_nat_gateway_public_ip_association" "runner" {
  nat_gateway_id       = azurerm_nat_gateway.runner.id
  public_ip_address_id = azurerm_public_ip.nat.id
}

resource "azurerm_subnet_nat_gateway_association" "runner" {
  subnet_id      = azurerm_subnet.runner.id
  nat_gateway_id = azurerm_nat_gateway.runner.id
}

resource "azurerm_container_registry" "runner" {
  name                          = var.registry_name
  location                      = azurerm_resource_group.execution.location
  resource_group_name           = azurerm_resource_group.execution.name
  sku                           = "Basic"
  admin_enabled                 = false
  anonymous_pull_enabled        = false
  public_network_access_enabled = true
  tags                          = var.tags
}

resource "azurerm_servicebus_namespace" "execution" {
  name                          = var.service_bus_namespace_name
  location                      = azurerm_resource_group.execution.location
  resource_group_name           = azurerm_resource_group.execution.name
  sku                           = "Standard"
  capacity                      = 0
  minimum_tls_version           = "1.2"
  local_auth_enabled            = false
  public_network_access_enabled = true
  tags                          = var.tags
}

resource "azurerm_servicebus_queue" "queues" {
  for_each = local.queue_names

  name                                    = each.value
  namespace_id                            = azurerm_servicebus_namespace.execution.id
  lock_duration                           = "PT5M"
  max_delivery_count                      = 5
  max_size_in_megabytes                   = 1024
  default_message_ttl                     = "P14D"
  dead_lettering_on_message_expiration    = true
  requires_duplicate_detection            = true
  duplicate_detection_history_time_window = "PT10M"
  requires_session                        = contains(["terraform_plan", "terraform_apply", "workflow_events"], each.key)
  batched_operations_enabled              = true
}

resource "azurerm_storage_account" "artifacts" {
  name                              = var.artifact_storage_account_name
  location                          = azurerm_resource_group.execution.location
  resource_group_name               = azurerm_resource_group.execution.name
  account_tier                      = "Standard"
  account_replication_type          = "LRS"
  account_kind                      = "StorageV2"
  min_tls_version                   = "TLS1_2"
  https_traffic_only_enabled        = true
  shared_access_key_enabled         = false
  default_to_oauth_authentication   = true
  allow_nested_items_to_be_public   = false
  cross_tenant_replication_enabled  = false
  public_network_access_enabled     = true
  infrastructure_encryption_enabled = true
  tags                              = var.tags

  blob_properties {
    versioning_enabled = true
    delete_retention_policy { days = 30 }
    container_delete_retention_policy { days = 30 }
  }
}

resource "azurerm_storage_account" "executor" {
  name                              = var.executor_storage_account_name
  location                          = azurerm_resource_group.execution.location
  resource_group_name               = azurerm_resource_group.execution.name
  account_tier                      = "Standard"
  account_replication_type          = "LRS"
  account_kind                      = "StorageV2"
  min_tls_version                   = "TLS1_2"
  https_traffic_only_enabled        = true
  shared_access_key_enabled         = false
  default_to_oauth_authentication   = true
  allow_nested_items_to_be_public   = false
  cross_tenant_replication_enabled  = false
  public_network_access_enabled     = true
  infrastructure_encryption_enabled = true
  tags                              = var.tags

  blob_properties {
    versioning_enabled = true
    delete_retention_policy { days = 30 }
    container_delete_retention_policy { days = 30 }
  }
}

# Storage containers are ARM child resources here rather than AzureRM data-plane
# resources.  That keeps shared-key authentication disabled end-to-end.
resource "azurerm_resource_group_template_deployment" "executor_containers" {
  name                = "zeroops-executor-containers"
  resource_group_name = azurerm_resource_group.execution.name
  deployment_mode     = "Incremental"

  template_content = jsonencode({
    "$schema"      = "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#"
    contentVersion = "1.0.0.0"
    resources = [for container_name in local.executor_container_names : {
      type       = "Microsoft.Storage/storageAccounts/blobServices/containers"
      apiVersion = "2023-05-01"
      name       = "${azurerm_storage_account.executor.name}/default/${container_name}"
      properties = {
        publicAccess = "None"
      }
    }]
  })

  depends_on = [azurerm_storage_account.executor]
}

resource "azurerm_role_assignment" "executor_acr_pull" {
  scope                = azurerm_container_registry.runner.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.executor.principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "executor_artifact_blobs" {
  scope                = azurerm_storage_account.artifacts.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.executor.principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "executor_state_blobs" {
  for_each = local.executor_container_scopes

  scope                = each.value
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = azurerm_user_assigned_identity.executor.principal_id
  principal_type       = "ServicePrincipal"

  depends_on = [azurerm_resource_group_template_deployment.executor_containers]
}

resource "azurerm_role_assignment" "executor_plan_receiver" {
  scope                = azurerm_servicebus_queue.queues["terraform_plan"].id
  role_definition_name = "Azure Service Bus Data Receiver"
  principal_id         = azurerm_user_assigned_identity.executor.principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "executor_apply_receiver" {
  scope                = azurerm_servicebus_queue.queues["terraform_apply"].id
  role_definition_name = "Azure Service Bus Data Receiver"
  principal_id         = azurerm_user_assigned_identity.executor.principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "executor_event_sender" {
  scope                = azurerm_servicebus_queue.queues["workflow_events"].id
  role_definition_name = "Azure Service Bus Data Sender"
  principal_id         = azurerm_user_assigned_identity.executor.principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "executor_demo_scope" {
  scope                = azurerm_resource_group.workload.id
  role_definition_name = "Contributor"
  principal_id         = azurerm_user_assigned_identity.executor.principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "cross_tenant_publisher_queues" {
  for_each = var.cross_tenant_publisher_principal_id == null ? {} : local.publisher_queue_ids

  scope                = each.value
  role_definition_name = "Azure Service Bus Data Sender"
  principal_id         = var.cross_tenant_publisher_principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "cross_tenant_publisher_artifacts" {
  count = var.cross_tenant_publisher_principal_id == null ? 0 : 1

  scope                = azurerm_storage_account.artifacts.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = var.cross_tenant_publisher_principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_linux_virtual_machine_scale_set" "runner" {
  count = var.deploy_runner ? 1 : 0

  name                            = var.vmss_name
  location                        = azurerm_resource_group.execution.location
  resource_group_name             = azurerm_resource_group.execution.name
  sku                             = var.vmss_sku
  instances                       = 0
  priority                        = "Regular"
  upgrade_mode                    = "Manual"
  extension_operations_enabled    = true
  extensions_time_budget          = "PT30M"
  admin_username                  = var.runner_admin_username
  disable_password_authentication = true
  secure_boot_enabled             = true
  vtpm_enabled                    = true
  overprovision                   = false
  single_placement_group          = true
  custom_data = base64encode(templatefile("${path.module}/cloud-init.yaml.tftpl", {
    identity_client_id            = azurerm_user_assigned_identity.executor.client_id
    tenant_id                     = var.tenant_id
    service_bus_namespace         = "${azurerm_servicebus_namespace.execution.name}.servicebus.windows.net"
    plan_queue_name               = azurerm_servicebus_queue.queues["terraform_plan"].name
    apply_queue_name              = azurerm_servicebus_queue.queues["terraform_apply"].name
    event_queue_name              = azurerm_servicebus_queue.queues["workflow_events"].name
    artifact_storage_account_name = azurerm_storage_account.artifacts.name
    executor_storage_account_name = azurerm_storage_account.executor.name
    executor_plan_container_name  = "saved-plans-private"
    executor_state_container_name = "terraform-state"
    vmss_resource_id              = local.vmss_resource_id
    resource_group_name           = azurerm_resource_group.execution.name
    vmss_name                     = var.vmss_name
    registry_name                 = azurerm_container_registry.runner.name
    runner_image_reference        = var.runner_image_reference
  }))
  tags = var.tags

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = var.runner_os_image_version
  }

  admin_ssh_key {
    username   = var.runner_admin_username
    public_key = var.runner_admin_ssh_public_key
  }

  provision_vm_agent = true

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
  }

  network_interface {
    name                          = "${var.vmss_name}-nic"
    primary                       = true
    enable_accelerated_networking = true

    ip_configuration {
      name      = "private"
      primary   = true
      subnet_id = azurerm_subnet.runner.id
      version   = "IPv4"
    }
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.executor.id]
  }

  boot_diagnostics {}

  termination_notification {
    enabled = true
    timeout = "PT5M"
  }

  lifecycle {
    precondition {
      condition     = local.runner_image_is_valid
      error_message = "Runner deployment requires this ACR's immutable sha256 image digest."
    }
    precondition {
      condition     = var.runner_admin_ssh_public_key != null
      error_message = "Runner deployment requires a public SSH key, even though inbound public access is disabled."
    }
  }

  depends_on = [
    azurerm_role_assignment.executor_acr_pull,
    azurerm_role_assignment.executor_artifact_blobs,
    azurerm_role_assignment.executor_state_blobs,
    azurerm_role_assignment.executor_plan_receiver,
    azurerm_role_assignment.executor_apply_receiver,
    azurerm_role_assignment.executor_event_sender,
  ]
}

resource "azurerm_role_assignment" "executor_vmss_control" {
  count = var.deploy_runner ? 1 : 0

  scope                = azurerm_linux_virtual_machine_scale_set.runner[0].id
  role_definition_name = "Virtual Machine Contributor"
  principal_id         = azurerm_user_assigned_identity.executor.principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_monitor_autoscale_setting" "runner" {
  count = var.deploy_runner ? 1 : 0

  name                = "${var.vmss_name}-queue-autoscale"
  resource_group_name = azurerm_resource_group.execution.name
  location            = azurerm_resource_group.execution.location
  target_resource_id  = azurerm_linux_virtual_machine_scale_set.runner[0].id
  enabled             = true
  tags                = var.tags

  profile {
    name = "queue-depth"

    capacity {
      default = "0"
      minimum = "0"
      maximum = "1"
    }

    dynamic "rule" {
      for_each = local.executor_queue_ids

      content {
        metric_trigger {
          metric_name              = "ActiveMessageCount"
          metric_resource_id       = rule.value
          metric_namespace         = "Microsoft.ServiceBus/namespaces/queues"
          time_grain               = "PT1M"
          statistic                = "Average"
          time_window              = "PT5M"
          time_aggregation         = "Average"
          operator                 = "GreaterThan"
          threshold                = 0
          divide_by_instance_count = false
        }

        scale_action {
          direction = "Increase"
          type      = "ChangeCount"
          value     = "1"
          cooldown  = "PT2M"
        }
      }
    }

    dynamic "rule" {
      for_each = local.executor_queue_ids

      content {
        metric_trigger {
          metric_name              = "ActiveMessageCount"
          metric_resource_id       = rule.value
          metric_namespace         = "Microsoft.ServiceBus/namespaces/queues"
          time_grain               = "PT1M"
          statistic                = "Average"
          time_window              = "PT10M"
          time_aggregation         = "Average"
          operator                 = "LessThan"
          threshold                = 1
          divide_by_instance_count = false
        }

        scale_action {
          direction = "Decrease"
          type      = "ChangeCount"
          value     = "1"
          cooldown  = "PT10M"
        }
      }
    }
  }
}
