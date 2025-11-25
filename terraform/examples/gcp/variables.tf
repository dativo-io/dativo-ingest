variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "image_uri" {
  description = "Container image URI for Dativo jobs"
  type        = string
  default     = "gcr.io/dativo/dativo-ingest:latest"
}

variable "service_account_email" {
  description = "Service account email for Cloud Run"
  type        = string
}
