# Azure Container Apps Terraform Module for Dativo ETL Jobs

This Terraform module provisions Azure Container Apps infrastructure for running Dativo ETL jobs as containerized workloads.

## Features

- **Container Apps Environment**: Shared infrastructure for container apps
- **Container App or Container App Job**: Choose between long-running app or batch job
- **Managed Identity**: User-assigned managed identity for Azure resource access
- **Log Analytics**: Centralized logging and monitoring
- **Role-Based Access Control**: Automatic role assignments for Storage and Key Vault
- **Tag Propagation**: All resources tagged with job metadata for cost allocation and compliance
- **Scale-to-Zero**: Cost-effective with automatic scaling based on workload

## Usage

```hcl
module "dativo_job_runtime" {
  source = "git::ssh://git@github.com/your-org/terraform-modules.git//dativo_runtime/azure_container_apps"

  region = "eastus"

  # Job metadata from Dativo job config (required)
  job_metadata = {
    job_name      = "stripe-customers-etl"
    team          = "data-engineering"
    pipeline_type = "ingestion"
    environment   = "prod"
    cost_center   = "data-platform"
  }

  # Default tags (merged with job_metadata)
  default_tags = {
    project     = "dativo-platform"
    managed_by  = "terraform"
  }

  # Resource group
  create_resource_group = true

  # Container configuration
  container_image = "acmeregistry.azurecr.io/dativo:1.1.0"
  cpu             = 1.0
  memory          = "2Gi"

  # Scaling
  min_replicas = 0  # Scale to zero when idle
  max_replicas = 1

  # Permissions - Storage Account access
  storage_account_ids = [
    "/subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/data-rg/providers/Microsoft.Storage/storageAccounts/acmedatalake"
  ]

  # Permissions - Key Vault access
  keyvault_ids = [
    "/subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/security-rg/providers/Microsoft.KeyVault/vaults/acme-secrets"
  ]

  # Environment variables
  environment_variables = [
    {
      name  = "DATIVO_MODE"
      value = "cloud"
    }
  ]

  # Secrets from Key Vault
  secrets_from_keyvault = [
    {
      name                = "STRIPE_API_KEY"
      secret_name         = "stripe-api-key"
      keyvault_secret_id  = "https://acme-secrets.vault.azure.net/secrets/stripe-api-key"
    }
  ]

  # Logging
  log_retention_days = 30

  # Use Container App Job for batch workloads
  create_job_instead_of_app   = true
  job_replica_timeout_seconds = 3600
  job_replica_retry_limit     = 3
}
```

## Container App vs Container App Job

### Container App (Default)
- Long-running applications
- HTTP ingress support
- Auto-scaling based on HTTP requests or custom metrics
- Use for: API services, web apps, streaming workloads

### Container App Job (`create_job_instead_of_app = true`)
- Batch/scheduled workloads
- Manual or scheduled triggers
- Runs to completion
- Use for: ETL jobs, data processing, cron jobs

## Outputs

Use these outputs in your Dativo job configuration:

```yaml
infrastructure:
  provider: azure
  runtime:
    type: azure_container_apps
  region: eastus
  resource_identifiers:
    cluster_name: "{{terraform_outputs.cluster_name}}"
    service_name: "{{terraform_outputs.service_name}}"
    managed_identity_id: "{{terraform_outputs.managed_identity_id}}"
  tags:
    job_name: stripe-customers-etl
    team: data-engineering
    pipeline_type: ingestion
    environment: prod
    cost_center: data-platform
```

## Tagging Strategy

All resources created by this module are tagged with:

1. **Job metadata tags** (from `job_metadata` variable):
   - `job_name`: Dativo job identifier
   - `team`: Owning team
   - `pipeline_type`: Type of pipeline (ingestion, transformation, etc.)
   - `environment`: Deployment environment (dev, staging, prod)
   - `cost_center`: Cost allocation identifier

2. **Default tags** (from `default_tags` variable):
   - Organization-wide tags (e.g., project, managed_by)

3. **Module-added tags**:
   - `managed_by`: terraform
   - `dativo_runtime`: azure_container_apps

This ensures consistent tagging for cost allocation, compliance auditing, and resource classification.

## Requirements

| Name | Version |
|------|---------|
| terraform | >= 1.5.0 |
| azurerm | ~> 3.0 |

## Inputs

See [variables.tf](./variables.tf) for complete input documentation.

## Outputs

See [outputs.tf](./outputs.tf) for complete output documentation.

## Cost Optimization

- Enable scale-to-zero (`min_replicas = 0`) for batch jobs
- Use appropriate CPU/memory combinations (see [Azure Container Apps Pricing](https://azure.microsoft.com/en-us/pricing/details/container-apps/))
- Configure `log_retention_days` based on compliance requirements
- Use consumption-based billing (no minimum charge when idle)

## Security Best Practices

1. **Managed Identity**: Use user-assigned managed identity for Azure resource access
2. **Least Privilege**: Role assignments grant only necessary permissions
3. **Key Vault Integration**: Store secrets in Azure Key Vault
4. **Network Isolation**: Deploy in virtual network for enhanced security (requires additional configuration)
5. **Logging**: All container output sent to Log Analytics

## References

- [Azure Container Apps Documentation](https://learn.microsoft.com/en-us/azure/container-apps/)
- [Container Apps Jobs](https://learn.microsoft.com/en-us/azure/container-apps/jobs)
- [Azure Tagging Strategy](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-tagging)
- [Managed Identities](https://learn.microsoft.com/en-us/azure/active-directory/managed-identities-azure-resources/overview)
