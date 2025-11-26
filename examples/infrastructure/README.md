# Dativo Infrastructure Integration Examples

Examples demonstrating external infrastructure integration with Terraform for cloud-agnostic deployment.

## Overview

This directory contains example code for integrating Dativo ETL jobs with externally provisioned infrastructure (AWS, GCP, Azure) via Terraform.

## Files

- **`dagster_integration.py`** - Dagster integration helpers for infrastructure metadata
- **Job examples** in `docs/examples/jobs/acme/` demonstrate infrastructure blocks

## Dagster Integration

The `dagster_integration.py` module provides utilities for:

- Adding infrastructure metadata to Dagster assets
- Extracting cost allocation tags
- Getting compliance metadata
- Creating resource configurations
- Multi-tenant asset factories

### Quick Example

```python
from dagster import asset, AssetExecutionContext
from dativo_ingest.config import JobConfig
from examples.infrastructure.dagster_integration import (
    add_infrastructure_metadata,
    get_cost_allocation_tags,
)

@asset
def stripe_customers(context: AssetExecutionContext):
    # Load job configuration
    job_config = JobConfig.from_yaml("jobs/acme/stripe_customers.yaml")
    
    # Add infrastructure metadata to asset
    add_infrastructure_metadata(context, job_config)
    
    # Get cost allocation tags
    cost_tags = get_cost_allocation_tags(job_config)
    context.log.info(f"Cost tags: {cost_tags}")
    
    # Run ingestion
    # ... (your ingestion logic)
```

## Usage Examples

### 1. AWS Infrastructure Integration

See `docs/examples/jobs/acme/stripe_customers_aws_infrastructure.yaml`:

```yaml
infrastructure:
  provider:
    provider: aws
    region: us-east-1
    resources:
      - resource_type: s3_bucket
        resource_id: "arn:aws:s3:::acme-dativo-data-lake-prod"
  terraform:
    module_path: ./terraform/aws/dativo-etl
    outputs:
      s3_bucket_name: "target.connection.s3.bucket"
  tags:
    cost_center: DATA-001
    environment: prod
```

### 2. GCP Infrastructure Integration

See `docs/examples/jobs/acme/hubspot_contacts_gcp_infrastructure.yaml`:

```yaml
infrastructure:
  provider:
    provider: gcp
    project_id: acme-data-platform
    region: us-central1
    resources:
      - resource_type: gcs_bucket
        resource_id: "gs://acme-dativo-data-lake-prod"
  terraform:
    module_path: ./terraform/gcp/dativo-etl
    outputs:
      gcs_bucket_name: "target.connection.gcs.bucket"
  tags:
    cost_center: data-001
    environment: prod
```

### 3. Multi-Environment Setup

See `docs/examples/jobs/acme/postgres_orders_multi_environment.yaml`:

Demonstrates using environment variables for environment-specific infrastructure:

```yaml
infrastructure:
  provider:
    provider: aws
    region: "${AWS_REGION}"
    resources:
      - resource_type: s3_bucket
        resource_name: "acme-dativo-data-lake-${ENVIRONMENT}"
  terraform:
    workspace: "acme-${ENVIRONMENT}"
  tags:
    environment: "${ENVIRONMENT}"
```

## Dagster Utilities

### add_infrastructure_metadata()

Adds infrastructure metadata to Dagster asset execution context:

```python
add_infrastructure_metadata(context, job_config)
```

**Metadata added:**
- `tenant_id`
- `environment`
- `provider` (aws/gcp/azure)
- `region`
- `cost_center`
- `business_unit`
- `compliance`

### get_cost_allocation_tags()

Extracts cost allocation tags for billing tracking:

```python
cost_tags = get_cost_allocation_tags(job_config)
# Returns: {"cost_center": "DATA-001", "tenant_id": "acme", ...}
```

### get_compliance_metadata()

Extracts compliance metadata for governance:

```python
compliance = get_compliance_metadata(job_config)
# Returns: {"regulations": ["SOC2", "GDPR"], "data_owner": "...", ...}
```

### get_infrastructure_resource_config()

Gets infrastructure resource configuration for Dagster resources:

```python
config = get_infrastructure_resource_config(job_config)
# Returns: {"provider": "aws", "s3_bucket_name": "...", "iam_role_arn": "...", ...}
```

### dativo_infrastructure_resource

Dagster resource for accessing infrastructure configuration:

