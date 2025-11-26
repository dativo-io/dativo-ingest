# Terraform Modules for Dativo ETL Infrastructure

This directory contains Terraform modules for deploying Dativo ETL jobs on various cloud platforms with comprehensive tag propagation for cost allocation, compliance, and resource traceability.

## Overview

These modules enable:
- **Cloud-Agnostic Deployment**: Support for AWS, GCP, and Azure
- **Orchestration Integration**: Native support for Dagster, Airflow, Kubernetes
- **Tag Propagation**: Automatic propagation of metadata tags from jobs to infrastructure
- **Multi-Tenant**: Full support for multi-tenant deployments with tenant isolation
- **Cost Allocation**: Comprehensive tagging for accurate cost attribution

## Architecture

```
Job Configuration (YAML)
    ↓
Dativo Infrastructure Module
    ↓
├─ Terraform Variables (.tfvars)
├─ Tag Merging (compliance + finops + infrastructure)
└─ Provider-Specific Formatting (AWS/GCP/Azure)
    ↓
Cloud Provider Resources
    ├─ Compute (ECS/Cloud Run/Kubernetes)
    ├─ Networking (VPC/Subnets/Security Groups)
    ├─ Storage (S3/GCS)
    └─ IAM (Roles/Service Accounts)
```

## Available Modules

### AWS Modules

- **[aws/ecs-dagster](./aws/ecs-dagster/)**: ECS Fargate with Dagster orchestration
  - Features: Task definitions, IAM roles, CloudWatch logs, security groups
  - Best for: Production workloads with AWS infrastructure

### GCP Modules

- **[gcp/cloud-run-dagster](./gcp/cloud-run-dagster/)**: Cloud Run with Dagster orchestration
  - Features: Cloud Run jobs, service accounts, VPC connectors, Cloud Logging
  - Best for: Serverless workloads on GCP

## Quick Start

### 1. Reference Module in Job Configuration

Add an `infrastructure` block to your Dativo job configuration:

```yaml
# jobs/acme/stripe_customers.yaml
tenant_id: acme
environment: prod

source_connector_path: /app/connectors/stripe.yaml
target_connector_path: /app/connectors/iceberg.yaml
asset_path: /app/assets/stripe/v1.0/customers.yaml

# Infrastructure configuration
infrastructure:
  provider: aws
  
  runtime:
    type: ecs
    cluster_name: dativo-prod-cluster
    service_account: arn:aws:iam::123456789012:role/dativo-etl-role
  
  compute:
    cpu: "2048"
    memory: "4096"
  
  networking:
    vpc_id: vpc-0123456789abcdef0
    subnet_ids:
      - subnet-0123456789abcdef0
      - subnet-0123456789abcdef1
  
  storage:
    bucket: acme-data-lake
    prefix: raw/stripe/customers
  
  tags:
    CostCenter: HR-001
    Project: data-platform
    Environment: production
  
  terraform:
    module_source: git::https://github.com/acme/terraform-dativo-aws.git//modules/ecs-dagster
    module_version: "1.2.0"
```

### 2. Generate Terraform Variables

Use Dativo CLI to generate Terraform variables:

```bash
# Export terraform.tfvars from job configuration
dativo terraform export \
  --config jobs/acme/stripe_customers.yaml \
  --output terraform/jobs/acme/stripe_customers.tfvars
```

This generates:

```hcl
# terraform/jobs/acme/stripe_customers.tfvars
tenant_id = "acme"
environment = "prod"
provider = "aws"
runtime_type = "ecs"
runtime_cluster_name = "dativo-prod-cluster"
compute_cpu = "2048"
compute_memory = "4096"
networking_vpc_id = "vpc-0123456789abcdef0"
networking_subnet_ids = ["subnet-0123456789abcdef0", "subnet-0123456789abcdef1"]
storage_bucket = "acme-data-lake"
storage_prefix = "raw/stripe/customers"

tags = {
  CostCenter = "HR-001"
  Project = "data-platform"
  Environment = "production"
  dativo:tenant = "acme"
  dativo:environment = "prod"
}
```

### 3. Apply Terraform

```bash
# Initialize Terraform
terraform init

# Plan infrastructure changes
terraform plan \
  -var-file=terraform/jobs/acme/stripe_customers.tfvars

# Apply infrastructure
terraform apply \
  -var-file=terraform/jobs/acme/stripe_customers.tfvars
```

## Module Structure

Each module follows this structure:

```
module-name/
├── main.tf           # Main infrastructure resources
├── variables.tf      # Input variables
├── outputs.tf        # Output values
├── README.md         # Module documentation
└── examples/         # Usage examples
```

## Tag Propagation

Tags flow through the system with this precedence (highest to lowest):

1. **infrastructure.tags** - Job-level infrastructure tags
2. **finops** - Job-level FinOps metadata
3. **asset.finops** - Asset-level FinOps metadata
4. **asset.compliance** - Asset-level compliance metadata
5. **Default tags** - tenant_id, environment, job name

### Example Tag Flow

**Asset Definition** (`assets/stripe/v1.0/customers.yaml`):
```yaml
compliance:
  classification: [PII, SENSITIVE]
  regulations: [GDPR]
finops:
  cost_center: FIN-001
  project: data-platform
```

**Job Configuration** (`jobs/acme/stripe_customers.yaml`):
```yaml
finops:
  cost_center: HR-001      # Overrides asset's FIN-001
  business_tags: [payments, revenue]

infrastructure:
  tags:
    Team: data-engineering # Additional infrastructure tag
```

