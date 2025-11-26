# Infrastructure Integration for Terraform Deployment

This guide explains how to configure external infrastructure integration for Dativo ETL jobs, enabling cloud-agnostic deployment in Dagster via Terraform with comprehensive tag propagation for cost allocation, compliance, and resource traceability.

## Overview

Dativo jobs can now reference infrastructure provisioned outside of Dativo using Terraform. The optional `infrastructure` block in job definitions describes the runtime environment and metadata that must flow into the Terraform module for cloud-agnostic deployment.

### Key Features

- **Cloud-Agnostic**: Supports both AWS and GCP
- **Tag Propagation**: Automatic propagation of tags for cost allocation, compliance, and resource traceability
- **Terraform Integration**: Seamless integration with Terraform modules
- **Metadata Extraction**: Automatic extraction of infrastructure metadata for Terraform variables

## Infrastructure Block Structure

The `infrastructure` block is optional and contains the following sections:

```yaml
infrastructure:
  cloud_provider: aws  # or 'gcp'
  
  runtime_environment:
    compute_type: ecs_task
    compute_size: medium
    memory_mb: 2048
    cpu_units: 1024
    timeout_seconds: 3600
    network:
      vpc_id: vpc-0123456789abcdef0
      subnet_ids:
        - subnet-0123456789abcdef0
      security_group_ids:
        - sg-0123456789abcdef0
    storage:
      ephemeral_storage_gb: 20
      persistent_volume: false
    service_account: dativo-etl-execution-role
  
  tags:
    CostCenter: "FIN-001"
    Project: "data-platform"
    Environment: "production"
    Owner: "data-engineering-team@company.com"
    Compliance: "PII"
    DataClassification: "SENSITIVE"
    Regulation: "GDPR,CCPA"
    TenantId: "production_tenant"
    JobName: "csv_employee_to_iceberg"
    ManagedBy: "Terraform"
  
  terraform:
    module_path: "modules/dativo-etl-job"
    module_version: "~> 1.0"
    resource_refs:
      execution_role_arn: "arn:aws:iam::123456789012:role/dativo-etl-execution-role"
      cluster_name: "dativo-etl-cluster"
      vpc_id: "vpc-0123456789abcdef0"
    variables:
      enable_cloudwatch_logs: true
```

## Cloud Provider Support

### AWS

Supported compute types:
- `ecs_task` - AWS ECS Task
- `lambda` - AWS Lambda function
- `ec2_instance` - EC2 instance

Example AWS configuration:
```yaml
infrastructure:
  cloud_provider: aws
  runtime_environment:
    compute_type: ecs_task
    memory_mb: 2048
    cpu_units: 1024  # 256 = 0.25 vCPU
    network:
      vpc_id: vpc-0123456789abcdef0
      subnet_ids:
        - subnet-0123456789abcdef0
      security_group_ids:
        - sg-0123456789abcdef0
  terraform:
    resource_refs:
      execution_role_arn: "arn:aws:iam::123456789012:role/dativo-etl-execution-role"
      task_definition_arn: "arn:aws:ecs:us-east-1:123456789012:task-definition/dativo-etl-base:1"
      cluster_name: "dativo-etl-cluster"
      log_group_name: "/aws/ecs/dativo-etl"
```

### GCP

Supported compute types:
- `cloud_run` - Cloud Run service
- `gce_instance` - Compute Engine instance
- `gke_pod` - GKE pod

Example GCP configuration:
```yaml
infrastructure:
  cloud_provider: gcp
  runtime_environment:
    compute_type: cloud_run
    memory_mb: 2048
    cpu_units: 1000  # 1000 = 1 vCPU in GCP
    network:
      vpc_id: "projects/my-project/global/networks/dativo-vpc"
      subnet_ids:
        - "projects/my-project/regions/us-central1/subnetworks/dativo-subnet-1"
      security_group_ids:
        - "dativo-etl-firewall-rule"
  terraform:
    resource_refs:
      service_account_email: "dativo-etl-execution@my-project.iam.gserviceaccount.com"
      cluster_name: "dativo-etl-gke-cluster"
      log_group_name: "projects/my-project/logs/dativo-etl"
```

## Tag Propagation

Tags are automatically propagated from multiple sources with the following precedence (highest to lowest):

1. **Infrastructure block tags** - Explicitly defined in `infrastructure.tags`
2. **FinOps metadata** - From `finops` section in job config and asset definition
3. **Compliance metadata** - From asset definition `compliance` section
4. **Governance metadata** - From asset definition `team` and `governance` sections
5. **Job-level metadata** - `tenant_id`, `environment`, `asset` name

### Standard Tags

The following tags are automatically generated and propagated:

- `CostCenter` - From FinOps metadata
- `Project` - From FinOps metadata
- `Environment` - From job config or FinOps metadata
- `Owner` - From asset definition team owner
- `Compliance` - From asset definition compliance classification
- `DataClassification` - From asset definition compliance classification
- `Regulation` - From asset definition compliance regulations
- `TenantId` - From job config tenant_id
- `JobName` - From job config asset name
- `ManagedBy` - Always set to "Terraform"

### Custom Tags

You can add custom tags in the `infrastructure.tags` section:

```yaml
infrastructure:
  tags:
    CustomTag: "custom-value"
    Department: "engineering"
    CostAllocation: "data-platform"
```

