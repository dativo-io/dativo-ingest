# Azure Container Apps Module Outputs
# These outputs are referenced in Dativo job configs via {{terraform_outputs.*}}

output "resource_group_name" {
  description = "Resource Group name"
  value       = var.create_resource_group ? azurerm_resource_group.dativo_rg[0].name : data.azurerm_resource_group.existing_rg[0].name
}

output "container_app_environment_id" {
  description = "Container Apps Environment ID"
  value       = azurerm_container_app_environment.dativo_env.id
}

output "container_app_environment_name" {
  description = "Container Apps Environment name"
  value       = azurerm_container_app_environment.dativo_env.name
}

output "container_app_name" {
  description = "Container App name"
  value       = azurerm_container_app.dativo_app.name
}

output "container_app_id" {
  description = "Container App resource ID"
  value       = azurerm_container_app.dativo_app.id
}

output "container_app_fqdn" {
  description = "Container App fully qualified domain name (if ingress enabled)"
  value       = var.enable_ingress ? azurerm_container_app.dativo_app.ingress[0].fqdn : null
}

output "container_app_job_name" {
  description = "Container App Job name (if created)"
  value       = var.create_job_instead_of_app ? azurerm_container_app_job.dativo_job[0].name : null
}

output "container_app_job_id" {
  description = "Container App Job resource ID (if created)"
  value       = var.create_job_instead_of_app ? azurerm_container_app_job.dativo_job[0].id : null
}

output "managed_identity_id" {
  description = "Managed Identity resource ID"
  value       = azurerm_user_assigned_identity.dativo_identity.id
}

output "managed_identity_client_id" {
  description = "Managed Identity client ID"
  value       = azurerm_user_assigned_identity.dativo_identity.client_id
}

output "managed_identity_principal_id" {
  description = "Managed Identity principal ID (for role assignments)"
  value       = azurerm_user_assigned_identity.dativo_identity.principal_id
}

output "log_analytics_workspace_id" {
  description = "Log Analytics Workspace ID"
  value       = azurerm_log_analytics_workspace.dativo_logs.id
}

output "log_analytics_workspace_name" {
  description = "Log Analytics Workspace name"
  value       = azurerm_log_analytics_workspace.dativo_logs.name
}

output "endpoint_url" {
  description = "Endpoint URL for the container app"
  value       = var.enable_ingress ? "https://${azurerm_container_app.dativo_app.ingress[0].fqdn}" : "container-app://${azurerm_container_app.dativo_app.name}"
}

output "service_name" {
  description = "Service name (alias for container_app_name)"
  value       = azurerm_container_app.dativo_app.name
}

output "cluster_name" {
  description = "Cluster name (alias for container_app_environment_name)"
  value       = azurerm_container_app_environment.dativo_env.name
}

output "all_tags" {
  description = "All tags applied to resources (for verification)"
  value       = local.common_tags
}
