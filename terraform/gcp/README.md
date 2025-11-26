# Dativo ETL Job Infrastructure - GCP Module

This Terraform module provisions cloud infrastructure for Dativo ETL jobs on Google Cloud Platform (GCP) with comprehensive label propagation for cost allocation, compliance, and resource traceability.

## Features

- **Cloud Run Jobs**: Serverless container execution for ETL jobs
- **Dagster Integration**: Compatible with Dagster orchestration
- **VPC Networking**: Private Google Access and VPC connectors
- **GCS Storage**: Buckets for data and state with encryption support
- **Cloud Logging**: Structured logging with log sinks
- **Cloud Monitoring**: Metrics, alerts, and dashboards
- **IAM Security**: Service accounts with least-privilege permissions
- **Comprehensive Labeling**: Automatic label propagation from job configurations

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Dativo Job Configuration                │
│  (infrastructure block with labels, compute, networking)    │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              Python Infrastructure Module                    │
│  • Validates configuration                                   │
│  • Propagates labels (cost_center, compliance, etc.)        │
│  • Generates terraform.tfvars                               │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   Terraform GCP Module                       │
│  • Provisions Cloud Run job                                 │
│  • Creates service account and IAM bindings                 │
│  • Sets up Cloud Logging and Monitoring                     │
│  • Applies labels to all resources                          │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                     GCP Resources                            │
│  • Cloud Run Job                                            │
│  • Service Account                                          │
│  • IAM Bindings                                             │
│  • Cloud Logging Sink                                       │
│  • Alert Policies                                           │
│  • All labeled with cost allocation and compliance metadata │
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
  provider: gcp
  
  runtime:
    type: cloud_run
    compute:
      cpu: "2"
      memory: "4Gi"
    timeout_seconds: 7200
  
  networking:
    vpc_id: projects/my-project/locations/us-central1/connectors/my-vpc-connector
    private_access: true
  
  storage:
    state_bucket: dativo-state-acme
    data_bucket: dativo-data-acme
    encryption:
      enabled: true
      kms_key_id: projects/my-project/locations/us-central1/keyRings/my-keyring/cryptoKeys/my-key
  
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
    metrics_namespace: Dativo/Jobs
    alerts:
      channels:
        - projects/my-project/notificationChannels/123456789
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
output_path = Path("terraform/gcp/terraform.tfvars.json")
infra_config.export_terraform_vars(
    output_path=output_path,
    job_config=job_config,
    asset_tags=asset_tags,
    format="json"
)
```

### 3. Apply Terraform

```bash
cd terraform/gcp

# Initialize Terraform
terraform init

# Review plan
terraform plan -var-file=terraform.tfvars.json -var="project_id=my-project"

# Apply infrastructure
terraform apply -var-file=terraform.tfvars.json -var="project_id=my-project"
```

## Label Propagation

GCP labels are automatically propagated from multiple sources. Note: GCP labels must be lowercase and use underscores.

1. **Infrastructure Labels** (from job config `infrastructure.tags`, normalized):
   - `costcenter`
   - `businessunit`
   - `project`
   - `environment`
   - `owner`
   - `compliance`
   - `dataclassification`

2. **Job Metadata Labels**:
   - `tenant_id`
   - `asset`
   - `sourceconnector`
   - `job_name`

3. **Asset Labels** (from asset schema):
   - `classification_*` (PII, sensitive data, etc.)
   - `governance_*` (retention, regulations)
   - `finops_*` (cost attribution)

4. **System Labels**:
   - `managed_by: dativo`
   - `terraform: true`
   - `module: dativo_etl_job`

### Example Label Output

```hcl
labels = {
  # Infrastructure labels (normalized)
  costcenter         = "fin_001"
  businessunit       = "finance"
  project            = "data_platform"
  environment        = "prod"
  owner              = "data_team_acme_com"
  compliance         = "gdpr_soc2"
  dataclassification = "confidential"
  
  # Job metadata labels
  tenant_id        = "acme"
  asset            = "stripe_customers"
  sourceconnector  = "stripe"
  job_name         = "stripe_customers_to_iceberg"
  
  # Asset labels
  classification_default       = "pii"
  classification_fields_email  = "pii"
  governance_retention_days    = "365"
  finops_cost_center          = "fin_001"
  
  # System labels
  managed_by   = "dativo"
  terraform    = "true"
  module       = "dativo_etl_job"
  runtime_type = "cloud_run"
}
```

## Cost Allocation

Use GCP Billing export to BigQuery and query by labels:

```sql
-- Example BigQuery cost analysis
SELECT 
  SUM(cost) as total_cost,
  labels.value as cost_center,
  labels.value as tenant_id,
  labels.value as job_name
FROM `project.dataset.gcp_billing_export_v1_XXXXXX`
CROSS JOIN UNNEST(labels) as labels
WHERE labels.key = 'managed_by' AND labels.value = 'dativo'
  AND labels.key = 'environment' AND labels.value = 'prod'
GROUP BY cost_center, tenant_id, job_name
ORDER BY total_cost DESC
```

## Compliance Tracking

Query resources by labels using gcloud:

```bash
# List all GDPR-compliant Cloud Run jobs
gcloud run jobs list \
  --filter="metadata.labels.compliance:gdpr" \
  --format="table(name,location,metadata.labels)"

# List all PII data processing jobs
gcloud run jobs list \
  --filter="metadata.labels.classification_default:pii" \
  --format="table(name,location,metadata.labels)"
```

## Cloud Logging

View logs in Cloud Logging console:

```
resource.type="cloud_run_job"
resource.labels.job_name="acme-stripe-customers-to-iceberg"
```

Or use gcloud:

```bash
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="acme-stripe-customers-to-iceberg"' \
  --limit 50 \
  --format json
```

## Outputs

| Output | Description |
|--------|-------------|
| `cloud_run_job_name` | Name of the Cloud Run job |
| `cloud_run_job_id` | ID of the Cloud Run job |
| `service_account_email` | Email of service account |
| `service_account_name` | Name of service account |
| `resource_labels` | All applied resource labels |
| `log_filter` | Cloud Logging filter for job |

## Requirements

| Name | Version |
|------|---------|
| terraform | >= 1.0 |
| google | ~> 5.0 |

## Providers

| Name | Version |
|------|---------|
| google | ~> 5.0 |

## Best Practices

1. **Label Governance**: Always specify `costcenter`, `owner`, and `environment` labels
2. **Encryption**: Enable Cloud KMS encryption for sensitive data
3. **Networking**: Use VPC connectors for private access to resources
4. **Monitoring**: Set up alert policies for job failures and SLOs
5. **IAM**: Use service accounts with least-privilege permissions
6. **Naming**: Use lowercase and hyphens for GCP resource names

## Troubleshooting

### Label Validation Errors

GCP has strict label requirements:
- Must be lowercase
- Use underscores (not hyphens) in values
- Maximum 63 characters
- Only alphanumeric and underscore characters

The module automatically normalizes labels to comply with GCP requirements.

### Service Account Permissions

If job fails with permission errors, verify service account has required roles:

```bash
# Check service account IAM bindings
gcloud projects get-iam-policy PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:SERVICE_ACCOUNT_EMAIL"
```

### VPC Connector Issues

Ensure VPC connector exists and is in the same region:

```bash
gcloud compute networks vpc-access connectors describe CONNECTOR_NAME \
  --region=REGION
```

## Examples

See `examples/jobs/` for complete job configurations with infrastructure blocks.

## License

Apache 2.0 - See LICENSE file for details
