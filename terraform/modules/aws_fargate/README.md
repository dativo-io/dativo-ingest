# AWS Fargate Runtime Skeleton

This reference module demonstrates how to receive infrastructure metadata from a Dativo job definition and forward it into AWS resources managed by Terraform. It is intentionally minimal: replace the placeholder resources with your organization’s ECS/Fargate deployment pattern.

## Key Practices

- Accept the `tags` map coming from the job definition and merge it with your platform’s `default_tags`.
- Configure the AWS provider with `default_tags` so that every downstream resource inherits the FinOps, ownership, and compliance metadata.
- When defining resources, always set `tags = local.merged_tags`.
- Expose outputs (`cluster_name`, `service_name`, `service_endpoint`) that the job definition references via `{{terraform_outputs.*}}`.

## Inputs

| Name | Description |
|------|-------------|
| `region` | AWS region for the runtime. Aligns with `infrastructure.region` in the job config. |
| `runtime_type` | Should be `"aws_fargate"`. Validation prevents misuse. |
| `tags` | Map of metadata from the job config (`job_name`, `team`, `pipeline_type`, `environment`, `cost_center`, etc.). |
| `default_tags` | Organization-wide defaults merged with the job metadata. |
| `existing_cluster_name` / `existing_service_name` | Let you reference previously created infrastructure while still emitting Terraform outputs. |
| `service_endpoint_override` | Override when the service endpoint is determined elsewhere (e.g., via load balancer module). |
| `deploy_example_resources` | Optional flag that provisions a sample `aws_ecs_cluster` to illustrate tag propagation. |

Extend the module with additional variables for VPC, networking, task definitions, IAM roles, observability, etc. as needed.

## Outputs

- `cluster_name` – ECS cluster coordinating the runtime.
- `service_name` – ECS service handling job container orchestration.
- `service_endpoint` – Endpoint/URL surfaced back to the job config (often an ALB DNS name or API Gateway URL).

## Usage Example

```hcl
module "dativo_runtime" {
  source = "git::ssh://example.com/terraform-modules.git//aws_fargate"

  region       = var.region
  runtime_type = var.runtime_type
  tags         = var.job_metadata
  default_tags = var.platform_defaults

  # Optional overrides when infrastructure already exists
  existing_cluster_name = var.precreated_cluster
  existing_service_name = var.precreated_service
}
```

Ensure the consuming pipeline serialises the module outputs to a JSON file so they can be injected into the Dativo job definition placeholders (`{{terraform_outputs.cluster_name}}`, etc.).

