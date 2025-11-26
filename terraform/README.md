# Dativo ETL Infrastructure - Terraform Modules

This directory contains Terraform modules for provisioning cloud infrastructure for Dativo ETL jobs with cloud-agnostic configuration and comprehensive tag propagation.

## Overview

The Terraform modules enable you to:

1. **Provision infrastructure** for Dativo ETL jobs on AWS, GCP, or Azure
2. **Propagate tags** automatically from job configurations for cost allocation and compliance
3. **Deploy consistently** across cloud providers using standardized configuration
4. **Integrate with orchestrators** like Dagster, Airflow, or Kubernetes

## Directory Structure

```
terraform/
├── aws/           # AWS infrastructure module (ECS, IAM, CloudWatch)
│   ├── main.tf
│   ├── variables.tf
│   └── README.md
├── gcp/           # GCP infrastructure module (Cloud Run, IAM, Cloud Logging)
│   ├── main.tf
│   ├── variables.tf
│   └── README.md
└── README.md      # This file
```

## Quick Start

### 1. Define Infrastructure in Job Configuration

Add an `infrastructure` block to your job configuration:

```yaml
# jobs/acme/stripe_customers_to_iceberg.yaml
infrastructure:
  provider: aws  # or gcp
  runtime:
    type: ecs
    compute:
      cpu: "2048"
      memory: "4096"
  storage:
    state_bucket: dativo-state-acme
    data_bucket: dativo-data-acme
  tags:
    cost_center: FIN-001
    owner: data-team@acme.com
```

### 2. Generate Terraform Variables

```bash
dativo infra generate-tfvars \
  --job-config jobs/acme/stripe_customers_to_iceberg.yaml \
  --output terraform/aws/terraform.tfvars.json
```

### 3. Apply Terraform

```bash
cd terraform/aws
terraform init
terraform plan -var-file=terraform.tfvars.json
terraform apply -var-file=terraform.tfvars.json
```

## Modules

### AWS Module

**Location:** `aws/`

Provisions:
- ECS Fargate cluster and task definition
- IAM roles and policies with least-privilege permissions
- CloudWatch log groups and metric filters
- Security groups and networking
- S3 bucket access policies

**Resources:** 10+ AWS resources with comprehensive tagging

See [aws/README.md](aws/README.md) for detailed documentation.

### GCP Module

**Location:** `gcp/`

Provisions:
- Cloud Run job
- Service account with IAM bindings
- Cloud Logging sink
- Alert policies
- VPC connector integration
- GCS bucket access policies

**Resources:** 8+ GCP resources with comprehensive labeling

See [gcp/README.md](gcp/README.md) for detailed documentation.

## Tag Propagation

Tags are automatically propagated from multiple sources:

### 1. Infrastructure Tags (from job config)

```yaml
infrastructure:
  tags:
    cost_center: FIN-001
    business_unit: Finance
    project: data-platform
    environment: prod
    owner: data-team@acme.com
    compliance: [GDPR, SOC2]
    data_classification: Confidential
```

### 2. Job Metadata Tags

Automatically added:
- `TenantId`: From `tenant_id` in job config
- `Asset`: From `asset` in job config
- `SourceConnector`: From `source_connector` in job config
- `Environment`: From `environment` in job config

### 3. Asset Tags (from asset schema)

```yaml
# assets/stripe/v1.0/customers.yaml
compliance:
  classification: [PII]
  retention_days: 365

finops:
  cost_center: FIN-001
  project: data-platform
```

Tags propagated:
- `Classification_*`: Data sensitivity classifications
- `Governance_*`: Retention policies, regulations
- `FinOps_*`: Cost attribution metadata

### 4. System Tags

Automatically added:
- `ManagedBy: dativo`
- `Terraform: true`
- `Module: dativo-etl-job`
- `RuntimeType`: Runtime orchestrator type

### Example Combined Tags

**AWS:**
```hcl
tags = {
  # Infrastructure tags
  CostCenter         = "FIN-001"
  BusinessUnit       = "Finance"
  Project            = "data-platform"
  Environment        = "prod"
  Owner              = "data-team@acme.com"
  Compliance         = "GDPR,SOC2"
  DataClassification = "Confidential"
  
  # Job metadata
  TenantId        = "acme"
  Asset           = "stripe_customers"
  SourceConnector = "stripe"
  
  # Asset tags
  Classification_default = "pii"
  Governance_retention_days = "365"
  FinOps_cost_center = "FIN-001"
  
  # System tags
  ManagedBy   = "dativo"
  Terraform   = "true"
  Module      = "dativo-etl-job"
  RuntimeType = "ecs"
}
```

