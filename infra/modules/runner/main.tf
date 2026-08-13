data "azurerm_resource_group" "this" {
  name = var.resource_group_name
}

resource "azurerm_container_registry" "this" {
  name                          = var.registry_name
  resource_group_name           = var.resource_group_name
  location                      = var.location
  sku                           = var.enable_registry_private_access ? "Premium" : "Basic"
  admin_enabled                 = false
  anonymous_pull_enabled        = false
  data_endpoint_enabled         = var.enable_registry_private_access
  public_network_access_enabled = !var.enable_registry_private_access
  retention_policy_in_days      = var.enable_registry_private_access ? 7 : 0
  zone_redundancy_enabled       = var.enable_registry_private_access
  tags                          = var.tags
}

data "azurerm_user_assigned_identity" "executor" {
  name                = reverse(split("/", var.identity_id))[0]
  resource_group_name = var.resource_group_name
}

resource "azurerm_role_assignment" "executor_acr_pull_by_identity" {
  scope                = azurerm_container_registry.this.id
  role_definition_name = "AcrPull"
  principal_id         = data.azurerm_user_assigned_identity.executor.principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_private_endpoint" "registry" {
  count = var.enable_registry_private_access ? 1 : 0

  name                = "${var.registry_name}-pe"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.private_endpoint_subnet_id
  tags                = var.tags

  private_service_connection {
    name                           = "${var.registry_name}-connection"
    private_connection_resource_id = azurerm_container_registry.this.id
    subresource_names              = ["registry"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "acr"
    private_dns_zone_ids = [var.private_dns_zone_id]
  }
}

locals {
  vmss_resource_id = "${data.azurerm_resource_group.this.id}/providers/Microsoft.Compute/virtualMachineScaleSets/${var.name}"
  queue_metric_ids = {
    plan = var.plan_queue_id
  }
  custom_data = base64encode(templatefile("${path.module}/cloud-init.yaml.tftpl", {
    identity_client_id            = var.identity_client_id
    service_bus_namespace         = var.service_bus_namespace
    plan_queue_name               = var.plan_queue_name
    event_queue_name              = var.event_queue_name
    artifact_storage_account_name = var.artifact_storage_account_name
    executor_storage_account_name = var.executor_storage_account_name
    executor_plan_container_name  = var.executor_plan_container_name
    executor_state_container_name = var.executor_state_container_name
    vmss_resource_id              = local.vmss_resource_id
    resource_group_name           = var.resource_group_name
    vmss_name                     = var.name
    registry_name                 = var.registry_name
    runner_image_reference        = var.runner_image_reference
  }))
}

resource "azurerm_orchestrated_virtual_machine_scale_set" "this" {
  name                         = var.name
  location                     = var.location
  resource_group_name          = var.resource_group_name
  platform_fault_domain_count  = 1
  zones                        = var.zones
  zone_balance                 = true
  sku_name                     = var.sku
  instances                    = 0
  priority                     = "Regular"
  upgrade_mode                 = "Manual"
  extension_operations_enabled = true
  extensions_time_budget       = "PT30M"
  tags                         = var.tags

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  os_profile {
    custom_data = local.custom_data

    linux_configuration {
      admin_username                  = var.admin_username
      disable_password_authentication = true
      patch_assessment_mode           = "AutomaticByPlatform"
      patch_mode                      = "ImageDefault"
      provision_vm_agent              = true

      admin_ssh_key {
        username   = var.admin_username
        public_key = var.admin_ssh_public_key
      }
    }
  }

  os_disk {
    caching              = "ReadOnly"
    storage_account_type = "StandardSSD_LRS"

    diff_disk_settings {
      option    = "Local"
      placement = "ResourceDisk"
    }
  }

  network_interface {
    name                          = "${var.name}-nic"
    primary                       = true
    enable_accelerated_networking = true

    ip_configuration {
      name      = "private"
      primary   = true
      subnet_id = var.subnet_id
      version   = "IPv4"
    }
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [var.identity_id]
  }

  extension {
    name                               = "AzureMonitorLinuxAgent"
    publisher                          = "Microsoft.Azure.Monitor"
    type                               = "AzureMonitorLinuxAgent"
    type_handler_version               = "1.33"
    auto_upgrade_minor_version_enabled = true
    settings = jsonencode({
      authentication = {
        managedIdentity = {
          "identifier-name"  = "mi_res_id"
          "identifier-value" = var.identity_id
        }
      }
    })
  }

  boot_diagnostics {}

  termination_notification {
    enabled = true
    timeout = "PT5M"
  }

  lifecycle {
    precondition {
      condition     = startswith(var.runner_image_reference, "${var.registry_name}.azurecr.io/") && can(regex("@sha256:[0-9a-f]{64}$", var.runner_image_reference))
      error_message = "runner_image_reference must use this module's ACR and an immutable sha256 digest."
    }
  }

  depends_on = [azurerm_role_assignment.executor_acr_pull_by_identity]
}

# AzureRM's Flexible VMSS resource does not yet expose the complete Trusted
# Launch profile. Keep the VMSS model in AzureRM and patch only those settings.
resource "azapi_update_resource" "trusted_launch" {
  type        = "Microsoft.Compute/virtualMachineScaleSets@2024-11-01"
  resource_id = azurerm_orchestrated_virtual_machine_scale_set.this.id

  body = {
    properties = {
      virtualMachineProfile = {
        securityProfile = {
          securityType = "TrustedLaunch"
          uefiSettings = {
            secureBootEnabled = true
            vTpmEnabled       = true
          }
        }
      }
    }
  }
}

resource "azurerm_monitor_autoscale_setting" "this" {
  name                = "${var.name}-queue-autoscale"
  resource_group_name = var.resource_group_name
  location            = var.location
  target_resource_id  = azurerm_orchestrated_virtual_machine_scale_set.this.id
  enabled             = true
  tags                = var.tags

  profile {
    name = "queue-depth"

    capacity {
      default = "0"
      minimum = "0"
      maximum = tostring(var.max_instances)
    }

    dynamic "rule" {
      for_each = local.queue_metric_ids

      content {
        metric_trigger {
          metric_name              = "ActiveMessageCount"
          metric_resource_id       = rule.value
          metric_namespace         = ""
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
      for_each = local.queue_metric_ids

      content {
        metric_trigger {
          metric_name              = "ActiveMessageCount"
          metric_resource_id       = rule.value
          metric_namespace         = ""
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

resource "azurerm_monitor_data_collection_rule" "runner" {
  name                = var.data_collection_rule_name
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = var.tags

  destinations {
    log_analytics {
      workspace_resource_id = var.log_analytics_workspace_id
      name                  = "zeroops-law"
    }
  }

  data_flow {
    streams      = ["Microsoft-Syslog"]
    destinations = ["zeroops-law"]
  }

  data_sources {
    syslog {
      name           = "runner-syslog"
      facility_names = ["auth", "authpriv", "daemon", "syslog", "user"]
      log_levels     = ["Info", "Notice", "Warning", "Error", "Critical", "Alert", "Emergency"]
      streams        = ["Microsoft-Syslog"]
    }
  }
}

resource "azurerm_monitor_data_collection_rule_association" "runner" {
  name                    = "${var.name}-dcr-association"
  target_resource_id      = azurerm_orchestrated_virtual_machine_scale_set.this.id
  data_collection_rule_id = azurerm_monitor_data_collection_rule.runner.id
}

resource "azurerm_role_assignment" "executor_vmss_control" {
  scope                = azurerm_orchestrated_virtual_machine_scale_set.this.id
  role_definition_name = "Virtual Machine Contributor"
  principal_id         = data.azurerm_user_assigned_identity.executor.principal_id
  principal_type       = "ServicePrincipal"
}
