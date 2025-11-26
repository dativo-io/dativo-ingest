# External Infrastructure Integration for Dativo ETL

## Overview

Dativo now supports external infrastructure integration, enabling cloud-agnostic deployment of ETL jobs via Terraform with comprehensive tag propagation for cost allocation, compliance, and resource traceability. Job definitions can reference infrastructure provisioned outside of Dativo, allowing seamless integration with existing cloud infrastructure and orchestration platforms.

## Key Features

- **Cloud-Agnostic**: Support for AWS, GCP, and Azure
- **Orchestration-Ready**: Built-in support for Dagster, Airflow, Kubernetes, ECS, and Cloud Run
- **Terraform Integration**: Reference external Terraform modules for infrastructure provisioning
- **Tag Propagation**: Automatic propagation of tags from jobs to infrastructure for cost allocation and compliance
- **Resource Management**: Declarative compute, networking, and storage configuration
- **Multi-Tenant**: Full support for multi-tenant deployments with tenant-specific infrastructure

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Dativo Job Configuration                      │
│  ┌────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  Source/Target │  │  Infrastructure │  │  FinOps/Tags    │  │
│  │  Configuration │  │  Configuration  │  │  Metadata       │  │
│  └────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Terraform Module                              │
│  ┌────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  Compute        │  │  Networking     │  │  Storage        │  │
│  │  Resources      │  │  Configuration  │  │  Buckets/Paths  │  │
│  └────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Cloud Provider (AWS/GCP/Azure)                │
│  ┌────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  ECS/Cloud Run │  │  VPC/Network    │  │  S3/GCS Buckets │  │
│  │  Kubernetes    │  │  Security Groups│  │  KMS Keys       │  │
│  └────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Orchestration Layer (Dagster)                 │
│  ┌────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  Code Locations│  │  Ops/Assets     │  │  Resource Mgmt  │  │
│  └────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Basic Infrastructure Configuration

Add an `infrastructure` block to your job configuration:

```yaml
# jobs/acme/stripe_customers_to_iceberg.yaml
tenant_id: acme
environment: prod

source_connector_path: /app/connectors/stripe.yaml
target_connector_path: /app/connectors/iceberg.yaml
asset_path: /app/assets/stripe/v1.0/customers.yaml

source:
  objects: [customers]

target:
  connection:
    s3:
      bucket: acme-data-lake
      prefix: raw/stripe/customers

# External infrastructure configuration
infrastructure:
  provider: aws
  
  runtime:
    type: dagster
    cluster_name: dativo-prod
    namespace: etl-jobs
    service_account: arn:aws:iam::123456789012:role/dativo-etl-role
  
  compute:
    cpu: "2"
    memory: "4Gi"
    instance_type: t3.medium
    max_runtime_seconds: 3600
  
  networking:
    vpc_id: vpc-0123456789abcdef0
    subnet_ids:
      - subnet-0123456789abcdef0
      - subnet-0123456789abcdef1
    security_group_ids:
      - sg-0123456789abcdef0
    private_networking: true
  
  storage:
    bucket: acme-data-lake
    prefix: raw/stripe/customers
    kms_key_id: arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-123456789012
  
  tags:
    CostCenter: HR-001
    Project: data-platform
    Environment: production
    ManagedBy: terraform
    Team: data-engineering
  
  terraform:
    module_source: git::https://github.com/acme/terraform-dativo-infrastructure.git//modules/etl-job
    module_version: "1.2.0"
    workspace: prod
    backend_config:
      bucket: acme-terraform-state
      key: dativo/etl-jobs/stripe-customers.tfstate
      region: us-east-1
    variables:
      enable_monitoring: true
      retention_days: 90

# FinOps metadata (propagated to infrastructure)
finops:
  cost_center: HR-001
  business_tags:
    - payments
    - revenue
    - stripe
  project: data-platform
  environment: production
```

## Configuration Reference

### Infrastructure Block

The `infrastructure` block contains all external infrastructure configuration.

#### Provider

Specifies the cloud provider:

```yaml
infrastructure:
  provider: aws  # Options: aws, gcp, azure
```

#### Runtime Configuration

Defines the runtime environment and orchestration platform:

```yaml
infrastructure:
  runtime:
    type: dagster                    # Options: dagster, airflow, kubernetes, ecs, cloud_run
    cluster_name: dativo-prod        # Cluster or environment name
    namespace: etl-jobs              # Kubernetes namespace or logical grouping
    service_account: <role-arn>      # Service account or IAM role for execution
```

