# Azure Container Apps Runtime Skeleton

Use this reference module when Dativo jobs run on Azure Container Apps provisioned by a separate Terraform pipeline. It illustrates how to merge job metadata with platform defaults and expose the runtime identifiers back to the job definition.

## Implementation Notes

- The AzureRM provider is configured with `default_tags = var.default_tags`; job metadata is merged via `local.merged_tags` and must be applied to every resource.
- The module derives canonical names (`environment_name`, `container_app_name`) from the job metadata when a value is not supplied. Override them by passing the optional `existing_*` variables.
- Extend the module with Container Apps environment, Log Analytics workspace, managed identities, virtual network integrations, and secrets as required by your platform.

## Inputs

| Name | Description |
|------|-------------|
| `subscription_id`, `tenant_id` | Azure context for the deployment. |
| `region` | Azure location (e.g., `eastus`, `westeurope`). |
| `resource_group_name` | Resource group hosting the runtime. |
| `runtime_type` | Validated to `"azure_container_apps"`. |
| `tags` | Metadata propagated from the Dativo job. |
| `default_tags` | Organization defaults that are merged with the job metadata. |
| `existing_environment_name` / `existing_container_app_name` | Use when infrastructure already exists but you still want module outputs. |
| `ingress_url_override` | Provide a custom URL (for private endpoints, Front Door, etc.). |
| `deploy_example_resources` | Optional flag that provisions a tagged `azurerm_resource_group` to demonstrate propagation. |

## Outputs

- `environment_name` – Container Apps environment reference.
- `container_app_name` – Container App that executes the job runtime.
- `ingress_url` – Ingress endpoint surfaced back to the job configuration.

## Usage Example

```hcl
module "dativo_runtime" {
  source = "git::ssh://example.com/terraform-modules.git//azure_container_apps"

  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id
  region          = var.region
  resource_group_name = azurerm_resource_group.runtime.name

  runtime_type = var.runtime_type
  tags         = var.job_metadata
  default_tags = var.platform_defaults

  existing_environment_name = azurerm_container_app_environment.runtime.name
  ingress_url_override      = azurerm_container_app.runtime.latest_revision_fqdn
}
```

Serialise the module outputs (e.g., `terraform output -json`) so the CI/CD pipeline can replace the `{{terraform_outputs.*}}` placeholders inside the Dativo job definition.

