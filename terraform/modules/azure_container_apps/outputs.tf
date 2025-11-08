output "environment_name" {
  description = "Name of the Container Apps environment hosting the runtime."
  value       = local.environment_name
}

output "container_app_name" {
  description = "Name of the Container App associated with the job runtime."
  value       = local.container_app
}

output "ingress_url" {
  description = "Ingress endpoint to reach the Container App."
  value       = local.ingress_url
}

