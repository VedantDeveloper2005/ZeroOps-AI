variable "subscription_id" {
  description = "Azure subscription that contains the existing ZeroOps resource group."
  type        = string
  nullable    = false
}

variable "tenant_id" {
  description = "Microsoft Entra tenant ID. Authentication is supplied out of band."
  type        = string
  nullable    = false
}

variable "resource_group_name" {
  description = "Existing resource group. Terraform references it and does not create or import it."
  type        = string
  default     = "zeroops-rg"
}

variable "location" {
  description = "Azure region for new resources."
  type        = string
  default     = "centralindia"
}

variable "environment" {
  description = "Deployment profile."
  type        = string
  default     = "test"

  validation {
    condition     = contains(["test", "production"], var.environment)
    error_message = "environment must be either test or production."
  }
}

variable "name_suffix" {
  description = "Approved deterministic suffix used for globally unique names."
  type        = string
  default     = "2f871a"

  validation {
    condition     = can(regex("^[a-z0-9]{6,12}$", var.name_suffix))
    error_message = "name_suffix must contain 6-12 lowercase alphanumeric characters."
  }
}

variable "existing_service_plan_name" {
  type    = string
  default = "ASP-zeroopsrg-8559"
}

variable "existing_frontend_app_name" {
  type    = string
  default = "zeroopsai"
}

variable "existing_backend_app_name" {
  type    = string
  default = "zeroops-backend"
}

variable "existing_postgresql_server_name" {
  type    = string
  default = "zeroops-db-prod"
}

variable "existing_control_key_vault_name" {
  type    = string
  default = "zeroops-kv-prod"
}

variable "existing_backend_identity_name" {
  type    = string
  default = "zeroops-backend-id-96a7"
}

variable "vnet_address_space" {
  description = "Address space reserved for the ZeroOps execution plane."
  type        = list(string)
  default     = ["10.72.0.0/16"]
}

variable "subnet_address_prefixes" {
  description = "Non-overlapping subnet prefixes."
  type = object({
    app_integration   = list(string)
    analysis_function = list(string)
    tfgen_function    = list(string)
    history_function  = list(string)
    executor_vmss     = list(string)
    private_endpoints = list(string)
  })
  default = {
    app_integration   = ["10.72.0.0/24"]
    analysis_function = ["10.72.1.0/24"]
    tfgen_function    = ["10.72.2.0/24"]
    history_function  = ["10.72.3.0/24"]
    executor_vmss     = ["10.72.4.0/24"]
    private_endpoints = ["10.72.5.0/24"]
  }
}

variable "enable_private_endpoints" {
  description = "Enable production PaaS private endpoints and private DNS."
  type        = bool
  default     = false
}

variable "service_bus_sku" {
  description = "Standard for test; Premium is required when private endpoints are enabled."
  type        = string
  default     = "Standard"

  validation {
    condition     = contains(["Standard", "Premium"], var.service_bus_sku)
    error_message = "service_bus_sku must be Standard or Premium."
  }
}

variable "service_bus_capacity" {
  description = "Premium messaging units. Ignored for Standard."
  type        = number
  default     = 1
}

variable "artifact_storage_redundancy" {
  type    = string
  default = "ZRS"
}

variable "state_storage_redundancy" {
  type    = string
  default = "ZRS"
}

variable "host_storage_redundancy" {
  type    = string
  default = "LRS"
}

variable "artifact_retention_days" {
  description = "Soft-delete and historical artifact retention."
  type        = number
  default     = 30
}

variable "audit_log_retention_days" {
  type    = number
  default = 30
}

variable "analysis_function_max_instances" {
  type    = number
  default = 2
}

variable "terraform_function_max_instances" {
  type    = number
  default = 2
}

variable "history_function_max_instances" {
  type    = number
  default = 2
}

variable "postgres_database_name" {
  description = "Existing ZeroOps application database used by the history projector."
  type        = string
  default     = "zeroops"
}

variable "function_instance_memory_mb" {
  type    = number
  default = 2048

  validation {
    condition     = contains([512, 2048, 4096], var.function_instance_memory_mb)
    error_message = "Flex Consumption memory must be 512, 2048, or 4096 MB."
  }
}

variable "repository_ai_provider" {
  description = "Primary provider for repository analysis. Only Microsoft Foundry deployments are supported."
  type        = string
  default     = "azure-openai"

  validation {
    condition     = contains(["azure-openai"], var.repository_ai_provider)
    error_message = "repository_ai_provider must be azure-openai."
  }
}

