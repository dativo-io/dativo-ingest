# GCP Cloud Run Runtime Module

Reference implementation for exposing a Cloud Run runtime to Dativo while enforcing consistent labelling.

## Inputs

| Name | Type | Description |
| ---- | ---- | ----------- |
| `project_id` | `string` | Google Cloud project hosting the runtime. |
| `region` | `string` | Cloud Run region. |
| `runtime_type` | `string` | Must be `gcp_cloud_run`. |
| `tags` | `map(string)` | Metadata from Dativo job config. Converted to labels. |
| `default_tags` | `map(string)` | Org-wide labels merged with job metadata. |
| `service_name_override` | `string` | Optional override for the Cloud Run service name. |
| `url_override` | `string` | Optional override for the service URL. |

## Outputs

| Name | Description |
| ---- | ----------- |
| `service_name` | Cloud Run service identifier used by the job (`{{terraform_outputs.service_name}}`). |
| `endpoint_url` | HTTPS endpoint to inject into the job definition (`{{terraform_outputs.endpoint_url}}`). |
| `applied_tags` | Normalised label map applied to resources (for CI assertions). |

## Usage

```hcl
module "dativo_job_runtime" {
  source       = "git::ssh://example.com/terraform-modules.git//gcp_cloud_run_runtime"
  project_id   = var.project_id
  region       = var.region
  runtime_type = "gcp_cloud_run"

  default_tags = local.default_labels
  tags = merge(
    local.job_metadata.required_tags,
    local.job_metadata.extra_tags,
  )
}

output "service_name" {
  value = module.dativo_job_runtime.service_name
}

output "endpoint_url" {
  value = module.dativo_job_runtime.endpoint_url
}

output "applied_tags" {
  value = module.dativo_job_runtime.applied_tags
}
```

> **Hint:** When applying Google Organisation Policies, ensure label keys comply with the [GCP label key format](https://cloud.google.com/resource-manager/docs/creating-managing-labels) (lowercase letters, numbers, underscores, and max length 63). This module normalises keys automatically, but you should still align on a canonical naming scheme.