**AWS Example:**
```yaml
runtime:
  type: ecs
  cluster_name: dativo-prod-cluster
  service_account: arn:aws:iam::123456789012:role/dativo-etl-role
```

**GCP Example:**
```yaml
runtime:
  type: cloud_run
  cluster_name: dativo-prod
  service_account: dativo-etl@acme-project.iam.gserviceaccount.com
```

**Kubernetes Example:**
```yaml
runtime:
  type: kubernetes
  cluster_name: dativo-prod-gke
  namespace: data-engineering
  service_account: dativo-etl-sa
```

#### Compute Configuration

Defines compute resource requirements:

```yaml
infrastructure:
  compute:
    cpu: "2"                         # CPU request (e.g., '2', '500m', '1000m')
    memory: "4Gi"                    # Memory request (e.g., '4Gi', '2048Mi')
    instance_type: t3.medium         # Cloud instance type (optional)
    max_runtime_seconds: 3600        # Maximum runtime before timeout (1 hour)
```

**Instance Type Examples:**
- AWS: `t3.micro`, `t3.small`, `t3.medium`, `t3.large`, `m5.xlarge`
- GCP: `n1-standard-1`, `n1-standard-2`, `n1-standard-4`, `e2-medium`
- Azure: `Standard_B1s`, `Standard_B2s`, `Standard_D2s_v3`

#### Networking Configuration

Defines network configuration:

```yaml
infrastructure:
  networking:
    vpc_id: vpc-0123456789abcdef0
    subnet_ids:
      - subnet-0123456789abcdef0
      - subnet-0123456789abcdef1
    security_group_ids:
      - sg-0123456789abcdef0
    private_networking: true         # Use private networking (default: true)
```

**GCP Example:**
```yaml
networking:
  vpc_id: projects/acme-project/global/networks/dativo-vpc
  subnet_ids:
    - projects/acme-project/regions/us-central1/subnetworks/dativo-subnet
  private_networking: true
```

#### Storage Configuration

Defines storage configuration:

```yaml
infrastructure:
  storage:
    bucket: acme-data-lake           # S3/GCS bucket name
    prefix: raw/stripe/customers     # Storage prefix/path
    kms_key_id: <kms-key-arn>        # KMS key for encryption
```

**AWS Example:**
```yaml
storage:
  bucket: acme-data-lake
  prefix: raw/stripe/customers
  kms_key_id: arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-123456789012
```

**GCP Example:**
```yaml
storage:
  bucket: acme-data-lake
  prefix: raw/stripe/customers
  kms_key_id: projects/acme-project/locations/us-central1/keyRings/dativo/cryptoKeys/etl-data
```

#### Infrastructure Tags

Tags for cost allocation, compliance, and resource traceability:

```yaml
infrastructure:
  tags:
    CostCenter: HR-001
    Project: data-platform
    Environment: production
    ManagedBy: terraform
    Team: data-engineering
    Owner: data-team@acme.com
    Compliance: PII
```

These tags are automatically propagated to:
- Cloud resources (EC2, ECS, Cloud Run, etc.)
- Storage buckets (S3, GCS)
- Networking resources (VPC, subnets, security groups)
- Iceberg tables (via table properties)

#### Terraform Configuration

Reference external Terraform modules:

```yaml
infrastructure:
  terraform:
    module_source: git::https://github.com/acme/terraform-dativo-infrastructure.git//modules/etl-job
    module_version: "1.2.0"
    workspace: prod
    backend_config:
      bucket: acme-terraform-state
      key: dativo/etl-jobs/stripe-customers.tfstate
      region: us-east-1
    variables:
      enable_monitoring: true
      retention_days: 90
```

**Module Source Examples:**
```yaml
# Git repository
module_source: git::https://github.com/acme/terraform-modules.git//dativo-etl

# Terraform Registry
module_source: acme/dativo-etl/aws

# Local path
module_source: ../../terraform/modules/dativo-etl
```

#### Dagster Configuration

Dagster-specific configuration:

```yaml
infrastructure:
  dagster:
    code_location: dativo-etl
    repository: etl_jobs
    op_config:
      max_retries: 3
      retry_delay_seconds: 60
    resource_requirements:
      request_cpu: "2"
      request_memory: "4Gi"
      limit_cpu: "4"
      limit_memory: "8Gi"
```

## Tag Propagation

Tags flow from three sources with this precedence (highest to lowest):

