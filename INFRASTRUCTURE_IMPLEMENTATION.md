# Cloud Infrastructure Integration - Implementation Guide

## Overview

Comprehensive implementation of external infrastructure integration for Dativo ETL jobs in AWS/GCP, enabling cloud-agnostic deployment via Terraform with comprehensive tag propagation for cost allocation, compliance, and resource traceability.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Dativo Job Config                        │
│  (tenant_id, environment, source, target, infrastructure)       │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Asset Definition (ODCS)                      │
│  (schema, compliance, team, finops, classification)             │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Tag Propagator                             │
│  • Derives tags from job config                                 │
│  • Derives tags from asset (ODCS)                               │
│  • Derives classification tags (PII, GDPR, retention)           │
│  • Derives FinOps tags (CostCenter, Project)                    │
│  • Enriches with infrastructure metadata                        │
└──────────────────────────────┬──────────────────────────────────┘
                               │
              ┌────────────────┴────────────────┐
              ▼                                 ▼
┌──────────────────────────────┐  ┌──────────────────────────────┐
│  AWS Infrastructure Manager  │  │  GCP Infrastructure Manager  │
│  • EMR cluster management    │  │  • GKE cluster management    │
│  • S3 bucket tagging         │  │  • GCS bucket labeling       │
│  • VPC & security groups     │  │  • VPC & firewalls          │
│  • IAM roles & policies      │  │  • Service accounts & IAM    │
│  • CloudWatch logging        │  │  • Cloud Logging             │
└──────────────────────────────┘  └──────────────────────────────┘
              │                                 │
              ▼                                 ▼
┌──────────────────────────────┐  ┌──────────────────────────────┐
│   Terraform Variables        │  │   Terraform Variables        │
│   (dativo.auto.tfvars)       │  │   (dativo.auto.tfvars)       │
└──────────────────────────────┘  └──────────────────────────────┘
              │                                 │
              ▼                                 ▼
┌──────────────────────────────┐  ┌──────────────────────────────┐
│     AWS Resources            │  │     GCP Resources            │
│  • EMR Clusters              │  │  • GKE Clusters              │
│  • S3 Buckets                │  │  • GCS Buckets               │
│  • EC2 Instances             │  │  • Compute Instances         │
│  • Security Groups           │  │  • Firewall Rules            │
│  • IAM Roles                 │  │  • Service Accounts          │
│  (All tagged with metadata)  │  │  (All labeled with metadata) │
└──────────────────────────────┘  └──────────────────────────────┘
```

## Key Components

### 1. Configuration Models (`src/dativo_ingest/config.py`)

Added comprehensive infrastructure configuration models:

```python
class InfrastructureConfig(BaseModel):
    """Infrastructure configuration for externally provisioned resources."""
    provider: Optional[str]  # terraform, cloudformation, pulumi
    terraform: Optional[TerraformConfig]
    runtime: Optional[RuntimeConfig]
    metadata: Optional[MetadataConfig]
    resources: Optional[ResourcesConfig]
    outputs: Optional[Dict[str, str]]
```

**Nested Models:**
- `TerraformConfig`: Module source, version, workspace, backend
- `RuntimeConfig`: Platform, compute, storage, network, service account
- `ComputeConfig`: Instance type, count, auto-scaling
- `StorageConfig`: Buckets, volumes, mount paths
- `NetworkConfig`: VPC, subnets, security groups
- `MetadataConfig`: Tags, labels, annotations, variables
- `ResourcesConfig`: Database, cache, queue, secrets

### 2. Tag Propagation System (`src/dativo_ingest/cloud_infrastructure/base.py`)

Comprehensive tag derivation from multiple sources:

```python
class TagPropagator:
    @staticmethod
    def build_complete_tag_set(job_config, asset):
        """Build complete tag set from all sources."""
        tags = {}
        
        # 1. Base tags from job (tenant_id, environment, connectors)
        tags.update(derive_tags_from_job(job_config))
        
        # 2. Asset metadata tags (domain, dataProduct, owner)
        tags.update(derive_tags_from_asset(asset))
        
        # 3. Classification tags (PII, GDPR, retention, encryption)
        tags.update(derive_classification_tags(asset))
        
        # 4. FinOps tags (CostCenter, Project, BusinessTags)
        tags.update(derive_finops_tags(job_config, asset))
        
        # 5. Infrastructure enrichment (provider, platform, workspace)
        tags.update(enrich_tags_with_infrastructure(infra_config))
        
        return tags
