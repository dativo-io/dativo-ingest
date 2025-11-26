# Dativo ETL Infrastructure Terraform Modules

Terraform modules for provisioning cloud-agnostic Dativo ETL infrastructure with comprehensive tag propagation for cost allocation, compliance, and resource traceability.

## Overview

This directory contains reference Terraform modules for deploying Dativo ETL infrastructure on:

- **AWS** - S3 buckets, IAM roles, Glue catalog
- **GCP** - GCS buckets, service accounts, BigQuery datasets
- **Azure** (Coming Soon) - Storage accounts, managed identities

Each module provisions the necessary infrastructure for running Dativo ETL jobs with:

✅ **Data Lake Storage** - S3/GCS buckets with encryption and versioning  
✅ **IAM/Identity** - Least-privilege service accounts and roles  
✅ **Catalog Integration** - Glue/BigQuery for Iceberg metadata  
✅ **Tag Propagation** - Comprehensive tagging for cost and compliance  
✅ **Multi-Tenancy** - Isolated resources per tenant  
✅ **Multi-Environment** - Separate resources per environment (dev/staging/prod)

## Quick Start

### AWS

```bash
cd aws/dativo-etl
terraform init
terraform plan \
  -var="tenant_id=acme" \
  -var="environment=prod" \
  -var="region=us-east-1" \
  -var="s3_bucket_name=acme-dativo-data-lake-prod"
terraform apply
```

### GCP

```bash
cd gcp/dativo-etl
terraform init
terraform plan \
  -var="project_id=my-gcp-project" \
  -var="tenant_id=acme" \
  -var="environment=prod" \
  -var="region=us-central1" \
  -var="gcs_bucket_name=acme-dativo-data-lake-prod"
terraform apply
```

## Module Structure

```
terraform/
├── aws/
│   └── dativo-etl/
│       ├── main.tf          # Main resource definitions
│       ├── variables.tf     # Input variables
│       ├── outputs.tf       # Output values
│       └── README.md        # AWS-specific documentation
├── gcp/
│   └── dativo-etl/
│       ├── main.tf          # Main resource definitions
│       ├── variables.tf     # Input variables
│       ├── outputs.tf       # Output values
│       └── README.md        # GCP-specific documentation
└── README.md                # This file
```

## Integration with Dativo

After provisioning infrastructure, reference it in your Dativo job configuration:

```yaml
infrastructure:
  provider:
    provider: aws
    region: us-east-1
    resources:
      - resource_type: s3_bucket
        resource_id: "${TF_OUTPUT_s3_bucket_arn}"
  terraform:
    module_path: ./terraform/aws/dativo-etl
    outputs:
      s3_bucket_name: "target.connection.s3.bucket"
  tags:
    cost_center: DATA-001
    environment: prod
```

See [INFRASTRUCTURE_INTEGRATION.md](../docs/INFRASTRUCTURE_INTEGRATION.md) for complete documentation.

## Multi-Environment Setup

Use Terraform workspaces for multi-environment deployments:

```bash
# Production
terraform workspace new acme-prod
terraform apply -var-file="environments/prod.tfvars"

# Staging
terraform workspace new acme-staging
terraform apply -var-file="environments/staging.tfvars"

# Development
terraform workspace new acme-dev
terraform apply -var-file="environments/dev.tfvars"
```

Example `prod.tfvars`:

```hcl
tenant_id       = "acme"
environment     = "prod"
region          = "us-east-1"
s3_bucket_name  = "acme-dativo-data-lake-prod"

tags = {
  CostCenter   = "DATA-001"
  BusinessUnit = "Analytics"
  Environment  = "production"
  Owner        = "data-team@acme.com"
}
```

## Tag Propagation

All modules apply comprehensive tags for cost allocation and compliance:

### Base Tags (Automatic)

- `ManagedBy`: `Terraform`
- `TenantId`: Value from `tenant_id` variable
- `Environment`: Value from `environment` variable
- `Component`: `DativoETL`

### Custom Tags

Pass additional tags via the `tags` variable:

```hcl
tags = {
  CostCenter   = "DATA-001"
  BusinessUnit = "Analytics"
  Project      = "data-platform"
  Owner        = "data-team@acme.com"
  Compliance   = "SOC2,GDPR"
}
```

### Cost Allocation

Enable cost tracking by activating cost allocation tags:

**AWS:**
- Navigate to AWS Cost Explorer → Cost Allocation Tags
- Activate: `TenantId`, `Environment`, `CostCenter`, `BusinessUnit`

**GCP:**
- Navigate to Cloud Console → Billing → Cost Table
- Filter by labels: `tenant_id`, `environment`, `cost_center`

## Security Best Practices

### AWS