**Resulting Tags** (applied to all infrastructure):
```yaml
# From asset (lowest priority)
dativo:classification: pii,sensitive
dativo:regulations: GDPR

# From job finops (medium priority)
dativo:cost-center: HR-001          # Overrode asset's FIN-001
dativo:business-tags: payments,revenue
dativo:project: data-platform        # Inherited from asset

# From infrastructure.tags (highest priority)
Team: data-engineering

# Auto-generated
dativo:tenant: acme
dativo:environment: prod
```

## Provider-Specific Formatting

### AWS
- Supports most tag formats
- Tag keys and values can be mixed case
- Maximum 50 tags per resource

### GCP
- Labels must be lowercase
- Hyphens instead of underscores/colons
- Maximum 64 labels per resource
- Keys and values ≤ 63 characters

### Azure
- Keys ≤ 512 characters
- Values ≤ 256 characters
- No specific case requirements

## Multi-Tenant Deployments

### Dedicated Infrastructure per Tenant

```yaml
# jobs/acme/stripe_customers.yaml
tenant_id: acme
infrastructure:
  storage:
    bucket: acme-data-lake
  tags:
    Tenant: acme
```

```yaml
# jobs/globex/stripe_customers.yaml
tenant_id: globex
infrastructure:
  storage:
    bucket: globex-data-lake
  tags:
    Tenant: globex
```

### Shared Infrastructure with Tenant Isolation

```yaml
# Shared infrastructure with dynamic tenant paths
tenant_id: "${TENANT_ID}"
infrastructure:
  storage:
    bucket: dativo-shared-data-lake
    prefix: "${TENANT_ID}/raw/stripe/customers"
  tags:
    Tenant: "${TENANT_ID}"
    SharedInfrastructure: "true"
```

## Cost Allocation and Reporting

### AWS Cost Explorer Query

```bash
aws ce get-cost-and-usage \
  --time-period Start=2025-01-01,End=2025-01-31 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --group-by Type=TAG,Key=CostCenter \
  --group-by Type=TAG,Key=dativo:tenant \
  --filter '{
    "Tags": {
      "Key": "dativo:environment",
      "Values": ["prod"]
    }
  }'
```

### GCP Cost Management Query

```bash
gcloud billing accounts \
  get-cost-allocation-policy \
  --format="table(
    labels.cost-center,
    labels.dativo-tenant,
    cost.amount
  )"
```

## Best Practices

### 1. Tag Consistency

Define required tags in organizational policy:

```yaml
# Required tags for all jobs
required_tags:
  - CostCenter
  - Project
  - Environment
  - Team
  - Owner
```

### 2. Module Versioning

Always use versioned modules:

```yaml
terraform:
  module_source: git::https://github.com/acme/terraform-dativo.git//modules/ecs?ref=v1.2.0
  module_version: "1.2.0"  # Track module version
```

### 3. State Management

Use remote state with locking:

```yaml
terraform:
  backend_config:
    bucket: acme-terraform-state
    key: dativo/jobs/${TENANT_ID}/${JOB_NAME}.tfstate
    region: us-east-1
    dynamodb_table: terraform-state-lock
```

### 4. Security

- Use private networking by default
- Enable encryption at rest with KMS
- Use least-privilege IAM roles
- Rotate credentials regularly

### 5. Monitoring

- Enable CloudWatch/Stackdriver logging
- Set up alerts for job failures
- Track resource utilization
- Monitor costs per tenant/project

## Integration with Dagster

Modules output configuration for Dagster operators:

```python
from dagster import job, op
from dagster_aws.ecs import EcsRunLauncher

@op
def run_dativo_etl():
    # ETL logic
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

## Troubleshooting

### Module Not Found

**Error**: `Failed to load Terraform module from source`

**Solution**:
- Verify `module_source` is accessible
- Check authentication for private repositories
- Ensure `module_version` is valid

### Tag Limit Exceeded

**Error**: `Too many tags for resource`

**Solution**:
- AWS: Maximum 50 tags
- GCP: Maximum 64 labels
- Reduce number of tags or use tag prefixes

### Invalid Tag Format

**Error**: `Invalid label format` (GCP)

**Solution**:
- Use lowercase labels for GCP
- Replace underscores with hyphens
- Ensure keys/values are ≤ 63 characters

## Contributing

To add a new module:

1. Create module directory: `terraform/{provider}/{module-name}/`
2. Add `main.tf`, `variables.tf`, `outputs.tf`, `README.md`
3. Follow naming conventions and tag structure
4. Add examples and documentation
5. Test with multiple job configurations

## Examples

See [examples/jobs/infrastructure/](../jobs/infrastructure/) for complete examples:
- AWS ECS deployment
- GCP Cloud Run deployment
- Kubernetes deployment
- Multi-tenant shared infrastructure

## Resources

- [Dativo Infrastructure Documentation](../../docs/INFRASTRUCTURE_INTEGRATION.md)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [Terraform GCP Provider](https://registry.terraform.io/providers/hashicorp/google/latest/docs)
- [Dagster Deployment](https://docs.dagster.io/deployment)
- [AWS Tagging Best Practices](https://docs.aws.amazon.com/general/latest/gr/aws_tagging.html)
- [GCP Resource Labels](https://cloud.google.com/resource-manager/docs/creating-managing-labels)

## License

Apache 2.0