```

**Tag Categories:**

| Category | Source | Examples |
|----------|--------|----------|
| **Identity** | Job Config | TenantId, Environment, SourceConnector, TargetConnector |
| **ODCS Metadata** | Asset Definition | Domain, DataProduct, Owner, Status |
| **Classification** | Asset Compliance | DataClassification, ContainsPII, Regulations, RetentionDays |
| **FinOps** | Job/Asset FinOps | CostCenter, Project, BusinessTags |
| **Infrastructure** | Infra Config | InfraProvider, Platform, TerraformWorkspace |
| **Governance** | System | ManagedBy, LastModified, CreatedAt |

### 3. AWS Infrastructure Manager (`src/dativo_ingest/cloud_infrastructure/aws_infrastructure.py`)

**Features:**
- EMR cluster validation and tagging
- S3 bucket tagging
- VPC and security group validation
- Terraform variable generation
- Terraform tfvars file generation
- Automated terraform apply execution
- Boto3 integration for AWS API operations

**Key Methods:**
```python
class AWSInfrastructureManager:
    def validate_infrastructure(self) -> bool:
        """Validate EMR, VPC, S3 connectivity"""
    
    def apply_tags_to_resources(self, resource_ids) -> Dict[str, bool]:
        """Apply tags to AWS resources via boto3"""
    
    def apply_all_infrastructure_tags(self) -> Dict[str, bool]:
        """Tag all infrastructure from config"""
    
    def get_terraform_variables(self) -> Dict[str, Any]:
        """Generate Terraform variables"""
    
    def generate_terraform_tfvars(self, output_path: str):
        """Generate HCL tfvars file"""
    
    def run_terraform_apply(self, terraform_dir: str):
        """Execute terraform apply"""
```

### 4. GCP Infrastructure Manager (`src/dativo_ingest/cloud_infrastructure/gcp_infrastructure.py`)

**Features:**
- GKE cluster validation and labeling
- GCS bucket labeling
- VPC and network validation
- Label conversion (GCP label restrictions)
- Terraform variable generation
- Google Cloud API integration

**GCP Label Conversion:**
```python
def _convert_tags_to_labels(self, tags):
    """Convert tags to GCP-compatible labels.
    
    Restrictions:
    - Lowercase only
    - Max 63 characters
    - Only hyphens, underscores, lowercase letters, numbers
    - Keys must start with letter
    """
```

### 5. Terraform Modules

#### AWS EMR Module (`terraform/aws/emr-dativo/`)

**Resources:**
- EMR Cluster with Spark, Hadoop, Hive
- KMS encryption keys
- S3 buckets for logs
- Security groups (master/slave)
- IAM roles and policies
- CloudWatch log groups
- Auto-scaling policies

**Tag Propagation:**
All resources tagged with complete tag set including:
- Dativo metadata
- ODCS metadata
- Classification tags
- FinOps tags
- Infrastructure tags

#### GCP GKE Module (`terraform/gcp/gke-dativo/`)

**Resources:**
- GKE cluster with private nodes
- Node pools with autoscaling
- KMS encryption
- GCS buckets
- Service accounts
- Kubernetes namespace
- RBAC roles and bindings
- Workload Identity

**Label Propagation:**
All resources labeled with converted labels:
- GCP resource labels
- Kubernetes labels
- Kubernetes annotations

## Tag Propagation Flow

### Example: Complete Tag Set

**Input:**

```yaml
# Job Config
tenant_id: acme
environment: prod
source_connector: postgres
target_connector: iceberg
asset: postgres_orders

finops:
  cost_center: data-engineering
  project: customer-analytics
  business_tags: [sales, analytics]

infrastructure:
  provider: terraform
  terraform:
    workspace: prod
  runtime:
    platform: emr
  metadata:
    tags:
      CustomTag: custom-value
```

```yaml
# Asset Definition (ODCS)
domain: sales
dataProduct: customer-analytics
team:
  owner: data-team@acme.com
compliance:
  classification: [PII, Financial]
  regulations: [GDPR, CCPA]
  retention_days: 365
  security:
    encryption_required: true
finops:
  cost_center: data-engineering
