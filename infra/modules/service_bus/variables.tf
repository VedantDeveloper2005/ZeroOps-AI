variable "name" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "sku" {
  type = string
}

variable "capacity" {
  type = number
}

variable "queue_names" {
  type = map(string)
}

variable "enable_private_endpoint" {
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