**GCP (normalized to lowercase with underscores):**
```hcl
labels = {
  costcenter         = "fin_001"
  businessunit       = "finance"
  project            = "data_platform"
  environment        = "prod"
  owner              = "data_team_acme_com"
  compliance         = "gdpr_soc2"
  dataclassification = "confidential"
  tenant_id          = "acme"
  asset              = "stripe_customers"
  managed_by         = "dativo"
  terraform          = "true"
}
```

## Cost Allocation

### AWS Cost Explorer

Filter by tags to track costs:

```sql
SELECT 
  cost,
  tags.CostCenter,
  tags.TenantId,
  tags.Project
FROM aws_cost_usage
WHERE tags.ManagedBy = 'dativo'
GROUP BY tags.CostCenter
```

### GCP BigQuery Billing Export

```sql
SELECT 
  SUM(cost) as total_cost,
  labels.value as cost_center,
  labels.value as tenant_id
FROM `project.dataset.gcp_billing_export_v1_XXXXXX`
CROSS JOIN UNNEST(labels) as labels
WHERE labels.key = 'managed_by' AND labels.value = 'dativo'
GROUP BY cost_center, tenant_id
```

## Compliance Tracking

### AWS Resource Groups

```bash
# List all GDPR-compliant resources
aws resourcegroupstaggingapi get-resources \
  --tag-filters Key=Compliance,Values=GDPR \
  --resource-type-filters ecs:cluster ecs:task-definition
```

### GCP Resource Manager

```bash
# List all PII data processing jobs
gcloud run jobs list \
  --filter="metadata.labels.classification_default:pii" \
  --format="table(name,location,metadata.labels)"
```

## Terraform State Management

### AWS (S3 Backend)

```hcl
terraform {
  backend "s3" {
    bucket         = "terraform-state"
    key            = "dativo/jobs/stripe_customers.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-locks"
  }
}
```

### GCP (GCS Backend)

```hcl
terraform {
  backend "gcs" {
    bucket = "terraform-state"
    prefix = "dativo/jobs/stripe_customers"
  }
}
```

## Best Practices

1. **Always specify tags**: Include `cost_center`, `owner`, and `environment` tags
2. **Use remote state**: Store Terraform state in S3/GCS with encryption and locking
3. **Enable encryption**: Use KMS/Cloud KMS for data encryption at rest
4. **Private networking**: Use private subnets/VPC connectors for production workloads
5. **Monitoring**: Enable CloudWatch/Cloud Logging and set up alert policies
6. **Resource sizing**: Start small and scale up based on actual usage
7. **Tag governance**: Establish and enforce tagging policies across teams

## Examples

See `examples/jobs/` for complete examples:

- **AWS ECS:** `aws_stripe_customers_to_iceberg.yaml`
- **GCP Cloud Run:** `gcp_hubspot_contacts_to_iceberg.yaml`
- **AWS Dagster:** `aws_dagster_mysql_to_iceberg.yaml`

## Documentation

- [Infrastructure Integration Guide](../docs/INFRASTRUCTURE_INTEGRATION.md)
- [AWS Module Documentation](aws/README.md)
- [GCP Module Documentation](gcp/README.md)
- [Tag Propagation](../docs/TAG_PROPAGATION.md)

## Troubleshooting

### Common Issues

1. **Tags not appearing**: Check that tags are defined in job config and Terraform has been applied
2. **Networking errors**: Verify VPC/subnet IDs are correct and in the same region
3. **Storage access errors**: Verify IAM roles/service accounts have correct permissions
4. **Terraform apply failures**: Check credentials and state lock status

See [Troubleshooting Guide](../docs/INFRASTRUCTURE_INTEGRATION.md#troubleshooting) for detailed solutions.

## Contributing

When adding new cloud provider modules:

1. Follow the existing module structure
2. Implement comprehensive tag/label propagation
3. Include validation for required configuration
4. Add examples and documentation
5. Write tests for the Python infrastructure module

## License

Apache 2.0 - See LICENSE file for details