```

**Output (Generated Tags):**

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
  "ContainsFinancial": "true",
  "Regulations": "GDPR,CCPA",
  "RetentionDays": "365",
  "EncryptionRequired": "true",
  
  "CostCenter": "data-engineering",
  "Project": "customer-analytics",
  "BusinessTags": "sales,analytics",
  
  "InfraProvider": "terraform",
  "Platform": "emr",
  "TerraformWorkspace": "prod",
  
  "ManagedBy": "dativo",
  "CustomTag": "custom-value",
  "LastModified": "2025-11-25T15:30:00Z"
}
```

## Usage

### 1. Configure Job with Infrastructure Block

```yaml
# jobs/acme/postgres_orders.yaml
tenant_id: acme
environment: prod

infrastructure:
  provider: terraform
  terraform:
    module_source: "../../terraform/aws/emr-dativo"
    workspace: "prod"
  runtime:
    platform: emr
    compute:
      cluster_id: "${EMR_CLUSTER_ID}"
      instance_type: "r5.2xlarge"
      instance_count: 8
      auto_scaling:
        enabled: true
        min_instances: 4
        max_instances: 12
    storage:
      bucket: "acme-data-lake-prod"
    network:
      vpc_id: "vpc-0a1b2c3d"
      subnet_ids: ["subnet-abc123"]
  metadata:
    tags:
      CostCenter: "data-engineering"
    variables:
      enable_spot_instances: true

source_connector: postgres
source_connector_path: /app/connectors/postgres.yaml
target_connector: iceberg
target_connector_path: /app/connectors/iceberg.yaml
asset: postgres_orders
asset_path: /app/assets/postgres/v1.0/db_orders.yaml
```

### 2. Initialize Infrastructure Manager in Code

```python
from dativo_ingest.cloud_infrastructure import (
    AWSInfrastructureManager,
    GCPInfrastructureManager
)
from dativo_ingest.config import JobConfig, AssetDefinition

# Load configuration
job_config = JobConfig.from_yaml("jobs/acme/postgres_orders.yaml")
asset = AssetDefinition.from_yaml(job_config.get_asset_path())

# Choose manager based on provider
if job_config.infrastructure.provider == "terraform":
    # Determine cloud from platform or explicit configuration
    platform = job_config.infrastructure.runtime.platform
    
    if platform in ["emr", "ecs", "fargate"]:
        manager = AWSInfrastructureManager(job_config, asset)
    elif platform in ["gke", "kubernetes", "dataproc"]:
        manager = GCPInfrastructureManager(job_config, asset)
    
    # Validate infrastructure
    manager.validate_infrastructure()
    
    # Generate Terraform variables
    tfvars_path = "terraform/aws/emr-dativo/dativo.auto.tfvars"
    manager.generate_terraform_tfvars(tfvars_path)
    
    # Apply tags to existing resources
    manager.apply_all_infrastructure_tags()
    
    # Export outputs
    manager.export_terraform_outputs("outputs/infrastructure.json")
```

### 3. Run Terraform

```bash
cd terraform/aws/emr-dativo

# Initialize
terraform init

# Select workspace
terraform workspace select prod

# Plan with generated variables
terraform plan

# Apply
terraform apply

# Export outputs
terraform output -json > outputs.json
export EMR_CLUSTER_ID=$(terraform output -raw emr_cluster_id)
```

### 4. Run Dativo Job

```bash
dativo run --config jobs/acme/postgres_orders.yaml --mode self_hosted
```

## Cost Allocation

### AWS Cost Explorer

Use FinOps tags for cost analysis:

```
Filter by:
- CostCenter: data-engineering
- Project: customer-analytics
- TenantId: acme
- Environment: prod
- Platform: emr
```

### GCP Cost Management

Use labels for billing export:

```sql
SELECT
  labels.key as label_key,
  labels.value as label_value,
  SUM(cost) as total_cost
FROM `project.dataset.gcp_billing_export`
WHERE labels.key IN ('costcenter', 'project', 'tenant_id')
GROUP BY label_key, label_value
```

## Compliance Tracking

### PII Detection

```python
# Find all resources with PII
tags = manager.context.classification_tags
if "ContainsPII" in tags and tags["ContainsPII"] == "true":
    print(f"Resource contains PII: {tags['DataClassification']}")
    print(f"Regulations: {tags['Regulations']}")
    print(f"Retention: {tags['RetentionDays']} days")
```

### Audit Trail

