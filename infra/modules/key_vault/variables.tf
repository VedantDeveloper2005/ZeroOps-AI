variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "tenant_id" {
  type = string
}

variable "analysis_vault_name" {
  type = string
}

variable "terraform_vault_name" {
  type = string
}

variable "enable_private_endpoints" {
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

