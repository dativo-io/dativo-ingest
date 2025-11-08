# Dativo Terraform Modules

This directory contains Terraform modules for provisioning cloud infrastructure for Dativo ETL jobs.

## Overview

Dativo jobs can reference externally-managed infrastructure provisioned via Terraform. These modules provide production-ready templates for:

- **AWS Fargate**: Serverless container runtime on Amazon ECS
- **Azure Container Apps**: Managed container platform on Microsoft Azure
- **GCP Cloud Run**: Serverless container execution on Google Cloud

## Module Structure

```
terraform/
├── modules/
│   ├── aws_fargate/           # AWS ECS Fargate module
│   ├── azure_container_apps/  # Azure Container Apps module
│   └── gcp_cloud_run/         # GCP Cloud Run module
└── README.md                  # This file
```

## Quick Start

### 1. Choose Your Cloud Provider

Select the appropriate module based on your cloud provider:

| Provider | Module | Runtime Type |
|----------|--------|--------------|
| AWS | `aws_fargate` | `aws_fargate` |
| Azure | `azure_container_apps` | `azure_container_apps` |
| GCP | `gcp_cloud_run` | `gcp_cloud_run` |

### 2. Create Terraform Configuration

Example for AWS Fargate:

```hcl
module "stripe_customers_runtime" {
  source = "./modules/aws_fargate"

  region = "us-east-1"

  # Job metadata from Dativo job config
  job_metadata = {
    job_name      = "stripe-customers-etl"
    team          = "data-engineering"
    pipeline_type = "ingestion"
    environment   = "prod"
    cost_center   = "data-platform"
  }

  # Container configuration
  container_image = "123456789012.dkr.ecr.us-east-1.amazonaws.com/dativo:1.1.0"
  cpu             = "1024"
  memory          = "2048"

  # Networking
  vpc_id             = var.vpc_id
  private_subnet_ids = var.private_subnet_ids

  # Permissions
  s3_bucket_arns = ["arn:aws:s3:::my-data-lake/*"]
}

output "cluster_name" {
  value = module.stripe_customers_runtime.cluster_name
}
```

### 3. Run Terraform

```bash
terraform init
terraform plan
terraform apply
```

### 4. Capture Outputs

```bash
terraform output -json > outputs.json
```

### 5. Update Dativo Job Config

Use the `update_job_config.py` script to replace placeholders:

```bash
python scripts/update_job_config.py jobs/stripe_customers.yaml outputs.json
```

## Module Documentation

Each module has comprehensive documentation:

- [AWS Fargate Module](modules/aws_fargate/README.md)
- [Azure Container Apps Module](modules/azure_container_apps/README.md)
- [GCP Cloud Run Module](modules/gcp_cloud_run/README.md)

## Tag Propagation

All modules implement consistent tag propagation:

1. **Required Tags** (from `job_metadata` variable):
   - `job_name`: Unique job identifier
   - `team`: Owning team
   - `pipeline_type`: Pipeline category
   - `environment`: Deployment environment
   - `cost_center`: Cost allocation identifier

2. **Default Tags** (from `default_tags` variable):
   - Organization-wide tags

3. **Module Tags** (automatically added):
   - `managed_by`: terraform
   - `dativo_runtime`: [runtime_type]

**All provisioned resources get these tags** for cost allocation, compliance, and traceability.

## Common Variables

All modules support these common variables:

| Variable | Type | Required | Description |
|----------|------|----------|-------------|
| `job_metadata` | map(string) | Yes | Job metadata tags (must include: job_name, team, pipeline_type, environment, cost_center) |
| `region` | string | Yes | Cloud region |
| `container_image` | string | Yes | Container image URI |
| `cpu` | string | Yes | CPU allocation (format varies by provider) |
| `memory` | string | Yes | Memory allocation (format varies by provider) |
| `default_tags` / `default_labels` | map(string) | No | Organization-wide tags/labels |

## Common Outputs

