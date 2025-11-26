# Infrastructure Integration Quick Start

Get started with external infrastructure integration in 5 minutes.

## Overview

Dativo's infrastructure integration enables cloud-agnostic deployment with Terraform on AWS and GCP, with comprehensive tag propagation for cost allocation and compliance.

## Prerequisites

- Terraform >= 1.3.0
- AWS CLI or GCP CLI configured
- Dativo installation

## Quick Start

### Step 1: Provision Infrastructure

**AWS:**
```bash
cd terraform/aws/dativo-etl
terraform init
terraform apply \
  -var="tenant_id=acme" \
  -var="environment=prod" \
  -var="region=us-east-1" \
  -var="s3_bucket_name=acme-dativo-data-lake-prod"
```

**GCP:**
```bash
cd terraform/gcp/dativo-etl
terraform init
terraform apply \
  -var="project_id=my-gcp-project" \
  -var="tenant_id=acme" \
  -var="environment=prod" \
  -var="region=us-central1" \
  -var="gcs_bucket_name=acme-dativo-data-lake-prod"
```

### Step 2: Add Infrastructure Block to Job Config

Create `jobs/acme/stripe_customers.yaml`:

```yaml
tenant_id: acme
environment: prod

# Infrastructure configuration
infrastructure:
  provider:
    provider: aws  # or "gcp"
    region: us-east-1
    account_id: "123456789012"
    resources:
      - resource_type: s3_bucket
        resource_id: "arn:aws:s3:::acme-dativo-data-lake-prod"
        resource_name: acme-dativo-data-lake-prod
  
  terraform:
    module_path: ./terraform/aws/dativo-etl
    workspace: acme-prod
    outputs:
      s3_bucket_name: "target.connection.s3.bucket"
  
  tags:
    cost_center: DATA-001
    business_unit: Analytics
    environment: prod

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
      bucket: acme-dativo-data-lake-prod
      prefix: raw/stripe/customers
```

### Step 3: Run Job

```bash
dativo run --config jobs/acme/stripe_customers.yaml --mode self_hosted
```

## Tag Propagation

Infrastructure tags automatically flow to Iceberg table properties:

```properties
infrastructure.cost_center=DATA-001
infrastructure.business_unit=Analytics
infrastructure.environment=prod
infrastructure.provider=aws
infrastructure.region=us-east-1
```

Query tags in your data catalog:

```sql
SELECT key, value
FROM system.metadata.table_properties
WHERE table_name = 'stripe_customers'
  AND key LIKE 'infrastructure.%';
```

## Cost Tracking

Enable cost allocation tags in AWS Cost Explorer or GCP Cost Management:

**AWS:**
- Navigate to Cost Explorer → Cost Allocation Tags
- Activate: `infrastructure.cost_center`, `infrastructure.tenant_id`

**GCP:**
- Navigate to Cloud Console → Billing → Cost Table
- Filter by labels: `cost_center`, `tenant_id`

## Next Steps

- **Multi-Environment Setup:** [docs/INFRASTRUCTURE_INTEGRATION.md#multi-environment-setup](docs/INFRASTRUCTURE_INTEGRATION.md#multi-environment-setup)
- **Dagster Integration:** [examples/infrastructure/dagster_integration.py](examples/infrastructure/dagster_integration.py)
- **Terraform Modules:** [terraform/README.md](terraform/README.md)
- **Full Documentation:** [docs/INFRASTRUCTURE_INTEGRATION.md](docs/INFRASTRUCTURE_INTEGRATION.md)

## Examples

See example job configurations:
- **AWS:** [docs/examples/jobs/acme/stripe_customers_aws_infrastructure.yaml](docs/examples/jobs/acme/stripe_customers_aws_infrastructure.yaml)
- **GCP:** [docs/examples/jobs/acme/hubspot_contacts_gcp_infrastructure.yaml](docs/examples/jobs/acme/hubspot_contacts_gcp_infrastructure.yaml)
- **Multi-Environment:** [docs/examples/jobs/acme/postgres_orders_multi_environment.yaml](docs/examples/jobs/acme/postgres_orders_multi_environment.yaml)

## Support

For questions or issues:
- Documentation: [docs/INFRASTRUCTURE_INTEGRATION.md](docs/INFRASTRUCTURE_INTEGRATION.md)
- GitHub Issues: https://github.com/dativo/dativo-ingest/issues
- Email: support@dativo.io
