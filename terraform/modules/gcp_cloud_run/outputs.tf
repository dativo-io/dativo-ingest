# GCP Cloud Run Module Outputs
# These outputs are referenced in Dativo job configs via {{terraform_outputs.*}}

output "service_name" {
  description = "Cloud Run service name"
  value       = !var.create_job_instead_of_service ? google_cloud_run_v2_service.dativo_service.name : null
}

output "service_id" {
  description = "Cloud Run service ID (full resource name)"
  value       = !var.create_job_instead_of_service ? google_cloud_run_v2_service.dativo_service.id : null
}

output "service_uri" {
  description = "Cloud Run service URI"
  value       = !var.create_job_instead_of_service ? google_cloud_run_v2_service.dativo_service.uri : null
}

output "job_name" {
  description = "Cloud Run job name (if created)"
  value       = var.create_job_instead_of_service ? google_cloud_run_v2_job.dativo_job[0].name : null
}

output "job_id" {
  description = "Cloud Run job ID (if created)"
  value       = var.create_job_instead_of_service ? google_cloud_run_v2_job.dativo_job[0].id : null
}

output "job_uri" {
  description = "Cloud Run job URI (if created)"
  value       = var.create_job_instead_of_service ? "${google_cloud_run_v2_job.dativo_job[0].name}:run" : null
}

output "service_account_email" {
  description = "Service account email for the Cloud Run service/job"
  value       = google_service_account.dativo_sa.email
}

output "service_account_name" {
  description = "Service account name"
  value       = google_service_account.dativo_sa.name
}

output "service_account_unique_id" {
  description = "Service account unique ID"
  value       = google_service_account.dativo_sa.unique_id
}

output "endpoint_url" {
  description = "Endpoint URL for the Cloud Run service/job"
  value       = var.create_job_instead_of_service ? "cloud-run-job://${google_cloud_run_v2_job.dativo_job[0].name}" : google_cloud_run_v2_service.dativo_service.uri
}

output "cluster_name" {
  description = "Cluster name (alias for service/job name)"
  value       = var.create_job_instead_of_service ? google_cloud_run_v2_job.dativo_job[0].name : google_cloud_run_v2_service.dativo_service.name
}

output "scheduler_job_name" {
  description = "Cloud Scheduler job name (if created)"
  value       = var.create_scheduler_job ? google_cloud_scheduler_job.dativo_scheduler[0].name : null
}

output "scheduler_job_id" {
  description = "Cloud Scheduler job ID (if created)"
  value       = var.create_scheduler_job ? google_cloud_scheduler_job.dativo_scheduler[0].id : null
}

output "all_labels" {
  description = "All labels applied to resources (for verification)"
  value       = local.common_labels
}

output "project_id" {
  description = "GCP project ID"
  value       = var.project_id
}

output "region" {
  description = "GCP region"
  value       = var.region
}
