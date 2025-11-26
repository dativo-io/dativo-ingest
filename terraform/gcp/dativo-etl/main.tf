# Terraform module for Dativo ETL infrastructure on GCP
# Provisions GCS buckets, IAM service accounts, and BigQuery datasets for Iceberg tables

terraform {
  required_version = ">= 1.3.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# ============================================================================
# Variables
# ============================================================================

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "tenant_id" {
  description = "Tenant identifier for multi-tenancy"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "region" {
  description = "GCP region for resources"
  type        = string
}

variable "gcs_bucket_name" {
  description = "Name for the GCS bucket (must be globally unique)"
  type        = string
}

variable "storage_class" {
  description = "Storage class for GCS bucket"
  type        = string
  default     = "STANDARD"
}

variable "enable_versioning" {
  description = "Enable GCS bucket versioning"
  type        = bool
  default     = true
}

variable "enable_encryption" {
  description = "Enable GCS bucket encryption (always enabled by default)"
  type        = bool
  default     = true
}

variable "enable_bigquery_catalog" {
  description = "Enable BigQuery dataset for Iceberg tables"
  type        = bool
  default     = true
}

variable "bigquery_dataset_id" {
  description = "BigQuery dataset ID for Iceberg catalog"
  type        = string
  default     = ""
}

variable "bigquery_location" {
  description = "BigQuery dataset location (defaults to region)"
  type        = string
  default     = ""
}

variable "labels" {
  description = "Labels to apply to all resources"
  type        = map(string)
  default     = {}
}

# ============================================================================
# Local Variables
# ============================================================================

locals {
  common_labels = merge(
    var.labels,
    {
      managed_by  = "terraform"
      tenant_id   = var.tenant_id
      environment = var.environment
      component   = "dativo-etl"
    }
  )
  
  bigquery_dataset_id = var.bigquery_dataset_id != "" ? var.bigquery_dataset_id : "${replace(var.tenant_id, "-", "_")}_iceberg_${var.environment}"
  bigquery_location   = var.bigquery_location != "" ? var.bigquery_location : upper(var.region)
  
  service_account_id = "${var.tenant_id}-dativo-etl-${var.environment}"
}

# ============================================================================
# GCS Bucket for Dativo Data Lake
# ============================================================================

resource "google_storage_bucket" "data_lake" {
  name          = var.gcs_bucket_name
  project       = var.project_id
  location      = upper(var.region)
  storage_class = var.storage_class
  
  labels = local.common_labels

  uniform_bucket_level_access = true
  
  versioning {
    enabled = var.enable_versioning
  }

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type = "Delete"
    }
  }

  # Prevent accidental deletion
  lifecycle {
    prevent_destroy = true
  }
}

# ============================================================================
# Service Account for Dativo ETL Job
# ============================================================================

resource "google_service_account" "dativo_etl" {
  account_id   = local.service_account_id
  display_name = "Dativo ETL Service Account - ${var.tenant_id} ${var.environment}"
  description  = "Service account for Dativo ETL jobs (tenant: ${var.tenant_id}, env: ${var.environment})"
  project      = var.project_id
}

# Grant Storage Object Admin role to service account
resource "google_storage_bucket_iam_member" "storage_admin" {
  bucket = google_storage_bucket.data_lake.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.dativo_etl.email}"
}

# Grant BigQuery Data Editor role (if BigQuery catalog enabled)
resource "google_project_iam_member" "bigquery_data_editor" {
  count   = var.enable_bigquery_catalog ? 1 : 0
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.dativo_etl.email}"
}

# Grant BigQuery Job User role (if BigQuery catalog enabled)
resource "google_project_iam_member" "bigquery_job_user" {
  count   = var.enable_bigquery_catalog ? 1 : 0
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.dativo_etl.email}"
}

# ============================================================================
# BigQuery Dataset for Iceberg Tables
# ============================================================================

resource "google_bigquery_dataset" "iceberg" {
  count       = var.enable_bigquery_catalog ? 1 : 0
  dataset_id  = local.bigquery_dataset_id
  project     = var.project_id
  location    = local.bigquery_location
  description = "Iceberg catalog dataset for ${var.tenant_id}"

  labels = local.common_labels

  # Default table expiration (optional)
  default_table_expiration_ms = null

  access {
    role          = "OWNER"
    user_by_email = google_service_account.dativo_etl.email
  }

  access {
    role          = "roles/bigquery.dataEditor"
    user_by_email = google_service_account.dativo_etl.email
  }
}

# ============================================================================
# Outputs
# ============================================================================

output "gcs_bucket_name" {
  description = "Name of the GCS bucket"
  value       = google_storage_bucket.data_lake.name
}

output "gcs_bucket_url" {
  description = "URL of the GCS bucket"
  value       = google_storage_bucket.data_lake.url
}

output "gcs_bucket_self_link" {
  description = "Self-link of the GCS bucket"
  value       = google_storage_bucket.data_lake.self_link
}

output "service_account_email" {
  description = "Email of the service account for Dativo ETL jobs"
  value       = google_service_account.dativo_etl.email
}

output "service_account_unique_id" {
  description = "Unique ID of the service account"
  value       = google_service_account.dativo_etl.unique_id
}

output "bigquery_dataset_id" {
  description = "ID of the BigQuery dataset"
  value       = var.enable_bigquery_catalog ? google_bigquery_dataset.iceberg[0].dataset_id : ""
}

output "bigquery_dataset_self_link" {
  description = "Self-link of the BigQuery dataset"
  value       = var.enable_bigquery_catalog ? google_bigquery_dataset.iceberg[0].self_link : ""
}

output "gcp_project_id" {
  description = "GCP project ID"
  value       = var.project_id
}

output "gcp_region" {
  description = "GCP region"
  value       = var.region
}

output "tenant_id" {
  description = "Tenant ID"
  value       = var.tenant_id
}

output "environment" {
  description = "Environment name"
  value       = var.environment
}
