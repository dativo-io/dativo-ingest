# Azure Container Apps Module Variables

variable "region" {
  description = "Azure region for deployment (e.g., eastus, westus2, westeurope)"
  type        = string
}

variable "job_metadata" {
  description = "Job metadata tags from Dativo job config (job_name, team, pipeline_type, environment, cost_center)"
  type        = map(string)

  validation {
    condition = alltrue([
      contains(keys(var.job_metadata), "job_name"),
      contains(keys(var.job_metadata), "team"),
      contains(keys(var.job_metadata), "pipeline_type"),
      contains(keys(var.job_metadata), "environment"),
      contains(keys(var.job_metadata), "cost_center")
    ])
    error_message = "job_metadata must contain: job_name, team, pipeline_type, environment, cost_center"
  }
}

variable "default_tags" {
  description = "Default tags to apply to all resources"
  type        = map(string)
  default     = {}
}

variable "create_resource_group" {
  description = "Create a new resource group (true) or use existing (false)"
  type        = bool
  default     = true
}

variable "existing_resource_group_name" {
  description = "Name of existing resource group (if create_resource_group is false)"
  type        = string
  default     = null
}

variable "container_image" {
  description = "Docker container image URI (e.g., ACR repository URI)"
  type        = string
}

variable "cpu" {
  description = "CPU allocation in cores (e.g., 0.25, 0.5, 1.0, 2.0)"
  type        = number
  default     = 1.0

  validation {
    condition     = contains([0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0], var.cpu)
    error_message = "CPU must be one of: 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0"
  }
}

variable "memory" {
  description = "Memory allocation (e.g., '0.5Gi', '1Gi', '2Gi', '4Gi')"
  type        = string
  default     = "2Gi"

  validation {
    condition     = can(regex("^[0-9]+(\\.[0-9]+)?Gi$", var.memory))
    error_message = "Memory must be in format: <number>Gi (e.g., '2Gi')"
  }
}

variable "min_replicas" {
  description = "Minimum number of replicas (0 for scale-to-zero)"
  type        = number
  default     = 0
}

variable "max_replicas" {
  description = "Maximum number of replicas"
  type        = number
  default     = 1
}

variable "storage_account_ids" {
  description = "List of Azure Storage Account resource IDs for role assignments"
  type        = list(string)
  default     = []
}

variable "keyvault_ids" {
  description = "List of Azure Key Vault resource IDs for role assignments"
  type        = list(string)
  default     = []
}

variable "environment_variables" {
  description = "Environment variables for the container"
  type = list(object({
    name  = string
    value = string
  }))
  default = []
}

variable "secrets_from_keyvault" {
  description = "Secrets from Azure Key Vault"
  type = list(object({
    name                = string
    secret_name         = string
    keyvault_secret_id  = string
  }))
  default = []
}

variable "log_retention_days" {
  description = "Log Analytics workspace retention period in days"
  type        = number
  default     = 30

  validation {
    condition     = contains([30, 60, 90, 120, 180, 270, 365, 550, 730], var.log_retention_days)
    error_message = "log_retention_days must be one of: 30, 60, 90, 120, 180, 270, 365, 550, 730"
  }
}

variable "enable_ingress" {
  description = "Enable HTTP ingress for the Container App"
  type        = bool
  default     = false
}

variable "ingress_external_enabled" {
  description = "Make ingress externally accessible (requires enable_ingress=true)"
  type        = bool
  default     = false
}

variable "ingress_target_port" {
  description = "Target port for ingress traffic"
  type        = number
  default     = 8080
}

variable "create_job_instead_of_app" {
  description = "Create Container App Job instead of Container App (for batch/scheduled workloads)"
  type        = bool
  default     = false
}

variable "job_replica_timeout_seconds" {
  description = "Maximum execution time for a job replica in seconds"
  type        = number
  default     = 3600
}

variable "job_replica_retry_limit" {
  description = "Number of retries for failed job replicas"
  type        = number
  default     = 3
}

variable "job_parallelism" {
  description = "Number of parallel job executions"
  type        = number
  default     = 1
}

variable "job_replica_completion_count" {
  description = "Number of successful job completions required"
  type        = number
  default     = 1
}
