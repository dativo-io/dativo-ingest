# Dativo EMR Terraform Module (AWS)

Terraform module for provisioning AWS EMR clusters for Dativo ETL workloads with comprehensive tag propagation for cost allocation, compliance, and resource traceability.

## Features

- **EMR Cluster**: Fully configured EMR cluster with Spark, Hadoop, and Hive
- **Auto-scaling**: Optional auto-scaling based on YARN memory utilization
- **Encryption**: KMS encryption for data at rest and in transit
- **Tag Propagation**: Comprehensive tag propagation from Dativo job configurations
- **Cost Optimization**: Optional spot instance support
- **Compliance**: Security groups, IAM roles, and CloudWatch logging

## Tag Categories

This module propagates three categories of tags from Dativo:

1. **Classification Tags**: Data security and compliance (PII, GDPR, retention policies)
2. **FinOps Tags**: Cost allocation (CostCenter, Project, BusinessTags)
3. **Governance Tags**: Ownership, environment, ManagedBy

## Usage

### 1. Configure Dativo Job with Infrastructure Block

```yaml
# jobs/acme/postgres_orders.yaml
tenant_id: acme
environment: prod

infrastructure:
  provider: terraform
  terraform:
    module_source: "../../terraform/aws/emr-dativo"
    workspace: "prod"
  runtime:
    platform: emr
    compute:
      cluster_id: "${EMR_CLUSTER_ID}"
      instance_type: "r5.2xlarge"
      instance_count: 8
      auto_scaling:
        enabled: true
        min_instances: 4
        max_instances: 12
    storage:
      bucket: "acme-data-lake-prod"
    network:
      vpc_id: "vpc-0a1b2c3d"
      subnet_ids: ["subnet-abc123", "subnet-def456"]
  metadata:
    tags:
      CostCenter: "data-engineering"
      Project: "customer-analytics"
      Environment: "production"
    variables:
      enable_spot_instances: true
      log_retention_days: 30

source_connector: postgres
source_connector_path: /app/connectors/postgres.yaml

target_connector: iceberg
target_connector_path: /app/connectors/iceberg.yaml

asset: postgres_orders
asset_path: /app/assets/postgres/v1.0/db_orders.yaml
```

### 2. Run Dativo to Generate Terraform Variables

```bash
dativo run --config jobs/acme/postgres_orders.yaml --mode self_hosted

# This will generate: terraform/aws/emr-dativo/dativo.auto.tfvars
```

### 3. Apply Terraform Configuration

```bash
cd terraform/aws/emr-dativo

terraform init
terraform workspace select prod
terraform plan
terraform apply
```

### 4. Use Cluster in Dativo Job

```bash
# Export cluster ID from Terraform output
export EMR_CLUSTER_ID=$(terraform output -raw emr_cluster_id)

# Run Dativo job
dativo run --config jobs/acme/postgres_orders.yaml --mode self_hosted
```

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| tenant_id | Tenant identifier | string | - | yes |
| environment | Environment name | string | - | yes |
| aws_region | AWS region | string | us-east-1 | no |
| tags | Complete tag set from Dativo | map(string) | {} | no |
| classification_tags | Data classification tags | map(string) | {} | no |
| finops_tags | FinOps cost allocation tags | map(string) | {} | no |
| instance_type | EMR instance type | string | r5.2xlarge | no |
| instance_count | Number of instances | number | 3 | no |
| enable_autoscaling | Enable auto-scaling | bool | false | no |
| min_instances | Minimum instances | number | 2 | no |
| max_instances | Maximum instances | number | 10 | no |
| vpc_id | VPC ID | string | - | yes |
| subnet_ids | Subnet IDs | list(string) | - | yes |
| s3_bucket | S3 bucket name | string | - | yes |
| enable_spot_instances | Use spot instances | bool | false | no |
| log_retention_days | CloudWatch log retention | number | 30 | no |
| enable_encryption | Enable encryption | bool | true | no |
| kms_key_alias | KMS key alias | string | alias/dativo | no |

## Outputs

| Name | Description |
|------|-------------|
| emr_cluster_id | EMR cluster ID |
| emr_cluster_arn | EMR cluster ARN |
| emr_master_public_dns | Master node public DNS |
| emr_log_bucket | S3 bucket for logs |
| applied_tags | All applied tags |
| classification_tags | Classification tags |
| finops_tags | FinOps tags |

## Tag Propagation Flow

```
Dativo Job Config
      ↓
  Asset Definition (ODCS)
      ↓
Tag Propagator
      ↓
Infrastructure Manager
      ↓
Terraform Variables (dativo.auto.tfvars)
      ↓
AWS Resources (EMR, S3, IAM, etc.)
```

## Example Generated Tags

```hcl
tags = {
  # Dativo metadata
  "TenantId"            = "acme"
  "Environment"         = "prod"
  "SourceConnector"     = "postgres"
  "TargetConnector"     = "iceberg"
  "Asset"               = "postgres_orders"
  
  # ODCS metadata
  "Domain"              = "sales"
  "DataProduct"         = "customer-analytics"
  "Owner"               = "data-team@acme.com"
  
  # Classification
  "DataClassification"  = "PII,Financial"
  "ContainsPII"         = "true"
  "Regulations"         = "GDPR,CCPA"
  "RetentionDays"       = "365"
  "EncryptionRequired"  = "true"
  
  # FinOps
  "CostCenter"          = "data-engineering"
  "Project"             = "customer-analytics"
  "BusinessTags"        = "sales,analytics"
  
  # Infrastructure
  "ManagedBy"           = "terraform"
  "TerraformModule"     = "dativo-emr"
  "TerraformWorkspace"  = "prod"
  "Platform"            = "emr"
}
```

## Cost Allocation

Use FinOps tags for AWS Cost Explorer filtering:

```
Cost Allocation Tags:
- CostCenter: data-engineering
- Project: customer-analytics
- TenantId: acme
- Environment: prod
```

## Compliance

Classification tags enable compliance tracking:

- **PII Detection**: `ContainsPII = true`
- **Retention Policy**: `RetentionDays = 365`
- **Encryption**: `EncryptionRequired = true`
- **Regulations**: `Regulations = GDPR,CCPA`

## Security

- EMR clusters run in private subnets
- Security groups restrict access
- KMS encryption for data at rest
- IAM roles follow least privilege
- CloudWatch logging for audit trail

## Auto-scaling

Auto-scaling triggers on YARN memory utilization:

- **Scale Up**: When available memory < 25%
- **Scale Down**: When available memory > 75%
- **Cool Down**: 300 seconds between scaling actions

## Multi-Environment

Use Terraform workspaces for multi-environment:

```bash
# Create workspaces
terraform workspace new dev
terraform workspace new staging
terraform workspace new prod

# Select workspace
terraform workspace select prod
terraform apply
```

## Integration with Dativo

The module integrates seamlessly with Dativo's infrastructure manager:

```python
from dativo_ingest.cloud_infrastructure import AWSInfrastructureManager

# Dativo automatically:
# 1. Builds infrastructure context from job config
# 2. Derives tags from asset definition (ODCS)
# 3. Generates terraform tfvars
# 4. Applies tags to resources via boto3
```

## Requirements

- Terraform >= 1.0
- AWS Provider ~> 5.0
- VPC with private subnets
- S3 bucket for data storage

## License

Internal use only
