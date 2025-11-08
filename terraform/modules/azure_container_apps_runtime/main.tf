terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 3.99"
    }
  }
}

provider "azurerm" {
  features {}
}

locals {
  merged_tags     = merge(var.default_tags, var.tags)
  runtime_suffix  = replace(var.runtime_type, "azure_", "")
  environment_name = var.environment_name_override != ""
    ? var.environment_name_override
    : format("%s-%s-env", var.tags["job_name"], local.runtime_suffix)
  service_name = var.service_name_override != ""
    ? var.service_name_override
    : format("%s-%s-svc", var.tags["job_name"], local.runtime_suffix)
  endpoint_url = var.endpoint_url_override != ""
    ? var.endpoint_url_override
    : format("https://%s.%s.azurecontainerapps.io", local.service_name, var.region)
}

# -------------------------------------------------------------------
# Replace the examples below with real Azure Container Apps resources.
# Apply local.merged_tags to each resource to guarantee consistent
# tagging across subscriptions and policy compliance.
# -------------------------------------------------------------------

# Example:
# resource "azurerm_container_app_environment" "runtime" {
#   name                = local.environment_name
#   location            = var.region
#   resource_group_name = var.resource_group_name
#   tags                = local.merged_tags
# }
#
# resource "azurerm_container_app" "runtime" {
#   name                         = local.service_name
#   container_app_environment_id = azurerm_container_app_environment.runtime.id
#   resource_group_name          = var.resource_group_name
#   tags                         = local.merged_tags
#   template {
#     revision_suffix = var.tags["environment"]
#   }
# }
