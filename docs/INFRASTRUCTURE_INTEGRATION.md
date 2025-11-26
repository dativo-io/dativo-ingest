# Infrastructure Integration for Cloud-Agnostic Deployment

Dativo ETL jobs can now reference infrastructure provisioned outside of Dativo via Terraform, enabling cloud-agnostic deployment (AWS/GCP) through Dagster with comprehensive tag propagation for cost allocation, compliance, and resource traceability.

## Overview

The `infrastructure` block in job definitions describes the runtime environment and metadata that must flow into Terraform modules. This enables:

- **Cloud-agnostic deployment**: Deploy jobs to AWS (ECS Fargate, EC2) or GCP (Cloud Run, GKE) via Terraform
- **Tag propagation**: Comprehensive tags flow from job definitions → Dagster → Terraform → cloud resources
- **Cost allocation**: FinOps tags propagate to cloud resources for accurate cost tracking
- **Compliance**: Classification and governance tags ensure resources are properly tagged
- **Resource traceability**: Link Dativo jobs to Terraform-provisioned infrastructure

## Quick Start

### 1. Add Infrastructure Block to Job Configuration

```yaml
tenant_id: acme
environment: production

source_connector: stripe
source_connector_path: connectors/stripe.yaml

target_connector: iceberg
target_connector_path: connectors/iceberg.yaml

asset: stripe_customers
asset_path: assets/stripe/v1.0/customers.yaml

# Infrastructure configuration
infrastructure:
  provider: aws  # or 'gcp'
  compute_type: fargate
  memory_mb: 2048
  vcpu: 1.0
  
  # Resource references (Terraform-provisioned resources)
  resource_refs:
    task_definition_arn: "arn:aws:ecs:us-east-1:123456789012:task-definition/dativo-job:1"
    cluster_name: "dativo-cluster"
  
  # Tags for Terraform propagation
  tags:
    ManagedBy: "dativo"
    Environment: "production"
    Team: "data-platform"
    CostCenter: "FIN-001"
  
  # Terraform module configuration
  terraform_module: "modules/dativo-job"
  terraform_vars:
    enable_logging: true
    log_retention_days: 30

# FinOps metadata (merged with infrastructure tags)
finops:
  cost_center: FIN-001
  business_tags: [payments, revenue]
  project: stripe-ingestion
  environment: production
```

### 2. Terraform Module Integration

Your Terraform module receives infrastructure metadata via Dagster asset metadata:

```hcl
# modules/dativo-job/main.tf

variable "job_name" {
  description = "Dagster job name"
  type        = string
}

variable "infrastructure_provider" {
  description = "Cloud provider (aws or gcp)"
  type        = string
}

variable "infrastructure_compute_type" {
  description = "Compute type (fargate, ec2, cloud-run)"
  type        = string
}

variable "infrastructure_memory_mb" {
  description = "Memory allocation in MB"
  type        = number
}

variable "infrastructure_vcpu" {
  description = "Virtual CPU allocation"
  type        = number
}

variable "terraform_module" {
  description = "Terraform module path"
  type        = string
}

variable "resource_refs" {
  description = "Resource references from job config"
  type        = map(string)
  default     = {}
}

# Example: AWS ECS Fargate task definition
resource "aws_ecs_task_definition" "dativo_job" {
  family                   = var.job_name
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.infrastructure_vcpu * 1024  # Convert to CPU units
  memory                   = var.infrastructure_memory_mb

  # Tags from infrastructure.tags + finops tags
  tags = {
    ManagedBy     = "dativo"
    Environment   = "production"
    Team          = "data-platform"
    CostCenter    = "FIN-001"
    # Additional tags from Dagster asset metadata
  }

  container_definitions = jsonencode([{
    name  = var.job_name
    image = "dativo:latest"
    # ... container configuration
  }])
}
```

### 3. Dagster Integration

Dagster automatically extracts infrastructure metadata and makes it available for Terraform:

