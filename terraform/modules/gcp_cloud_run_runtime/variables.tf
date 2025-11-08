variable "project_id" {
  description = "GCP project ID where Cloud Run resources will be created."
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Run deployment."
  type        = string
}

variable "runtime_type" {
  description = "Runtime selector. Must be set to \"gcp_cloud_run\" when using this module."
  type        = string
  default     = "gcp_cloud_run"

  validation {
    condition     = var.runtime_type == "gcp_cloud_run"
    error_message = "runtime_type must be \"gcp_cloud_run\" for the Cloud Run module."
  }
}

variable "tags" {
  description = "Job metadata propagated from Dativo job configuration. These will be converted into Cloud Run labels."
  type        = map(string)
}

variable "default_tags" {
  description = "Default platform labels (e.g., billing codes) merged with job metadata."
  type        = map(string)
  default     = {}
}

variable "service_name_override" {
  description = "Optional override for the Cloud Run service name."
  type        = string
  default     = ""
}

variable "url_override" {
  description = "Optional override for the Cloud Run service URL."
  type        = string
  default     = ""
}