All modules provide these common outputs:

| Output | Description |
|--------|-------------|
| `cluster_name` | Cluster/environment name |
| `service_name` | Service/job name |
| `endpoint_url` | Service endpoint URL |
| `all_tags` / `all_labels` | All tags/labels applied to resources |

## Best Practices

### 1. Remote State

Use remote state backend for production:

```hcl
terraform {
  backend "s3" {
    bucket = "my-terraform-state"
    key    = "dativo/infrastructure/terraform.tfstate"
    region = "us-east-1"
  }
}
```

### 2. Module Versioning

Pin module versions in production:

```hcl
module "runtime" {
  source = "git::ssh://git@github.com/my-org/terraform-modules.git//dativo_runtime/aws_fargate?ref=v1.2.3"
  # ...
}
```

### 3. Variable Files

Use separate variable files per environment:

```hcl
# terraform.tfvars.prod
job_metadata = {
  job_name      = "stripe-customers-etl"
  team          = "data-engineering"
  pipeline_type = "ingestion"
  environment   = "prod"
  cost_center   = "data-platform"
}
```

### 4. Secrets Management

Never commit secrets to git. Use:
- AWS Secrets Manager (AWS)
- Azure Key Vault (Azure)
- Google Secret Manager (GCP)

### 5. Testing

Test in non-prod environments first:

```bash
# Dev environment
terraform workspace select dev
terraform plan -var-file=terraform.tfvars.dev

# Prod environment (after testing)
terraform workspace select prod
terraform plan -var-file=terraform.tfvars.prod
```

## CI/CD Integration

See [CI/CD Workflows Guide](../docs/TERRAFORM_CICD_WORKFLOWS.md) for complete automation examples.

### GitHub Actions Example

```yaml
- name: Terraform Apply
  run: |
    cd terraform/dativo_jobs
    terraform init
    terraform apply -auto-approve
    terraform output -json > outputs.json

- name: Update Job Configs
  run: |
    python scripts/update_job_config.py jobs/my_job.yaml terraform/dativo_jobs/outputs.json
```

## Troubleshooting

### Issue: "job_metadata must contain: job_name, team, ..."

**Solution:** Ensure all required tags are present in `job_metadata` variable.

### Issue: "Runtime type 'aws_fargate' is not compatible with provider 'azure'"

**Solution:** Match provider with runtime type in your Dativo job config.

### Issue: Terraform state locking errors

**Solution:** Enable state locking in your backend configuration.

## Cost Optimization

1. **Right-size resources**: Start with minimal CPU/memory and scale up based on metrics
2. **Enable scale-to-zero**: For batch jobs, set `min_instances`/`min_replicas` to 0
3. **Configure log retention**: Balance compliance requirements with storage costs
4. **Monitor costs by tags**: Use cost allocation reports filtered by `cost_center` tag

## Security

1. **Least-privilege IAM**: Grant only necessary permissions
2. **Private networking**: Use VPC/VNet for database access
3. **Secrets management**: Use cloud-native secret managers
4. **Encryption at rest**: Enable for logs and storage
5. **State encryption**: Enable backend encryption

## Additional Resources

- [Main Integration Guide](../docs/TERRAFORM_INFRASTRUCTURE_INTEGRATION.md)
- [Implementation Summary](../TERRAFORM_INTEGRATION_SUMMARY.md)
- [Example Job Configurations](../docs/examples/jobs/acme/)
- [AWS Tagging Best Practices](https://docs.aws.amazon.com/whitepapers/latest/tagging-best-practices/)
- [Azure Tagging Strategy](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-tagging)
- [GCP Labeling Best Practices](https://cloud.google.com/resource-manager/docs/creating-managing-labels)

## Support

For issues or questions:
1. Check module-specific README files
2. Review [troubleshooting section](../docs/TERRAFORM_INFRASTRUCTURE_INTEGRATION.md#troubleshooting)
3. Open an issue on the repository
4. Contact the Dativo platform team
