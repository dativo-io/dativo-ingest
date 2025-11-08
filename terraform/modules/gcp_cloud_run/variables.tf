variable "region" {
  description = "GCP region for the Cloud Run service."
  type        = string
}

variable "runtime_type" {
  description = "Runtime identifier propagated from the Dativo job configuration."
  type        = string
  default     = "gcp_cloud_run"

  validation {
    condition     = var.runtime_type == "gcp_cloud_run"
    error_message = "This module only supports the gcp_cloud_run runtime."
  }
}

variable "project_id" {
  description = "Google Cloud project that hosts the runtime."
  type        = string
}

variable "tags" {
  description = "Job metadata tags propagated from the Dativo job definition."
  type        = map(string)
}

variable "default_tags" {
  description = "Baseline platform labels merged with job metadata."
  type        = map(string)
  default     = {}
}

variable "existing_service_name" {
  description = "Optional pre-existing Cloud Run service name."
  type        = string
  default     = null
}

variable "service_url_override" {
  description = "Optional service URL override when sourced from a different module."
  type        = string
  default     = null
}

variable "deploy_example_resources" {
  description = "Set to true to create a sample Cloud Run service demonstrating label propagation."
  type        = bool
  default     = false
}

variable "container_image" {
  description = "Container image to use for the example Cloud Run service."
  type        = string
  default     = "gcr.io/cloudrun/hello"
}

