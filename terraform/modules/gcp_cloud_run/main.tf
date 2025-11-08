terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  merged_labels = merge(var.default_tags, var.tags)
  normalized_name = substr(
    regexreplace(lower(var.tags["job_name"]), "[^a-z0-9-]", "-"),
    0,
    63,
  )
  service_name = coalesce(var.existing_service_name, "${local.normalized_name}-run")
  inferred_service_url = format("https://%s-%s.a.run.app", local.service_name, var.region)
}

resource "google_cloud_run_v2_service" "example" {
  count    = var.deploy_example_resources ? 1 : 0
  name     = local.service_name
  location = var.region

  labels = local.merged_labels

  template {
    containers {
      image = var.container_image
    }
  }
}

# -----------------------------------------------------------------------------
# Add IAM bindings, secrets, Cloud Logging sinks, or load balancer components as
# needed. Ensure every Google resource includes:
#   labels = local.merged_labels
# -----------------------------------------------------------------------------
