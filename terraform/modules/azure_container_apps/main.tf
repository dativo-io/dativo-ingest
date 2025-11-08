# Azure Container Apps Runtime Module for Dativo ETL Jobs
# This module provisions Azure Container Apps infrastructure for running Dativo containerized workloads

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

# Local variables for consistent naming and tagging
locals {
  # Merge default tags with job-specific metadata
  common_tags = merge(
    var.default_tags,
    var.job_metadata,
    {
      "managed_by"     = "terraform"
      "dativo_runtime" = "azure_container_apps"
    }
  )

  # Resource naming convention (Azure has strict naming requirements)
  name_prefix = lower(replace("${var.job_metadata["job_name"]}-${var.job_metadata["environment"]}", "_", "-"))
}

# Resource Group for Dativo job resources
resource "azurerm_resource_group" "dativo_rg" {
  count    = var.create_resource_group ? 1 : 0
  name     = "${local.name_prefix}-rg"
  location = var.region

  tags = local.common_tags
}

data "azurerm_resource_group" "existing_rg" {
  count = var.create_resource_group ? 0 : 1
  name  = var.existing_resource_group_name
}

# Log Analytics Workspace for Container Apps logs
resource "azurerm_log_analytics_workspace" "dativo_logs" {
  name                = "${local.name_prefix}-logs"
  location            = var.region
  resource_group_name = var.create_resource_group ? azurerm_resource_group.dativo_rg[0].name : data.azurerm_resource_group.existing_rg[0].name
  sku                 = "PerGB2018"
  retention_in_days   = var.log_retention_days

  tags = local.common_tags
}

# Container Apps Environment (shared infrastructure)
resource "azurerm_container_app_environment" "dativo_env" {
  name                       = "${local.name_prefix}-env"
  location                   = var.region
  resource_group_name        = var.create_resource_group ? azurerm_resource_group.dativo_rg[0].name : data.azurerm_resource_group.existing_rg[0].name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.dativo_logs.id

  tags = local.common_tags
}

# User-Assigned Managed Identity for Container App
resource "azurerm_user_assigned_identity" "dativo_identity" {
  name                = "${local.name_prefix}-identity"
  location            = var.region
  resource_group_name = var.create_resource_group ? azurerm_resource_group.dativo_rg[0].name : data.azurerm_resource_group.existing_rg[0].name

  tags = local.common_tags
}

# Role assignments for managed identity
# Storage Blob Data Contributor role for Azure Storage access
resource "azurerm_role_assignment" "storage_blob_contributor" {
  count                = length(var.storage_account_ids)
  scope                = var.storage_account_ids[count.index]
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.dativo_identity.principal_id
}

# Key Vault Secrets User role for accessing secrets
resource "azurerm_role_assignment" "keyvault_secrets_user" {
  count                = length(var.keyvault_ids)
  scope                = var.keyvault_ids[count.index]
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.dativo_identity.principal_id
}

# Container App
resource "azurerm_container_app" "dativo_app" {
  name                         = "${local.name_prefix}-app"
  container_app_environment_id = azurerm_container_app_environment.dativo_env.id
  resource_group_name          = var.create_resource_group ? azurerm_resource_group.dativo_rg[0].name : data.azurerm_resource_group.existing_rg[0].name
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.dativo_identity.id]
  }

  template {
    container {
      name   = "dativo-etl"
      image  = var.container_image
      cpu    = var.cpu
      memory = var.memory

      # Environment variables
      dynamic "env" {
        for_each = var.environment_variables
        content {
          name  = env.value.name
          value = env.value.value
        }
      }

      # Secrets from Azure Key Vault
      dynamic "env" {
        for_each = var.secrets_from_keyvault
        content {
          name        = env.value.name
          secret_name = env.value.secret_name
        }
      }
    }

    min_replicas = var.min_replicas
    max_replicas = var.max_replicas
  }

  # Manual trigger mode for batch jobs (set ingress for HTTP-triggered jobs)
  dynamic "ingress" {
    for_each = var.enable_ingress ? [1] : []
    content {
      external_enabled = var.ingress_external_enabled
      target_port      = var.ingress_target_port
      traffic_weight {
        percentage      = 100
        latest_revision = true
      }
    }
  }

  # Secrets for the container app (from Key Vault references)
  dynamic "secret" {
    for_each = var.secrets_from_keyvault
    content {
      name                = secret.value.secret_name
      key_vault_secret_id = secret.value.keyvault_secret_id
      identity            = azurerm_user_assigned_identity.dativo_identity.id
    }
  }

  tags = local.common_tags
}

# Container App Job (for scheduled/batch workloads)
resource "azurerm_container_app_job" "dativo_job" {
  count                        = var.create_job_instead_of_app ? 1 : 0
  name                         = "${local.name_prefix}-job"
  location                     = var.region
  resource_group_name          = var.create_resource_group ? azurerm_resource_group.dativo_rg[0].name : data.azurerm_resource_group.existing_rg[0].name
  container_app_environment_id = azurerm_container_app_environment.dativo_env.id

  replica_timeout_in_seconds = var.job_replica_timeout_seconds
  replica_retry_limit        = var.job_replica_retry_limit

  manual_trigger_config {
    parallelism              = var.job_parallelism
    replica_completion_count = var.job_replica_completion_count
  }

  template {
    container {
      name   = "dativo-etl-job"
      image  = var.container_image
      cpu    = var.cpu
      memory = var.memory

      # Environment variables
      dynamic "env" {
        for_each = var.environment_variables
        content {
          name  = env.value.name
          value = env.value.value
        }
      }
    }
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.dativo_identity.id]
  }

  tags = local.common_tags
}