- ✅ S3 buckets encrypted with AES256
- ✅ Public access blocked
- ✅ IAM roles with least-privilege policies
- ✅ Bucket versioning enabled
- ✅ Lifecycle prevent destroy

### GCP

- ✅ GCS buckets encrypted by default
- ✅ Uniform bucket-level access
- ✅ Service accounts with least-privilege IAM
- ✅ Bucket versioning enabled
- ✅ Lifecycle prevent destroy

## Backend Configuration

### AWS (S3 Backend)

```hcl
terraform {
  backend "s3" {
    bucket = "acme-terraform-state"
    key    = "dativo/acme/prod/terraform.tfstate"
    region = "us-east-1"
  }
}
```

### GCP (GCS Backend)

```hcl
terraform {
  backend "gcs" {
    bucket = "acme-terraform-state"
    prefix = "dativo/acme/prod"
  }
}
```

## State Management

### Remote State

Store Terraform state in cloud storage for team collaboration:

```bash
# AWS
terraform init \
  -backend-config="bucket=acme-terraform-state" \
  -backend-config="key=dativo/acme/prod/terraform.tfstate"

# GCP
terraform init \
  -backend-config="bucket=acme-terraform-state" \
  -backend-config="prefix=dativo/acme/prod"
```

### State Locking

Enable state locking to prevent concurrent modifications:

**AWS (DynamoDB):**
```hcl
terraform {
  backend "s3" {
    bucket         = "acme-terraform-state"
    key            = "dativo/acme/prod/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-state-lock"
  }
}
```

**GCP (built-in):**
State locking is automatically enabled for GCS backends.

## Module Outputs

### AWS Module

```hcl
output "s3_bucket_name"
output "s3_bucket_arn"
output "iam_role_arn"
output "glue_database_name"
output "aws_region"
output "tenant_id"
output "environment"
```

### GCP Module

```hcl
output "gcs_bucket_name"
output "gcs_bucket_url"
output "service_account_email"
output "bigquery_dataset_id"
output "gcp_region"
output "tenant_id"
output "environment"
```

## Examples

### Single Tenant, Single Environment

```hcl
module "dativo_etl" {
  source = "./terraform/aws/dativo-etl"

  tenant_id       = "acme"
  environment     = "prod"
  region          = "us-east-1"
  s3_bucket_name  = "acme-dativo-data-lake-prod"

  tags = {
    CostCenter = "DATA-001"
  }
}
```

### Multi-Tenant

```hcl
module "dativo_etl_acme" {
  source = "./terraform/aws/dativo-etl"
  tenant_id = "acme"
  s3_bucket_name = "acme-dativo-data-lake-prod"
}

module "dativo_etl_globex" {
  source = "./terraform/aws/dativo-etl"
  tenant_id = "globex"
  s3_bucket_name = "globex-dativo-data-lake-prod"
}
```

### With Custom Encryption (AWS KMS)

```hcl
module "dativo_etl" {
  source = "./terraform/aws/dativo-etl"

  tenant_id      = "acme"
  environment    = "prod"
  region         = "us-east-1"
  s3_bucket_name = "acme-dativo-data-lake-prod"

  enable_encryption = true
  kms_key_id        = "arn:aws:kms:us-east-1:123456789012:key/..."
}
```

## Troubleshooting

### Bucket Name Already Exists

S3/GCS bucket names must be globally unique. If you get this error:

```
Error: Error creating bucket: BucketAlreadyExists
```

Choose a different bucket name with a unique prefix or suffix.

### Permission Denied

Ensure your Terraform execution environment has sufficient permissions:

**AWS:**
- `s3:CreateBucket`, `s3:PutBucketVersioning`, `s3:PutBucketEncryption`
- `iam:CreateRole`, `iam:PutRolePolicy`
- `glue:CreateDatabase`

**GCP:**
- `storage.buckets.create`
- `iam.serviceAccounts.create`
- `bigquery.datasets.create`

### State Lock Errors

If state is locked by a previous run:

```bash
# Force unlock (use with caution)
terraform force-unlock <LOCK_ID>
```

## Testing

Test module configurations with `terraform plan`:

```bash
terraform plan -var-file="test.tfvars"
```

Validate syntax:

```bash
terraform validate
terraform fmt -check -recursive
```

## Contributing

When modifying Terraform modules:

1. Update variable descriptions
2. Add/update outputs
3. Update README.md
4. Test with `terraform plan`
5. Run `terraform fmt`
6. Validate with `terraform validate`

## Support

For questions or issues:
- Documentation: https://docs.dativo.io
- GitHub Issues: https://github.com/dativo/dativo-ingest/issues
- Email: support@dativo.io

## License

Proprietary - Dativo Platform Team
