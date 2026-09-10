locals {
  queue_names = {
    repo_analysis        = "repo-analysis"
    terraform_generation = "terraform-generation"
    terraform_plan       = "terraform-plan"
    terraform_apply      = "terraform-apply"
    workflow_events      = "workflow-events"
  }

  executor_queue_ids = {
    terraform_plan  = azurerm_servicebus_queue.queues["terraform_plan"].id
    terraform_apply = azurerm_servicebus_queue.queues["terraform_apply"].id
  }

  publisher_queue_ids = {
    repo_analysis        = azurerm_servicebus_queue.queues["repo_analysis"].id
    terraform_generation = azurerm_servicebus_queue.queues["terraform_generation"].id
    terraform_plan       = azurerm_servicebus_queue.queues["terraform_plan"].id
    terraform_apply      = azurerm_servicebus_queue.queues["terraform_apply"].id
  }

  # These are executor-internal containers, unlike tenant-scoped artifact
  # containers that are created by the application when a tenant first uploads.
  executor_container_names = toset([
    "saved-plans-private",
    "terraform-state",
  ])

  executor_container_scopes = {
    for container_name in local.executor_container_names :
    container_name => "${azurerm_storage_account.executor.id}/blobServices/default/containers/${container_name}"
  }

  vmss_resource_id      = "${azurerm_resource_group.execution.id}/providers/Microsoft.Compute/virtualMachineScaleSets/${var.vmss_name}"
  runner_image_is_valid = var.runner_image_reference != null && startswith(var.runner_image_reference, "${var.registry_name}.azurecr.io/") && can(regex("@sha256:[0-9a-f]{64}$", var.runner_image_reference))
}
