# GCP Cloud Run Runtime Module for Dativo ETL Jobs
# This module provisions Google Cloud Run infrastructure for running Dativo containerized workloads

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# Local variables for consistent naming and labeling
locals {
  # Convert tags to GCP labels (lowercase, alphanumeric + underscore/hyphen only)
  # GCP labels have strict format requirements
  common_labels = merge(
    { for k, v in var.default_labels : lower(replace(k, " ", "_")) => lower(replace(v, " ", "-")) },
    { for k, v in var.job_metadata : lower(replace(k, " ", "_")) => lower(replace(v, " ", "-")) },
    {
      "managed_by"     = "terraform"
      "dativo_runtime" = "gcp_cloud_run"
    }
  )

  # Resource naming convention (GCP has specific naming requirements)
  name_prefix = lower(replace("${var.job_metadata["job_name"]}-${var.job_metadata["environment"]}", "_", "-"))
  
  # Truncate to 63 characters (GCP limit)
  service_name = substr("${local.name_prefix}-svc", 0, 63)
}

# Service Account for Cloud Run service
resource "google_service_account" "dativo_sa" {
  account_id   = substr("${local.name_prefix}-sa", 0, 30)
  display_name = "Dativo ETL Job: ${var.job_metadata["job_name"]}"
  description  = "Service account for Dativo ETL job running on Cloud Run"
  project      = var.project_id
}

# IAM bindings for service account
# Storage Object Viewer (read access)
resource "google_storage_bucket_iam_member" "bucket_read" {
  count  = length(var.storage_bucket_names)
  bucket = var.storage_bucket_names[count.index]
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.dativo_sa.email}"
}

# Storage Object Creator (write access)
resource "google_storage_bucket_iam_member" "bucket_write" {
  count  = length(var.storage_bucket_names)
  bucket = var.storage_bucket_names[count.index]
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.dativo_sa.email}"
}

# Secret Manager Secret Accessor
resource "google_secret_manager_secret_iam_member" "secret_accessor" {
  count     = length(var.secret_ids)
  project   = var.project_id
  secret_id = var.secret_ids[count.index]
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.dativo_sa.email}"
}

# Cloud Run Service (v2 API for improved features)
resource "google_cloud_run_v2_service" "dativo_service" {
  name     = local.service_name
  location = var.region
  project  = var.project_id

  template {
    service_account = google_service_account.dativo_sa.email

    # Scaling configuration
    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    # Execution environment
    execution_environment = var.execution_environment

    # Timeout
    timeout = "${var.timeout_seconds}s"

    containers {
      name  = "dativo-etl"
      image = var.container_image

      # Resources
      resources {
        limits = {
          cpu    = var.cpu
          memory = var.memory
        }
        cpu_idle          = var.cpu_throttling
        startup_cpu_boost = var.startup_cpu_boost
      }

      # Environment variables
      dynamic "env" {
        for_each = var.environment_variables
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
              secret  = env.value.secret_name
              version = env.value.version
            }
          }
        }
      }

      # Volume mounts for secrets (if needed)
      dynamic "volume_mounts" {
        for_each = var.secret_volumes
        content {
          name       = volume_mounts.value.name
          mount_path = volume_mounts.value.mount_path
        }
      }
    }

    # Secret volumes
    dynamic "volumes" {
      for_each = var.secret_volumes
      content {
        name = volumes.value.name
        secret {
          secret       = volumes.value.secret_name
          default_mode = 0444
          dynamic "items" {
            for_each = volumes.value.items
            content {
              path    = items.value.path
              version = items.value.version
            }
          }
        }
      }
    }

    # VPC connector (for private network access)
    dynamic "vpc_access" {
      for_each = var.vpc_connector_name != null ? [1] : []
      content {
        connector = var.vpc_connector_name
        egress    = var.vpc_egress_mode
      }
    }
  }

  # Traffic routing (100% to latest revision)
  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  labels = local.common_labels

  lifecycle {
    ignore_changes = [
      # Ignore client and client_version changes to prevent unnecessary updates
      client,
      client_version,
    ]
  }
}

# Cloud Run Job (for batch/scheduled workloads)
resource "google_cloud_run_v2_job" "dativo_job" {
  count    = var.create_job_instead_of_service ? 1 : 0
  name     = substr("${local.name_prefix}-job", 0, 63)
  location = var.region
  project  = var.project_id

  template {
    template {
      service_account = google_service_account.dativo_sa.email

      # Timeout
      timeout = "${var.timeout_seconds}s"

      # Task count for parallelism
      parallelism    = var.job_parallelism
      task_count     = var.job_task_count
      max_retries    = var.job_max_retries

      containers {
        name  = "dativo-etl-job"
        image = var.container_image

        # Resources
        resources {
          limits = {
            cpu    = var.cpu
            memory = var.memory
          }
        }

        # Environment variables
        dynamic "env" {
          for_each = var.environment_variables
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
                secret  = env.value.secret_name
                version = env.value.version
              }
            }
          }
        }
      }

      # VPC connector (for private network access)
      dynamic "vpc_access" {
        for_each = var.vpc_connector_name != null ? [1] : []
        content {
          connector = var.vpc_connector_name
          egress    = var.vpc_egress_mode
        }
      }
    }
  }

  labels = local.common_labels

  lifecycle {
    ignore_changes = [
      # Ignore client and client_version changes
      client,
      client_version,
    ]
  }
}

# IAM policy for public access (if enabled)
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  count    = var.allow_unauthenticated_access && !var.create_job_instead_of_service ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.dativo_service.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Cloud Scheduler job for scheduled execution (optional)
resource "google_cloud_scheduler_job" "dativo_scheduler" {
  count       = var.create_scheduler_job ? 1 : 0
  name        = substr("${local.name_prefix}-scheduler", 0, 63)
  description = "Scheduled trigger for Dativo ETL job: ${var.job_metadata["job_name"]}"
  schedule    = var.scheduler_cron
  time_zone   = var.scheduler_timezone
  project     = var.project_id
  region      = var.region

  retry_config {
    retry_count = var.scheduler_retry_count
  }

  http_target {
    http_method = "POST"
    uri         = var.create_job_instead_of_service ? "${google_cloud_run_v2_job.dativo_job[0].uri}:run" : google_cloud_run_v2_service.dativo_service.uri

    oidc_token {
      service_account_email = google_service_account.dativo_sa.email
    }
  }
}
