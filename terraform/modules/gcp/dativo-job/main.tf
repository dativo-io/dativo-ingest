# Dativo ETL Job - GCP Cloud Run Module
#
# This module provisions infrastructure for a Dativo ETL job on GCP using Cloud Run.
# It includes comprehensive tag propagation for cost allocation, compliance, and resource traceability.

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# Variables
variable "job_name" {
  description = "Name of the Dativo job"
  type        = string
}

variable "tenant_id" {
  description = "Tenant identifier"
  type        = string
}

variable "image_uri" {
  description = "Container image URI for the job"
  type        = string
}

variable "cpu" {
  description = "CPU allocation (e.g., '1', '2')"
  type        = string
  default     = "1"
}

variable "memory" {
  description = "Memory allocation (e.g., '2Gi', '4Gi')"
  type        = string
  default     = "2Gi"
}

variable "timeout_seconds" {
  description = "Timeout in seconds"
  type        = number
  default     = 3600
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "job_config_path" {
  description = "Path to job configuration file in container"
  type        = string
  default     = "/app/jobs"
}

variable "environment_variables" {
  description = "Additional environment variables"
  type        = map(string)
  default     = {}
}

variable "labels" {
  description = "Labels to apply to all resources (GCP format)"
  type        = map(string)
  default     = {}
}

variable "max_instances" {
  description = "Maximum number of instances"
  type        = number
  default     = 10
}

variable "min_instances" {
  description = "Minimum number of instances"
  type        = number
  default     = 0
}

# Cloud Run Service
resource "google_cloud_run_service" "job" {
  name     = "${var.tenant_id}-${var.job_name}"
  location = var.region
  project  = var.project_id

  template {
    spec {
      containers {
        image = var.image_uri

        env {
          name  = "TENANT_ID"
          value = var.tenant_id
        }
        env {
          name  = "JOB_CONFIG_PATH"
          value = "${var.job_config_path}/${var.tenant_id}/${var.job_name}.yaml"
        }

        dynamic "env" {
          for_each = var.environment_variables
          content {
            name  = env.key
            value = env.value
          }
        }

        resources {
          limits = {
            cpu    = var.cpu
            memory = var.memory
          }
        }
      }

      timeout_seconds = var.timeout_seconds
      service_account_name = var.service_account_email
    }

    metadata {
      annotations = {
        "autoscaling.knative.dev/maxScale" = tostring(var.max_instances)
        "autoscaling.knative.dev/minScale" = tostring(var.min_instances)
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }

  labels = merge(
    var.labels,
    {
      managed-by    = "dativo-terraform"
      resource-type = "cloud-run-service"
      tenant-id     = var.tenant_id
      job-name      = var.job_name
    }
  )
}

# Cloud Scheduler Job (optional - for scheduled execution)
resource "google_cloud_scheduler_job" "job_schedule" {
  count     = var.schedule_cron != null ? 1 : 0
  name      = "${var.tenant_id}-${var.job_name}-schedule"
  region    = var.region
  project   = var.project_id
  schedule  = var.schedule_cron
  time_zone = var.timezone
  attempt_deadline = "${var.timeout_seconds}s"

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_service.job.status[0].url}/run"
    oidc_token {
      service_account_email = var.service_account_email
    }
  }

  labels = merge(
    var.labels,
    {
      managed-by    = "dativo-terraform"
      resource-type = "cloud-scheduler-job"
      tenant-id     = var.tenant_id
      job-name      = var.job_name
    }
  )
}

# IAM Policy for Cloud Run (allow unauthenticated invocations if needed)
resource "google_cloud_run_service_iam_member" "job_invoker" {
  count    = var.allow_unauthenticated ? 1 : 0
  service  = google_cloud_run_service.job.name
  location = google_cloud_run_service.job.location
  project  = var.project_id
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Outputs
output "service_url" {
  description = "URL of the Cloud Run service"
  value       = google_cloud_run_service.job.status[0].url
}

output "service_name" {
  description = "Name of the Cloud Run service"
  value       = google_cloud_run_service.job.name
}

output "service_id" {
  description = "ID of the Cloud Run service"
  value       = google_cloud_run_service.job.id
}
