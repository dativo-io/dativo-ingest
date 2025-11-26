# Dativo ETL Job Infrastructure - AWS Module

This Terraform module provisions cloud infrastructure for Dativo ETL jobs on AWS with comprehensive tag propagation for cost allocation, compliance, and resource traceability.

## Features

- **ECS Fargate Tasks**: Serverless container execution for ETL jobs
- **Dagster Integration**: Compatible with Dagster orchestration
- **VPC Networking**: Private/public subnet configuration with security groups
- **S3 Storage**: Buckets for data and state with encryption support
- **CloudWatch Monitoring**: Logs, metrics, and custom alarms
- **IAM Security**: Least-privilege roles and policies
- **Comprehensive Tagging**: Automatic tag propagation from job configurations

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Dativo Job Configuration                │
│  (infrastructure block with tags, compute, networking)      │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              Python Infrastructure Module                    │
│  • Validates configuration                                   │
│  • Propagates tags (cost_center, compliance, etc.)          │
│  • Generates terraform.tfvars                               │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   Terraform AWS Module                       │
│  • Provisions ECS cluster and task definition               │
│  • Creates IAM roles and policies                           │
│  • Sets up CloudWatch logging and monitoring                │
│  • Applies tags to all resources                            │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                     AWS Resources                            │
│  • ECS Fargate Task                                         │
│  • CloudWatch Log Group                                     │
│  • IAM Roles/Policies                                       │
│  • Security Groups                                          │
│  • All tagged with cost allocation and compliance metadata  │
└─────────────────────────────────────────────────────────────┘
```

## Usage

### 1. Define Infrastructure in Job Configuration

```yaml
# jobs/acme/stripe_customers_to_iceberg.yaml
tenant_id: acme
environment: prod

source_connector: stripe
source_connector_path: /app/connectors/stripe.yaml
target_connector: iceberg
target_connector_path: /app/connectors/iceberg.yaml
asset: stripe_customers
asset_path: /app/assets/stripe/v1.0/customers.yaml

# External infrastructure configuration
infrastructure:
  provider: aws
  
  runtime:
    type: ecs
    compute:
      cpu: "2048"
      memory: "4096"
    timeout_seconds: 7200
  
  networking:
    vpc_id: vpc-12345678
    subnet_ids:
      - subnet-12345678
      - subnet-87654321
    private_access: true
  
  storage:
    state_bucket: dativo-state-acme
    data_bucket: dativo-data-acme
    encryption:
      enabled: true
      kms_key_id: arn:aws:kms:us-east-1:123456789012:key/12345678
  
  tags:
    cost_center: FIN-001
    business_unit: Finance
    project: data-platform
    environment: prod
    owner: data-team@acme.com
    compliance:
      - GDPR
      - SOC2
    data_classification: Confidential
  
  monitoring:
    enabled: true
    log_group: /dativo/jobs/acme/stripe_customers
    metrics_namespace: Dativo/Jobs
```

### 2. Generate Terraform Variables

```python
from dativo_ingest.infrastructure import InfrastructureConfig, load_infrastructure_config
from dativo_ingest.config import JobConfig
from dativo_ingest.tag_derivation import derive_tags_from_asset
from pathlib import Path

# Load job configuration
job_config = JobConfig.from_yaml("jobs/acme/stripe_customers_to_iceberg.yaml")

# Load infrastructure configuration
infra_config = load_infrastructure_config(job_config.infrastructure)

# Derive asset tags
asset = job_config.get_asset()
asset_tags = derive_tags_from_asset(asset)

# Export Terraform variables
output_path = Path("terraform/aws/terraform.tfvars.json")
infra_config.export_terraform_vars(
    output_path=output_path,
    job_config=job_config,
    asset_tags=asset_tags,
    format="json"
)
```

### 3. Apply Terraform

```bash
cd terraform/aws

# Initialize Terraform
terraform init

# Review plan
terraform plan -var-file=terraform.tfvars.json