All infrastructure changes tracked via:
- CloudWatch (AWS) / Cloud Logging (GCP)
- Tags include LastModified timestamp
- Terraform state history
- Dativo execution logs

## Multi-Cloud Strategy

### Cloud-Agnostic Job Definition

Same job definition works on both AWS and GCP:

```yaml
infrastructure:
  provider: terraform
  runtime:
    platform: ${CLOUD_PLATFORM}  # emr or gke
    compute:
      cluster_id: ${CLUSTER_ID}
      instance_type: ${INSTANCE_TYPE}
    storage:
      bucket: ${DATA_BUCKET}
  metadata:
    tags:
      CostCenter: data-engineering
```

### Platform Selection

```bash
# AWS Deployment
export CLOUD_PLATFORM=emr
export CLUSTER_ID=$EMR_CLUSTER_ID
export INSTANCE_TYPE=r5.2xlarge
export DATA_BUCKET=s3://acme-data-lake

# GCP Deployment
export CLOUD_PLATFORM=gke
export CLUSTER_ID=$GKE_CLUSTER_NAME
export INSTANCE_TYPE=n2-standard-4
export DATA_BUCKET=gs://acme-data-lake
```

## Security

### Encryption

**AWS:**
- KMS encryption for EBS volumes
- S3 server-side encryption
- EMR encryption at rest and in transit

**GCP:**
- KMS encryption for GCS buckets
- GKE database encryption
- Disk encryption for nodes

### Network Security

**AWS:**
- Private subnets for EMR
- Security groups with minimal access
- VPC endpoints for AWS services

**GCP:**
- Private GKE nodes
- VPC firewall rules
- Private Google Access

### IAM / Service Accounts

**AWS:**
- Instance profiles with least privilege
- IAM roles for EMR
- S3 bucket policies

**GCP:**
- Service accounts with minimal permissions
- Workload Identity for GKE
- GCS IAM bindings

## Testing

### Unit Tests

```python
# tests/test_infrastructure.py
def test_tag_propagation():
    job_config = JobConfig.from_yaml("tests/fixtures/test_job.yaml")
    asset = AssetDefinition.from_yaml("tests/fixtures/test_asset.yaml")
    
    manager = AWSInfrastructureManager(job_config, asset)
    tags = manager.context.tags
    
    assert "TenantId" in tags
    assert "CostCenter" in tags
    assert "DataClassification" in tags
```

### Integration Tests

```bash
# Test AWS integration
pytest tests/integration/test_aws_infrastructure.py

# Test GCP integration
pytest tests/integration/test_gcp_infrastructure.py

# Test Terraform generation
pytest tests/integration/test_terraform_generation.py
```

## Monitoring

### AWS CloudWatch

```python
# Metrics published to CloudWatch
- dativo.infrastructure.tags_applied
- dativo.infrastructure.validation_duration
- dativo.infrastructure.terraform_apply_duration
```

### GCP Cloud Monitoring

```python
# Metrics published to Cloud Monitoring
- dativo/infrastructure/labels_applied
- dativo/infrastructure/validation_duration
- dativo/infrastructure/terraform_apply_duration
```

## Benefits

✅ **Cost Visibility**: FinOps tags enable accurate cost allocation  
✅ **Compliance**: Classification tags track PII, GDPR, retention  
✅ **Traceability**: Complete audit trail from job to resources  
✅ **Cloud-Agnostic**: Same job definition works on AWS/GCP  
✅ **Automation**: Terraform integration for IaC  
✅ **Security**: Encryption, network isolation, IAM best practices  
✅ **Governance**: ODCS integration for data contracts  

## Future Enhancements

- [ ] Azure support (AKS, Databricks)
- [ ] CloudFormation support
- [ ] Pulumi support
- [ ] Cost estimation before apply
- [ ] Policy enforcement (e.g., require encryption for PII)
- [ ] Automated cleanup of unused resources
- [ ] Multi-region deployment
- [ ] Disaster recovery configuration

## Related Documentation

- [INFRASTRUCTURE.md](docs/INFRASTRUCTURE.md) - Infrastructure configuration reference
- [CONFIG_REFERENCE.md](docs/CONFIG_REFERENCE.md) - Job configuration reference
- [SETUP_AND_ONBOARDING.md](docs/SETUP_AND_ONBOARDING.md) - Setup guide
- [terraform/aws/emr-dativo/README.md](terraform/aws/emr-dativo/README.md) - AWS module docs
