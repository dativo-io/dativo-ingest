output "service_name" {
  description = "Name of the Cloud Run service executing the runtime."
  value       = local.service_name
}

output "project_id" {
  description = "Project identifier to use when referencing the runtime."
  value       = var.project_id
}

output "service_url" {
  description = "Endpoint URL serving the Cloud Run workload."
  value = coalesce(
    var.service_url_override,
    try(google_cloud_run_v2_service.example[0].uri, local.inferred_service_url)
  )
}

