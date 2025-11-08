# GCP Cloud Run Terraform Module for Dativo ETL Jobs

This Terraform module provisions Google Cloud Run infrastructure for running Dativo ETL jobs as containerized workloads.

## Features

- **Cloud Run Service or Job**: Choose between HTTP-triggered service or batch job
- **Service Account**: Dedicated service account with least-privilege IAM permissions
- **Automatic Scaling**: Scale to zero when idle, up to max instances under load
- **Secret Manager Integration**: Secure secret management
- **Cloud Storage Access**: Automatic IAM bindings for GCS buckets
- **Label Propagation**: All resources labeled with job metadata for cost allocation and compliance
- **VPC Connector Support**: Private network access (optional)
- **Cloud Scheduler Integration**: Optional scheduled execution

## Usage

```hcl
module "dativo_job_runtime" {
  source = "git::ssh://git@github.com/your-org/terraform-modules.git//dativo_runtime/gcp_cloud_run"

  project_id = "acme-data-platform"
  region     = "us-central1"

  # Job metadata from Dativo job config (required)
  job_metadata = {
    job_name      = "stripe-customers-etl"
    team          = "data-engineering"
    pipeline_type = "ingestion"
    environment   = "prod"
    cost_center   = "data-platform"
  }

  # Default labels (merged with job_metadata)
  default_labels = {
    project     = "dativo-platform"
    managed_by  = "terraform"
  }

  # Container configuration
  container_image = "us-central1-docker.pkg.dev/acme-data-platform/dativo/dativo:1.1.0"
  cpu             = "1"
  memory          = "2Gi"

  # Scaling
  min_instances = 0  # Scale to zero when idle
  max_instances = 1

  # Timeout
  timeout_seconds = 3600

  # Performance
  execution_environment = "EXECUTION_ENVIRONMENT_GEN2"
  cpu_throttling       = true
  startup_cpu_boost    = false

  # Permissions - Storage bucket access
  storage_bucket_names = [
    "acme-data-lake",
    "acme-raw-data"
  ]

  # Permissions - Secret Manager access
  secret_ids = [
    "stripe-api-key",
    "database-credentials"
  ]

  # Environment variables
  environment_variables = [
    {
      name  = "DATIVO_MODE"
      value = "cloud"
    }
  ]

  # Secrets from Secret Manager
  secrets_from_secret_manager = [
    {
      name        = "STRIPE_API_KEY"
      secret_name = "stripe-api-key"
      version     = "latest"
    }
  ]

  # Use Cloud Run Job for batch workloads
  create_job_instead_of_service = true
  job_parallelism              = 1
  job_task_count               = 1
  job_max_retries              = 3

  # Optional: Cloud Scheduler for scheduled execution
  create_scheduler_job   = true
  scheduler_cron         = "0 2 * * *"  # 2 AM daily
  scheduler_timezone     = "America/New_York"
  scheduler_retry_count  = 3

  # Optional: VPC connector for private network access
  # vpc_connector_name = "projects/acme-data-platform/locations/us-central1/connectors/dativo-vpc-connector"
  # vpc_egress_mode    = "PRIVATE_RANGES_ONLY"
}
```

## Cloud Run Service vs Cloud Run Job

### Cloud Run Service (Default)
- HTTP-triggered execution
- Scales based on incoming requests
- Ideal for: APIs, webhooks, streaming workloads
- Use for: Long-running services with HTTP interface

### Cloud Run Job (`create_job_instead_of_service = true`)
- Task-based execution
- Manual or scheduled triggers via Cloud Scheduler
- Runs to completion
- Use for: ETL jobs, batch processing, cron jobs

## Outputs

Use these outputs in your Dativo job configuration:

```yaml
infrastructure:
  provider: gcp
  runtime:
    type: gcp_cloud_run
  region: us-central1
  resource_identifiers:
    cluster_name: "{{terraform_outputs.cluster_name}}"
    service_name: "{{terraform_outputs.service_name}}"
    service_uri: "{{terraform_outputs.service_uri}}"
    service_account_email: "{{terraform_outputs.service_account_email}}"
  tags:
    job_name: stripe-customers-etl
    team: data-engineering
    pipeline_type: ingestion
    environment: prod
    cost_center: data-platform
```

## Labeling Strategy

All resources created by this module are labeled with:

1. **Job metadata labels** (from `job_metadata` variable):
   - `job_name`: Dativo job identifier
   - `team`: Owning team
   - `pipeline_type`: Type of pipeline (ingestion, transformation, etc.)
   - `environment`: Deployment environment (dev, staging, prod)
   - `cost_center`: Cost allocation identifier

2. **Default labels** (from `default_labels` variable):
   - Organization-wide labels (e.g., project, managed_by)

3. **Module-added labels**:
   - `managed_by`: terraform
   - `dativo_runtime`: gcp_cloud_run

**Note**: GCP labels are converted to lowercase with underscores/hyphens only (GCP naming requirements).

This ensures consistent labeling for cost allocation, compliance auditing, and resource classification.

## Requirements

| Name | Version |
|------|---------|
| terraform | >= 1.5.0 |
| google | ~> 5.0 |

## Inputs

See [variables.tf](./variables.tf) for complete input documentation.

## Outputs

See [outputs.tf](./outputs.tf) for complete output documentation.

## Cost Optimization

- Enable scale-to-zero (`min_instances = 0`) for batch jobs
- Use appropriate CPU/memory combinations (see [Cloud Run Pricing](https://cloud.google.com/run/pricing))
- Enable CPU throttling (`cpu_throttling = true`) to reduce costs when idle
- Use Gen2 execution environment for better performance and lower cold start times
- Consider Cloud Run Jobs for batch workloads (no idle costs)

## Security Best Practices

1. **Service Account**: Dedicated service account with least-privilege IAM permissions
2. **Secret Manager**: Store all secrets in Google Secret Manager
3. **VPC Connector**: Use VPC connector for private network access
4. **No Public Access**: Keep `allow_unauthenticated_access = false` (default)
5. **IAM Roles**: Grant only necessary storage and secret access

## References

- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Cloud Run Jobs](https://cloud.google.com/run/docs/create-jobs)
- [Cloud Scheduler](https://cloud.google.com/scheduler/docs)
- [GCP Labeling Best Practices](https://cloud.google.com/resource-manager/docs/creating-managing-labels)
- [Service Accounts Best Practices](https://cloud.google.com/iam/docs/best-practices-service-accounts)