# Apply infrastructure
terraform apply -var-file=terraform.tfvars.json
```

## Tag Propagation

Tags are automatically propagated from multiple sources:

1. **Infrastructure Tags** (from job config `infrastructure.tags`):
   - `CostCenter`
   - `BusinessUnit`
   - `Project`
   - `Environment`
   - `Owner`
   - `Compliance`
   - `DataClassification`

2. **Job Metadata Tags**:
   - `TenantId`
   - `Asset`
   - `SourceConnector`
   - `JobName`

3. **Asset Tags** (from asset schema):
   - `Classification_*` (PII, sensitive data, etc.)
   - `Governance_*` (retention, regulations)
   - `FinOps_*` (cost attribution)

4. **System Tags**:
   - `ManagedBy: dativo`
   - `Terraform: true`
   - `Module: dativo-etl-job`

### Example Tag Output

```hcl
tags = {
  # Infrastructure tags
  CostCenter         = "FIN-001"
  BusinessUnit       = "Finance"
  Project            = "data-platform"
  Environment        = "prod"
  Owner              = "data-team@acme.com"
  Compliance         = "GDPR,SOC2"
  DataClassification = "Confidential"
  
  # Job metadata tags
  TenantId        = "acme"
  Asset           = "stripe_customers"
  SourceConnector = "stripe"
  JobName         = "stripe_customers_to_iceberg"
  
  # Asset tags
  Classification_default       = "pii"
  Classification_fields_email  = "pii"
  Governance_retention_days    = "365"
  FinOps_cost_center          = "FIN-001"
  
  # System tags
  ManagedBy   = "dativo"
  Terraform   = "true"
  Module      = "dativo-etl-job"
  RuntimeType = "ecs"
}
```

## Cost Allocation

Use AWS Cost Explorer to filter by tags:

```sql
-- Example AWS Cost Explorer filter
SELECT 
  cost,
  tags.CostCenter,
  tags.BusinessUnit,
  tags.TenantId,
  tags.JobName
FROM aws_cost_usage
WHERE tags.ManagedBy = 'dativo'
  AND tags.Environment = 'prod'
GROUP BY tags.CostCenter
```

## Compliance Tracking

Query resources by compliance tags:

```bash
# List all GDPR-compliant resources
aws resourcegroupstaggingapi get-resources \
  --tag-filters Key=Compliance,Values=GDPR \
  --resource-type-filters ecs:cluster ecs:task-definition

# List all PII data processing resources
aws resourcegroupstaggingapi get-resources \
  --tag-filters Key=Classification_default,Values=pii
```

## Outputs

| Output | Description |
|--------|-------------|
| `ecs_cluster_arn` | ARN of the ECS cluster |
| `ecs_task_definition_arn` | ARN of the task definition |
| `ecs_task_execution_role_arn` | ARN of execution role |
| `ecs_task_role_arn` | ARN of task role |
| `security_group_ids` | Security group IDs |
| `log_group_name` | CloudWatch log group name |
| `resource_tags` | All applied resource tags |

## Requirements

| Name | Version |
|------|---------|
| terraform | >= 1.0 |
| aws | ~> 5.0 |

## Providers

| Name | Version |
|------|---------|
| aws | ~> 5.0 |

## Best Practices

1. **Tag Governance**: Always specify `cost_center`, `owner`, and `environment` tags
2. **Encryption**: Enable KMS encryption for sensitive data
3. **Networking**: Use private subnets for production workloads
4. **Monitoring**: Enable CloudWatch Container Insights for observability
5. **IAM**: Review and adjust IAM policies based on least-privilege principle

## Troubleshooting

### Missing Tags Warning

If you see warnings about missing tags:

```
Infrastructure configuration warning: No cost_center tag specified
Infrastructure configuration warning: No owner tag specified
```

Add tags to your job configuration:

```yaml
infrastructure:
  tags:
    cost_center: YOUR-COST-CENTER
    owner: your-team@company.com
```

### VPC Configuration Issues

Ensure VPC and subnets exist and are in the same region:

```bash
aws ec2 describe-vpcs --vpc-ids vpc-12345678
aws ec2 describe-subnets --subnet-ids subnet-12345678
```

## Examples

See `examples/jobs/` for complete job configurations with infrastructure blocks.

## License

Apache 2.0 - See LICENSE file for details
