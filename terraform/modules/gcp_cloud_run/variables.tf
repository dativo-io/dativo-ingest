# GCP Cloud Run Module Variables

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for deployment (e.g., us-central1, us-east1, europe-west1)"
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

variable "default_labels" {
  description = "Default labels to apply to all resources"
  type        = map(string)
  default     = {}
}

variable "container_image" {
  description = "Docker container image URI (e.g., GCR or Artifact Registry URI)"
  type        = string
}

variable "cpu" {
  description = "CPU allocation (e.g., '1', '2', '4')"
  type        = string
  default     = "1"

  validation {
    condition     = can(regex("^[0-9]+(\\.[0-9]+)?$", var.cpu))
    error_message = "CPU must be a numeric string (e.g., '1', '2', '4')"
  }
}

variable "memory" {
  description = "Memory allocation (e.g., '512Mi', '1Gi', '2Gi', '4Gi')"
  type        = string
  default     = "2Gi"

  validation {
    condition     = can(regex("^[0-9]+(Mi|Gi)$", var.memory))
    error_message = "Memory must be in format: <number>Mi or <number>Gi (e.g., '2Gi')"
  }
}

variable "min_instances" {
  description = "Minimum number of instances (0 for scale-to-zero)"
  type        = number
  default     = 0

  validation {
    condition     = var.min_instances >= 0 && var.min_instances <= 1000
    error_message = "min_instances must be between 0 and 1000"
  }
}

variable "max_instances" {
  description = "Maximum number of instances"
  type        = number
  default     = 1

  validation {
    condition     = var.max_instances >= 1 && var.max_instances <= 1000
    error_message = "max_instances must be between 1 and 1000"
  }
}

variable "timeout_seconds" {
  description = "Request timeout in seconds (max 3600 for services, higher for jobs)"
  type        = number
  default     = 3600

  validation {
    condition     = var.timeout_seconds >= 1 && var.timeout_seconds <= 86400
    error_message = "timeout_seconds must be between 1 and 86400 (24 hours)"
  }
}

variable "execution_environment" {
  description = "Execution environment (EXECUTION_ENVIRONMENT_GEN1 or EXECUTION_ENVIRONMENT_GEN2)"
  type        = string
  default     = "EXECUTION_ENVIRONMENT_GEN2"

  validation {
    condition     = contains(["EXECUTION_ENVIRONMENT_GEN1", "EXECUTION_ENVIRONMENT_GEN2"], var.execution_environment)
    error_message = "execution_environment must be EXECUTION_ENVIRONMENT_GEN1 or EXECUTION_ENVIRONMENT_GEN2"
  }
}

variable "cpu_throttling" {
  description = "Enable CPU throttling when idle (true to save costs)"
  type        = bool
  default     = true
}

variable "startup_cpu_boost" {
  description = "Enable CPU boost during startup for faster cold starts"
  type        = bool
  default     = false
}

variable "storage_bucket_names" {
  description = "List of GCS bucket names that the service needs access to"
  type        = list(string)
  default     = []
}

variable "secret_ids" {
  description = "List of Secret Manager secret IDs for IAM bindings"
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

variable "secrets_from_secret_manager" {
  description = "Secrets from Google Secret Manager"
  type = list(object({
    name        = string
    secret_name = string
    version     = string
  }))
  default = []
}

variable "secret_volumes" {
  description = "Mount secrets as volumes"
  type = list(object({
    name        = string
    secret_name = string
    mount_path  = string
    items = list(object({
      path    = string
      version = string
    }))
  }))
  default = []
}

variable "vpc_connector_name" {
  description = "VPC connector name for private network access (optional)"
  type        = string
  default     = null
}

variable "vpc_egress_mode" {
  description = "VPC egress mode (ALL_TRAFFIC or PRIVATE_RANGES_ONLY)"
  type        = string
  default     = "PRIVATE_RANGES_ONLY"

  validation {
    condition     = contains(["ALL_TRAFFIC", "PRIVATE_RANGES_ONLY"], var.vpc_egress_mode)
    error_message = "vpc_egress_mode must be ALL_TRAFFIC or PRIVATE_RANGES_ONLY"
  }
}

variable "allow_unauthenticated_access" {
  description = "Allow unauthenticated access to the service (public access)"
  type        = bool
  default     = false
}

variable "create_job_instead_of_service" {
  description = "Create Cloud Run Job instead of Service (for batch/scheduled workloads)"
  type        = bool
  default     = false
}

variable "job_parallelism" {
  description = "Number of tasks to execute in parallel for Cloud Run Jobs"
  type        = number
  default     = 1
}

variable "job_task_count" {
  description = "Total number of tasks to execute for Cloud Run Jobs"
  type        = number
  default     = 1
}

variable "job_max_retries" {
  description = "Maximum number of retries for failed tasks in Cloud Run Jobs"
  type        = number
  default     = 3
}

variable "create_scheduler_job" {
  description = "Create Cloud Scheduler job for scheduled execution"
  type        = bool
  default     = false
}

variable "scheduler_cron" {
  description = "Cron expression for Cloud Scheduler (if create_scheduler_job is true)"
  type        = string
  default     = "0 2 * * *"  # Default: 2 AM daily
}

variable "scheduler_timezone" {
  description = "Timezone for Cloud Scheduler (e.g., America/New_York, UTC)"
  type        = string
  default     = "UTC"
}

variable "scheduler_retry_count" {
  description = "Number of retries for failed Cloud Scheduler executions"
  type        = number
  default     = 3
}
