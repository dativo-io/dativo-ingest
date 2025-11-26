# Terraform module for Dativo ETL job on GCP Cloud Run with Dagster
# This module provisions infrastructure for running Dativo ETL jobs in GCP
# with comprehensive label propagation for cost allocation and compliance

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# Local variables for label merging
locals {
  # Merge labels from multiple sources with precedence
  # Note: GCP labels must be lowercase with hyphens
  common_labels = merge(
    { for k, v in var.tags : lower(replace(k, "_", "-")) => lower(replace(v, "_", "-")) },
    {
      "dativo-tenant"      = var.tenant_id
      "dativo-environment" = var.environment
      "dativo-job"         = var.job_name
      "dativo-managed-by"  = "terraform"
      "dativo-provider"    = var.provider
      "dativo-runtime"     = var.runtime_type
    }
  )
  
  # Format container resources
  container_cpu    = var.compute_cpu
  container_memory = var.compute_memory
  
  # Service account email
  service_account_email = var.runtime_service_account != null ? var.runtime_service_account : google_service_account.dativo[0].email
}

# Data source for GCP project
data "google_project" "current" {
  project_id = var.project_id
}

# Service Account for Cloud Run
resource "google_service_account" "dativo" {
  count = var.runtime_service_account == null ? 1 : 0
  
  account_id   = "${var.tenant_id}-${var.job_name}"
  display_name = "Dativo ETL Service Account for ${var.job_name}"
  description  = "Service account for running Dativo ETL job: ${var.job_name}"
  project      = var.project_id
}

# IAM binding for GCS access
resource "google_storage_bucket_iam_member" "dativo" {
  bucket = var.storage_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${local.service_account_email}"
}

# IAM binding for KMS access (if KMS key is provided)
resource "google_kms_crypto_key_iam_member" "dativo" {
  count = var.storage_kms_key_id != null ? 1 : 0
  
  crypto_key_id = var.storage_kms_key_id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${local.service_account_email}"
}

# Cloud Run Job
resource "google_cloud_run_v2_job" "dativo" {
  name     = "${var.tenant_id}-${var.job_name}"
  location = var.region
  project  = var.project_id
  
  labels = local.common_labels
  
  template {
    labels = local.common_labels
    
    template {
      service_account = local.service_account_email
      
      timeout         = "${var.compute_max_runtime_seconds}s"
      max_retries     = 3
      
      vpc_access {
        network_interfaces {
          network    = var.networking_vpc_id
          subnetwork = length(var.networking_subnet_ids) > 0 ? var.networking_subnet_ids[0] : null
        }
        egress = var.networking_private_networking ? "PRIVATE_RANGES_ONLY" : "ALL_TRAFFIC"
      }
      
      containers {
        image = var.container_image
        
        resources {
          limits = {
            cpu    = local.container_cpu
            memory = local.container_memory
          }
        }
        
        env {
          name  = "DATIVO_TENANT_ID"
          value = var.tenant_id
        }
        
        env {
          name  = "DATIVO_ENVIRONMENT"
          value = var.environment
        }
        
        env {
          name  = "DATIVO_JOB_NAME"
          value = var.job_name
        }
        
        env {
          name  = "GCS_BUCKET"
          value = var.storage_bucket
        }
        
        env {
          name  = "GCS_PREFIX"
          value = var.storage_prefix
        }
        
        # Additional environment variables
        dynamic "env" {
          for_each = var.additional_environment_variables
          content {
            name  = env.value.name
            value = env.value.value
          }
        }
        
        # Secrets from Secret Manager
        dynamic "env" {
          for_each = var.secrets_from_secret_manager
          content {
            name = env.value.name
            value_source {
              secret_key_ref {
                secret  = env.value.secret
                version = env.value.version
              }
            }
          }
        }
        
        args = [
          "dativo",
          "run",
          "--config",
          "/app/jobs/${var.tenant_id}/${var.job_name}.yaml",
          "--mode",
          "self_hosted"
        ]
      }
    }
  }
  
  lifecycle {
    ignore_changes = [
      launch_stage,
    ]
  }
}

# Cloud Scheduler for scheduled execution (optional)
resource "google_cloud_scheduler_job" "dativo" {
  count = var.schedule_cron != null ? 1 : 0
  
  name             = "${var.tenant_id}-${var.job_name}"
  description      = "Scheduled execution of Dativo ETL job: ${var.job_name}"
  schedule         = var.schedule_cron
  time_zone        = var.schedule_timezone
  attempt_deadline = "${var.compute_max_runtime_seconds}s"
  project          = var.project_id
  region           = var.region
  
  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/${google_cloud_run_v2_job.dativo.name}:run"
    
    oauth_token {
      service_account_email = local.service_account_email
    }
  }
}

# Cloud Logging sink for job logs
resource "google_logging_project_sink" "dativo" {
  name        = "${var.tenant_id}-${var.job_name}-logs"
  destination = "storage.googleapis.com/${var.storage_bucket}"
  
  filter = "resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"${google_cloud_run_v2_job.dativo.name}\""
  
  unique_writer_identity = true
}

# IAM binding for log writer
resource "google_storage_bucket_iam_member" "log_writer" {
  bucket = var.storage_bucket
  role   = "roles/storage.objectCreator"
  member = google_logging_project_sink.dativo.writer_identity
}

# Outputs for integration with Dagster
output "job_name" {
  description = "Cloud Run Job name"
  value       = google_cloud_run_v2_job.dativo.name
}

output "job_id" {
  description = "Cloud Run Job ID"
  value       = google_cloud_run_v2_job.dativo.id
}

output "service_account_email" {
  description = "Service account email"
  value       = local.service_account_email
}

output "region" {
  description = "GCP region"
  value       = var.region
}

output "project_id" {
  description = "GCP project ID"
  value       = var.project_id
}

output "labels" {
  description = "Applied resource labels"
  value       = local.common_labels
}

# Outputs for Dagster Cloud Run operator
output "dagster_cloud_run_config" {
  description = "Configuration for Dagster Cloud Run operator"
  value = {
    project_id            = var.project_id
    region                = var.region
    job_name              = google_cloud_run_v2_job.dativo.name
    service_account_email = local.service_account_email
    vpc_connector         = var.networking_vpc_id
    max_retries           = 3
    timeout_seconds       = var.compute_max_runtime_seconds
    cpu                   = local.container_cpu
    memory                = local.container_memory
    labels                = local.common_labels
  }
}
