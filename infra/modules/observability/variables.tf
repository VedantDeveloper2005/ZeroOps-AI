variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "workspace_name" {
  type = string
}

variable "action_group_name" {
  type = string
}

variable "retention_days" {
  type = number
}

variable "alert_email_receivers" {
  type      = map(string)
  sensitive = true
}

variable "service_bus_namespace_id" {
  type = string
}

variable "storage_account_ids" {
  type = map(string)
}

variable "storage_data_service_ids" {
  type = map(string)
}

variable "tags" {
  type = map(string)
}
