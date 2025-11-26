# Dativo ETL Job - GCP Cloud Run with Dagster

This Terraform module provisions infrastructure for running Dativo ETL jobs on GCP Cloud Run with Dagster orchestration.

## Features

- **Cloud Run Jobs**: Serverless container execution with automatic scaling
- **Service Accounts**: Least-privilege service accounts for secure access
- **GCS Integration**: Secure access to GCS buckets with KMS encryption
- **Cloud Logging**: Centralized logging with long-term storage
- **VPC Connector**: Private networking support
- **Cloud Scheduler**: Optional scheduled execution
- **Label Propagation**: Comprehensive labeling for cost allocation and compliance

## Usage

### Basic Example

```hcl
module "dativo_etl_job" {
  source = "git::https://github.com/your-org/terraform-dativo-gcp.git//modules/cloud-run-dagster?ref=v1.0.0"
  
  # GCP configuration
  project_id = "acme-data-platform"
  region     = "us-central1"
  
  # Job identification
  job_name    = "stripe-customers"
  tenant_id   = "acme"
  environment = "prod"
  
  # Compute resources
  compute_cpu                = "2"
  compute_memory             = "4Gi"
  compute_max_runtime_seconds = 3600
  
  # Networking
  networking_vpc_id             = "projects/acme-data-platform/global/networks/dativo-vpc"
  networking_subnet_ids         = ["projects/acme-data-platform/regions/us-central1/subnetworks/dativo-subnet"]
  networking_private_networking = true
  
  # Storage
  storage_bucket     = "acme-data-lake"
  storage_prefix     = "raw/stripe/customers"
  storage_kms_key_id = "projects/acme-data-platform/locations/us-central1/keyRings/dativo/cryptoKeys/etl-data"
  
  # Labels for cost allocation
  tags = {
    cost-center  = "hr-001"
    project      = "data-platform"
    environment  = "production"
    managed-by   = "terraform"
    team         = "data-engineering"
  }
}
```

### With Scheduled Execution

```hcl
module "dativo_etl_job" {
  source = "./modules/cloud-run-dagster"
  
  project_id  = "acme-data-platform"
  job_name    = "stripe-customers"
  tenant_id   = "acme"
  environment = "prod"
  
  # ... other configuration ...
  
  # Schedule with Cloud Scheduler
  schedule_cron     = "0 2 * * *"  # Daily at 2 AM
  schedule_timezone = "America/New_York"
}
```

### With Secrets from Secret Manager

```hcl
module "dativo_etl_job" {
  source = "./modules/cloud-run-dagster"
  
  project_id  = "acme-data-platform"
  job_name    = "stripe-customers"
  tenant_id   = "acme"
  environment = "prod"
  
  # ... other configuration ...
  
  # Secrets from Secret Manager
  secrets_from_secret_manager = [
    {
      name    = "STRIPE_API_KEY"
      secret  = "dativo-acme-stripe-api-key"
      version = "latest"
    },
    {
      name    = "NESSIE_URI"
      secret  = "dativo-nessie-uri"
      version = "latest"
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
  
  source = "./modules/cloud-run-dagster"
  
  project_id  = "dativo-shared-platform"
  region      = "us-central1"
  
  job_name    = "stripe-customers"
  tenant_id   = each.key
  environment = "prod"
  
  storage_bucket = "dativo-shared-data-lake"
  storage_prefix = "${each.key}/raw/stripe/customers"
  
  tags = {
    tenant      = each.key
    cost-center = "data-001"
    environment = "production"
  }
  
  # ... other configuration ...
}
```

## Requirements

| Name | Version |
|------|---------|
| terraform | >= 1.0 |
| google | ~> 5.0 |

## Providers

| Name | Version |
|------|---------|
| google | ~> 5.0 |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|----------|
| project_id | GCP project ID | string | - | yes |
| region | GCP region | string | "us-central1" | no |
| job_name | Job name from Dativo configuration | string | - | yes |
| tenant_id | Tenant ID | string | - | yes |
| environment | Environment (dev, staging, prod) | string | - | yes |
| compute_cpu | CPU request (e.g., '1', '2', '4') | string | "1" | no |
| compute_memory | Memory request (e.g., '2Gi', '4Gi') | string | "2Gi" | no |
| networking_vpc_id | VPC network name | string | - | yes |
| storage_bucket | GCS bucket name | string | - | yes |
| storage_prefix | GCS prefix | string | - | yes |
| storage_kms_key_id | KMS key ID | string | null | no |
| tags | Resource labels | map(string) | {} | no |

See [variables.tf](./variables.tf) for complete list of inputs.

## Outputs

| Name | Description |
|------|-------------|
| job_name | Cloud Run Job name |
| job_id | Cloud Run Job ID |
| service_account_email | Service account email |
| region | GCP region |
| project_id | GCP project ID |
| dagster_cloud_run_config | Configuration for Dagster Cloud Run operator |

## Integration with Dagster

This module outputs a `dagster_cloud_run_config` object that can be used directly with Dagster's Cloud Run operator:

```python
from dagster import job, op
from dagster_gcp.cloud_run import CloudRunJobExecutor

@op
def run_dativo_etl():
    # Your ETL logic here
    pass

@job(
    executor_def=CloudRunJobExecutor(
        **terraform_output["dagster_cloud_run_config"]
    )
)
def dativo_etl_job():
    run_dativo_etl()
```

## Cost Optimization

### Right-Sizing

- Start with smaller CPU/memory allocation and scale up based on monitoring
- Use Cloud Run's automatic scaling to handle variable workloads
- Set appropriate timeout values to prevent long-running jobs

### Storage Optimization

- Use GCS Storage Classes for automatic cost optimization
- Implement lifecycle policies to transition old data to cheaper storage classes
- Use KMS encryption with customer-managed keys for compliance

### Monitoring

- Track Cloud Run CPU and memory utilization in Cloud Monitoring
- Set up budget alerts in Cloud Billing
- Use Cloud Asset Inventory for resource tracking

## Security Best Practices

1. **Least Privilege**: Service accounts have minimal permissions for GCS and KMS access
2. **Network Isolation**: Use VPC connectors with private networking
3. **Encryption**: Enable encryption at rest (GCS with KMS) and in transit (TLS)
4. **Secrets Management**: Use Secret Manager for sensitive data
5. **Logging**: Enable Cloud Logging with long-term storage in GCS

## Troubleshooting

### Job fails to start

1. Check Cloud Logging: Filter by `resource.type="cloud_run_job"`
2. Verify service account permissions for GCS and KMS access
3. Ensure container image is accessible from Cloud Run
4. Check VPC connector configuration

### Insufficient CPU/Memory

Increase `compute_cpu` and `compute_memory` in module configuration:

```hcl
compute_cpu    = "4"
compute_memory = "8Gi"
```

### Network connectivity issues

1. Verify VPC connector is properly configured
2. Check firewall rules for outbound connectivity
3. Ensure Private Google Access is enabled for subnets

## GCP Labels Best Practices

GCP labels have specific requirements:
- Must be lowercase
- Can contain hyphens, underscores, and lowercase letters
- Maximum 64 labels per resource
- Keys and values must be ≤ 63 characters

This module automatically converts tags to GCP-compliant labels.

## Examples

See [examples/](../../../jobs/) for complete examples:
- Basic Cloud Run job
- Multi-tenant deployment
- Integration with Dagster
- Custom service account configuration
- VPC connector setup

## License

Apache 2.0