1. **Job-level tags** (`infrastructure.tags`, `finops`)
2. **Asset-level tags** (`compliance`, `finops` in asset definition)
3. **Default tags** (tenant_id, environment, job name)

### Example: Complete Tag Flow

**Asset Definition** (`assets/stripe/v1.0/customers.yaml`):
```yaml
name: stripe_customers
compliance:
  classification: [PII, SENSITIVE]
  regulations: [GDPR, CCPA]
finops:
  cost_center: FIN-001
  project: data-platform
```

**Job Configuration** (`jobs/acme/stripe_customers.yaml`):
```yaml
tenant_id: acme
environment: prod

finops:
  cost_center: HR-001  # Overrides asset cost_center
  business_tags: [payments, revenue]

infrastructure:
  tags:
    Team: data-engineering
    Owner: data-team@acme.com
```

**Resulting Tags** (applied to all infrastructure):
```yaml
# From asset (lowest priority)
classification.default: pii
compliance.regulations: GDPR,CCPA

# From job finops (medium priority)
finops.cost_center: HR-001           # Overrode asset's FIN-001
finops.business_tags: payments,revenue
finops.project: data-platform        # Inherited from asset

# From infrastructure.tags (highest priority)
Team: data-engineering
Owner: data-team@acme.com

# Auto-generated
tenant_id: acme
environment: prod
```

These tags are applied to:
- ✅ AWS resources (ECS tasks, EC2 instances, Lambda functions)
- ✅ GCP resources (Cloud Run services, Compute Engine instances)
- ✅ Storage buckets (S3, GCS)
- ✅ Networking resources (VPC, subnets, security groups)
- ✅ Iceberg tables (table properties)
- ✅ Terraform state and outputs

## Terraform Module Integration

### Module Requirements

Your Terraform module should accept these variables from Dativo:

```hcl
# modules/dativo-etl-job/variables.tf

variable "job_name" {
  description = "Job name from Dativo configuration"
  type        = string
}

variable "tenant_id" {
  description = "Tenant ID from Dativo configuration"
  type        = string
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
}

variable "provider" {
  description = "Cloud provider (aws, gcp, azure)"
  type        = string
}

variable "runtime_type" {
  description = "Runtime type (dagster, airflow, kubernetes, ecs, cloud_run)"
  type        = string
}

variable "compute_cpu" {
  description = "CPU request"
  type        = string
  default     = "1"
}

variable "compute_memory" {
  description = "Memory request"
  type        = string
  default     = "2Gi"
}

variable "compute_instance_type" {
  description = "Cloud instance type"
  type        = string
  default     = null
}

variable "networking_vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "networking_subnet_ids" {
  description = "Subnet IDs"
  type        = list(string)
}

variable "networking_security_group_ids" {
  description = "Security group IDs"
  type        = list(string)
  default     = []
}

variable "storage_bucket" {
  description = "Storage bucket name"
  type        = string
}

variable "storage_prefix" {
  description = "Storage prefix"
  type        = string
}

variable "storage_kms_key_id" {
  description = "KMS key ID for encryption"
  type        = string
  default     = null
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}

variable "dagster_code_location" {
  description = "Dagster code location name"
  type        = string
  default     = null
}

variable "dagster_repository" {
  description = "Dagster repository name"
  type        = string
  default     = null
}
```

### Module Outputs

Your module should output infrastructure details:

```hcl
# modules/dativo-etl-job/outputs.tf

output "cluster_arn" {
  description = "ECS cluster ARN or GKE cluster name"
  value       = aws_ecs_cluster.dativo.arn
}

output "task_role_arn" {
  description = "Task execution role ARN"
  value       = aws_iam_role.task_role.arn
}

output "security_group_id" {
  description = "Security group ID"
  value       = aws_security_group.dativo.id
}

output "bucket_name" {
  description = "S3 bucket name"
  value       = aws_s3_bucket.data_lake.id
}

output "kms_key_id" {
  description = "KMS key ID"
  value       = aws_kms_key.data.id
}

output "tags" {
  description = "Applied resource tags"
  value       = local.tags
}
```

## Cloud Provider Examples

### AWS with ECS and Dagster

