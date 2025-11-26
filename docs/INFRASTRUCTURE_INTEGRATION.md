# Infrastructure Integration Guide

This guide explains how to configure external infrastructure integration for Dativo ETL jobs, enabling cloud-agnostic deployment via Terraform with comprehensive tag propagation for cost allocation, compliance, and resource traceability.

## Overview

Dativo supports deploying ETL jobs on external infrastructure provisioned outside of the platform (e.g., via Terraform, CloudFormation, or manual setup). By adding an optional `infrastructure` block to your job configuration, you can:

1. **Reference existing infrastructure** - VPCs, subnets, IAM roles, service accounts, clusters
2. **Enable cloud-agnostic deployment** - Support for AWS (ECS, EKS) and GCP (GKE, Cloud Run)
3. **Propagate tags comprehensively** - Cost allocation, compliance, governance, and custom metadata flow through all layers
4. **Generate Terraform modules** - Automatically generate deployment configurations from job definitions

## Architecture

### Tag Propagation Hierarchy

Tags flow through multiple layers with the following precedence (highest to lowest):

1. **Infrastructure tags** (`infrastructure.tags`) - HIGHEST priority
2. **Job config tags** (`finops`, `governance_overrides`)
3. **Asset definition tags** (from ODCS schema)
4. **Source system tags** (from connector metadata) - LOWEST priority

### Infrastructure Components

The infrastructure block supports:

- **Compute** - ECS, EKS (AWS), GKE, Cloud Run (GCP)
- **Network** - VPC, subnets, security groups
- **Storage** - S3 (AWS), GCS (GCP), KMS encryption
- **Monitoring** - CloudWatch (AWS), Cloud Logging (GCP)
- **Tags** - Cost center, project, environment, compliance, custom tags

## Configuration

### Infrastructure Block Structure

```yaml
infrastructure:
  provider: aws | gcp
  region: <cloud-region>
  
  compute:
    type: ecs | eks | gke | cloud_run
    cluster_name: <cluster-name>
    task_cpu: <cpu-units>
    task_memory: <memory-mb>
    execution_role_arn: <iam-role-arn>  # AWS only
    task_role_arn: <iam-role-arn>       # AWS only
    service_account: <sa-email>         # GCP only
  
  network:
    vpc_id: <vpc-id>
    subnets:
      - <subnet-id-1>
      - <subnet-id-2>
    security_groups:  # AWS only
      - <sg-id-1>
  
  storage:
    bucket: <bucket-name>
    kms_key_id: <kms-key-id-or-arn>
  
  tags:
    cost_center: <cost-center-code>
    project: <project-name>
    environment: <env-name>
    owner: <owner-email>
    compliance:
      - <compliance-framework-1>
      - <compliance-framework-2>
    # ... additional custom tags
  
  monitoring:
    log_group: <log-group-path>
    metrics_namespace: <metrics-namespace>
    alert_topic_arn: <sns-topic-arn>  # AWS only
    alert_topic: <pubsub-topic>       # GCP only
```

### Required Fields

- `provider` - Cloud provider (`aws` or `gcp`)
- `region` - Cloud region (e.g., `us-east-1`, `us-central1`)

All other fields are optional but recommended for production deployments.

## AWS Deployment Examples

### AWS ECS (Fargate)

```yaml
tenant_id: acme_corp
environment: prod

source_connector_path: connectors/stripe.yaml
target_connector_path: connectors/iceberg.yaml
asset_path: assets/stripe/v1.0/customers.yaml

infrastructure:
  provider: aws
  region: us-east-1
  
  compute:
    type: ecs
    cluster_name: dativo-prod-cluster
    task_cpu: "1024"
    task_memory: "2048"
    execution_role_arn: "arn:aws:iam::123456789012:role/dativo-ecs-execution-role"
    task_role_arn: "arn:aws:iam::123456789012:role/dativo-ecs-task-role"
  
  network:
    vpc_id: "vpc-0abc123def456"
    subnets:
      - "subnet-0abc123def456"
      - "subnet-0def456abc123"
    security_groups:
      - "sg-0abc123def456"
  
  storage:
    bucket: "acme-corp-data-lake-prod"
    kms_key_id: "arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-123456789012"
  
  tags:
    cost_center: "CC-PAYMENTS-001"
    project: "data-platform"
    environment: "prod"
    owner: "data-platform-team@acme.com"
    compliance:
      - PCI-DSS
      - SOC2
  
  monitoring:
    log_group: "/ecs/dativo/acme-corp-prod"
    metrics_namespace: "Dativo/ETL"
    alert_topic_arn: "arn:aws:sns:us-east-1:123456789012:dativo-alerts"
```

