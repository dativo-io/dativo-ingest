# AWS Fargate Terraform Module for Dativo ETL Jobs

This Terraform module provisions AWS ECS Fargate infrastructure for running Dativo ETL jobs as containerized workloads.

## Features

- **ECS Fargate Cluster**: Serverless container runtime
- **Task Definition**: Container specifications with resource limits
- **IAM Roles**: Separate execution and task roles with least-privilege permissions
- **CloudWatch Logs**: Centralized logging with configurable retention
- **Security Groups**: Network isolation for Fargate tasks
- **Tag Propagation**: All resources tagged with job metadata for cost allocation and compliance
- **Optional ECS Service**: For long-running jobs (disabled for batch/scheduled jobs)

## Usage

```hcl
module "dativo_job_runtime" {
  source = "git::ssh://git@github.com/your-org/terraform-modules.git//dativo_runtime/aws_fargate"

  region = "us-east-1"

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

  # Container configuration
  container_image = "123456789012.dkr.ecr.us-east-1.amazonaws.com/dativo:1.1.0"
  cpu             = "1024"
  memory          = "2048"

  # Networking
  vpc_id             = var.vpc_id
  private_subnet_ids = var.private_subnet_ids
  assign_public_ip   = false

  # Permissions
  s3_bucket_arns = [
    "arn:aws:s3:::acme-data-lake",
    "arn:aws:s3:::acme-data-lake/*"
  ]
  secrets_arns = [
    "arn:aws:secretsmanager:us-east-1:123456789012:secret:dativo/stripe-*"
  ]

  # Environment variables
  environment_variables = [
    {
      name  = "DATIVO_MODE"
      value = "cloud"
    }
  ]

  # Logging
  enable_container_insights = true
  log_retention_days        = 30

  # Service configuration (set to false for batch jobs)
  create_service        = false
  service_desired_count = 0
}
```

## Outputs

Use these outputs in your Dativo job configuration:

```yaml
infrastructure:
  provider: aws
  runtime:
    type: aws_fargate
  region: us-east-1
  resource_identifiers:
    cluster_name: "{{terraform_outputs.cluster_name}}"
    task_definition_arn: "{{terraform_outputs.task_definition_arn}}"
    service_name: "{{terraform_outputs.service_name}}"
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
   - `dativo_runtime`: aws_fargate

This ensures consistent tagging for cost allocation, compliance auditing, and resource classification.

## Requirements

| Name | Version |
|------|---------|
| terraform | >= 1.5.0 |
| aws | ~> 5.0 |

## Inputs

See [variables.tf](./variables.tf) for complete input documentation.

## Outputs

See [outputs.tf](./outputs.tf) for complete output documentation.

## Cost Optimization

- Use appropriate CPU/memory combinations (see [AWS Fargate Pricing](https://aws.amazon.com/fargate/pricing/))
- Configure `log_retention_days` based on compliance requirements
- Set `enable_container_insights` to false in non-prod environments
- Use Fargate Spot for non-critical workloads (requires additional configuration)

## Security Best Practices

1. **Network Isolation**: Tasks run in private subnets with no public IP
2. **Least Privilege IAM**: Separate execution and task roles with minimal permissions
3. **Secrets Management**: Use AWS Secrets Manager for credentials
4. **Logging**: All task output sent to CloudWatch Logs
5. **Encryption**: Enable encryption at rest for logs (add KMS key configuration)

## References

- [AWS Fargate Documentation](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html)
- [ECS Task Definition Parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html)
- [AWS Tagging Best Practices](https://docs.aws.amazon.com/whitepapers/latest/tagging-best-practices/tagging-best-practices.html)
