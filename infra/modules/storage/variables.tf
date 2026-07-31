variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "account_names" {
  type = object({
    artifacts     = string
    executor      = string
    analysis_host = string
    tfgen_host    = string
    history_host  = string
  })
}

variable "artifact_redundancy" {
  type = string
}

variable "executor_redundancy" {
  type = string
}

variable "host_redundancy" {
  type = string
}

variable "retention_days" {
  type = number
}

variable "enable_private_endpoints" {
  type = bool
}

variable "private_endpoint_subnet_id" {
  type = string
}

variable "private_dns_zone_ids" {
  type = object({
    blob  = string
    queue = string
    table = string
  })
}

variable "tags" {
  type = map(string)
}