### AWS EKS (Kubernetes)

```yaml
infrastructure:
  provider: aws
  region: us-west-2
  
  compute:
    type: eks
    cluster_name: techco-staging-eks
    task_cpu: "2048"
    task_memory: "4096"
    execution_role_arn: "arn:aws:iam::987654321098:role/techco-eks-execution-role"
    task_role_arn: "arn:aws:iam::987654321098:role/techco-eks-pod-role"
  
  network:
    vpc_id: "vpc-0xyz789abc123"
    subnets:
      - "subnet-0xyz789abc123"
      - "subnet-0abc123xyz789"
    security_groups:
      - "sg-0xyz789abc123"
  
  tags:
    cost_center: "CC-ENGINEERING-003"
    kubernetes_cluster: "techco-staging-eks"
```

## GCP Deployment Examples

### GCP Cloud Run

```yaml
tenant_id: acme_corp
environment: prod

source_connector_path: connectors/hubspot.yaml
target_connector_path: connectors/iceberg.yaml
asset_path: assets/hubspot/v1.0/contacts.yaml

infrastructure:
  provider: gcp
  region: us-central1
  
  compute:
    type: cloud_run
    task_cpu: "1000m"
    task_memory: "2048"
    service_account: "dativo-etl@acme-prod.iam.gserviceaccount.com"
  
  network:
    vpc_id: "projects/acme-prod/global/networks/dativo-vpc"
    subnets:
      - "projects/acme-prod/regions/us-central1/subnetworks/dativo-subnet-1"
  
  storage:
    bucket: "acme-corp-data-lake-prod"
    kms_key_id: "projects/acme-prod/locations/us-central1/keyRings/dativo/cryptoKeys/etl-data"
  
  tags:
    cost_center: "CC-MARKETING-002"
    project: "crm-analytics"
    environment: "prod"
    owner: "marketing-analytics@acme.com"
    compliance:
      - GDPR
      - CCPA
  
  monitoring:
    log_group: "projects/acme-prod/logs/dativo-etl"
    metrics_namespace: "custom.googleapis.com/dativo/etl"
    alert_topic: "projects/acme-prod/topics/dativo-alerts"
```

### GCP GKE (Kubernetes)

```yaml
infrastructure:
  provider: gcp
  region: europe-west1
  
  compute:
    type: gke
    cluster_name: dativo-prod-gke
    task_cpu: "2000m"
    task_memory: "4096"
    service_account: "dativo-etl@company-prod.iam.gserviceaccount.com"
  
  network:
    vpc_id: "projects/company-prod/global/networks/prod-vpc"
    subnets:
      - "projects/company-prod/regions/europe-west1/subnetworks/gke-subnet"
  
  tags:
    cost_center: "CC-DATA-PLATFORM"
    kubernetes_cluster: "dativo-prod-gke"
```

## Terraform Generation

Dativo can automatically generate Terraform modules from job configurations with infrastructure blocks.

### Generate Terraform Module

```python
from dativo_ingest.config import JobConfig
from dativo_ingest.terraform_generator import generate_terraform_for_job
from pathlib import Path

# Load job configuration
job_config = JobConfig.from_yaml("jobs/acme_corp/stripe_customers.yaml")

# Generate Terraform module
output_dir = Path("terraform/acme_corp")
generate_terraform_for_job(job_config, output_dir)
```

This generates:
- `main.tf` - Infrastructure resources (ECS task definition, Cloud Run service, etc.)
- `variables.tf` - Input variables
- `terraform.tfvars.json` - Variable values from job config
- `outputs.tf` - Output values

### Generated Terraform Structure

