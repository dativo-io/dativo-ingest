# GCP Cloud Run Runtime Skeleton

This reference module shows how to wire metadata from a Dativo job definition into Google Cloud Run infrastructure managed by Terraform. Replace the sample resources with your production deployment pattern (networking, IAM, secrets, etc.).

## Highlights

- Merges `var.tags` (job metadata) with `var.default_tags` to create a unified `local.merged_labels` map that should be applied to every Google resource (`labels = local.merged_labels`).
- Emits standard outputs (`service_name`, `project_id`, `service_url`) that map directly to `{{terraform_outputs.*}}` placeholders in job configurations.
- Provides an optional example Cloud Run service (`deploy_example_resources = true`) that demonstrates label propagation.

## Inputs

| Name | Description |
|------|-------------|
| `project_id` | GCP project hosting the runtime. |
| `region` | Cloud Run region (e.g., `us-central1`). |
| `runtime_type` | Validated to `"gcp_cloud_run"`. |
| `tags` | Map of metadata forwarded from the job definition. |
| `default_tags` | Platform defaults merged with job metadata. |
| `existing_service_name` | Supply when the Cloud Run service already exists but you still need outputs. |
| `service_url_override` | Custom URL (e.g., HTTPS Load Balancer, custom domain). |
| `deploy_example_resources` | Provision the sample Cloud Run service for demonstration purposes. |
| `container_image` | Image used by the sample service when `deploy_example_resources` is true. |

## Outputs

- `service_name` – Cloud Run service identifier.
- `project_id` – Echoed for convenience and cross-environment scripting.
- `service_url` – URL returned to the job definition (Cloud Run URI or override).

## Usage Example

```hcl
module "dativo_runtime" {
  source = "git::ssh://example.com/terraform-modules.git//gcp_cloud_run"

  project_id  = var.project_id
  region      = var.region
  runtime_type = var.runtime_type

  tags         = var.job_metadata
  default_tags = var.platform_defaults

  existing_service_name = google_cloud_run_v2_service.runtime.name
  service_url_override  = google_cloud_run_v2_service.runtime.uri
}
```

Export the outputs (`terraform output -json`) so your pipeline can inject them into the Dativo job definition’s `resource_identifiers`.