## Terraform Integration

### Generating Terraform Variables

Use the `infrastructure_metadata` module to extract Terraform variables:

```python
from dativo_ingest.config import JobConfig
from dativo_ingest.infrastructure_metadata import generate_terraform_variables

# Load job configuration
job_config = JobConfig.from_yaml("jobs/my_job.yaml")
asset_definition = job_config._resolve_asset()

# Generate Terraform variables
variables = generate_terraform_variables(job_config, asset_definition)

# Output as JSON
import json
print(json.dumps(variables, indent=2))
```

### Terraform Module Structure

Your Terraform module should accept the following variables:

```hcl
variable "cloud_provider" {
  description = "Cloud provider (aws or gcp)"
  type        = string
}

variable "runtime_environment" {
  description = "Runtime environment metadata"
  type = object({
    compute_type      = string
    compute_size      = string
    memory_mb         = number
    cpu_units         = number
    timeout_seconds   = number
    network = object({
      vpc_id              = string
      subnet_ids          = list(string)
      security_group_ids  = list(string)
    })
    storage = object({
      ephemeral_storage_gb = number
      persistent_volume    = bool
    })
    service_account = string
  })
}

variable "tags" {
  description = "Tags for cost allocation, compliance, and resource traceability"
  type        = map(string)
}

variable "resource_refs" {
  description = "References to externally provisioned resources"
  type        = map(string)
  default     = {}
}

variable "job_metadata" {
  description = "Job metadata"
  type = object({
    tenant_id       = string
    environment     = string
    asset_name      = string
    source_connector = string
    target_connector = string
  })
}
```

### Example Terraform Module Usage

```hcl
module "dativo_etl_job" {
  source = "./modules/dativo-etl-job"
  
  cloud_provider     = var.cloud_provider
  runtime_environment = var.runtime_environment
  tags               = var.tags
  resource_refs      = var.resource_refs
  job_metadata       = var.job_metadata
  
  # Additional module-specific variables
  enable_cloudwatch_logs = var.enable_cloudwatch_logs
  enable_xray_tracing    = var.enable_xray_tracing
}
```

## Dagster Integration

When deploying jobs in Dagster, the infrastructure metadata is automatically extracted and passed to Terraform modules. The Dagster orchestrator can:

1. Extract infrastructure metadata from job configurations
2. Generate Terraform variables
3. Invoke Terraform modules to provision infrastructure
4. Pass resource references back to job execution

### Example Dagster Asset

```python
from dagster import asset, Config
from dativo_ingest.config import JobConfig
from dativo_ingest.infrastructure_metadata import generate_terraform_variables

@asset
def csv_employee_to_iceberg(context):
    # Load job configuration
    job_config = JobConfig.from_yaml("jobs/csv_employee_to_iceberg.yaml")
    asset_definition = job_config._resolve_asset()
    
    # Extract infrastructure metadata
    if job_config.infrastructure:
        terraform_vars = generate_terraform_variables(job_config, asset_definition)
        
        # Provision infrastructure via Terraform
        # (Terraform execution logic here)
        
        # Execute job with infrastructure references
        # (Job execution logic here)
    else:
        # Execute job without infrastructure block
        # (Job execution logic here)
```

## Examples

See example job configurations with infrastructure blocks:

- [AWS Example](examples/jobs/csv_employee_to_iceberg_with_infrastructure_aws.yaml)
- [GCP Example](examples/jobs/csv_employee_to_iceberg_with_infrastructure_gcp.yaml)

## Best Practices

1. **Tag Consistency**: Use consistent tag naming across all jobs for proper cost allocation
2. **Resource References**: Reference externally provisioned resources via `terraform.resource_refs`
3. **Environment Separation**: Use different infrastructure configurations for dev/staging/prod
4. **Compliance Tags**: Always include compliance and data classification tags for sensitive data
5. **Cost Allocation**: Include FinOps metadata for accurate cost tracking

## Troubleshooting

### Tags Not Propagating

Ensure that:
- Infrastructure block is present in job configuration
- Asset definition contains compliance and FinOps metadata
- Job configuration includes FinOps metadata if needed

### Terraform Variables Not Generated

Check that:
- Job configuration is valid (schema validation passes)
- Asset definition is properly loaded
- Infrastructure block is correctly formatted

### Resource References Missing

Verify that:
- `terraform.resource_refs` section is populated
- Resource ARNs/IDs are correct for your cloud provider
- Resources are actually provisioned in your cloud account

## API Reference

### `extract_infrastructure_tags(job_config, asset_definition)`

Extract and merge all tags for infrastructure resources.

**Parameters:**
- `job_config`: JobConfig instance
- `asset_definition`: AssetDefinition instance

**Returns:** Dictionary of tags suitable for Terraform resource tagging

### `generate_terraform_variables(job_config, asset_definition)`

Generate Terraform variables from job configuration.

**Parameters:**
- `job_config`: JobConfig instance
- `asset_definition`: AssetDefinition instance

**Returns:** Dictionary of Terraform variables

### `generate_terraform_output(job_config, asset_definition, format='json')`

Generate Terraform-compatible output.

**Parameters:**
- `job_config`: JobConfig instance
- `asset_definition`: AssetDefinition instance
- `format`: Output format ('json' or 'hcl')

**Returns:** Terraform variables in specified format
