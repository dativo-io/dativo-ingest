# ==============================================================================
# Dativo ETL Job Infrastructure - GCP Module
# ==============================================================================
# This module provisions cloud infrastructure for Dativo ETL jobs on GCP
# with comprehensive tag/label propagation for cost allocation and compliance.
#
# Supports:
# - Cloud Run jobs for serverless job execution
# - Dagster Cloud integration
# - VPC networking with private Google access
# - GCS buckets for data and state storage
# - Cloud Logging and Cloud Monitoring
# - IAM service accounts and policies
# - Comprehensive resource labeling
# ==============================================================================

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# ==============================================================================
# Variables
# ==============================================================================

variable "provider" {
  description = "Cloud provider (should be 'gcp')"
  type        = string
  default     = "gcp"
}

variable "runtime_type" {
  description = "Runtime orchestration platform (dagster, cloud_run, kubernetes)"
  type        = string
  
  validation {
    condition     = contains(["dagster", "cloud_run", "kubernetes", "cloud_functions"], var.runtime_type)
    error_message = "Runtime type must be one of: dagster, cloud_run, kubernetes, cloud_functions"
  }
}

variable "compute" {
  description = "Compute configuration for job execution"
  type = object({
    cpu    = optional(string, "1")
    memory = optional(string, "2Gi")
    disk_size = optional(string, "20Gi")
  })
  default = {
    cpu    = "1"
    memory = "2Gi"
    disk_size = "20Gi"
  }
}

variable "scaling" {
  description = "Auto-scaling configuration"
  type = object({
    min_instances           = optional(number, 0)
    max_instances           = optional(number, 5)
    target_cpu_utilization = optional(number, 70)
  })
  default = {
    min_instances           = 0
    max_instances           = 5
    target_cpu_utilization = 70
  }
}

variable "timeout_seconds" {
  description = "Maximum execution time in seconds"
  type        = number
  default     = 3600
}

variable "networking" {
  description = "Network configuration"
  type = object({
    vpc_id             = optional(string)
    subnet_ids         = optional(list(string), [])
    security_group_ids = optional(list(string), [])
    private_access     = optional(bool, true)
  })
  default = {
    private_access = true
  }
}

variable "storage" {
  description = "Storage configuration"
  type = object({
    state_bucket = string
    data_bucket  = string
    encryption = optional(object({
      enabled    = optional(bool, true)
      kms_key_id = optional(string)
    }), { enabled = true })
  })
}

variable "monitoring" {
  description = "Monitoring configuration"
  type = object({
    enabled           = optional(bool, true)
    metrics_namespace = optional(string)
    log_group         = optional(string)
    alerts = optional(object({
      channels   = optional(list(string), [])
      thresholds = optional(map(any), {})
    }), { channels = [], thresholds = {} })
  })
  default = {
    enabled = true
  }
}

variable "labels" {
  description = "Resource labels for cost allocation, compliance, and traceability"
  type        = map(string)
  default     = {}
}

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "job_name" {
  description = "Job name for resource naming"
  type        = string
}

variable "tenant_id" {
  description = "Tenant identifier"
  type        = string
}

variable "docker_image" {
  description = "Docker image for the job"
  type        = string
  default     = "gcr.io/PROJECT_ID/dativo:latest"
}

# ==============================================================================
# Local Variables
# ==============================================================================

locals {
  # GCP labels must be lowercase and use underscores
  # Convert tags to GCP-compatible labels
  normalized_labels = {
    for k, v in var.labels : 
    lower(replace(k, "-", "_")) => lower(replace(v, " ", "_"))
  }
  
  # Merge provided labels with required labels
  common_labels = merge(
    local.normalized_labels,
    {
      terraform    = "true"
      module       = "dativo_etl_job"
      job_name     = lower(replace(var.job_name, " ", "_"))
      tenant_id    = lower(replace(var.tenant_id, " ", "_"))
      runtime_type = lower(replace(var.runtime_type, " ", "_"))
      managed_by   = "dativo"
    }
  )
  
  # Resource name prefix (GCP naming rules: lowercase, hyphens)
  name_prefix = lower("${var.tenant_id}-${var.job_name}")
}

# ==============================================================================
# Service Account for Cloud Run Job
# ==============================================================================

resource "google_service_account" "job_sa" {
  account_id   = "${local.name_prefix}-sa"
  display_name = "Dativo ETL Job ${var.job_name} (${var.tenant_id})"
  description  = "Service account for Dativo ETL job execution"
  project      = var.project_id
}

# Grant Storage Object Admin role for data and state buckets
resource "google_storage_bucket_iam_member" "data_bucket_access" {
  bucket = var.storage.data_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.job_sa.email}"
}

resource "google_storage_bucket_iam_member" "state_bucket_access" {
  bucket = var.storage.state_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.job_sa.email}"
}

