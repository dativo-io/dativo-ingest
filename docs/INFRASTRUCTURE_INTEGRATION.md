# Infrastructure Integration Guide

This guide explains how to integrate Dativo ETL jobs with external infrastructure provisioned via Terraform for AWS and GCP deployments.

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Job Configuration](#job-configuration)
4. [Tag Propagation](#tag-propagation)
5. [AWS Deployment](#aws-deployment)
6. [GCP Deployment](#gcp-deployment)
7. [Generating Terraform Configurations](#generating-terraform-configurations)
8. [Cost Allocation](#cost-allocation)
9. [Compliance and Resource Traceability](#compliance-and-resource-traceability)
10. [Best Practices](#best-practices)

---

## Overview

Dativo supports cloud-agnostic infrastructure deployment via Terraform, enabling you to:

- **Provision infrastructure** for ETL jobs on AWS (ECS Fargate, Lambda) or GCP (Cloud Run, Cloud Functions)
- **Propagate tags** automatically from job definitions and asset metadata to infrastructure resources
- **Track costs** with FinOps tags for accurate cost allocation
- **Ensure compliance** with regulatory tags and resource traceability
- **Maintain consistency** across cloud providers with unified configuration

### Architecture

```
Job Definition (YAML)
    ↓
Infrastructure Block (runtime + metadata)
    ↓
Asset Definition (finops, compliance, team)
    ↓
Tag Extraction Module
    ↓
Terraform Generator
    ↓
Cloud Resources (AWS/GCP) with Tags
```

---

## Quick Start

### 1. Add Infrastructure Block to Job Definition

```yaml
# jobs/acme/hubspot_contacts.yaml
tenant_id: acme
environment: prod

source_connector_path: connectors/hubspot.yaml
target_connector_path: connectors/iceberg.yaml
asset_path: assets/hubspot/v1.0/contacts.yaml

# Infrastructure configuration
infrastructure:
  runtime:
    type: "aws_ecs_fargate"  # or "gcp_cloud_run"
    cpu: 1024
    memory: 2048
    image_uri: "dativo/dativo-ingest:latest"
  metadata:
    terraform_workspace: "prod"
    cost_center: "ENG-001"
```

### 2. Generate Terraform Configuration

```bash
# Generate AWS Terraform config
python3 scripts/generate_terraform.py \
  jobs/acme/hubspot_contacts.yaml \
  --cloud aws \
  --resource-type ecs_fargate \
  --output-dir terraform/generated

# Generate GCP Terraform config
python3 scripts/generate_terraform.py \
  jobs/acme/hubspot_contacts.yaml \
  --cloud gcp \
  --resource-type cloud_run \
  --output-dir terraform/generated
```

### 3. Deploy with Terraform

```bash
cd terraform/generated
terraform init
terraform plan
terraform apply
```

---

## Job Configuration

### Infrastructure Block Structure

The `infrastructure` block in job definitions has two main sections:

```yaml
infrastructure:
  runtime:
    # Runtime environment configuration
    type: "aws_ecs_fargate"  # or "gcp_cloud_run", "aws_lambda", "gcp_cloud_function"
    cpu: 1024                 # CPU units (AWS) or allocation (GCP)
    memory: 2048              # Memory in MB (AWS) or allocation like "2Gi" (GCP)
    image_uri: "dativo/dativo-ingest:latest"
    timeout: 3600             # Timeout in seconds
    region: "us-east-1"       # Cloud region
  
  metadata:
    # Additional metadata for Terraform
    terraform_workspace: "prod"
    cost_center: "ENG-001"    # Override asset-level cost center
    environment: "production"
```

### Runtime Configuration

#### AWS ECS Fargate

```yaml
infrastructure:
  runtime:
    type: "aws_ecs_fargate"
    cpu: 1024        # 1024 = 1 vCPU, 2048 = 2 vCPU, etc.
    memory: 2048     # Memory in MB
    image_uri: "dativo/dativo-ingest:latest"
```

#### AWS Lambda

```yaml
infrastructure:
  runtime:
    type: "aws_lambda"
    timeout: 900     # Maximum 15 minutes
    memory: 2048     # Memory in MB (128-10240)
    image_uri: "dativo/dativo-ingest:latest"
```

#### GCP Cloud Run

```yaml
infrastructure:
  runtime:
    type: "gcp_cloud_run"
    cpu: "1"         # CPU allocation
    memory: "2Gi"    # Memory allocation
    image_uri: "gcr.io/dativo/dativo-ingest:latest"
    region: "us-central1"
    timeout: 3600    # Timeout in seconds
```

#### GCP Cloud Function

```yaml
infrastructure:
  runtime:
    type: "gcp_cloud_function"
    runtime: "python311"
    timeout: 540     # Maximum 9 minutes
    memory: "256MB"  # Memory allocation
    region: "us-central1"
```

---

## Tag Propagation

Tags are automatically extracted from job configurations and asset definitions, then propagated to all infrastructure resources.

### Tag Sources

Tags are collected from multiple sources with the following precedence (highest to lowest):

1. **Job Configuration** (`infrastructure.metadata`, `finops`, `governance_overrides`)
2. **Asset Definition** (`finops`, `compliance`, `team`)
3. **Source System** (connector metadata, if available)

### Tag Categories

#### FinOps Tags

For cost allocation and financial tracking:

- `finops_cost_center`: Cost center identifier (e.g., "ENG-001")
- `finops_business_tags`: Comma-separated business tags (e.g., "sales,crm")
- `finops_project`: Project identifier (e.g., "data-platform")
- `finops_environment`: Environment name (e.g., "production")

**Example:**
```yaml
# In asset definition
finops:
  cost_center: "ENG-001"
  business_tags: ["sales", "crm"]
  project: "data-platform"
  environment: "production"

# Can be overridden in job config
finops:
  cost_center: "ENG-002"  # Overrides asset-level value
```

#### Compliance Tags

For regulatory tracking and data governance:

- `compliance_classification`: Data classification (e.g., "PII", "SENSITIVE")
- `compliance_regulations`: Comma-separated regulations (e.g., "GDPR,CCPA")
- `compliance_retention_days`: Data retention period in days
- `compliance_encryption_required`: Whether encryption is required ("true"/"false")
- `compliance_access_control`: Access control method (e.g., "role_based")

**Example:**
```yaml
# In asset definition
compliance:
  classification: [PII, SENSITIVE]
  regulations: [GDPR, CCPA]
  retention_days: 365
  security:
    encryption_required: true
    access_control: role_based
```

#### Governance Tags

For ownership and data lineage:

- `governance_owner`: Data owner email (e.g., "data-team@company.com")
- `governance_domain`: Business domain (e.g., "sales")
- `governance_data_product`: Data product name
- `governance_retention_days`: Retention period (from compliance or override)

**Example:**
```yaml
# In asset definition
team:
  owner: "data-team@company.com"

domain: "sales"
dataProduct: "customer-data"

# Can be overridden in job config
governance_overrides:
  owner: "sales-team@company.com"  # Overrides asset-level value
  retention_days: 730  # Overrides compliance.retention_days
```

#### Asset Metadata Tags

For resource identification:

- `asset_name`: Asset name (e.g., "hubspot_contacts")
- `asset_version`: Asset version (e.g., "1.0")
- `tenant_id`: Tenant identifier
- `environment`: Environment name

### Tag Format by Cloud Provider

#### AWS Tags

AWS tags are key-value pairs with the following constraints:
- Keys: 1-128 characters, alphanumeric + `_` `-` `.` `:`
- Values: 0-256 characters

Tags are automatically converted to AWS-compatible format:
```
finops_cost_center → finops_cost_center
compliance_classification → compliance_classification
```

#### GCP Labels

GCP labels have stricter constraints:
- Keys: 1-63 characters, lowercase, alphanumeric + `-` `_`
- Values: 0-63 characters, lowercase, alphanumeric + `-` `_`

Tags are automatically converted to GCP-compatible format:
```
finops_cost_center → finops-cost-center
compliance_classification → compliance-classification
```

---

## AWS Deployment

### Using the Terraform Module

```hcl
module "hubspot_contacts_job" {
  source = "../../modules/aws/dativo-job"

  job_name         = "hubspot-contacts"
  tenant_id        = "acme"
  image_uri        = "dativo/dativo-ingest:latest"
  cpu              = 1024
  memory           = 2048
  ecs_cluster_name = "dativo-cluster"
  subnet_ids       = ["subnet-12345", "subnet-67890"]
  security_group_ids = ["sg-12345"]
  aws_region       = "us-east-1"

  # Tags from job/asset configuration
  tags = {
    finops_cost_center   = "ENG-001"
    finops_business_tags = "sales,crm"
    compliance_classification = "PII"
    governance_owner    = "data-team@acme.com"
    asset_name          = "hubspot_contacts"
  }

  # Optional: Scheduled execution
  schedule_expression = "cron(0 2 * * ? *)"  # Daily at 2 AM UTC
  ecs_cluster_arn     = "arn:aws:ecs:us-east-1:123456789012:cluster/dativo-cluster"
}
```

### Module Outputs

- `task_definition_arn`: ARN of the ECS task definition
- `service_name`: Name of the ECS service
- `log_group_name`: Name of the CloudWatch log group

### Manual Execution

To manually trigger a job:

```bash
aws ecs run-task \
  --cluster dativo-cluster \
  --task-definition acme-hubspot-contacts \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-12345],securityGroups=[sg-12345],assignPublicIp=DISABLED}"
```

---

## GCP Deployment

### Using the Terraform Module

```hcl
module "hubspot_contacts_job" {
  source = "../../modules/gcp/dativo-job"

  job_name      = "hubspot-contacts"
  tenant_id     = "acme"
  image_uri     = "gcr.io/dativo/dativo-ingest:latest"
  cpu           = "1"
  memory        = "2Gi"
  timeout_seconds = 3600
  region        = "us-central1"
  project_id    = "my-project"

  # Labels from job/asset configuration (GCP format)
  labels = {
    finops_cost_center   = "eng-001"
    finops_business_tags = "sales-crm"
    compliance_classification = "pii"
    governance_owner    = "data-team-acme-com"
    asset_name          = "hubspot-contacts"
  }

  # Optional: Scheduled execution
  schedule_cron = "0 2 * * *"  # Daily at 2 AM UTC
  timezone      = "UTC"
  service_account_email = "dativo-runner@my-project.iam.gserviceaccount.com"
}
```

### Module Outputs

- `service_url`: URL of the Cloud Run service
- `service_name`: Name of the Cloud Run service
- `service_id`: ID of the Cloud Run service

### Manual Execution

To manually trigger a job:

```bash
gcloud run jobs execute acme-hubspot-contacts \
  --region us-central1 \
  --project my-project
```

---

## Generating Terraform Configurations

### Using the Generation Script

The `generate_terraform.py` script automatically extracts infrastructure requirements and tags from job definitions:

```bash
python3 scripts/generate_terraform.py \
  jobs/acme/hubspot_contacts.yaml \
  --cloud aws \
  --resource-type ecs_fargate \
  --output-dir terraform/generated \
  --format hcl
```

**Options:**
- `--cloud`: Cloud provider (`aws` or `gcp`)
- `--resource-type`: Resource type (`ecs_fargate`, `lambda`, `cloud_run`, `cloud_function`)
- `--output-dir`: Output directory for Terraform files
- `--format`: Output format (`hcl` or `json`)

### Generated Files

The script generates:
- `{tenant}-{asset}.tf`: HCL Terraform configuration
- `{tenant}-{asset}.tf.json`: JSON Terraform configuration (alternative format)

### Example Output

```hcl
# terraform/generated/acme-hubspot-contacts.tf
locals {
  common_tags = {
    tenant_id                = "acme"
    environment              = "prod"
    asset_name               = "hubspot_contacts"
    asset_version            = "1.0"
    finops_cost_center       = "ENG-001"
    finops_business_tags     = "sales,crm"
    compliance_classification = "PII"
    governance_owner          = "data-team@acme.com"
    # ... more tags
  }
}

resource "aws_ecs_task_definition" "hubspot_contacts" {
  # ... configuration
  tags = local.common_tags
}
```

---

## Cost Allocation

### FinOps Tag Strategy

FinOps tags enable accurate cost allocation across teams, projects, and business units:

1. **Cost Center**: Primary cost allocation dimension
   ```yaml
   finops:
     cost_center: "ENG-001"
   ```

2. **Business Tags**: Secondary dimensions for flexible grouping
   ```yaml
   finops:
     business_tags: ["sales", "crm", "customer-data"]
   ```

3. **Project**: Project-level tracking
   ```yaml
   finops:
     project: "data-platform"
   ```

### Querying Costs

#### AWS Cost Explorer

```bash
# Filter by cost center
aws ce get-cost-and-usage \
  --time-period Start=2024-01-01,End=2024-01-31 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --filter file://filter-cost-center.json
```

```json
{
  "Tags": {
    "Key": "finops_cost_center",
    "Values": ["ENG-001"]
  }
}
```

#### GCP Billing

```bash
# Export billing data with labels
gcloud billing accounts list
gcloud billing projects describe my-project
```

Query BigQuery billing export:
```sql
SELECT
  labels.finops_cost_center,
  SUM(cost) as total_cost
FROM `my-project.billing.gcp_billing_export`
WHERE DATE(_PARTITIONTIME) >= '2024-01-01'
GROUP BY labels.finops_cost_center
```

---

## Compliance and Resource Traceability

### Compliance Tags

Compliance tags ensure resources meet regulatory requirements:

```yaml
compliance:
  classification: [PII, SENSITIVE]
  regulations: [GDPR, CCPA]
  retention_days: 365
  security:
    encryption_required: true
    access_control: role_based
```

### Resource Traceability

All resources are tagged with:
- **Asset metadata**: `asset_name`, `asset_version`
- **Ownership**: `governance_owner`
- **Tenant**: `tenant_id`
- **Environment**: `environment`

### Querying Resources

#### AWS

```bash
# Find all resources for a specific asset
aws resourcegroupstaggingapi get-resources \
  --tag-filters Key=asset_name,Values=hubspot_contacts

# Find all resources for a cost center
aws resourcegroupstaggingapi get-resources \
  --tag-filters Key=finops_cost_center,Values=ENG-001
```

#### GCP

```bash
# List Cloud Run services with specific label
gcloud run services list \
  --filter="labels.asset_name=hubspot-contacts" \
  --format="table(name,status.url,labels)"

# List all resources with cost center label
gcloud asset search-all-resources \
  --asset-types="run.googleapis.com/Service" \
  --query="labels.finops_cost_center:ENG-001"
```

---

## Best Practices

### 1. Tag Consistency

- Use consistent tag keys across all jobs
- Define tag standards in asset definitions
- Override only when necessary in job configs

### 2. Cost Allocation

- Always specify `finops.cost_center` in asset definitions
- Use `business_tags` for flexible grouping
- Review cost allocation reports regularly

### 3. Compliance

- Classify all data in asset definitions
- Specify regulatory requirements
- Set appropriate retention periods

### 4. Resource Naming

- Use consistent naming: `{tenant_id}-{asset_name}`
- Include environment in resource names
- Use tags for additional metadata

### 5. Infrastructure as Code

- Generate Terraform configs from job definitions
- Version control all Terraform configurations
- Use modules for reusability

### 6. Security

- Never include sensitive data in tags
- Use IAM roles for service accounts
- Encrypt sensitive data at rest and in transit

### 7. Monitoring

- Set up CloudWatch/GCP monitoring for all jobs
- Alert on job failures
- Track resource utilization

---

## Additional Resources

- [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) - Job configuration reference
- [TAG_PROPAGATION.md](TAG_PROPAGATION.md) - Tag propagation details
- [SETUP_AND_ONBOARDING.md](SETUP_AND_ONBOARDING.md) - Setup guide

---

## Troubleshooting

### Tags Not Appearing

1. Verify infrastructure block is present in job config
2. Check asset definition has finops/compliance sections
3. Ensure tag extractor is called correctly

### Terraform Generation Fails

1. Validate job configuration schema
2. Check asset definition exists and is valid
3. Verify all required fields are present

### Resource Provisioning Fails

1. Check IAM permissions
2. Verify network configuration
3. Review CloudWatch/GCP logs for errors

---

## Examples

See `terraform/examples/` for complete working examples:
- `terraform/examples/aws/` - AWS deployment examples
- `terraform/examples/gcp/` - GCP deployment examples