```yaml
# jobs/acme/stripe_customers_aws.yaml
tenant_id: acme
environment: prod

source_connector_path: /app/connectors/stripe.yaml
target_connector_path: /app/connectors/iceberg.yaml
asset_path: /app/assets/stripe/v1.0/customers.yaml

infrastructure:
  provider: aws
  
  runtime:
    type: ecs
    cluster_name: dativo-prod-cluster
    namespace: etl-jobs
    service_account: arn:aws:iam::123456789012:role/dativo-etl-role
  
  compute:
    cpu: "2048"           # 2 vCPU in ECS units
    memory: "4096"        # 4GB in MB
    instance_type: t3.medium
    max_runtime_seconds: 3600
  
  networking:
    vpc_id: vpc-0123456789abcdef0
    subnet_ids:
      - subnet-0123456789abcdef0  # us-east-1a
      - subnet-0123456789abcdef1  # us-east-1b
    security_group_ids:
      - sg-0123456789abcdef0
    private_networking: true
  
  storage:
    bucket: acme-data-lake
    prefix: raw/stripe/customers
    kms_key_id: arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-123456789012
  
  tags:
    CostCenter: HR-001
    Project: data-platform
    Environment: production
    ManagedBy: terraform
  
  terraform:
    module_source: git::https://github.com/acme/terraform-aws-dativo.git//modules/ecs-etl-job
    module_version: "1.2.0"
    workspace: prod
    backend_config:
      bucket: acme-terraform-state
      key: dativo/etl-jobs/stripe-customers.tfstate
      region: us-east-1
      dynamodb_table: terraform-state-lock
  
  dagster:
    code_location: dativo-etl-prod
    repository: etl_jobs
    resource_requirements:
      request_cpu: "2048"
      request_memory: "4096"
      limit_cpu: "4096"
      limit_memory: "8192"

finops:
  cost_center: HR-001
  business_tags: [payments, revenue, stripe]
  project: data-platform
  environment: production
```

### GCP with Cloud Run and Dagster

```yaml
# jobs/acme/stripe_customers_gcp.yaml
tenant_id: acme
environment: prod

source_connector_path: /app/connectors/stripe.yaml
target_connector_path: /app/connectors/iceberg.yaml
asset_path: /app/assets/stripe/v1.0/customers.yaml

infrastructure:
  provider: gcp
  
  runtime:
    type: cloud_run
    cluster_name: dativo-prod
    namespace: etl-jobs
    service_account: dativo-etl@acme-project.iam.gserviceaccount.com
  
  compute:
    cpu: "2"
    memory: "4Gi"
    max_runtime_seconds: 3600
  
  networking:
    vpc_id: projects/acme-project/global/networks/dativo-vpc
    subnet_ids:
      - projects/acme-project/regions/us-central1/subnetworks/dativo-subnet
    private_networking: true
  
  storage:
    bucket: acme-data-lake
    prefix: raw/stripe/customers
    kms_key_id: projects/acme-project/locations/us-central1/keyRings/dativo/cryptoKeys/etl-data
  
  tags:
    cost-center: hr-001
    project: data-platform
    environment: production
    managed-by: terraform
  
  terraform:
    module_source: git::https://github.com/acme/terraform-gcp-dativo.git//modules/cloud-run-etl-job
    module_version: "1.2.0"
    workspace: prod
    backend_config:
      bucket: acme-terraform-state
      prefix: dativo/etl-jobs/stripe-customers
  
  dagster:
    code_location: dativo-etl-prod
    repository: etl_jobs
    resource_requirements:
      request_cpu: "2"
      request_memory: "4Gi"
      limit_cpu: "4"
      limit_memory: "8Gi"

finops:
  cost_center: HR-001
  business_tags: [payments, revenue, stripe]
  project: data-platform
  environment: production
```

### Kubernetes with Dagster

```yaml
# jobs/acme/stripe_customers_k8s.yaml
tenant_id: acme
environment: prod

source_connector_path: /app/connectors/stripe.yaml
target_connector_path: /app/connectors/iceberg.yaml
asset_path: /app/assets/stripe/v1.0/customers.yaml

infrastructure:
  provider: aws  # or gcp
  
  runtime:
    type: kubernetes
    cluster_name: dativo-prod-eks
    namespace: data-engineering
    service_account: dativo-etl-sa
  
  compute:
    cpu: "2"
    memory: "4Gi"
    max_runtime_seconds: 3600
  
  networking:
    private_networking: true
  
  storage:
    bucket: acme-data-lake
    prefix: raw/stripe/customers
  
  tags:
    CostCenter: HR-001
    Project: data-platform
    Environment: production
  
  terraform:
    module_source: git::https://github.com/acme/terraform-k8s-dativo.git//modules/etl-job
    module_version: "1.2.0"
    workspace: prod
  
  dagster:
    code_location: dativo-etl-prod
    repository: etl_jobs
    op_config:
      max_retries: 3
      retry_delay_seconds: 60
    resource_requirements:
      request_cpu: "2"
      request_memory: "4Gi"
      limit_cpu: "4"
      limit_memory: "8Gi"

finops:
  cost_center: HR-001
  business_tags: [payments, revenue, stripe]
  project: data-platform
  environment: production
```

