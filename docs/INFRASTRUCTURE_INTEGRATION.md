# External Infrastructure Integration

Enable cloud-agnostic deployment of Dativo ETL jobs with comprehensive tag propagation for cost allocation, compliance, and resource traceability via Terraform.

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Infrastructure Block](#infrastructure-block)
4. [Terraform Integration](#terraform-integration)
5. [Tag Propagation](#tag-propagation)
6. [Cloud Provider Support](#cloud-provider-support)
7. [Dagster Integration](#dagster-integration)
8. [Best Practices](#best-practices)
9. [Examples](#examples)

---

## Overview

Dativo's infrastructure integration enables you to:

- **Reference External Infrastructure**: Connect jobs to infrastructure provisioned outside Dativo (via Terraform)
- **Cloud-Agnostic Deployment**: Deploy on AWS, GCP, or Azure with consistent configuration
- **Comprehensive Tag Propagation**: Flow tags from infrastructure → job → asset → Iceberg tables
- **Cost Allocation**: Track costs by tenant, environment, cost center, and project
- **Compliance Tracking**: Maintain compliance metadata (GDPR, HIPAA, SOC2) across the stack
- **Resource Traceability**: Link jobs to specific cloud resources (buckets, IAM roles, catalogs)

### Key Features

✅ **Cloud-agnostic** - AWS, GCP, Azure support  
✅ **Terraform integration** - Map Terraform outputs to job configs  
✅ **Tag propagation** - Infrastructure tags → Iceberg table properties  
✅ **Resource references** - Link jobs to S3 buckets, IAM roles, Glue catalogs  
✅ **Multi-tenancy** - Isolated infrastructure per tenant  
✅ **Dagster compatible** - Full integration with orchestrator  

---

## Quick Start

### 1. Provision Infrastructure with Terraform

**AWS:**
```bash
cd terraform/aws/dativo-etl
terraform init
terraform plan -var="tenant_id=acme" -var="environment=prod" -var="region=us-east-1" -var="s3_bucket_name=acme-dativo-data-lake-prod"
terraform apply
```

**GCP:**
```bash
cd terraform/gcp/dativo-etl
terraform init
terraform plan -var="project_id=my-gcp-project" -var="tenant_id=acme" -var="environment=prod" -var="region=us-central1" -var="gcs_bucket_name=acme-dativo-data-lake-prod"
terraform apply
```

### 2. Add Infrastructure Block to Job Config

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
      - resource_type: iam_role
        resource_id: "arn:aws:iam::123456789012:role/acme-dativo-etl-role-prod"
        resource_name: acme-dativo-etl-role-prod
  
  terraform:
    module_path: "./terraform/aws/dativo-etl"
    workspace: "acme-prod"
    outputs:
      s3_bucket_name: "target.connection.s3.bucket"
      iam_role_arn: "infrastructure.metadata.iam_role_arn"
  
  tags:
    cost_center: DATA-001
    business_unit: Analytics
    project: data-platform
    environment: prod
    owner: data-team@acme.com
    compliance: ["SOC2", "GDPR"]

# Rest of job config
source_connector: stripe
source_connector_path: connectors/stripe.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: stripe_customers
asset_path: assets/stripe/v1.0/customers.yaml
```

### 3. Run Job

```bash
dativo run --config jobs/acme/stripe_customers.yaml --mode self_hosted
```

**Result:** Tags flow from infrastructure → Iceberg table properties for cost allocation and compliance tracking.

---

## Infrastructure Block

The `infrastructure` block is **optional** and describes the runtime environment and metadata.

### Structure

```yaml
infrastructure:
  provider:           # Cloud provider configuration (required)
    provider: aws     # "aws", "gcp", or "azure"
    region: us-east-1
    account_id: "123456789012"  # AWS account ID
    project_id: my-gcp-project  # GCP project ID (required for GCP)
    resources:        # List of managed resources
      - resource_type: s3_bucket
        resource_id: "arn:aws:s3:::my-bucket"
        resource_name: my-bucket
        region: us-east-1
        tags:
          team: data-engineering
  
  terraform:          # Terraform integration (optional)
    module_path: ./terraform/aws/dativo-etl
    workspace: acme-prod
    backend:          # Backend configuration
      type: s3
      bucket: terraform-state
      key: dativo/acme/prod/terraform.tfstate
    variables:        # Input variables
      tenant_id: acme
      environment: prod
    outputs:          # Map outputs to job config fields
      s3_bucket_name: "target.connection.s3.bucket"
      iam_role_arn: "infrastructure.metadata.iam_role_arn"
  
  tags:               # Infrastructure tags (optional)
    cost_center: DATA-001
    business_unit: Analytics
    project: data-platform
    environment: prod
    owner: data-team@acme.com
    compliance: ["SOC2", "GDPR"]
    custom:
      data_classification: confidential
      retention_policy: 90_days
  
  metadata:           # Additional metadata (optional)
    deployment_id: deploy-20250126-001
    provisioned_by: terraform
```

### Provider Configuration

#### AWS

```yaml
infrastructure:
  provider:
    provider: aws
    region: us-east-1              # Required for AWS
    account_id: "123456789012"     # Optional
    resources:
      - resource_type: s3_bucket
        resource_id: "arn:aws:s3:::acme-dativo-data-lake-prod"
        resource_name: acme-dativo-data-lake-prod
      - resource_type: iam_role
        resource_id: "arn:aws:iam::123456789012:role/acme-dativo-etl-role-prod"
      - resource_type: glue_catalog
        resource_id: "arn:aws:glue:us-east-1:123456789012:database/acme_iceberg_prod"
        resource_name: acme_iceberg_prod
```

#### GCP

```yaml
infrastructure:
  provider:
    provider: gcp
    region: us-central1
    project_id: my-gcp-project     # Required for GCP
    resources:
      - resource_type: gcs_bucket
        resource_id: "gs://acme-dativo-data-lake-prod"
        resource_name: acme-dativo-data-lake-prod
      - resource_type: service_account
        resource_id: "acme-dativo-etl-prod@my-gcp-project.iam.gserviceaccount.com"
      - resource_type: bigquery_dataset
        resource_id: "my-gcp-project.acme_iceberg_prod"
        resource_name: acme_iceberg_prod
```

#### Azure (Preview)

```yaml
infrastructure:
  provider:
    provider: azure
    region: eastus
    resources:
      - resource_type: storage_account
        resource_id: "/subscriptions/.../storageAccounts/acmedatiostore"
        resource_name: acmedatiostore
```

### Resource Types

| Provider | Resource Type | Description |
|----------|---------------|-------------|
| AWS | `s3_bucket` | S3 bucket for data storage |
| AWS | `iam_role` | IAM role for ECS tasks |
| AWS | `glue_catalog` | Glue catalog database |
| GCP | `gcs_bucket` | GCS bucket for data storage |
| GCP | `service_account` | Service account for compute |
| GCP | `bigquery_dataset` | BigQuery dataset for metadata |
| Azure | `storage_account` | Storage account for data |
| Azure | `managed_identity` | Managed identity for auth |

---

## Terraform Integration

### Terraform Configuration

```yaml
infrastructure:
  terraform:
    module_path: ./terraform/aws/dativo-etl
    workspace: acme-prod
    backend:
      type: s3
      bucket: terraform-state
      key: dativo/acme/prod/terraform.tfstate
    variables:
      tenant_id: acme
      environment: prod
      region: us-east-1
      s3_bucket_name: acme-dativo-data-lake-prod
    outputs:
      s3_bucket_name: "target.connection.s3.bucket"
      s3_bucket_arn: "infrastructure.metadata.s3_bucket_arn"
      iam_role_arn: "infrastructure.metadata.iam_role_arn"
      glue_database_name: "target.catalog.glue_database"
```

### Output Mapping

Map Terraform outputs to job configuration fields using dot notation:

```yaml
outputs:
  # Map to target connection
  s3_bucket_name: "target.connection.s3.bucket"
  s3_bucket_region: "target.connection.s3.region"
  
  # Map to infrastructure metadata
  iam_role_arn: "infrastructure.metadata.iam_role_arn"
  glue_database_name: "infrastructure.metadata.glue_database"
  
  # Map to source connection (for databases)
  rds_endpoint: "source.connection.host"
  rds_port: "source.connection.port"
```

### Terraform Modules

Dativo provides reference Terraform modules:

**AWS Module:**
- S3 bucket with encryption and versioning
- IAM role with least-privilege access
- Glue catalog database for Iceberg
- Comprehensive tagging

**GCP Module:**
- GCS bucket with versioning
- Service account with least-privilege access
- BigQuery dataset for metadata
- Comprehensive labeling

See [terraform/aws/dativo-etl/](../terraform/aws/dativo-etl/) and [terraform/gcp/dativo-etl/](../terraform/gcp/dativo-etl/) for full documentation.

---

## Tag Propagation

Infrastructure tags flow through the entire data pipeline:

```
Infrastructure Tags (Terraform)
    ↓
Job Configuration (infrastructure.tags)
    ↓
Asset Definition (finops, compliance)
    ↓
Iceberg Table Properties (table.properties)
    ↓
Data Catalogs (Unity Catalog, Glue, etc.)
```

### Tag Namespaces

Infrastructure tags are stored with the `infrastructure.*` prefix:

```properties
# Infrastructure tags
infrastructure.cost_center=DATA-001
infrastructure.business_unit=Analytics
infrastructure.project=data-platform
infrastructure.environment=prod
infrastructure.owner=data-team@acme.com
infrastructure.compliance=SOC2,GDPR

# Provider metadata
infrastructure.provider=aws
infrastructure.region=us-east-1
infrastructure.account_id=123456789012

# Custom tags
infrastructure.custom.data_classification=confidential
infrastructure.custom.retention_policy=90_days
```

### Tag Precedence

Tags are merged in this order (later overrides earlier):

1. Infrastructure tags (from `infrastructure.tags`)
2. Asset FinOps tags (from asset `finops` section)
3. Job FinOps overrides (from job `finops` section)
4. Asset compliance tags (from asset `compliance` section)
5. Job classification overrides (from job `classification_overrides`)

### Cost Allocation

Enable cost tracking by infrastructure tags:

**AWS Cost Explorer:**
- Activate cost allocation tags: `infrastructure.cost_center`, `infrastructure.business_unit`
- Filter costs by tenant: `infrastructure.tenant_id`
- Track by environment: `infrastructure.environment`

**GCP Cost Management:**
- Use labels for cost tracking: `cost_center`, `business_unit`, `tenant_id`
- Create custom cost reports by label
- Export to BigQuery for analysis

---

## Cloud Provider Support

### AWS

**Supported Services:**
- **Storage**: S3 buckets
- **Compute**: ECS tasks, Lambda
- **Catalog**: Glue catalog
- **IAM**: IAM roles, policies

**Terraform Module:** `terraform/aws/dativo-etl`

**Required Outputs:**
- `s3_bucket_name`
- `iam_role_arn`
- `glue_database_name` (if Glue catalog enabled)

### GCP

**Supported Services:**
- **Storage**: GCS buckets
- **Compute**: Cloud Run, GKE
- **Catalog**: BigQuery datasets
- **IAM**: Service accounts

**Terraform Module:** `terraform/gcp/dativo-etl`

**Required Outputs:**
- `gcs_bucket_name`
- `service_account_email`
- `bigquery_dataset_id` (if BigQuery catalog enabled)

### Azure (Preview)

**Supported Services:**
- **Storage**: Storage accounts (blob)
- **Compute**: Container Instances, AKS
- **Catalog**: Purview (planned)
- **IAM**: Managed identities

---

## Dagster Integration

Infrastructure metadata is automatically available in Dagster assets.

### Asset Metadata

```python
from dagster import asset, AssetExecutionContext
from dativo_ingest.infrastructure import get_infrastructure_tags

@asset
def stripe_customers(context: AssetExecutionContext):
    job_config = load_job_config("jobs/acme/stripe_customers.yaml")
    
    # Get infrastructure tags
    infra_tags = get_infrastructure_tags(job_config.infrastructure)
    
    # Add to Dagster metadata
    context.add_output_metadata({
        "cost_center": infra_tags.get("infrastructure.cost_center"),
        "environment": infra_tags.get("infrastructure.environment"),
        "provider": infra_tags.get("infrastructure.provider"),
        "tenant_id": job_config.tenant_id,
    })
    
    # Run ingestion
    run_ingestion(job_config)
```

### Resource Tags

Apply infrastructure tags to Dagster resources:

```python
from dagster import resource
from dativo_ingest.config import JobConfig

@resource
def dativo_infrastructure(context):
    job_config = context.resource_config["job_config"]
    return {
        "provider": job_config.infrastructure.provider.provider,
        "region": job_config.infrastructure.provider.region,
        "tags": get_infrastructure_tags(job_config.infrastructure),
    }
```

---

## Best Practices

### 1. Consistent Tagging

Use consistent tag keys across all environments:

```yaml
tags:
  cost_center: DATA-001        # Always use cost_center
  business_unit: Analytics     # Always use business_unit
  project: data-platform       # Always use project
  environment: prod            # dev, staging, prod
  owner: data-team@acme.com   # Email format
  compliance: ["SOC2", "GDPR"] # Array of regulations
```

### 2. Multi-Environment Setup

Create separate Terraform workspaces per environment:

```bash
# Production
terraform workspace new acme-prod
terraform apply -var-file="environments/prod.tfvars"

# Staging
terraform workspace new acme-staging
terraform apply -var-file="environments/staging.tfvars"
```

### 3. Resource Naming Conventions

Use consistent naming:
- **S3 Buckets**: `{tenant_id}-dativo-data-lake-{environment}`
- **IAM Roles**: `{tenant_id}-dativo-etl-role-{environment}`
- **Glue Databases**: `{tenant_id}_iceberg_{environment}`

### 4. Secret Management

Store Terraform outputs in secure secret managers:

```bash
# Store S3 bucket name
aws secretsmanager create-secret \
  --name "dativo/acme/prod/s3_bucket_name" \
  --secret-string "acme-dativo-data-lake-prod"

# Retrieve in job config
export S3_BUCKET=$(aws secretsmanager get-secret-value --secret-id "dativo/acme/prod/s3_bucket_name" --query SecretString --output text)
```

### 5. Cost Tracking

Enable detailed cost tracking:

**AWS:**
```hcl
tags = {
  CostCenter   = "DATA-001"
  BusinessUnit = "Analytics"
  TenantId     = "acme"
  Environment  = "prod"
}
```

**GCP:**
```hcl
labels = {
  cost_center   = "data-001"
  business_unit = "analytics"
  tenant_id     = "acme"
  environment   = "prod"
}
```

### 6. Compliance Documentation

Document compliance requirements in infrastructure tags:

```yaml
tags:
  compliance: ["SOC2", "GDPR", "HIPAA"]
  data_classification: confidential
  retention_policy: 90_days
  encryption_required: "true"
```

---

## Examples

### Example 1: AWS with Glue Catalog

```yaml
tenant_id: acme
environment: prod

infrastructure:
  provider:
    provider: aws
    region: us-east-1
    account_id: "123456789012"
    resources:
      - resource_type: s3_bucket
        resource_id: "arn:aws:s3:::acme-dativo-data-lake-prod"
        resource_name: acme-dativo-data-lake-prod
      - resource_type: iam_role
        resource_id: "arn:aws:iam::123456789012:role/acme-dativo-etl-role-prod"
      - resource_type: glue_catalog
        resource_id: "arn:aws:glue:us-east-1:123456789012:database/acme_iceberg_prod"
        resource_name: acme_iceberg_prod
  
  terraform:
    module_path: ./terraform/aws/dativo-etl
    workspace: acme-prod
    outputs:
      s3_bucket_name: "target.connection.s3.bucket"
      glue_database_name: "target.catalog.glue_database"
  
  tags:
    cost_center: DATA-001
    environment: prod
    compliance: ["SOC2"]

source_connector: stripe
source_connector_path: connectors/stripe.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: stripe_customers
asset_path: assets/stripe/v1.0/customers.yaml

target:
  connection:
    s3:
      bucket: acme-dativo-data-lake-prod
      prefix: raw/stripe/customers
  catalog:
    type: glue
    glue_database: acme_iceberg_prod
```

### Example 2: GCP with BigQuery Catalog

```yaml
tenant_id: acme
environment: prod

infrastructure:
  provider:
    provider: gcp
    region: us-central1
    project_id: my-gcp-project
    resources:
      - resource_type: gcs_bucket
        resource_id: "gs://acme-dativo-data-lake-prod"
        resource_name: acme-dativo-data-lake-prod
      - resource_type: service_account
        resource_id: "acme-dativo-etl-prod@my-gcp-project.iam.gserviceaccount.com"
      - resource_type: bigquery_dataset
        resource_id: "my-gcp-project.acme_iceberg_prod"
        resource_name: acme_iceberg_prod
  
  terraform:
    module_path: ./terraform/gcp/dativo-etl
    workspace: acme-prod
    outputs:
      gcs_bucket_name: "target.connection.gcs.bucket"
      bigquery_dataset_id: "target.catalog.bigquery_dataset"
  
  tags:
    cost_center: data-001
    environment: prod
    compliance: ["GDPR"]

source_connector: hubspot
source_connector_path: connectors/hubspot.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: hubspot_contacts
asset_path: assets/hubspot/v1.0/contacts.yaml

target:
  connection:
    gcs:
      bucket: acme-dativo-data-lake-prod
      prefix: raw/hubspot/contacts
  catalog:
    type: bigquery
    bigquery_dataset: acme_iceberg_prod
```

### Example 3: Multi-Tenant AWS Setup

```yaml
# Tenant 1: acme
tenant_id: acme
infrastructure:
  provider:
    provider: aws
    region: us-east-1
    resources:
      - resource_type: s3_bucket
        resource_id: "arn:aws:s3:::acme-dativo-data-lake-prod"
  tags:
    cost_center: ACME-DATA-001
    business_unit: acme-analytics

# Tenant 2: globex
tenant_id: globex
infrastructure:
  provider:
    provider: aws
    region: us-west-2
    resources:
      - resource_type: s3_bucket
        resource_id: "arn:aws:s3:::globex-dativo-data-lake-prod"
  tags:
    cost_center: GLOBEX-DATA-002
    business_unit: globex-analytics
```

---

## Troubleshooting

### Infrastructure Tags Not Appearing

1. **Check job config**: Verify `infrastructure.tags` is populated
2. **Verify tag propagation**: Look for `infrastructure.*` keys in Iceberg table properties
3. **Check asset config**: Ensure asset has `finops` section
4. **Review logs**: Look for `infrastructure_warning` events

### Terraform Output Mapping Failed

1. **Verify output names**: Check Terraform outputs match `terraform.outputs` keys
2. **Check workspace**: Ensure correct Terraform workspace is active
3. **Validate module path**: Verify `terraform.module_path` exists
4. **Review state**: Check Terraform state file contains expected outputs

### Provider Validation Errors

1. **AWS**: Ensure `region` is set
2. **GCP**: Ensure `project_id` is set
3. **Check resource IDs**: Verify resource ARNs/URIs are valid
4. **Review permissions**: Ensure service accounts have required permissions

---

## API Reference

### Python API

```python
from dativo_ingest.infrastructure import (
    get_infrastructure_tags,
    resolve_terraform_outputs,
    validate_infrastructure
)
from dativo_ingest.config import JobConfig

# Load job configuration
job_config = JobConfig.from_yaml("jobs/acme/stripe_customers.yaml")

# Get infrastructure tags
infra_tags = get_infrastructure_tags(job_config.infrastructure)
# Returns: {"infrastructure.cost_center": "DATA-001", ...}

# Resolve Terraform outputs
terraform_state = load_terraform_state("terraform.tfstate")
outputs = resolve_terraform_outputs(job_config.infrastructure, terraform_state)
# Returns: {"target.connection.s3.bucket": "acme-dativo-data-lake-prod", ...}

# Validate infrastructure
validate_infrastructure(job_config)
# Raises ValueError if validation fails
```

---

## Additional Resources

- [Terraform AWS Module](../terraform/aws/dativo-etl/README.md)
- [Terraform GCP Module](../terraform/gcp/dativo-etl/README.md)
- [Tag Propagation Guide](TAG_PROPAGATION.md)
- [Config Reference](CONFIG_REFERENCE.md)
- [Dagster Integration](RUNNER_AND_ORCHESTRATION.md)

---

## Support

For questions or issues:
- GitHub Issues: https://github.com/dativo/dativo-ingest/issues
- Documentation: https://docs.dativo.io
- Email: support@dativo.io