variable "repository_ai_endpoint" {
  description = "Non-secret endpoint for repository analysis. Azure OpenAI must use https://<resource>.openai.azure.com/openai/v1."
  type        = string
  default     = ""
}

variable "repository_ai_model" {
  description = "Microsoft Foundry Azure OpenAI deployment name for repository analysis."
  type        = string
  default     = ""
}

variable "terraform_ai_provider" {
  description = "Primary provider for Terraform generation. Only Microsoft Foundry deployments are supported."
  type        = string
  default     = "azure-openai"

  validation {
    condition     = contains(["azure-openai"], var.terraform_ai_provider)
    error_message = "terraform_ai_provider must be azure-openai."
  }
}

variable "terraform_ai_endpoint" {
  description = "Non-secret endpoint for Terraform generation. Azure OpenAI must use https://<resource>.openai.azure.com/openai/v1."
  type        = string
  default     = ""
}

variable "terraform_ai_model" {
  description = "Microsoft Foundry Azure OpenAI deployment name for Terraform generation."
  type        = string
  default     = ""
}

variable "vmss_sku" {
  description = "Regular (non-Spot) worker VM size."
  type        = string
  default     = "Standard_B2as_v2"
}

variable "vmss_zones" {
  type    = list(string)
  default = ["1", "2"]
}

variable "vmss_max_instances" {
  description = "Maximum Terraform executor instances."
  type        = number
  default     = 1

  validation {
    condition     = var.vmss_max_instances >= 1 && var.vmss_max_instances <= 10
    error_message = "vmss_max_instances must be between 1 and 10."
  }
}

variable "deploy_runner" {
  description = "Create the VMSS only after a runner image has been pushed and pinned by digest. The registry is created even when this is false."
  type        = bool
  default     = false
}

variable "runner_os_image_version" {
  description = "Exact Canonical Ubuntu 22.04 Gen2 image version for the runner. Mutable labels such as latest are rejected."
  type        = string
  default     = "22.04.202608060"

  validation {
    condition     = can(regex("^[0-9]+\\.[0-9]+\\.[0-9]+$", var.runner_os_image_version))
    error_message = "runner_os_image_version must be an exact numeric image version, never latest."
  }
}

variable "runner_admin_username" {
  type    = string
  default = "zeroopsrunner"
}

variable "runner_admin_ssh_public_key" {
  description = "SSH public key only. Private keys must never be supplied to Terraform."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^ssh-(rsa|ed25519) ", var.runner_admin_ssh_public_key))
    error_message = "runner_admin_ssh_public_key must be an OpenSSH RSA or Ed25519 public key."
  }
}

variable "runner_image_reference" {
  description = "Immutable ACR image reference including @sha256:digest."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition = (
      (!var.deploy_runner && var.runner_image_reference == null) ||
      (var.deploy_runner && var.runner_image_reference != null && can(regex("@sha256:[0-9a-f]{64}$", var.runner_image_reference)))
    )
    error_message = "runner_image_reference must be null during foundation deployment and a real immutable sha256 reference when deploy_runner is true."
  }
}

variable "deployment_identity_principal_id" {
  description = "Object ID of the dedicated federated apply identity. Used only for release publishing access; never use the validation VM identity."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition = (
      var.deployment_identity_principal_id == null ||
      can(regex("^[0-9a-fA-F-]{36}$", var.deployment_identity_principal_id))
    )
    error_message = "deployment_identity_principal_id must be a managed-identity object ID or null."
  }
}

variable "execution_scope_resource_id" {
  description = "Optional dedicated customer workload resource-group ID on which the executor receives Contributor. Never point this at the platform resource group or subscription."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition = (
      var.execution_scope_resource_id == null ||
      can(regex("^/subscriptions/[^/]+/resourceGroups/[^/]+$", var.execution_scope_resource_id))
    )
    error_message = "execution_scope_resource_id must be a resource-group resource ID or null."
  }
}

variable "budget_enabled" {
  type    = bool
  default = false
}

variable "budget_amount" {
  description = "Monthly resource-group budget. Required and greater than zero when budget_enabled is true."
  type        = number
  default     = 0
}

variable "budget_start_date" {
  description = "ISO 8601 first day of a month, for example 2026-08-01T00:00:00Z."
  type        = string
  default     = null
  nullable    = true
}

variable "budget_end_date" {
  description = "ISO 8601 budget end date."
  type        = string
  default     = null
  nullable    = true
}

variable "alert_email_receivers" {
  description = "Map of Azure Monitor receiver names to email addresses."
  type        = map(string)
  default     = {}
  sensitive   = true
}

variable "tags" {
  type        = map(string)
  description = "Additional non-secret resource tags."
  default     = {}
}