## Multi-Tenant Deployments

### Tenant-Specific Infrastructure

Each tenant can have its own infrastructure configuration:

```yaml
# jobs/acme/stripe_customers.yaml
tenant_id: acme
environment: prod

infrastructure:
  provider: aws
  runtime:
    cluster_name: dativo-acme-prod
    namespace: acme-etl
    service_account: arn:aws:iam::123456789012:role/dativo-acme-etl-role
  networking:
    vpc_id: vpc-acme
    subnet_ids: [subnet-acme-1, subnet-acme-2]
  storage:
    bucket: acme-data-lake
  tags:
    Tenant: acme
```

```yaml
# jobs/globex/stripe_customers.yaml
tenant_id: globex
environment: prod

infrastructure:
  provider: aws
  runtime:
    cluster_name: dativo-globex-prod
    namespace: globex-etl
    service_account: arn:aws:iam::123456789012:role/dativo-globex-etl-role
  networking:
    vpc_id: vpc-globex
    subnet_ids: [subnet-globex-1, subnet-globex-2]
  storage:
    bucket: globex-data-lake
  tags:
    Tenant: globex
```

### Shared Infrastructure with Tenant Isolation

```yaml
# Shared infrastructure with logical tenant isolation
infrastructure:
  provider: aws
  runtime:
    cluster_name: dativo-shared-prod
    namespace: "${tenant_id}-etl"  # Dynamic namespace per tenant
    service_account: "arn:aws:iam::123456789012:role/dativo-${tenant_id}-etl-role"
  storage:
    bucket: dativo-shared-data-lake
    prefix: "${tenant_id}/raw/stripe/customers"  # Tenant-specific prefix
  tags:
    Tenant: "${tenant_id}"
    SharedInfrastructure: "true"
```

## Cost Allocation and Reporting

### Tag Strategy for Cost Allocation

Use consistent tagging for accurate cost allocation:

```yaml
infrastructure:
  tags:
    # Mandatory cost allocation tags
    CostCenter: HR-001
    Project: data-platform
    Environment: production
    Tenant: acme
    
    # Optional organizational tags
    Team: data-engineering
    Owner: data-team@acme.com
    ManagedBy: terraform
    
    # Compliance tags
    DataClassification: PII
    Compliance: GDPR
    
    # Business tags
    BusinessUnit: sales
    Application: customer-analytics
```

### Cost Allocation Report Example

Query AWS Cost Explorer or GCP Cost Management with tags:

**AWS CLI Example:**
```bash
aws ce get-cost-and-usage \
  --time-period Start=2025-01-01,End=2025-01-31 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --group-by Type=TAG,Key=CostCenter \
  --group-by Type=TAG,Key=Project \
  --filter file://cost-filter.json
```

**cost-filter.json:**
```json
{
  "Tags": {
    "Key": "Tenant",
    "Values": ["acme"],
    "MatchOptions": ["EQUALS"]
  }
}
```

## Best Practices

### 1. Tag Consistency

- Use consistent tag naming conventions across all environments
- Use PascalCase for AWS (`CostCenter`) and kebab-case for GCP (`cost-center`)
- Define required vs. optional tags in your organization policy

### 2. Infrastructure as Code

- Always use Terraform modules for infrastructure provisioning
- Version your Terraform modules
- Use remote state backends (S3, GCS) with state locking
- Document module variables and outputs

### 3. Security

- Use private networking by default (`private_networking: true`)
- Enable encryption at rest with KMS keys
- Use least-privilege IAM roles/service accounts
- Rotate credentials regularly

### 4. Resource Management

- Set appropriate CPU and memory limits
- Use `max_runtime_seconds` to prevent runaway jobs
- Monitor resource utilization and adjust as needed
- Use auto-scaling where supported

### 5. Monitoring and Observability

