output "cluster_name" {
  description = "Name of the ECS cluster hosting the Dativo runtime."
  value       = local.cluster_name
}

output "service_name" {
  description = "Name of the ECS service orchestrating the job containers."
  value       = local.service_name
}

output "service_endpoint" {
  description = "Service endpoint or console URL for the provisioned runtime."
  value       = local.service_endpoint
}

