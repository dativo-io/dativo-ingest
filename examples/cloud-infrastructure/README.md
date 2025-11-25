# Cloud Infrastructure Examples

Complete examples demonstrating external infrastructure integration for Dativo ETL jobs in AWS and GCP.

## Overview

These examples show:
- **Full infrastructure configuration** for AWS EMR and GCP GKE
- **Comprehensive tag/label propagation** for cost allocation and compliance
- **Terraform integration** for infrastructure as code
- **Cloud-agnostic job definitions** that work on both platforms
- **Best practices** for security, networking, and cost optimization

## Examples

### 1. AWS EMR Complete (`aws-emr-complete.yaml`)

Production-ready example for AWS EMR with:
- EMR cluster configuration with auto-scaling
- VPC and security group setup
- S3 bucket configuration
- IAM roles and policies
- KMS encryption
- CloudWatch logging
- Comprehensive tag propagation (35+ tags)
- FinOps metadata for cost allocation
- Classification tags for compliance

**Key Features:**
- **Platform**: AWS EMR
- **Source**: PostgreSQL database
- **Target**: Apache Iceberg on S3
- **Deployment**: Terraform module
- **Tags**: Classification, FinOps, governance

**Usage:**
```bash
# 1. Set environment variables
export POSTGRES_HOST=db.acme.com
export POSTGRES_USER=dativo
export POSTGRES_PASSWORD=secret
export EMR_CLUSTER_ID=$(terraform output -raw emr_cluster_id)

# 2. Run Dativo
dativo run --config examples/cloud-infrastructure/aws-emr-complete.yaml --mode self_hosted
```

### 2. GCP GKE Complete (`gcp-gke-complete.yaml`)

Production-ready example for GCP GKE with:
- GKE cluster configuration with auto-scaling
- Private nodes and Workload Identity
- GCS bucket configuration
- Service accounts and IAM
- KMS encryption
- Cloud Logging
- Comprehensive label propagation (35+ labels)
- Kubernetes labels and annotations
- FinOps metadata for cost allocation

**Key Features:**
- **Platform**: GCP GKE
- **Source**: Stripe API
- **Target**: Apache Iceberg on GCS
- **Deployment**: Terraform module
- **Labels**: Classification, FinOps, Kubernetes

**Usage:**
```bash
# 1. Set environment variables
export STRIPE_API_KEY=sk_live_...
export GCP_PROJECT_ID=acme-prod
export GCP_REGION=us-central1

# 2. Run Dativo
dativo run --config examples/cloud-infrastructure/gcp-gke-complete.yaml --mode self_hosted
```

## Tag/Label Propagation

### AWS Tags

**Generated from job config and asset definition:**

```json
{
  "TenantId": "acme",
  "Environment": "prod",
  "SourceConnector": "postgres",
  "TargetConnector": "iceberg",
  "Asset": "postgres_orders",
  "Domain": "sales",
  "DataProduct": "customer-analytics",
  "Owner": "data-team@acme.com",
  "DataClassification": "PII,Financial",
  "ContainsPII": "true",
  "Regulations": "GDPR,CCPA",
  "RetentionDays": "730",
  "EncryptionRequired": "true",
  "CostCenter": "data-engineering",
  "Project": "customer-analytics",
  "Platform": "emr",
  "ManagedBy": "terraform"
}
```

### GCP Labels

**Converted to GCP-compliant format:**

```json
{
  "tenant_id": "acme",
  "environment": "prod",
  "source_connector": "stripe",
  "target_connector": "iceberg",
  "asset": "stripe_customers",
  "domain": "payments",
  "data_product": "payment-analytics",
  "owner": "payments-team",
  "data_classification": "pii-financial",
  "contains_pii": "true",
  "regulations": "gdpr-ccpa",
  "retention_days": "1095",
  "cost_center": "data-engineering",
  "project": "payment-analytics",
  "platform": "kubernetes",
  "managed_by": "terraform"
}
```

## Terraform Integration

### AWS Workflow

```bash
# 1. Generate Terraform variables from Dativo config
python -c "
from dativo_ingest.cloud_infrastructure import AWSInfrastructureManager
from dativo_ingest.config import JobConfig, AssetDefinition

job_config = JobConfig.from_yaml('examples/cloud-infrastructure/aws-emr-complete.yaml')
asset = AssetDefinition.from_yaml(job_config.get_asset_path())

manager = AWSInfrastructureManager(job_config, asset)
manager.generate_terraform_tfvars('terraform/aws/emr-dativo/dativo.auto.tfvars')
"

# 2. Apply Terraform
cd terraform/aws/emr-dativo
terraform init
terraform workspace select prod
terraform plan
terraform apply

# 3. Export outputs
export EMR_CLUSTER_ID=$(terraform output -raw emr_cluster_id)

# 4. Run Dativo
dativo run --config examples/cloud-infrastructure/aws-emr-complete.yaml
```

### GCP Workflow