```
terraform/
└── acme_corp/
    ├── main.tf              # Infrastructure resources
    ├── variables.tf         # Variable declarations
    ├── terraform.tfvars.json # Variable values
    └── outputs.tf           # Output values
```

### Deploy with Terraform

```bash
cd terraform/acme_corp

# Initialize Terraform
terraform init

# Plan deployment
terraform plan

# Apply deployment
terraform apply

# View outputs
terraform output
```

## Tag Propagation

### Tag Hierarchy

Tags are merged with the following precedence:

1. **Infrastructure tags** - Highest priority, defined in `infrastructure.tags`
2. **FinOps tags** - Defined in `finops` section of job config
3. **Governance tags** - Derived from asset definition (`team.owner`, `compliance`, etc.)
4. **Default tags** - Automatically added (`tenant_id`, `managed_by`, etc.)

### Tag Namespaces

Tags are propagated to Iceberg table properties with namespaces:

- `infrastructure.*` - Infrastructure tags (cost_center, environment, compliance)
- `finops.*` - FinOps tags (cost_center, project, business_tags)
- `governance.*` - Governance tags (owner, retention_days, domain)
- `classification.*` - Data classification tags

### Example Tag Propagation

Job configuration:
```yaml
tenant_id: acme_corp
environment: prod

finops:
  cost_center: "CC-001"
  project: "data-platform"

infrastructure:
  tags:
    cost_center: "CC-INFRA-999"  # Overrides finops.cost_center
    environment: "production"
    compliance:
      - PCI-DSS
      - SOC2
```

Resulting Iceberg table properties:
```
infrastructure.cost_center = "CC-INFRA-999"  # From infrastructure.tags (highest priority)
infrastructure.environment = "production"
infrastructure.compliance = "PCI-DSS,SOC2"
finops.cost_center = "CC-INFRA-999"         # Overridden by infrastructure.tags
finops.project = "data-platform"
governance.owner = "data-team@acme.com"     # From asset definition
```

## Cost Allocation

Infrastructure tags enable precise cost allocation:

1. **Cost Centers** - Tag resources with cost centers for chargeback
2. **Projects** - Track spending by project or initiative
3. **Environments** - Separate dev, staging, and production costs
4. **Business Tags** - Custom tags for business unit allocation

### AWS Cost Allocation Tags

Enable cost allocation tags in AWS Cost Explorer:
1. Go to AWS Billing Console
2. Select "Cost Allocation Tags"
3. Activate tags: `cost_center`, `project`, `environment`, `owner`

### GCP Labels for Billing

Labels automatically appear in GCP Billing reports:
- View in BigQuery: `billing_export` dataset
- Filter by labels in Cost Management dashboard

## Compliance Tracking

Infrastructure tags support compliance requirements:

### Compliance Tags

```yaml
infrastructure:
  tags:
    compliance:
      - GDPR
      - HIPAA
      - SOC2
      - PCI-DSS
    data_residency: "EU"
    encryption_required: "true"
```

### Audit Trail

All tags are:
1. Propagated to Iceberg table properties
2. Applied to cloud infrastructure resources
3. Logged in deployment metadata
4. Tracked in Terraform state

## Best Practices

### 1. Use Externally Provisioned Infrastructure

Provision infrastructure separately from job deployment:
- **Terraform** - Manage VPCs, IAM roles, clusters via separate Terraform root modules
- **CloudFormation** - Use AWS CloudFormation stacks for infrastructure
- **Manual** - Create resources manually and reference IDs/ARNs in job configs

### 2. Standardize Tag Taxonomy

Define organization-wide tag standards:
```yaml
# Required tags for all infrastructure
tags:
  cost_center: "CC-XXX-NNN"      # Format: CC-<dept>-<number>
  project: "project-name"
  environment: "dev|staging|prod"
  owner: "team@company.com"
  
# Optional compliance tags
  compliance: [...]
  data_classification: "public|internal|confidential|restricted"
```

### 3. Separate Environments

