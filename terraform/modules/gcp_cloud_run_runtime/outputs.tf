output "service_name" {
  description = "Cloud Run service name referenced by the Dativo job definition."
  value       = local.service_name
}

output "endpoint_url" {
  description = "Public HTTPS endpoint for the Cloud Run service."
  value       = local.service_url
}

output "applied_tags" {
  description = "Normalized label map (labels) applied to Cloud Run resources."
  value       = local.normalized_labels
}
