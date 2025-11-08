terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 3.80.0"
    }
  }
}

provider "azurerm" {
  features {}

  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id

  default_tags {
    tags = var.default_tags
  }
}

locals {
  merged_tags      = merge(var.default_tags, var.tags)
  normalized_name  = substr(regexreplace(lower(var.tags["job_name"]), "[^a-z0-9-]", "-"), 0, 50)
  environment_name = coalesce(var.existing_environment_name, "${local.normalized_name}-env")
  container_app    = coalesce(var.existing_container_app_name, "${local.normalized_name}-app")
  ingress_url      = coalesce(
    var.ingress_url_override,
    format("https://%s.%s.azurecontainerapps.io", local.container_app, var.region)
  )
}

resource "azurerm_resource_group" "example" {
  count    = var.deploy_example_resources ? 1 : 0
  name     = var.resource_group_name
  location = var.region

  tags = local.merged_tags
}

# -----------------------------------------------------------------------------
# Add Container Apps environment, managed identity, log analytics, and other
# dependencies as needed. Every resource must include:
#   tags = local.merged_tags
# so that job metadata flows through to Azure resource tags and cost reports.
# -----------------------------------------------------------------------------