Use different infrastructure blocks per environment:
```yaml
# jobs/acme_corp/stripe_prod.yaml
infrastructure:
  provider: aws
  region: us-east-1
  compute:
    cluster_name: dativo-prod-cluster
  tags:
    environment: "prod"
    cost_center: "CC-PROD-001"

# jobs/acme_corp/stripe_staging.yaml
infrastructure:
  provider: aws
  region: us-east-1
  compute:
    cluster_name: dativo-staging-cluster
  tags:
    environment: "staging"
    cost_center: "CC-NONPROD-001"
```

### 4. Enable Encryption

Always specify KMS keys for encryption:
```yaml
storage:
  bucket: "data-lake-prod"
  kms_key_id: "arn:aws:kms:us-east-1:123456789012:key/..."
```

### 5. Configure Monitoring

Set up comprehensive monitoring:
```yaml
monitoring:
  log_group: "/ecs/dativo/tenant-env"
  metrics_namespace: "Dativo/ETL"
  alert_topic_arn: "arn:aws:sns:region:account:alerts"
```

## CLI Integration

### Generate Terraform for Single Job

```bash
# Generate Terraform module from job config
python -m dativo_ingest.cli generate-terraform \
  --config jobs/acme_corp/stripe_customers.yaml \
  --output terraform/acme_corp
```

### Generate Terraform for All Jobs

```bash
# Generate Terraform modules for all jobs in directory
python -m dativo_ingest.cli generate-terraform \
  --job-dir jobs/acme_corp \
  --output terraform
```

### View Infrastructure Configuration

```bash
# Display infrastructure config for job
python -m dativo_ingest.cli show-infrastructure \
  --config jobs/acme_corp/stripe_customers.yaml
```

## Dagster Integration

Infrastructure metadata flows into Dagster for orchestration:

### Asset Tags

Infrastructure tags are added to Dagster asset metadata:
```python
@asset(
    tags={
        "tenant": "acme_corp",
        "environment": "prod",
        "cost_center": "CC-PAYMENTS-001",
        "compliance": "PCI-DSS,SOC2"
    }
)
def stripe_customers():
    ...
```

### Run Queue Configuration

Use infrastructure tags for run queue management:
```yaml
# dagster.yaml
run_queue:
  max_concurrent_runs: 10
  tag_concurrency_limits:
    - key: "cost_center"
      value: "CC-PAYMENTS-001"
      limit: 2
```

## Troubleshooting

### Infrastructure Validation Errors

**Error**: `Invalid compute type 'ecs' for GCP`
- **Solution**: Ensure compute type matches provider (AWS: ecs/eks, GCP: gke/cloud_run)

**Error**: `Missing required field: provider`
- **Solution**: Add `provider: aws` or `provider: gcp` to infrastructure block

### Tag Propagation Issues

**Issue**: Tags not appearing in Iceberg table properties
- **Check**: Verify infrastructure block exists in job config
- **Check**: Ensure tags are valid (no special characters in keys)
- **Check**: Verify tag derivation with `derive_tags_from_asset()`

### Terraform Generation Errors

**Error**: `Job configuration must include infrastructure block`
- **Solution**: Add infrastructure block to job config before generating Terraform

**Error**: `Invalid provider: xyz`
- **Solution**: Provider must be `aws` or `gcp`

## Security Considerations

1. **IAM Roles/Service Accounts** - Use least-privilege principles
2. **KMS Encryption** - Always encrypt data at rest
3. **Network Isolation** - Deploy in private subnets with security groups
4. **Secret Management** - Never store credentials in infrastructure blocks
5. **Audit Logging** - Enable CloudTrail (AWS) or Cloud Audit Logs (GCP)

## Related Documentation

- [Config Reference](CONFIG_REFERENCE.md) - Complete job configuration reference
- [Tag Propagation](TAG_PROPAGATION.md) - Detailed tag propagation mechanics
- [Secret Management](SECRET_MANAGEMENT.md) - Credential management guide
- [Deployment Guide](DEPLOYMENT.md) - Production deployment best practices

## Examples

See complete examples in `examples/jobs/`:
- `aws_ecs_example.yaml` - AWS ECS deployment
- `aws_eks_example.yaml` - AWS EKS deployment
- `gcp_cloud_run_example.yaml` - GCP Cloud Run deployment
- `gcp_gke_example.yaml` - GCP GKE deployment