```bash
# 1. Generate Terraform variables from Dativo config
python -c "
from dativo_ingest.cloud_infrastructure import GCPInfrastructureManager
from dativo_ingest.config import JobConfig, AssetDefinition

job_config = JobConfig.from_yaml('examples/cloud-infrastructure/gcp-gke-complete.yaml')
asset = AssetDefinition.from_yaml(job_config.get_asset_path())

manager = GCPInfrastructureManager(job_config, asset)
manager.generate_terraform_tfvars('terraform/gcp/gke-dativo/dativo.auto.tfvars')
"

# 2. Apply Terraform
cd terraform/gcp/gke-dativo
terraform init
terraform workspace select prod
terraform plan
terraform apply

# 3. Configure kubectl
gcloud container clusters get-credentials dativo-acme-prod --region us-central1

# 4. Run Dativo
dativo run --config examples/cloud-infrastructure/gcp-gke-complete.yaml
```

## Cost Allocation

### AWS Cost Explorer Queries

```python
# Query by CostCenter
cost_center_filter = {
    "Tags": {
        "Key": "CostCenter",
        "Values": ["data-engineering"]
    }
}

# Query by Project
project_filter = {
    "Tags": {
        "Key": "Project",
        "Values": ["customer-analytics"]
    }
}

# Query by Tenant and Environment
tenant_filter = {
    "Tags": {
        "Key": "TenantId",
        "Values": ["acme"]
    }
}
```

### GCP Billing Export

```sql
-- BigQuery query for cost by label
SELECT
  labels.value AS project,
  SUM(cost) AS total_cost,
  SUM(usage.amount) AS usage_amount
FROM `project.dataset.gcp_billing_export`
WHERE labels.key = 'project'
  AND labels.value = 'customer-analytics'
  AND DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY labels.value
ORDER BY total_cost DESC
```

## Compliance Tracking

### PII Detection

```python
from dativo_ingest.cloud_infrastructure import AWSInfrastructureManager

manager = AWSInfrastructureManager(job_config, asset)
tags = manager.context.tags

if tags.get("ContainsPII") == "true":
    print(f"⚠️  Resource contains PII")
    print(f"Classification: {tags['DataClassification']}")
    print(f"Regulations: {tags['Regulations']}")
    print(f"Retention: {tags['RetentionDays']} days")
    print(f"Encryption: {tags['EncryptionRequired']}")
```

### Audit Reports

```bash
# AWS - List all resources with PII
aws resourcegroupstaggingapi get-resources \
  --tag-filters Key=ContainsPII,Values=true \
  --query 'ResourceTagMappingList[].{Arn:ResourceARN,Tags:Tags}'

# GCP - List all resources with PII
gcloud asset search-all-resources \
  --query="labels.contains_pii=true" \
  --format="table(name,labels)"
```

## Multi-Cloud Deployment

### Same Job, Different Clouds

```yaml
# Common configuration
tenant_id: acme
environment: ${ENVIRONMENT}

infrastructure:
  provider: terraform
  runtime:
    platform: ${CLOUD_PLATFORM}  # emr or kubernetes
    compute:
      cluster_id: ${CLUSTER_ID}
      instance_type: ${INSTANCE_TYPE}
      instance_count: ${INSTANCE_COUNT}
```

```bash
# Deploy to AWS
export CLOUD_PLATFORM=emr
export CLUSTER_ID=$EMR_CLUSTER_ID
export INSTANCE_TYPE=r5.2xlarge

# Deploy to GCP
export CLOUD_PLATFORM=kubernetes
export CLUSTER_ID=$GKE_CLUSTER_NAME
export INSTANCE_TYPE=n2-standard-4
```

## Best Practices

### 1. Tag Standardization

Use consistent tag keys across clouds:
- `CostCenter` → `cost_center`
- `Project` → `project`
- `Environment` → `environment`
- `Owner` → `owner`

### 2. Cost Optimization

- Use spot/preemptible instances for non-critical workloads
- Enable auto-scaling to match workload demand
- Set appropriate retention policies
- Monitor costs by tag/label

### 3. Security

- Enable encryption at rest and in transit
- Use private networks and security groups
- Follow least privilege for IAM/service accounts
- Enable audit logging

### 4. Compliance

- Tag all resources with classification
- Document retention policies
- Track regulatory requirements
- Implement data lifecycle policies

### 5. Governance

- Require owner tags for all resources
- Use Terraform workspaces for environments
- Version infrastructure modules
- Maintain audit trail

## Troubleshooting

### AWS Issues

```bash
# Validate EMR cluster
aws emr describe-cluster --cluster-id $EMR_CLUSTER_ID

# Check S3 bucket tags
aws s3api get-bucket-tagging --bucket acme-data-lake-prod

# Verify IAM role
aws iam get-role --role-name DativoEMRRole
```

### GCP Issues

```bash
# Validate GKE cluster
gcloud container clusters describe dativo-acme-prod --region us-central1

# Check GCS bucket labels
gsutil label get gs://acme-data-lake-prod

# Verify service account
gcloud iam service-accounts describe dativo-runner@acme-prod.iam.gserviceaccount.com
```

## Related Documentation

- [INFRASTRUCTURE_IMPLEMENTATION.md](../../INFRASTRUCTURE_IMPLEMENTATION.md) - Implementation guide
- [docs/INFRASTRUCTURE.md](../../docs/INFRASTRUCTURE.md) - Configuration reference
- [terraform/aws/emr-dativo/README.md](../../terraform/aws/emr-dativo/README.md) - AWS module
- [terraform/gcp/gke-dativo/README.md](../../terraform/gcp/gke-dativo/README.md) - GCP module
