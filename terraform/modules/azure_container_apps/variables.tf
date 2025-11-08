variable "region" {
  description = "Azure region where the Container Apps environment resides."
  type        = string
}

variable "runtime_type" {
  description = "Runtime identifier propagated from the Dativo job configuration."
  type        = string
  default     = "azure_container_apps"

  validation {
    condition     = var.runtime_type == "azure_container_apps"
    error_message = "This module only supports the azure_container_apps runtime."
  }
}

variable "subscription_id" {
  description = "Azure subscription ID used for deployment."
  type        = string
}

variable "tenant_id" {
  description = "Azure AD tenant ID used for authentication."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group containing the Container Apps environment and related resources."
  type        = string
}

variable "tags" {
  description = "Job metadata tags propagated from the Dativo job definition."
  type        = map(string)
}

variable "default_tags" {
  description = "Baseline platform tags merged with the job metadata."
  type        = map(string)
  default     = {}
}

variable "existing_environment_name" {
  description = "Optional pre-created Container Apps environment name."
  type        = string
  default     = null
}

variable "existing_container_app_name" {
  description = "Optional pre-created Container App name."
  type        = string
  default     = null
}

variable "ingress_url_override" {
  description = "Optional ingress URL override when sourced from another module."
  type        = string
  default     = null
}

variable "deploy_example_resources" {
  description = "Set to true to create a sample resource group showing tag propagation."
  type        = bool
  default     = false
}

