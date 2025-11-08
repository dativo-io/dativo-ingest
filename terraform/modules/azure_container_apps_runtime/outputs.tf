output "environment_name" {
  description = "Name of the Azure Container Apps environment referenced by Dativo."
  value       = local.environment_name
}

output "service_name" {
  description = "Name of the Azure Container App created for the job runtime."
  value       = local.service_name
}

output "endpoint_url" {
  description = "Default FQDN of the Container App. Inject into the job definition via {{terraform_outputs.endpoint_url}}."
  value       = local.endpoint_url
}

output "applied_tags" {
  description = "Merged tag map applied to every Azure resource."
  value       = local.merged_tags
}
