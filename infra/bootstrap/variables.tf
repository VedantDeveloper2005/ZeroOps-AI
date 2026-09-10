variable "subscription_id" {
  type     = string
  nullable = false
}

variable "tenant_id" {
  type     = string
  nullable = false
}

variable "location" {
  type    = string
  default = "centralindia"
}

variable "platform_resource_group_name" {
  type    = string
  default = "zeroops-rg"
}

variable "state_resource_group_name" {
  type    = string
  default = "zeroops-tfstate-rg"
}

variable "state_storage_account_name" {
  description = "Existing state account created by bootstrap-state.ps1."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]{3,24}$", var.state_storage_account_name))
    error_message = "state_storage_account_name must be a valid Azure Storage account name."
  }
}

variable "state_container_name" {
  type    = string
  default = "platform-tfstate"
}

variable "plan_container_name" {
  type    = string
  default = "deployment-plans"
}

variable "execution_scope_resource_id" {
  description = "Optional dedicated customer workload resource-group ID. When set, plan gets Reader and apply gets RBAC Administrator only so Terraform can bind the executor identity."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition = (
      var.execution_scope_resource_id == null ||
      can(regex("^/subscriptions/[^/]+/resourceGroups/[^/]+$", var.execution_scope_resource_id))
    )
    error_message = "execution_scope_resource_id must be a resource-group ID or null."
  }
}

variable "github_repository" {
  description = "GitHub repository in owner/name form."
  type        = string
  default     = "VedantDeveloper2005/ZeroOps-AI"

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository must use owner/name form."
  }
}

variable "github_apply_environment" {
  description = "Protected GitHub environment used only by mutation jobs."
  type        = string
  default     = "azure-test-apply"

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]{1,64}$", var.github_apply_environment))
    error_message = "github_apply_environment contains unsupported characters."
  }
}

variable "name_suffix" {
  type    = string
  default = "2f871a"

  validation {
    condition     = can(regex("^[a-z0-9]{6,12}$", var.name_suffix))
    error_message = "name_suffix must contain 6-12 lowercase alphanumeric characters."
  }
}

variable "tags" {
  type = map(string)
  default = {
    application = "ZeroOps AI"
    managed-by  = "terraform-bootstrap"
    workload    = "deployment-identity"
  }
}
