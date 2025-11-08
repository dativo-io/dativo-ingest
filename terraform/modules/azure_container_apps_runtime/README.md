# Azure Container Apps Runtime Module

This reference module demonstrates how to front Dativo jobs with Azure Container Apps while retaining end-to-end tagging and traceability.

## Inputs

| Name | Type | Description |
| ---- | ---- | ----------- |
| `region` | `string` | Azure region (location) for the resources. |
| `resource_group_name` | `string` | Resource group hosting the Container Apps environment. |
| `runtime_type` | `string` | Must be `azure_container_apps`. |
| `tags` | `map(string)` | Mandatory metadata from the Dativo job definition. |
| `default_tags` | `map(string)` | Subscription or landing-zone defaults merged with the job tags. |
| `environment_name_override` | `string` | Optional override for the Container Apps environment name. |
| `service_name_override` | `string` | Optional override for the Container App name. |
| `endpoint_url_override` | `string` | Optional override for the default FQDN. |

## Outputs

| Name | Description |
| ---- | ----------- |
| `environment_name` | Environment identifier surfaced back to the job config (`{{terraform_outputs.environment_name}}`). |
| `service_name` | Container App name used by the runtime (`{{terraform_outputs.service_name}}`). |
| `endpoint_url` | Default FQDN for inbound traffic (`{{terraform_outputs.endpoint_url}}`). |
| `applied_tags` | Final tag map after merging defaults and job metadata. |

## Usage

```hcl
module "dativo_job_runtime" {
  source              = "git::ssh://example.com/terraform-modules.git//azure_container_apps_runtime"
  region              = var.azure_region
  resource_group_name = azurerm_resource_group.data_jobs.name
  runtime_type        = "azure_container_apps"

  default_tags = local.platform_default_tags
  tags = merge(
    local.job_metadata.required_tags,
    local.job_metadata.extra_tags,
  )
}

output "environment_name" {
  value = module.dativo_job_runtime.environment_name
}

output "service_name" {
  value = module.dativo_job_runtime.service_name
}

output "endpoint_url" {
  value = module.dativo_job_runtime.endpoint_url
}
```

> **Best practice:** Align tag keys with Azure Policy requirements so non-compliant resources are blocked before deployment. Microsoft recommends enforcing [`CostCenter`, `Owner`, `Environment`, and `Application`](https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/resource-tagging).
