# AWS Fargate Runtime Module

This reference module demonstrates how platform teams can expose an AWS Fargate runtime to Dativo jobs while honouring the tagging metadata defined in the job configuration.

## Inputs

| Name | Type | Description |
| ---- | ---- | ----------- |
| `region` | `string` | AWS region for the runtime infrastructure. |
| `runtime_type` | `string` | Must be `aws_fargate`. Validated to avoid misconfiguration. |
| `tags` | `map(string)` | Mandatory job metadata propagated from Dativo (`job_name`, `team`, `pipeline_type`, `environment`, `cost_center`, plus any extras). |
| `default_tags` | `map(string)` | Platform-wide defaults (e.g. `owner`, `compliance`). Merged with `tags`. |
| `cluster_name_override` | `string` | Optional override for the ECS cluster name. |
| `service_name_override` | `string` | Optional override for the ECS service name. |
| `endpoint_url_override` | `string` | Optional override when the URL is known ahead of time. |

The module builds a `local.merged_tags` map using:

```hcl
locals {
  merged_tags = merge(var.default_tags, var.tags)
}
```

Apply `local.merged_tags` to every resource to guarantee FinOps, audit, and compliance metadata is consistent.

## Outputs

| Name | Description |
| ---- | ----------- |
| `cluster_name` | ECS cluster identifier referenced by the Dativo job (`{{terraform_outputs.cluster_name}}`). |
| `service_name` | Service identifier for task scheduling (`{{terraform_outputs.service_name}}`). |
| `endpoint_url` | Public/runtime endpoint propagated back into the job definition. |
| `applied_tags` | Snapshot of the merged tag map for debugging and CI assertions. |

## Usage

```hcl
module "dativo_job_runtime" {
  source       = "git::ssh://example.com/terraform-modules.git//aws_fargate_runtime"
  region       = var.aws_region
  runtime_type = "aws_fargate"

  default_tags = local.global_default_tags
  tags = merge(
    {
      job_name      = local.job_metadata.job_name
      team          = local.job_metadata.team
      pipeline_type = local.job_metadata.pipeline_type
      environment   = local.job_metadata.environment
      cost_center   = local.job_metadata.cost_center
    },
    local.job_metadata.extra_tags,
    var.additional_tags,
  )
}

output "cluster_name" {
  value = module.dativo_job_runtime.cluster_name
}

output "service_name" {
  value = module.dativo_job_runtime.service_name
}

output "endpoint_url" {
  value = module.dativo_job_runtime.endpoint_url
}
```

> **Tip:** Export `module.dativo_job_runtime.applied_tags` to your CI pipeline to assert that required keys are always present before the job definition is updated.
