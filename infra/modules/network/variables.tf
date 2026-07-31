variable "name" {
  type = string
}

variable "nat_gateway_name" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "address_space" {
  type = list(string)
}

variable "subnet_address_prefixes" {
  type = object({
    app_integration   = list(string)
    analysis_function = list(string)
    tfgen_function    = list(string)
    history_function  = list(string)
    executor_vmss     = list(string)
    private_endpoints = list(string)
  })
}

variable "private_dns_zones" {
  type = map(string)
}

variable "enable_private_dns" {
  type    = bool
  default = false
}

variable "tags" {
  type = map(string)
}