```python
# Dagster asset automatically includes infrastructure metadata
@asset(
    name="stripe_customers_asset",
    tags={
        "tenant": "acme",
        "infrastructure_provider": "aws",
        "infrastructure_compute_type": "fargate",
        # ... additional infrastructure tags
    }
)
def stripe_customers_asset(context: AssetExecutionContext):
    # Infrastructure metadata available via context
    infrastructure_metadata = context.metadata
    # Pass to Terraform module
    ...
```

## Infrastructure Block Schema

### Required Fields

- **`provider`** (string, required): Cloud provider - `"aws"` or `"gcp"`

### Optional Fields

#### Runtime Environment

- **`compute_type`** (string, optional): Compute instance type
  - AWS: `"fargate"`, `"ec2"`, `"lambda"`
  - GCP: `"cloud-run"`, `"gke"`, `"cloud-functions"`
- **`memory_mb`** (integer, optional): Memory allocation in MB
- **`vcpu`** (float, optional): Virtual CPU allocation
- **`runtime`** (dict, optional): Additional runtime environment metadata

#### Resource References

- **`resource_refs`** (dict, optional): References to Terraform-provisioned resources
  - Example: `{"task_definition_arn": "arn:aws:ecs:...", "cluster_name": "dativo-cluster"}`

#### Tags

- **`tags`** (dict, optional): Additional tags to propagate to Terraform-provisioned resources
  - These tags are merged with FinOps and governance tags from the job/asset
  - Tags are namespaced as `infrastructure.*` in Iceberg table properties

#### Terraform Configuration

- **`terraform_module`** (string, optional): Terraform module path or reference
  - Example: `"modules/dativo-job"` or `"github.com/org/terraform-modules//dativo-job"`
- **`terraform_vars`** (dict, optional): Additional Terraform variables to pass to the module

## Tag Propagation Flow

Tags flow through the system in this order (later overrides earlier):

1. **Asset Definition** - Base tags from asset schema, compliance, finops
2. **Job Configuration** - FinOps and governance overrides
3. **Infrastructure Block** - Infrastructure-specific tags
4. **Dagster Asset** - All tags merged and exposed as asset metadata
5. **Terraform Module** - Tags applied to cloud resources

### Tag Namespaces

All tags are namespaced to avoid conflicts:

- `classification.*` - Data classification tags
- `governance.*` - Governance and compliance tags
- `finops.*` - Cost allocation tags
- `infrastructure.*` - Infrastructure-specific tags

### Example Tag Flow

```yaml
# Asset definition
finops:
  cost_center: FIN-001
  business_tags: [payments]

# Job configuration
finops:
  cost_center: FIN-002  # Overrides asset
  business_tags: [payments, revenue]  # Merged with asset

# Infrastructure block
tags:
  ManagedBy: "dativo"
  Environment: "production"

# Result in Dagster asset metadata:
# - finops.cost_center: FIN-002
# - finops.business_tags: payments,revenue
# - infrastructure.ManagedBy: dativo
# - infrastructure.Environment: production
```

## Cloud Provider Examples

### AWS (ECS Fargate)

```yaml
infrastructure:
  provider: aws
  compute_type: fargate
  memory_mb: 2048
  vcpu: 1.0
  resource_refs:
    task_definition_arn: "arn:aws:ecs:us-east-1:123456789012:task-definition/dativo-job:1"
    cluster_name: "dativo-cluster"
    execution_role_arn: "arn:aws:iam::123456789012:role/dativo-execution-role"
  terraform_module: "modules/dativo-job-aws"
  tags:
    ManagedBy: "dativo"
    Environment: "production"
```

### GCP (Cloud Run)

```yaml
infrastructure:
  provider: gcp
  compute_type: cloud-run
  memory_mb: 2048
  vcpu: 1.0
  resource_refs:
    service_name: "dativo-job-stripe-customers"
    project_id: "my-gcp-project"
    region: "us-central1"
  terraform_module: "modules/dativo-job-gcp"
  tags:
    ManagedBy: "dativo"
    Environment: "production"
```

## Terraform Module Best Practices

### 1. Accept Infrastructure Metadata