# Grant Cloud Logging write permissions
resource "google_project_iam_member" "logging_write" {
  count = var.monitoring.enabled ? 1 : 0
  
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.job_sa.email}"
}

# Grant Cloud Monitoring write permissions
resource "google_project_iam_member" "monitoring_write" {
  count = var.monitoring.enabled ? 1 : 0
  
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.job_sa.email}"
}

# Grant KMS decrypt permissions (if encryption is enabled)
resource "google_kms_crypto_key_iam_member" "key_decrypt" {
  count = var.storage.encryption.enabled && var.storage.encryption.kms_key_id != null ? 1 : 0
  
  crypto_key_id = var.storage.encryption.kms_key_id
  role          = "roles/cloudkms.cryptoKeyDecrypter"
  member        = "serviceAccount:${google_service_account.job_sa.email}"
}

# ==============================================================================
# Cloud Run Job
# ==============================================================================

resource "google_cloud_run_v2_job" "etl_job" {
  name     = local.name_prefix
  location = var.region
  project  = var.project_id
  
  labels = local.common_labels
  
  template {
    labels = local.common_labels
    
    template {
      service_account = google_service_account.job_sa.email
      
      timeout         = "${var.timeout_seconds}s"
      max_retries     = 3
      
      containers {
        image = var.docker_image
        
        resources {
          limits = {
            cpu    = var.compute.cpu
            memory = var.compute.memory
          }
        }
        
        env {
          name  = "DATIVO_TENANT_ID"
          value = var.tenant_id
        }
        
        env {
          name  = "DATIVO_JOB_NAME"
          value = var.job_name
        }
        
        env {
          name  = "DATIVO_RUNTIME_TYPE"
          value = var.runtime_type
        }
        
        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }
        
        env {
          name  = "GCS_STATE_BUCKET"
          value = var.storage.state_bucket
        }
        
        env {
          name  = "GCS_DATA_BUCKET"
          value = var.storage.data_bucket
        }
      }
      
      # VPC connector (if specified)
      dynamic "vpc_access" {
        for_each = var.networking.vpc_id != null ? [1] : []
        content {
          connector = var.networking.vpc_id
          egress    = var.networking.private_access ? "PRIVATE_RANGES_ONLY" : "ALL_TRAFFIC"
        }
      }
    }
  }
  
  lifecycle {
    ignore_changes = [
      launch_stage,
    ]
  }
}

# ==============================================================================
# Cloud Scheduler (for scheduled execution)
# ==============================================================================

# Note: Cloud Scheduler jobs are typically created separately per schedule
# This is a placeholder for manual scheduling or Dagster integration

# ==============================================================================
# Cloud Logging
# ==============================================================================

# Log sink for structured logging
resource "google_logging_project_sink" "job_logs" {
  count = var.monitoring.enabled ? 1 : 0
  
  name        = "${local.name_prefix}-logs"
  destination = "logging.googleapis.com/projects/${var.project_id}/logs/${local.name_prefix}"
  
  filter = "resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"${local.name_prefix}\""
  
  unique_writer_identity = true
}

# ==============================================================================
# Cloud Monitoring Alerts
# ==============================================================================

# Alert policy for job failures
resource "google_monitoring_alert_policy" "job_failures" {
  count = var.monitoring.enabled && length(var.monitoring.alerts.channels) > 0 ? 1 : 0
  
  display_name = "${local.name_prefix} - Job Failures"
  combiner     = "OR"
  
  conditions {
    display_name = "Job execution failures"
    
    condition_threshold {
      filter          = "resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"${local.name_prefix}\" AND metric.type=\"run.googleapis.com/request_count\" AND metric.labels.response_code_class=\"5xx\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }
  
  notification_channels = var.monitoring.alerts.channels
  
  user_labels = local.common_labels
}

# ==============================================================================
# GCS Buckets (optional - typically created separately)
# ==============================================================================

# Note: In production, buckets are typically created separately.
# This ensures bucket names are globally unique and managed independently.

# ==============================================================================
# Outputs
# ==============================================================================

output "cloud_run_job_name" {
  description = "Name of the Cloud Run job"
  value       = google_cloud_run_v2_job.etl_job.name
}

output "cloud_run_job_id" {
  description = "ID of the Cloud Run job"
  value       = google_cloud_run_v2_job.etl_job.id
}

output "service_account_email" {
  description = "Email of the service account"
  value       = google_service_account.job_sa.email
}

output "service_account_name" {
  description = "Name of the service account"
  value       = google_service_account.job_sa.name
}

output "resource_labels" {
  description = "All resource labels applied"
  value       = local.common_labels
}

output "log_filter" {
  description = "Cloud Logging filter for job logs"
  value       = "resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"${local.name_prefix}\""
}
