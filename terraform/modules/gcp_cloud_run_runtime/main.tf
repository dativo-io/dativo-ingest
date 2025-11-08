terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  merged_tags = merge(var.default_tags, var.tags)
  normalized_labels = {
    for key, value in local.merged_tags :
    lower(regexreplace(key, "[^0-9A-Za-z_]", "_")) => value
  }
  runtime_suffix = replace(var.runtime_type, "gcp_", "")
  service_name = var.service_name_override != ""
    ? var.service_name_override
    : lower(regexreplace(format("%s-%s", var.tags["job_name"], runtime_suffix), "[^0-9a-z-]", "-"))
  service_url = var.url_override != ""
    ? var.url_override
    : format("https://%s-%s.a.run.app", local.service_name, var.region)
}

# -------------------------------------------------------------------
# Replace the examples below with real Cloud Run resources. Ensure
# every resource and supporting artifact (IAM, Pub/Sub topics, etc.)
# applies local.normalized_labels for audit and cost allocation.
# -------------------------------------------------------------------

# Example:
# resource "google_cloud_run_v2_service" "runtime" {
#   name     = local.service_name
#   location = var.region
#   labels   = local.normalized_labels
#   template {
#     containers {
#       image = var.container_image
#       env {
#         name  = "JOB_NAME"
#         value = var.tags["job_name"]
#       }
#     }
#   }
# }
