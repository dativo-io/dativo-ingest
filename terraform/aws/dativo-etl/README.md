# Dativo ETL Infrastructure Module - AWS

Terraform module for provisioning Dativo ETL infrastructure on AWS with comprehensive tag propagation.

## Features

- **S3 Data Lake**: Encrypted, versioned S3 bucket for Iceberg tables
- **IAM Roles**: Least-privilege IAM roles for ECS tasks and compute
- **Glue Catalog**: AWS Glue catalog database for Iceberg metadata
- **Tag Propagation**: Comprehensive tagging for cost allocation and compliance
- **Multi-tenancy**: Isolated resources per tenant

## Usage

### Basic Example

```hcl
module "dativo_etl" {
  source = "./terraform/aws/dativo-etl"

  tenant_id       = "acme"
  environment     = "prod"
  region          = "us-east-1"
  s3_bucket_name  = "acme-dativo-data-lake-prod"

  enable_glue_catalog = true
  glue_database_name  = "acme_iceberg_prod"

  tags = {
    CostCenter   = "DATA-001"
    BusinessUnit = "Analytics"
    Owner        = "data-team@acme.com"
    Compliance   = "SOC2,GDPR"
  }
}
```

### With Custom Encryption

```hcl
module "dativo_etl" {
  source = "./terraform/aws/dativo-etl"

  tenant_id       = "acme"
  environment     = "prod"
  region          = "us-east-1"
  s3_bucket_name  = "acme-dativo-data-lake-prod"

  enable_encryption   = true
  enable_versioning   = true
  enable_glue_catalog = true

  tags = {
    CostCenter = "DATA-001"
    Project    = "data-platform"
  }
}
```

### Multi-Environment Setup

```hcl
# Production
module "dativo_etl_prod" {
  source = "./terraform/aws/dativo-etl"

  tenant_id       = "acme"
  environment     = "prod"
  region          = "us-east-1"
  s3_bucket_name  = "acme-dativo-data-lake-prod"

  tags = {
    Environment = "production"
    CostCenter  = "DATA-001"
  }
}

# Staging
module "dativo_etl_staging" {
  source = "./terraform/aws/dativo-etl"

  tenant_id       = "acme"
  environment     = "staging"
  region          = "us-east-1"
  s3_bucket_name  = "acme-dativo-data-lake-staging"

  tags = {
    Environment = "staging"
    CostCenter  = "DATA-001"
  }
}
```

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| tenant_id | Tenant identifier for multi-tenancy | `string` | n/a | yes |
| environment | Environment name (dev, staging, prod) | `string` | `"prod"` | no |
| region | AWS region for resources | `string` | n/a | yes |
| s3_bucket_name | Name for the S3 bucket (globally unique) | `string` | n/a | yes |
| enable_versioning | Enable S3 bucket versioning | `bool` | `true` | no |
| enable_encryption | Enable S3 bucket encryption | `bool` | `true` | no |
| enable_glue_catalog | Enable AWS Glue catalog for Iceberg | `bool` | `true` | no |
| glue_database_name | Name for the Glue database | `string` | `"{tenant_id}_iceberg"` | no |
| tags | Tags to apply to all resources | `map(string)` | `{}` | no |

## Outputs

| Name | Description |
|------|-------------|
| s3_bucket_name | Name of the S3 bucket |
| s3_bucket_arn | ARN of the S3 bucket |
| s3_bucket_region | Region of the S3 bucket |
| iam_role_arn | ARN of the IAM role for Dativo ETL jobs |
| iam_role_name | Name of the IAM role |
| glue_database_name | Name of the Glue catalog database |
| glue_database_arn | ARN of the Glue catalog database |
| aws_region | AWS region |
| tenant_id | Tenant ID |
| environment | Environment name |

## Integration with Dativo Job Configs

After provisioning infrastructure, reference outputs in your Dativo job configuration:

```yaml
tenant_id: acme
environment: prod

# Infrastructure block
infrastructure:
  provider:
    provider: aws
    region: us-east-1
    account_id: "123456789012"
    resources:
      - resource_type: s3_bucket
        resource_id: "arn:aws:s3:::acme-dativo-data-lake-prod"
        resource_name: acme-dativo-data-lake-prod
        region: us-east-1
      - resource_type: iam_role
        resource_id: "arn:aws:iam::123456789012:role/acme-dativo-etl-role-prod"
        resource_name: acme-dativo-etl-role-prod
      - resource_type: glue_catalog
        resource_id: "arn:aws:glue:us-east-1:123456789012:database/acme_iceberg_prod"
        resource_name: acme_iceberg_prod
        region: us-east-1
  
  terraform:
    module_path: "./terraform/aws/dativo-etl"
    workspace: "acme-prod"
    outputs:
      s3_bucket_name: "target.connection.s3.bucket"
      iam_role_arn: "infrastructure.metadata.iam_role_arn"
      glue_database_name: "target.catalog.glue_database"
  
  tags:
    cost_center: DATA-001
    business_unit: Analytics
    project: data-platform
    environment: prod
    owner: data-team@acme.com
    compliance: ["SOC2", "GDPR"]

# Source and target configurations
source_connector: stripe
source_connector_path: connectors/stripe.yaml

target_connector: iceberg
target_connector_path: connectors/iceberg.yaml

asset: stripe_customers
asset_path: assets/stripe/v1.0/customers.yaml

target:
  connection:
    s3:
      bucket: "${TF_OUTPUT_s3_bucket_name}"
      prefix: "raw/stripe/customers"
```

## Tag Propagation

All resources are automatically tagged with:

- **ManagedBy**: `Terraform`
- **TenantId**: Value from `tenant_id` variable
- **Environment**: Value from `environment` variable
- **Component**: `DativoETL`

Additional tags from the `tags` variable are merged with these base tags.

### Cost Allocation Tags

Enable AWS Cost Allocation tags for these keys:
- `TenantId`
- `Environment`
- `CostCenter`
- `BusinessUnit`
- `Project`

This enables cost tracking per tenant, environment, and cost center.

## Security Best Practices

1. **S3 Encryption**: All objects encrypted at rest with AES256
2. **Bucket Policies**: Public access blocked by default
3. **IAM Roles**: Least-privilege access to S3 and Glue
4. **Versioning**: Optional versioning for disaster recovery
5. **Lifecycle Prevent Destroy**: S3 bucket has lifecycle protection

## Requirements

- Terraform >= 1.3.0
- AWS Provider ~> 5.0
- AWS CLI configured with appropriate credentials

## Authors

Dativo Platform Team

## License

Proprietary
