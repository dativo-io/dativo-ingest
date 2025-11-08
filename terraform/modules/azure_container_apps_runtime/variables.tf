variable "region" {
  description = "Azure region (location) for Container Apps deployment."
  type        = string
}

variable "runtime_type" {
  description = "Runtime selector. Must be set to \"azure_container_apps\" when using this module."
  type        = string
  default     = "azure_container_apps"

  validation {
    condition     = var.runtime_type == "azure_container_apps"
    error_message = "runtime_type must be \"azure_container_apps\" for the Azure Container Apps module."
  }
}

variable "tags" {
  description = "Job metadata propagated from Dativo job configuration. Required keys: job_name, team, pipeline_type, environment, cost_center."
  type        = map(string)
}

variable "resource_group_name" {
  description = "Azure resource group that hosts the Container Apps environment."
  type        = string
}

variable "default_tags" {
  description = "Default platform tags applied to every Azure resource (e.g., owner, subscription metadata)."
  type        = map(string)
  default     = {}
}

variable "service_name_override" {
  description = "Optional override for the Container App service name."
  type        = string
  default     = ""
}

variable "environment_name_override" {
  description = "Optional override for the Container Apps environment name."
  type        = string
  default     = ""
}

variable "endpoint_url_override" {
  description = "Optional override for the Container Apps default endpoint."
  type        = string
  default     = ""
}
