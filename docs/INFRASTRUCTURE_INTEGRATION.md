# Infrastructure Integration for Cloud Deployment

This guide describes how to integrate Dativo ETL jobs with external cloud infrastructure provisioned via Terraform, enabling cloud-agnostic deployment with comprehensive tag propagation for cost allocation, compliance, and resource traceability.

## Table of Contents

1. [Overview](#overview)
2. [Key Features](#key-features)
3. [Architecture](#architecture)
4. [Configuration](#configuration)
5. [Tag Propagation](#tag-propagation)
6. [Terraform Modules](#terraform-modules)
7. [Deployment Workflow](#deployment-workflow)
8. [Cloud Provider Support](#cloud-provider-support)
9. [Best Practices](#best-practices)
10. [Troubleshooting](#troubleshooting)

---

## Overview

The Infrastructure Integration feature allows Dativo ETL jobs to reference and utilize infrastructure provisioned outside of the Dativo platform (e.g., via Terraform). This enables:

- **Cloud-agnostic deployment**: Deploy jobs to AWS, GCP, or Azure using consistent configuration
- **External orchestration**: Integrate with Dagster, Airflow, or Kubernetes
- **Comprehensive tagging**: Automatic tag/label propagation for cost allocation and compliance
- **Infrastructure as Code**: Manage job infrastructure alongside application infrastructure
- **Separation of concerns**: Job logic and infrastructure provisioned separately

## Key Features

### 1. Cloud-Agnostic Configuration

Define infrastructure requirements once, deploy to any cloud:

```yaml
infrastructure:
  provider: aws  # or gcp, azure
  runtime:
    type: ecs  # or cloud_run, kubernetes, dagster
    compute:
      cpu: "2048"
      memory: "4096"
```

### 2. Comprehensive Tag Propagation

Tags automatically flow from multiple sources:

- **Infrastructure tags**: Cost center, business unit, project
- **Job metadata**: Tenant ID, environment, asset name
- **Asset tags**: Data classification, compliance requirements, governance
- **System tags**: Managed by, Terraform metadata

### 3. Terraform Integration

Generate Terraform variables automatically from job configuration:

```python
infra_config.export_terraform_vars(
    output_path="terraform.tfvars.json",
    job_config=job_config,
    asset_tags=asset_tags
)
```

### 4. Multi-Runtime Support

Support for multiple orchestration platforms:

- **Dagster**: Serverless orchestration on ECS/Cloud Run
- **Airflow**: DAG-based scheduling
- **Kubernetes**: Container orchestration
- **ECS/Cloud Run**: Native cloud services

---

## Architecture

### Component Interaction

```
┌─────────────────────────────────────────────────────────────┐
│                  Dativo Job Configuration                   │
│  (jobs/acme/stripe_customers_to_iceberg.yaml)              │
│                                                             │
│  infrastructure:                                            │
│    provider: aws                                            │
│    runtime: { type: ecs, compute: {...} }                  │
│    tags: { cost_center, compliance, ... }                  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│         Python Infrastructure Module                        │
│  (src/dativo_ingest/infrastructure.py)                     │
│                                                             │
│  • Validates infrastructure config                          │
│  • Loads asset tags from tag_derivation module             │
│  • Merges tags from all sources                            │
│  • Generates Terraform variables                           │
│  • Exports terraform.tfvars.json                           │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Terraform Module (AWS/GCP)                     │
│  (terraform/aws/main.tf or terraform/gcp/main.tf)         │
│                                                             │
│  • Provisions compute resources (ECS/Cloud Run)            │
│  • Creates IAM roles and policies                          │
│  • Sets up monitoring and logging                          │
│  • Applies tags to all resources                           │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  Cloud Resources                            │
│                                                             │
│  AWS:                          GCP:                         │
│  • ECS Cluster/Task           • Cloud Run Job              │
│  • IAM Roles                  • Service Account            │
│  • CloudWatch Logs            • Cloud Logging              │
│  • Security Groups            • IAM Bindings               │
│                                                             │
│  All tagged with cost allocation and compliance metadata   │
└─────────────────────────────────────────────────────────────┘
```

---

## Configuration

### Infrastructure Block Schema

Add an `infrastructure` block to your job configuration:

```yaml
infrastructure:
  # Required
  provider: aws | gcp | azure
  
  runtime:
    type: dagster | ecs | cloud_run | kubernetes | airflow
    compute:
      cpu: string
      memory: string
      disk_size: string
      instance_type: string  # AWS-specific
    scaling:
      min_instances: number
      max_instances: number
      target_cpu_utilization: number
    timeout_seconds: number
  
  # Optional
  networking:
    vpc_id: string
    subnet_ids: [string]
    security_group_ids: [string]
    private_access: boolean
  
  storage:
    state_bucket: string
    data_bucket: string
    encryption:
      enabled: boolean
      kms_key_id: string
  
  tags:
    cost_center: string
    business_unit: string
    project: string
    environment: dev | staging | prod
    owner: string
    compliance: [string]
    data_classification: string
    custom:
      key: value
  
  terraform:
    module_source: string
    module_version: string
    backend:
      type: s3 | gcs | azurerm
      config: object
    variables: object
  
  monitoring:
    enabled: boolean
    metrics_namespace: string
    log_group: string
    alerts:
      channels: [string]
      thresholds: object
```

### Minimal Example

```yaml
infrastructure:
  provider: aws
  runtime:
    type: ecs
    compute:
      cpu: "1024"
      memory: "2048"
  storage:
    state_bucket: dativo-state-acme
    data_bucket: dativo-data-acme
  tags:
    cost_center: DATA-001
    owner: data-team@acme.com
```

### Complete Example

See `examples/jobs/aws_stripe_customers_to_iceberg.yaml` for a comprehensive example.

---

## Tag Propagation

### Tag Sources and Priority

Tags are merged from multiple sources in this order (later overrides earlier):

1. **Infrastructure Tags** (from `infrastructure.tags`)
2. **Job Metadata** (from job config: `tenant_id`, `environment`, `asset`)
3. **Asset Tags** (from asset schema via `tag_derivation` module)
4. **System Tags** (automatically added: `ManagedBy`, `Terraform`)

### Tag Namespaces

Different tag types use different namespaces:

| Namespace | Description | Example Keys |
|-----------|-------------|--------------|
| Infrastructure | Cost and organization | `CostCenter`, `BusinessUnit`, `Project`, `Owner` |
| Job Metadata | Job identification | `TenantId`, `Asset`, `SourceConnector`, `JobName` |
| Classification | Data sensitivity | `Classification_default`, `Classification_fields_email` |
| Governance | Compliance | `Governance_retention_days`, `Governance_regulations` |
| FinOps | Cost attribution | `FinOps_cost_center`, `FinOps_project` |
| System | Platform metadata | `ManagedBy`, `Terraform`, `Module`, `RuntimeType` |

### Tag Normalization

Tags are automatically normalized for cloud provider requirements:

**AWS:**
- Tags remain as-is (PascalCase)
- Example: `CostCenter`, `BusinessUnit`

**GCP:**
- Labels converted to lowercase with underscores
- Example: `costcenter`, `businessunit`

**Azure:**
- Tags remain as-is (similar to AWS)

### Example Tag Propagation

**Job Configuration:**
```yaml
tenant_id: acme
environment: prod
asset: stripe_customers

infrastructure:
  tags:
    cost_center: FIN-001
    business_unit: Finance
    compliance: [GDPR, SOC2]
```

**Asset Schema:**
```yaml
compliance:
  classification: [PII]
  retention_days: 365

finops:
  cost_center: FIN-001
  project: data-platform
```

**Generated Tags:**
```json
{
  "CostCenter": "FIN-001",
  "BusinessUnit": "Finance",
  "Compliance": "GDPR,SOC2",
  "TenantId": "acme",
  "Environment": "prod",
  "Asset": "stripe_customers",
  "Classification_default": "pii",
  "Governance_retention_days": "365",
  "FinOps_cost_center": "FIN-001",
  "FinOps_project": "data-platform",
  "ManagedBy": "dativo",
  "Terraform": "true",
  "Module": "dativo-etl-job"
}
```

---

## Terraform Modules

### AWS Module

**Location:** `terraform/aws/`

**Resources:**
- ECS Cluster and Task Definition
- IAM Roles and Policies
- Security Groups
- CloudWatch Log Groups
- CloudWatch Alarms

**Usage:**
```bash
cd terraform/aws
terraform init
terraform plan -var-file=terraform.tfvars.json
terraform apply -var-file=terraform.tfvars.json
```

See [terraform/aws/README.md](../terraform/aws/README.md) for details.

### GCP Module

**Location:** `terraform/gcp/`

**Resources:**
- Cloud Run Job
- Service Account
- IAM Bindings
- Cloud Logging Sink
- Alert Policies

**Usage:**
```bash
cd terraform/gcp
terraform init
terraform plan -var-file=terraform.tfvars.json -var="project_id=my-project"
terraform apply -var-file=terraform.tfvars.json -var="project_id=my-project"
```

See [terraform/gcp/README.md](../terraform/gcp/README.md) for details.

---

## Deployment Workflow

### 1. Define Job Configuration

Create job configuration with infrastructure block:

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

infrastructure:
  provider: aws
  runtime:
    type: ecs
    compute:
      cpu: "2048"
      memory: "4096"
  # ... rest of configuration
```

### 2. Validate Configuration

```python
from dativo_ingest.config import JobConfig
from dativo_ingest.infrastructure import load_infrastructure_config, validate_infrastructure_for_job

# Load job config
job_config = JobConfig.from_yaml("jobs/acme/stripe_customers_to_iceberg.yaml")

# Load and validate infrastructure config
infra_config = load_infrastructure_config(job_config.infrastructure)
validate_infrastructure_for_job(job_config, infra_config)
```

### 3. Generate Terraform Variables

```python
from dativo_ingest.tag_derivation import derive_tags_from_asset
from pathlib import Path

# Derive asset tags
asset = job_config.get_asset()
asset_tags = derive_tags_from_asset(asset)

# Export Terraform variables
output_path = Path("terraform/aws/terraform.tfvars.json")
infra_config.export_terraform_vars(
    output_path=output_path,
    job_config=job_config,
    asset_tags=asset_tags,
    format="json"
)
```

### 4. Apply Terraform

```bash
cd terraform/aws
terraform init
terraform plan -var-file=terraform.tfvars.json
terraform apply -var-file=terraform.tfvars.json
```

### 5. Deploy Job

Once infrastructure is provisioned, deploy the job using Dagster or your orchestration platform.

---

## Cloud Provider Support

### AWS

**Supported Runtimes:**
- ECS Fargate
- Dagster on ECS
- Kubernetes (EKS)

**Key Features:**
- VPC networking with private subnets
- S3 storage with KMS encryption
- CloudWatch logging and monitoring
- IAM roles with least-privilege permissions

**Example:**
```yaml
infrastructure:
  provider: aws
  runtime:
    type: ecs
    compute:
      cpu: "2048"
      memory: "4096"
  networking:
    vpc_id: vpc-12345678
    subnet_ids: [subnet-12345678, subnet-87654321]
    private_access: true
```

### GCP

**Supported Runtimes:**
- Cloud Run Jobs
- Dagster on Cloud Run
- Kubernetes (GKE)
- Cloud Functions

**Key Features:**
- VPC networking with Private Google Access
- GCS storage with Cloud KMS encryption
- Cloud Logging and Cloud Monitoring
- Service accounts with IAM bindings

**Example:**
```yaml
infrastructure:
  provider: gcp
  runtime:
    type: cloud_run
    compute:
      cpu: "2"
      memory: "4Gi"
  networking:
    vpc_id: projects/my-project/locations/us-central1/connectors/my-vpc-connector
    private_access: true
```

### Azure (Coming Soon)

Azure support is planned for a future release.

---

## Best Practices

### 1. Tag Governance

**Always specify these tags:**
- `cost_center`: For cost allocation
- `owner`: For ownership tracking
- `environment`: For environment segregation
- `project`: For project tracking

```yaml
infrastructure:
  tags:
    cost_center: DATA-001
    owner: data-team@acme.com
    environment: prod
    project: data-platform
```

### 2. Compliance Tags

**Include compliance metadata:**
- `compliance`: List of regulatory requirements
- `data_classification`: Data sensitivity level

```yaml
infrastructure:
  tags:
    compliance: [GDPR, SOC2, PCI-DSS]
    data_classification: Confidential
```

### 3. Security

**Enable encryption:**
```yaml
infrastructure:
  storage:
    encryption:
      enabled: true
      kms_key_id: arn:aws:kms:...
```

**Use private networking:**
```yaml
infrastructure:
  networking:
    private_access: true
```

### 4. Monitoring

**Enable comprehensive monitoring:**
```yaml
infrastructure:
  monitoring:
    enabled: true
    alerts:
      channels: [arn:aws:sns:us-east-1:123456789012:alerts]
      thresholds:
        error_rate: 5
        timeout_rate: 2
```

### 5. Resource Sizing

**Start small, scale up:**
```yaml
infrastructure:
  runtime:
    compute:
      cpu: "1024"    # Start with 1 vCPU
      memory: "2048"  # 2 GB
    scaling:
      min_instances: 1
      max_instances: 5
```

### 6. Terraform State Management

**Use remote state:**
```yaml
infrastructure:
  terraform:
    backend:
      type: s3
      config:
        bucket: terraform-state
        key: dativo/jobs/my-job.tfstate
        region: us-east-1
        encrypt: true
```

---

## Troubleshooting

### Configuration Validation Warnings

**Problem:**
```
Infrastructure configuration warning: No cost_center tag specified
Infrastructure configuration warning: No owner tag specified
```

**Solution:**
Add required tags to your job configuration:
```yaml
infrastructure:
  tags:
    cost_center: YOUR-COST-CENTER
    owner: your-team@company.com
    environment: prod
```

### Tag Propagation Issues

**Problem:** Tags not appearing on cloud resources

**Solution:**
1. Verify tags are defined in job configuration
2. Check Terraform apply output for tag creation
3. Query cloud resources:
   ```bash
   # AWS
   aws ecs describe-clusters --clusters CLUSTER_NAME --include TAGS
   
   # GCP
   gcloud run jobs describe JOB_NAME --format="value(metadata.labels)"
   ```

### Networking Issues

**Problem:** Job cannot access VPC resources

**Solution (AWS):**
1. Verify VPC and subnet IDs are correct
2. Check security group rules
3. Ensure private subnets have NAT gateway for egress

**Solution (GCP):**
1. Verify VPC connector exists in same region
2. Check VPC connector has sufficient capacity
3. Verify private Google access is enabled

### Storage Access Issues

**Problem:** Job cannot access S3/GCS buckets

**Solution (AWS):**
1. Verify IAM role has S3 permissions
2. Check bucket policy allows access
3. Verify KMS key permissions (if encryption enabled)

**Solution (GCP):**
1. Verify service account has Storage Object Admin role
2. Check bucket IAM bindings
3. Verify Cloud KMS permissions (if encryption enabled)

### Terraform Apply Failures

**Problem:** Terraform apply fails with permission errors

**Solution:**
1. Ensure Terraform has sufficient permissions
2. Check AWS/GCP credentials are configured
3. Verify Terraform backend is accessible
4. Review Terraform state lock status

### Cost Tracking Issues

**Problem:** Cannot track costs by tag

**Solution:**
1. Enable cost allocation tags in AWS Cost Explorer
2. Enable billing export to BigQuery (GCP)
3. Wait 24 hours for tags to propagate
4. Verify tags are applied to resources

---

## Examples

See `examples/jobs/` for complete examples:

- **AWS ECS:** `aws_stripe_customers_to_iceberg.yaml`
- **GCP Cloud Run:** `gcp_hubspot_contacts_to_iceberg.yaml`
- **AWS Dagster:** `aws_dagster_mysql_to_iceberg.yaml`

---

## API Reference

### Python Infrastructure Module

```python
from dativo_ingest.infrastructure import (
    InfrastructureConfig,
    load_infrastructure_config,
    validate_infrastructure_for_job
)

# Load infrastructure configuration
infra_config = load_infrastructure_config(config_dict)

# Validate configuration
validate_infrastructure_for_job(job_config, infra_config)

# Generate Terraform variables
tf_vars = infra_config.generate_terraform_vars(
    job_config=job_config,
    asset_tags=asset_tags
)

# Export to file
infra_config.export_terraform_vars(
    output_path=Path("terraform.tfvars.json"),
    job_config=job_config,
    asset_tags=asset_tags,
    format="json"  # or "tfvars"
)
```

### CLI Usage

```bash
# Generate Terraform variables from job config
dativo infra generate-tfvars \
  --job-config jobs/acme/stripe_customers.yaml \
  --output terraform/aws/terraform.tfvars.json

# Validate infrastructure configuration
dativo infra validate \
  --job-config jobs/acme/stripe_customers.yaml

# Export tag report
dativo infra tag-report \
  --job-config jobs/acme/stripe_customers.yaml \
  --output tags-report.json
```

---

## References

- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [Terraform GCP Provider](https://registry.terraform.io/providers/hashicorp/google/latest/docs)
- [AWS Tagging Best Practices](https://docs.aws.amazon.com/general/latest/gr/aws_tagging.html)
- [GCP Labeling Resources](https://cloud.google.com/resource-manager/docs/creating-managing-labels)
- [Tag Propagation Documentation](TAG_PROPAGATION.md)
- [Dagster Cloud](https://docs.dagster.io/dagster-cloud)

---

## License

Apache 2.0 - See LICENSE file for details