- Propagate tags to monitoring systems (CloudWatch, Stackdriver)
- Set up alerts for job failures and resource exhaustion
- Track job execution metrics (duration, cost, data volume)
- Use distributed tracing (OpenTelemetry)

### 6. Multi-Tenant Isolation

- Use separate VPCs/networks for tenant isolation
- Use tenant-specific IAM roles/service accounts
- Implement network policies to prevent cross-tenant access
- Use separate storage buckets or prefixes per tenant

## Troubleshooting

### Infrastructure Validation Errors

**Error**: `Invalid provider: xyz. Must be one of: aws, gcp, azure`

**Solution**: Ensure `provider` is set to one of the supported values.

### Terraform Module Not Found

**Error**: `Failed to load Terraform module from source`

**Solution**: 
- Verify `module_source` is accessible
- Check authentication for private Git repositories
- Ensure `module_version` is valid

### Tag Propagation Issues

**Error**: `Tags not appearing on cloud resources`

**Solution**:
- Verify Terraform module accepts `tags` variable
- Check IAM permissions for tagging resources
- Ensure tags don't exceed cloud provider limits (AWS: 50 tags, GCP: 64 labels)

### Resource Limit Exceeded

**Error**: `Insufficient CPU/memory resources`

**Solution**:
- Increase `compute.cpu` and `compute.memory`
- Use larger `instance_type`
- Check cluster capacity (Kubernetes/ECS)

## Migration from Legacy Infrastructure

### Step 1: Identify Current Infrastructure

Document existing infrastructure:
- Cloud provider and regions
- Compute resources (ECS clusters, GKE clusters)
- Networking (VPCs, subnets, security groups)
- Storage (S3 buckets, GCS buckets)
- IAM roles and service accounts

### Step 2: Create Terraform Modules

Create Terraform modules to match existing infrastructure:

```hcl
# modules/legacy-ecs-etl/main.tf
resource "aws_ecs_task_definition" "dativo" {
  family = var.job_name
  # ... existing configuration ...
  
  tags = merge(
    var.tags,
    {
      ManagedBy = "terraform"
      MigratedFrom = "manual"
    }
  )
}
```

### Step 3: Add Infrastructure Blocks

Add `infrastructure` blocks to existing job configurations:

```yaml
# Before (no infrastructure block)
tenant_id: acme
source_connector_path: /app/connectors/stripe.yaml
target_connector_path: /app/connectors/iceberg.yaml
asset_path: /app/assets/stripe/v1.0/customers.yaml

# After (with infrastructure block)
tenant_id: acme
source_connector_path: /app/connectors/stripe.yaml
target_connector_path: /app/connectors/iceberg.yaml
asset_path: /app/assets/stripe/v1.0/customers.yaml

infrastructure:
  provider: aws
  runtime:
    type: ecs
    cluster_name: existing-cluster  # Reference existing infrastructure
    service_account: arn:aws:iam::123456789012:role/existing-role
  # ... rest of configuration ...
```

### Step 4: Test and Validate

1. Validate job configuration:
   ```bash
   dativo run --config jobs/acme/stripe_customers.yaml --mode self_hosted --dry-run
   ```

2. Run Terraform plan:
   ```bash
   terraform plan -var-file=jobs/acme/stripe_customers.tfvars
   ```

3. Apply infrastructure:
   ```bash
   terraform apply
   ```

4. Run job with new infrastructure:
   ```bash
   dativo run --config jobs/acme/stripe_customers.yaml --mode self_hosted
   ```

## Next Steps

1. **Define Infrastructure Standards**: Create organization-wide standards for infrastructure configuration
2. **Create Terraform Modules**: Build reusable Terraform modules for common deployment patterns
3. **Implement Tag Policies**: Define required tags and validation rules
4. **Set Up Cost Monitoring**: Configure cost allocation reports and alerts
5. **Automate Deployment**: Integrate infrastructure provisioning into CI/CD pipelines
6. **Monitor and Optimize**: Track resource utilization and optimize configurations

## References

- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [Terraform GCP Provider](https://registry.terraform.io/providers/hashicorp/google/latest/docs)
- [Dagster Deployment](https://docs.dagster.io/deployment)
- [AWS ECS Best Practices](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/)
- [GCP Cloud Run Best Practices](https://cloud.google.com/run/docs/best-practices)
- [AWS Tagging Best Practices](https://docs.aws.amazon.com/general/latest/gr/aws_tagging.html)
- [GCP Resource Labels Best Practices](https://cloud.google.com/resource-manager/docs/creating-managing-labels)
