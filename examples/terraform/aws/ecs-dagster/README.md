# Dativo ETL Job - AWS ECS with Dagster

This Terraform module provisions infrastructure for running Dativo ETL jobs on AWS ECS with Dagster orchestration.

## Features

- **ECS Fargate Tasks**: Serverless container execution
- **IAM Roles**: Least-privilege IAM roles for task execution and application access
- **S3 Integration**: Secure access to S3 buckets with KMS encryption
- **CloudWatch Logs**: Centralized logging with retention policies
- **Security Groups**: Network isolation and security
- **Tag Propagation**: Comprehensive tagging for cost allocation and compliance

## Usage

### Basic Example

```hcl
module "dativo_etl_job" {
  source = "git::https://github.com/your-org/terraform-dativo-aws.git//modules/ecs-dagster?ref=v1.0.0"
  
  # Job identification
  job_name    = "stripe-customers"
  tenant_id   = "acme"
  environment = "prod"
  
  # Runtime configuration
  runtime_cluster_name = "dativo-prod-cluster"
  create_cluster       = false  # Use existing cluster
  
  # Compute resources
  compute_cpu    = "2048"  # 2 vCPU
  compute_memory = "4Gi"   # 4 GB
  
  # Networking
  networking_vpc_id             = "vpc-0123456789abcdef0"
  networking_subnet_ids         = ["subnet-0123456789abcdef0", "subnet-0123456789abcdef1"]
  networking_private_networking = true
  
  # Storage
  storage_bucket     = "acme-data-lake"
  storage_prefix     = "raw/stripe/customers"
  storage_kms_key_id = "arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-123456789012"
  
  # Tags for cost allocation
  tags = {
    CostCenter  = "HR-001"
    Project     = "data-platform"
    Environment = "production"
    ManagedBy   = "terraform"
    Team        = "data-engineering"
  }
}
```

### With Secrets from SSM Parameter Store

```hcl
module "dativo_etl_job" {
  source = "./modules/ecs-dagster"
  
  job_name    = "stripe-customers"
  tenant_id   = "acme"
  environment = "prod"
  
  # ... other configuration ...
  
  # Secrets from SSM
  secrets_from_ssm = [
    {
      name      = "STRIPE_API_KEY"
      valueFrom = "arn:aws:ssm:us-east-1:123456789012:parameter/dativo/acme/stripe/api_key"
    },
    {
      name      = "NESSIE_URI"
      valueFrom = "arn:aws:ssm:us-east-1:123456789012:parameter/dativo/nessie/uri"
    }
  ]
}
```

### Multi-Tenant Deployment

```hcl
locals {
  tenants = ["acme", "globex", "initech"]
}

module "dativo_etl_jobs" {
  for_each = toset(local.tenants)
  
  source = "./modules/ecs-dagster"
  
  job_name    = "stripe-customers"
  tenant_id   = each.key
  environment = "prod"
  
  runtime_cluster_name = "dativo-shared-prod"
  
  storage_bucket = "dativo-shared-data-lake"
  storage_prefix = "${each.key}/raw/stripe/customers"
  
  tags = {
    Tenant      = each.key
    CostCenter  = "DATA-001"
    Environment = "production"
  }
  
  # ... other configuration ...
}
```

## Requirements

| Name | Version |
|------|---------|
| terraform | >= 1.0 |
| aws | ~> 5.0 |

## Providers

| Name | Version |
|------|---------|
| aws | ~> 5.0 |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|----------|
| job_name | Job name from Dativo configuration | string | - | yes |
| tenant_id | Tenant ID | string | - | yes |
| environment | Environment (dev, staging, prod) | string | - | yes |
| runtime_cluster_name | ECS cluster name | string | - | yes |
| compute_cpu | CPU request (e.g., '1024', '2048') | string | "1024" | no |
| compute_memory | Memory request (e.g., '2Gi', '4Gi') | string | "2Gi" | no |
| networking_vpc_id | VPC ID | string | - | yes |
| networking_subnet_ids | Subnet IDs | list(string) | - | yes |
| storage_bucket | S3 bucket name | string | - | yes |
| storage_prefix | S3 prefix | string | - | yes |
| storage_kms_key_id | KMS key ARN | string | null | no |
| tags | Resource tags | map(string) | {} | no |

See [variables.tf](./variables.tf) for complete list of inputs.

## Outputs

| Name | Description |
|------|-------------|
| cluster_arn | ECS cluster ARN |
| task_definition_arn | ECS task definition ARN |
| task_role_arn | Task role ARN |
| execution_role_arn | Execution role ARN |
| security_group_id | Security group ID |
| log_group_name | CloudWatch log group name |
| dagster_ecs_config | Configuration for Dagster ECS operator |

## Integration with Dagster

This module outputs a `dagster_ecs_config` object that can be used directly with Dagster's ECS operator:

```python
from dagster import job, op
from dagster_aws.ecs import EcsRunLauncher

@op
def run_dativo_etl():
    # Your ETL logic here
    pass

@job(
    resource_defs={
        "ecs": EcsRunLauncher(
            **terraform_output["dagster_ecs_config"]
        )
    }
)
def dativo_etl_job():
    run_dativo_etl()
```

## Cost Optimization

### Right-Sizing

- Start with smaller CPU/memory allocation and scale up based on monitoring
- Use Fargate Spot for non-critical jobs (up to 70% cost savings)
- Implement auto-scaling based on queue depth

### Storage Optimization

- Use S3 Intelligent-Tiering for automatic cost optimization
- Enable S3 lifecycle policies to transition old data to cheaper storage classes
- Use KMS encryption with customer-managed keys for compliance

### Monitoring

- Track ECS task CPU and memory utilization in CloudWatch
- Set up Cost Anomaly Detection in AWS Cost Explorer
- Use AWS Cost and Usage Reports for detailed cost analysis

## Security Best Practices

1. **Least Privilege**: Task roles have minimal permissions for S3 and KMS access
2. **Network Isolation**: Use private subnets with no public IP assignment
3. **Encryption**: Enable encryption at rest (S3 with KMS) and in transit (TLS)
4. **Secrets Management**: Use SSM Parameter Store or Secrets Manager for sensitive data
5. **Logging**: Enable CloudWatch Logs with encryption and retention policies

## Troubleshooting

### Task fails to start

1. Check CloudWatch logs: `/ecs/dativo/{tenant_id}/{job_name}`
2. Verify IAM role permissions for S3 and KMS access
3. Ensure container image is accessible from ECS
4. Check security group rules for outbound connectivity

### Insufficient CPU/Memory

Increase `compute_cpu` and `compute_memory` in module configuration:

```hcl
compute_cpu    = "4096"  # 4 vCPU
compute_memory = "8Gi"   # 8 GB
```

### Network connectivity issues

1. Verify subnets have NAT Gateway for internet access
2. Check security group rules
3. Ensure VPC endpoints are configured for AWS services

## Examples

See [examples/](../../../jobs/) for complete examples:
- Basic ECS job
- Multi-tenant deployment
- Integration with Dagster
- Custom IAM policies
- VPC configuration

## License

Apache 2.0