Your Terraform module should accept infrastructure metadata as variables:

```hcl
variable "infrastructure_provider" {
  type = string
}

variable "infrastructure_compute_type" {
  type = string
}

variable "infrastructure_memory_mb" {
  type = number
}

variable "infrastructure_vcpu" {
  type = number
}
```

### 2. Apply Tags to Resources

Apply tags from Dagster asset metadata to all resources:

```hcl
locals {
  # Merge tags from infrastructure block + finops + governance
  common_tags = {
    ManagedBy   = "dativo"
    Environment = var.environment
    CostCenter  = var.finops_cost_center
    # ... additional tags from asset metadata
  }
}

resource "aws_ecs_task_definition" "job" {
  # ... resource configuration
  tags = local.common_tags
}
```

### 3. Use Resource References

Reference Terraform-provisioned resources in job configurations:

```hcl
# Terraform outputs
output "task_definition_arn" {
  value = aws_ecs_task_definition.job.arn
}

output "cluster_name" {
  value = aws_ecs_cluster.dativo.name
}
```

Then reference in job config:

```yaml
infrastructure:
  resource_refs:
    task_definition_arn: "${terraform_output.task_definition_arn}"
    cluster_name: "${terraform_output.cluster_name}"
```

## Dagster Integration Details

### Asset Metadata

Dagster assets automatically include infrastructure metadata:

```python
# Infrastructure metadata available in asset context
@asset(name="my_job_asset")
def my_job(context: AssetExecutionContext):
    # Access infrastructure metadata
    metadata = context.metadata
    provider = metadata.get("infrastructure_provider")
    compute_type = metadata.get("infrastructure_compute_type")
    # ... use for Terraform integration
```

### Tag Propagation

All tags (classification, governance, finops, infrastructure) are automatically propagated to:

1. **Dagster asset tags** - For filtering and organization
2. **Dagster asset metadata** - For Terraform module inputs
3. **Iceberg table properties** - For data governance
4. **Cloud resource tags** - Via Terraform modules

## Cost Allocation

Infrastructure tags enable accurate cost allocation:

```yaml
infrastructure:
  tags:
    CostCenter: "FIN-001"
    Project: "stripe-ingestion"
    Team: "data-platform"

finops:
  cost_center: FIN-001
  business_tags: [payments, revenue]
  project: stripe-ingestion
```

These tags flow to:
- AWS Cost Explorer tags
- GCP Billing labels
- Cloud resource tags (ECS tasks, Cloud Run services, etc.)

## Compliance and Governance

Infrastructure tags support compliance requirements:

```yaml
infrastructure:
  tags:
    Compliance: "GDPR"
    DataClassification: "PII"
    RetentionDays: "365"

governance_overrides:
  retention_days: 365
  owner: data-platform@company.com
```

These tags ensure:
- Resources are properly classified
- Retention policies are enforced
- Ownership is tracked
- Compliance requirements are met

## Testing

### Validate Infrastructure Configuration

```python
from dativo_ingest.config import JobConfig

# Load job config
job_config = JobConfig.from_yaml("jobs/my_job.yaml")

# Validate infrastructure block
if job_config.infrastructure:
    assert job_config.infrastructure.provider in ["aws", "gcp"]
    assert job_config.infrastructure.compute_type is not None
    # ... additional validation
```

### Test Tag Propagation

```python
from dativo_ingest.tag_derivation import derive_tags_from_asset

# Derive all tags (including infrastructure)
tags = derive_tags_from_asset(
    asset_definition=asset,
    finops=job_config.finops,
    infrastructure=job_config.infrastructure,
)

# Verify infrastructure tags
assert "infrastructure.provider" in tags
assert "infrastructure.compute_type" in tags
# ... additional assertions
```

## Examples

See `examples/jobs/infrastructure_example.yaml` for a complete example.

## References

- [Tag Propagation Documentation](TAG_PROPAGATION.md)
- [Dagster Documentation](https://docs.dagster.io/)
- [Terraform Documentation](https://www.terraform.io/docs)
