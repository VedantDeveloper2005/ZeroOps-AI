variable "name" {
  type = string
}

variable "registry_name" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "subnet_id" {
  type = string
}

variable "identity_id" {
  type = string
}

variable "identity_client_id" {
  type = string
}

variable "service_bus_namespace" {
  type = string
}

variable "plan_queue_name" {
  type = string
}

variable "plan_queue_id" {
  type = string
}

variable "event_queue_name" {
  type = string
}

variable "artifact_storage_account_name" {
  type = string
}

variable "executor_storage_account_name" {
  type = string
}

variable "executor_plan_container_name" {
  type = string
}

variable "executor_state_container_name" {
  type = string
}

variable "runner_image_reference" {
  type = string
}

variable "admin_username" {
  type = string
}

variable "admin_ssh_public_key" {
  type = string
}

variable "sku" {
  type = string
}

variable "zones" {
  type = list(string)
}

variable "max_instances" {
  type = number
}

variable "log_analytics_workspace_id" {
  type = string
}

variable "data_collection_rule_name" {
  type = string
}

variable "enable_registry_private_access" {
  type = bool
}

variable "private_endpoint_subnet_id" {
  type = string
}

variable "private_dns_zone_id" {
  type     = string
  nullable = true
}

variable "tags" {
  type = map(string)
}
