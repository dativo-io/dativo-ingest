# Dativo ETL Infrastructure Module - GCP

Terraform module for provisioning Dativo ETL infrastructure on Google Cloud Platform with comprehensive label propagation.

## Features

- **GCS Data Lake**: Versioned GCS bucket for Iceberg tables
- **Service Accounts**: Least-privilege service accounts for compute
- **BigQuery Catalog**: BigQuery dataset for Iceberg metadata
- **Label Propagation**: Comprehensive labeling for cost allocation and compliance
- **Multi-tenancy**: Isolated resources per tenant

## Usage

### Basic Example

```hcl
module "dativo_etl" {
  source = "./terraform/gcp/dativo-etl"

  project_id     = "my-gcp-project"
  tenant_id      = "acme"
  environment    = "prod"
  region         = "us-central1"
  gcs_bucket_name = "acme-dativo-data-lake-prod"

  enable_bigquery_catalog = true
  bigquery_dataset_id     = "acme_iceberg_prod"

  labels = {
    cost_center   = "data-001"
    business_unit = "analytics"
    owner         = "data-team"
    compliance    = "soc2-gdpr"
  }
}
```

### With Custom Storage Class

```hcl
module "dativo_etl" {
  source = "./terraform/gcp/dativo-etl"

  project_id      = "my-gcp-project"
  tenant_id       = "acme"
  environment     = "prod"
  region          = "us-central1"
  gcs_bucket_name = "acme-dativo-data-lake-prod"

  storage_class       = "NEARLINE"  # For cost optimization
  enable_versioning   = true
  enable_bigquery_catalog = true

  labels = {
    cost_center = "data-001"
    project     = "data-platform"
  }
}
```

### Multi-Environment Setup

```hcl
# Production
module "dativo_etl_prod" {
  source = "./terraform/gcp/dativo-etl"

  project_id      = "my-gcp-project"
  tenant_id       = "acme"
  environment     = "prod"
  region          = "us-central1"
  gcs_bucket_name = "acme-dativo-data-lake-prod"

  labels = {
    environment = "production"
    cost_center = "data-001"
  }
}

# Staging
module "dativo_etl_staging" {
  source = "./terraform/gcp/dativo-etl"

  project_id      = "my-gcp-project"
  tenant_id       = "acme"
  environment     = "staging"
  region          = "us-central1"
  gcs_bucket_name = "acme-dativo-data-lake-staging"

  labels = {
    environment = "staging"
    cost_center = "data-001"
  }
}
```

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| project_id | GCP project ID | `string` | n/a | yes |
| tenant_id | Tenant identifier for multi-tenancy | `string` | n/a | yes |
| environment | Environment name (dev, staging, prod) | `string` | `"prod"` | no |
| region | GCP region for resources | `string` | n/a | yes |
| gcs_bucket_name | Name for the GCS bucket (globally unique) | `string` | n/a | yes |
| storage_class | Storage class for GCS bucket | `string` | `"STANDARD"` | no |
| enable_versioning | Enable GCS bucket versioning | `bool` | `true` | no |
| enable_encryption | Enable GCS bucket encryption | `bool` | `true` | no |
| enable_bigquery_catalog | Enable BigQuery dataset for Iceberg | `bool` | `true` | no |
| bigquery_dataset_id | BigQuery dataset ID for Iceberg catalog | `string` | `"{tenant_id}_iceberg_{env}"` | no |
| bigquery_location | BigQuery dataset location | `string` | `"{region}"` | no |
| labels | Labels to apply to all resources | `map(string)` | `{}` | no |

## Outputs

| Name | Description |
|------|-------------|
| gcs_bucket_name | Name of the GCS bucket |
| gcs_bucket_url | URL of the GCS bucket |
| gcs_bucket_self_link | Self-link of the GCS bucket |
| service_account_email | Email of the service account for Dativo ETL jobs |
| service_account_unique_id | Unique ID of the service account |
| bigquery_dataset_id | ID of the BigQuery dataset |
| bigquery_dataset_self_link | Self-link of the BigQuery dataset |
| gcp_project_id | GCP project ID |
| gcp_region | GCP region |
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
    provider: gcp
    region: us-central1
    project_id: my-gcp-project
    resources:
      - resource_type: gcs_bucket
        resource_id: "gs://acme-dativo-data-lake-prod"
        resource_name: acme-dativo-data-lake-prod
        region: us-central1
      - resource_type: service_account
        resource_id: "acme-dativo-etl-prod@my-gcp-project.iam.gserviceaccount.com"
        resource_name: acme-dativo-etl-prod
      - resource_type: bigquery_dataset
        resource_id: "my-gcp-project.acme_iceberg_prod"
        resource_name: acme_iceberg_prod
        region: US
  
  terraform:
    module_path: "./terraform/gcp/dativo-etl"
    workspace: "acme-prod"
    outputs:
      gcs_bucket_name: "target.connection.gcs.bucket"
      service_account_email: "infrastructure.metadata.service_account"
      bigquery_dataset_id: "target.catalog.bigquery_dataset"
  
  tags:
    cost_center: data-001
    business_unit: analytics
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
    gcs:
      bucket: "${TF_OUTPUT_gcs_bucket_name}"
      prefix: "raw/stripe/customers"
```

## Label Propagation

All resources are automatically labeled with:

- **managed_by**: `terraform`
- **tenant_id**: Value from `tenant_id` variable
- **environment**: Value from `environment` variable
- **component**: `dativo-etl`

Additional labels from the `labels` variable are merged with these base labels.

### Cost Allocation Labels

Configure GCP Cost Management to track costs by:
- `tenant_id`
- `environment`
- `cost_center`
- `business_unit`
- `project`

This enables cost tracking per tenant, environment, and cost center.

## Security Best Practices

1. **GCS Encryption**: All objects encrypted at rest by default
2. **Uniform Bucket Access**: Uniform bucket-level access enabled
3. **Service Accounts**: Least-privilege access to GCS and BigQuery
4. **Versioning**: Optional versioning for disaster recovery
5. **Lifecycle Prevent Destroy**: GCS bucket has lifecycle protection

## Storage Classes

GCP offers multiple storage classes for cost optimization:

- **STANDARD**: For frequently accessed data
- **NEARLINE**: For data accessed < once per month
- **COLDLINE**: For data accessed < once per quarter
- **ARCHIVE**: For long-term archival (< once per year)

Choose the appropriate storage class based on your access patterns.

## Requirements

- Terraform >= 1.3.0
- Google Provider ~> 5.0
- GCP CLI configured with appropriate credentials

## Authors

Dativo Platform Team

## License

Proprietary
