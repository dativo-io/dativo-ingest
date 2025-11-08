output "cluster_name" {
  description = "Name of the ECS/Fargate cluster created for this Dativo job runtime."
  value       = local.cluster_name
}

output "service_name" {
  description = "Primary Fargate service identifier exposed to the job definition."
  value       = local.service_name
}

output "endpoint_url" {
  description = "Service endpoint URL (typically fronted by an ALB or API Gateway) propagated back to Dativo."
  value       = local.endpoint_url
}

output "applied_tags" {
  description = "Merged tag map applied to every provisioned resource."
  value       = local.merged_tags
}
