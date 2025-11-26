# Variables for Dativo ETL job Terraform module (GCP Cloud Run)

# GCP project configuration
variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

# Job identification
variable "job_name" {
  description = "Job name from Dativo configuration"
  type        = string
}

variable "tenant_id" {
  description = "Tenant ID from Dativo configuration"
  type        = string
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
}

# Cloud provider configuration
variable "provider" {
  description = "Cloud provider (should be 'gcp' for this module)"
  type        = string
  default     = "gcp"
}

# Runtime configuration
variable "runtime_type" {
  description = "Runtime type (cloud_run, dagster, etc.)"
  type        = string
  default     = "cloud_run"
}

variable "runtime_service_account" {
  description = "Service account email (if null, a new one will be created)"
  type        = string
  default     = null
}

# Compute configuration
variable "compute_cpu" {
  description = "CPU request (e.g., '1', '2', '4')"
  type        = string
  default     = "1"
}

variable "compute_memory" {
  description = "Memory request (e.g., '2Gi', '4Gi', '8Gi')"
  type        = string
  default     = "2Gi"
}

variable "compute_max_runtime_seconds" {
  description = "Maximum runtime in seconds before timeout"
  type        = number
  default     = 3600
}

# Networking configuration
variable "networking_vpc_id" {
  description = "VPC network name or ID"
  type        = string
}

variable "networking_subnet_ids" {
  description = "Subnet names"
  type        = list(string)
  default     = []
}

variable "networking_private_networking" {
  description = "Whether to use private networking"
  type        = bool
  default     = true
}

# Storage configuration
variable "storage_bucket" {
  description = "GCS bucket name for data output"
  type        = string
}

variable "storage_prefix" {
  description = "GCS prefix/path"
  type        = string
}

variable "storage_kms_key_id" {
  description = "KMS key ID for encryption"
  type        = string
  default     = null
}

# Container configuration
variable "container_image" {
  description = "Docker container image for Dativo ETL"
  type        = string
  default     = "gcr.io/dativo/etl:latest"
}

variable "additional_environment_variables" {
  description = "Additional environment variables for the container"
  type = list(object({
    name  = string
    value = string
  }))
  default = []
}

variable "secrets_from_secret_manager" {
  description = "Secrets from GCP Secret Manager"
  type = list(object({
    name    = string
    secret  = string
    version = string
  }))
  default = []
}

# Scheduling configuration
variable "schedule_cron" {
  description = "Cron schedule for Cloud Scheduler (null to disable)"
  type        = string
  default     = null
}

variable "schedule_timezone" {
  description = "Timezone for schedule"
  type        = string
  default     = "UTC"
}

# Labels (GCP equivalent of tags)
variable "tags" {
  description = "Resource labels for cost allocation and compliance"
  type        = map(string)
  default     = {}
}

# Dagster-specific configuration
variable "dagster_code_location" {
  description = "Dagster code location name"
  type        = string
  default     = null
}

variable "dagster_repository" {
  description = "Dagster repository name"
  type        = string
  default     = null
}
