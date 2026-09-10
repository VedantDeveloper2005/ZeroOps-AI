variable "subscription_id" {
  description = "Execution-plane subscription only; never the App Service subscription."
  type        = string
  default     = "7abbc9d1-585e-452a-9f6d-a137a0015959"

  validation {
    condition     = var.subscription_id == "7abbc9d1-585e-452a-9f6d-a137a0015959"
    error_message = "This demo root is intentionally locked to the approved VMSS subscription."
  }
}

variable "tenant_id" {
  description = "Tenant that owns the execution-plane subscription."
  type        = string
  default     = "4df935fe-ee7e-4b05-9701-bf58fd1fd854"
}

variable "location" {
  type    = string
  default = "centralindia"
}

variable "resource_group_name" {
  type    = string
  default = "zeroops-exec-demo-rg"
}

variable "execution_workload_resource_group_name" {
  description = "Dedicated demo scope that the runner may manage; never use zeroops-rg."
  type        = string
  default     = "zeroops-demo-workload-rg"
}

variable "registry_name" {
  type    = string
  default = "zeroopsexec7abb"
}

variable "artifact_storage_account_name" {
  type    = string
  default = "zeroopsexecart7abb"
}

variable "executor_storage_account_name" {
  type    = string
  default = "zeroopsexecstate7abb"
}

variable "service_bus_namespace_name" {
  type    = string
  default = "zeroops-exec-7abb"
}

variable "vmss_name" {
  type    = string
  default = "vmss-zops-tfexec"
}

variable "vmss_sku" {
  type    = string
  default = "Standard_B2as_v2"
}

variable "runner_admin_username" {
  type    = string
  default = "zeroopsrunner"
}

variable "runner_admin_ssh_public_key" {
  description = "Public key only. It is required by Azure even though this VMSS has no inbound public IP."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.runner_admin_ssh_public_key == null || can(regex("^ssh-(rsa|ed25519) ", var.runner_admin_ssh_public_key))
    error_message = "runner_admin_ssh_public_key must be a public OpenSSH RSA or Ed25519 key."
  }
}

variable "runner_os_image_version" {
  description = "An exact Ubuntu Gen2 image version, never latest."
  type        = string
  default     = "22.04.202608060"

  validation {
    condition     = can(regex("^[0-9]+\\.[0-9]+\\.[0-9]+$", var.runner_os_image_version))
    error_message = "runner_os_image_version must be an exact numeric version."
  }
}

variable "runner_image_reference" {
  description = "Immutable ACR image reference including @sha256 digest."
  type        = string
  default     = null
  nullable    = true
}

variable "deploy_runner" {
  description = "The foundation stage is false. Set true only after ACR build returns a digest."
  type        = bool
  default     = false
}

variable "cross_tenant_publisher_principal_id" {
  description = "Target-tenant service-principal object ID for the existing backend's federated publisher."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.cross_tenant_publisher_principal_id == null || can(regex("^[0-9a-fA-F-]{36}$", var.cross_tenant_publisher_principal_id))
    error_message = "cross_tenant_publisher_principal_id must be a GUID or null."
  }
}

variable "tags" {
  type = map(string)
  default = {
    application = "ZeroOps AI"
    environment = "demo"
    managed-by  = "terraform"
    workload    = "terraform-execution"
  }
}
