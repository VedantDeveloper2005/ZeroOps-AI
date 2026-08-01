variable "name" {
  type = string
}

variable "service_plan_name" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "identity_id" {
  type = string
}

variable "identity_client_id" {
  type = string
}

variable "identity_principal_id" {
  type = string
}

variable "host_storage_account_id" {
  type = string
}

variable "host_storage_account_name" {
  type = string
}

variable "deployment_container_name" {
  type = string
}

variable "subnet_id" {
  type = string
}

variable "service_bus_namespace" {
  type = string
}

variable "model_key_vault_uri" {
  type     = string
  default  = null
  nullable = true
}

variable "model_api_key_setting_name" {
  type     = string
  default  = null
  nullable = true
}

variable "model_api_key_secret_name" {
  type     = string
  default  = null
  nullable = true
}

variable "fallback_model_api_key_setting_name" {
  type     = string
  default  = null
  nullable = true
}

variable "fallback_model_api_key_secret_name" {
  type     = string
  default  = null
  nullable = true
}

variable "application_settings" {
  type    = map(string)
  default = {}
}

variable "app_environment" {
  type = string
}

variable "app_insights_connection" {
  type      = string
  sensitive = true
}

variable "app_insights_id" {
  type = string
}

variable "max_instances" {
  type = number
}

variable "instance_memory_mb" {
  type = number
}

variable "enable_private_networking" {
  type = bool
}

variable "tags" {
  type = map(string)
}