```python
from dagster import op

@op(required_resource_keys={"dativo_infra"})
def my_op(context):
    infra = context.resources.dativo_infra
    s3_bucket = infra["s3_bucket_name"]
    cost_center = infra["tags"]["infrastructure.cost_center"]
```

### create_dativo_asset_with_infrastructure()

Factory function for creating Dagster assets with infrastructure integration:

```python
asset_def = create_dativo_asset_with_infrastructure(
    job_config_path="jobs/acme/stripe_customers.yaml",
    asset_name="stripe_customers"
)
```

### create_multi_tenant_assets()

Factory for creating assets for multiple tenants:

```python
assets = create_multi_tenant_assets({
    "acme": "jobs/acme/stripe_customers.yaml",
    "globex": "jobs/globex/stripe_customers.yaml",
})
```

## Integration Patterns

### Pattern 1: Single Asset with Infrastructure

```python
from dagster import asset, AssetExecutionContext
from dativo_ingest.config import JobConfig
from examples.infrastructure.dagster_integration import add_infrastructure_metadata

@asset
def my_asset(context: AssetExecutionContext):
    job_config = JobConfig.from_yaml("jobs/acme/my_job.yaml")
    add_infrastructure_metadata(context, job_config)
    # ... run ingestion
```

### Pattern 2: Resource-Based Configuration

```python
from dagster import job, op
from examples.infrastructure.dagster_integration import dativo_infrastructure_resource

@op(required_resource_keys={"dativo_infra"})
def ingest_op(context):
    infra = context.resources.dativo_infra
    s3_bucket = infra["s3_bucket_name"]
    # ... use infrastructure config

@job(resource_defs={"dativo_infra": dativo_infrastructure_resource})
def ingest_job():
    ingest_op()
```

### Pattern 3: Multi-Tenant Asset Factory

```python
from examples.infrastructure.dagster_integration import create_multi_tenant_assets

# Create assets for all tenants
tenant_assets = create_multi_tenant_assets({
    "acme": "jobs/acme/stripe_customers.yaml",
    "globex": "jobs/globex/stripe_customers.yaml",
    "initech": "jobs/initech/stripe_customers.yaml",
})
```

## Cost Tracking

Use infrastructure tags for cost allocation:

```python
from examples.infrastructure.dagster_integration import get_cost_allocation_tags

@asset
def my_asset(context):
    job_config = JobConfig.from_yaml("jobs/acme/my_job.yaml")
    cost_tags = get_cost_allocation_tags(job_config)
    
    # Log cost tags for external cost tracking systems
    context.log.info(f"Cost allocation: {cost_tags}")
    
    # Add to metadata for Dagster UI
    context.add_output_metadata(cost_tags)
```

## Compliance Tracking

Track compliance requirements:

```python
from examples.infrastructure.dagster_integration import get_compliance_metadata

@asset
def my_asset(context):
    job_config = JobConfig.from_yaml("jobs/acme/my_job.yaml")
    compliance = get_compliance_metadata(job_config)
    
    # Enforce compliance requirements
    if "HIPAA" in compliance.get("regulations", []):
        context.log.info("HIPAA compliance required - enabling encryption")
        # ... enable encryption
```

## Best Practices

1. **Consistent Tagging**: Use the same tag keys across all environments
2. **Cost Attribution**: Always include `cost_center` and `business_unit` tags
3. **Compliance**: Document compliance requirements in infrastructure tags
4. **Multi-Tenancy**: Use tenant-specific infrastructure resources
5. **Environment Isolation**: Separate infrastructure per environment (dev/staging/prod)

## Testing

Test infrastructure integration:

```bash
# Load job config and verify infrastructure block
python -c "
from dativo_ingest.config import JobConfig
config = JobConfig.from_yaml('jobs/acme/stripe_customers.yaml')
print(f'Provider: {config.infrastructure.provider.provider}')
print(f'Region: {config.infrastructure.provider.region}')
"
```

## Additional Resources

- [Infrastructure Integration Guide](../../docs/INFRASTRUCTURE_INTEGRATION.md)
- [Terraform AWS Module](../../terraform/aws/dativo-etl/README.md)
- [Terraform GCP Module](../../terraform/gcp/dativo-etl/README.md)
- [Tag Propagation](../../docs/TAG_PROPAGATION.md)

## Support

For questions or issues:
- Documentation: https://docs.dativo.io
- GitHub Issues: https://github.com/dativo/dativo-ingest/issues
- Email: support@dativo.io
