# Terraform Infrastructure Integration for Dativo ETL Jobs

This guide explains how to integrate externally-managed infrastructure (via Terraform) with Dativo ETL job definitions in a cloud-agnostic manner.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Job Configuration Extension](#job-configuration-extension)
- [Terraform Module Integration](#terraform-module-integration)
- [Tag Propagation Strategy](#tag-propagation-strategy)
- [Cloud Provider Support](#cloud-provider-support)
- [End-to-End Workflow](#end-to-end-workflow)
- [CI/CD Integration](#cicd-integration)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

## Overview

Dativo ETL jobs can now reference externally-managed infrastructure provisioned via Terraform. This allows:

- **Separation of Concerns**: Infrastructure team manages runtime environments via Terraform; data team manages ETL job definitions
- **Cloud Agnostic**: Support for AWS Fargate, Azure Container Apps, and GCP Cloud Run
- **Tag Propagation**: Job metadata flows into Terraform and tags all infrastructure resources for cost allocation and compliance
- **Placeholder Resolution**: Job configs use `{{terraform_outputs.*}}` placeholders that are resolved after Terraform provisioning

### Key Benefits

1. **Cost Allocation**: All infrastructure resources tagged with job metadata (job_name, team, cost_center, etc.)
2. **Compliance**: Consistent tagging strategy for auditing and resource classification
3. **Flexibility**: Choose runtime environment per job (AWS, Azure, GCP)
4. **Traceability**: Every resource traceable back to the Dativo job that uses it

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Dativo Job Definition                        │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ infrastructure:                                             │ │
│  │   provider: aws                                             │ │
│  │   runtime:                                                  │ │
│  │     type: aws_fargate                                       │ │
│  │   tags:                                                     │ │
│  │     job_name: stripe-customers-etl                          │ │
│  │     team: data-engineering                                  │ │
│  │     cost_center: data-platform                              │ │
│  │   resource_identifiers:                                     │ │
│  │     cluster_name: "{{terraform_outputs.cluster_name}}"      │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Tags extracted
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Terraform Configuration                       │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ module "dativo_runtime" {                                   │ │
│  │   source = ".../aws_fargate"                                │ │
│  │   job_metadata = {                                          │ │
│  │     job_name: "stripe-customers-etl"                        │ │
│  │     team: "data-engineering"                                │ │
│  │     cost_center: "data-platform"                            │ │
│  │     ...                                                     │ │
│  │   }                                                         │ │
│  │ }                                                           │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ terraform apply
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Cloud Provider Infrastructure                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ ✓ ECS Cluster (AWS Fargate)                                │ │
│  │ ✓ Task Definition                                           │ │
│  │ ✓ IAM Roles                                                 │ │
│  │ ✓ CloudWatch Logs                                           │ │
│  │                                                             │ │
│  │ ALL tagged with:                                            │ │
│  │   - job_name: stripe-customers-etl                          │ │
│  │   - team: data-engineering                                  │ │
│  │   - cost_center: data-platform                              │ │
│  │   - managed_by: terraform                                   │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Terraform outputs
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Terraform Outputs                          │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ {                                                           │ │
│  │   "cluster_name": "stripe-customers-etl-prod-cluster",      │ │
│  │   "task_definition_arn": "arn:aws:ecs:...",                │ │
│  │   "service_name": "stripe-customers-etl-prod-service"       │ │
│  │ }                                                           │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Placeholder substitution
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│               Updated Dativo Job Configuration                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ infrastructure:                                             │ │
│  │   resource_identifiers:                                     │ │
│  │     cluster_name: "stripe-customers-etl-prod-cluster"       │ │
│  │     task_definition_arn: "arn:aws:ecs:..."                 │ │
│  │     service_name: "stripe-customers-etl-prod-service"       │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Deploy job
                              ▼
                      Dativo Job Execution
```

## Job Configuration Extension

### Infrastructure Section Schema

Add an `infrastructure` section to your job definition YAML:

```yaml
infrastructure:
  provider: aws | azure | gcp
  runtime:
    type: aws_fargate | azure_container_apps | gcp_cloud_run
    image: <container_image_uri>
    cpu: <cpu_allocation>
    memory: <memory_allocation>
  region: <cloud_region>
  resource_identifiers:
    # Placeholders replaced with Terraform outputs
    cluster_name: "{{terraform_outputs.cluster_name}}"
    service_name: "{{terraform_outputs.service_name}}"
    # ... other resource identifiers
  tags:
    # Required tags (minimum set)
    job_name: <job_identifier>
    team: <owning_team>
    pipeline_type: <pipeline_category>
    environment: <deployment_env>
    cost_center: <cost_allocation_id>
    # Optional tags
    project: <project_name>
    owner: <owner_email>
```

### Required Fields

| Field | Required | Description |
|-------|----------|-------------|
| `provider` | Yes | Cloud provider: `aws`, `azure`, or `gcp` |
| `runtime.type` | Yes | Runtime type: `aws_fargate`, `azure_container_apps`, or `gcp_cloud_run` |
| `region` | Yes | Cloud region (e.g., `us-east-1`, `eastus`, `us-central1`) |
| `tags.job_name` | Yes | Unique job identifier |
| `tags.team` | Yes | Owning team |
| `tags.pipeline_type` | Yes | Pipeline category (e.g., `ingestion`, `transformation`) |
| `tags.environment` | Yes | Environment (e.g., `dev`, `staging`, `prod`) |
| `tags.cost_center` | Yes | Cost allocation identifier |

### Provider-Runtime Compatibility

| Provider | Allowed Runtime Types |
|----------|----------------------|
| `aws` | `aws_fargate` |
| `azure` | `azure_container_apps` |
| `gcp` | `gcp_cloud_run` |

Validation will fail if you specify an incompatible combination.

## Terraform Module Integration

### Module Structure

Dativo provides three Terraform modules for runtime provisioning:

```
terraform/modules/
├── aws_fargate/
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   └── README.md
├── azure_container_apps/
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   └── README.md
└── gcp_cloud_run/
    ├── main.tf
    ├── variables.tf
    ├── outputs.tf
    └── README.md
```

### Using the Modules

#### AWS Fargate Example

```hcl
module "stripe_customers_runtime" {
  source = "git::ssh://git@github.com/your-org/terraform-modules.git//dativo_runtime/aws_fargate"

  region = "us-east-1"

  # Job metadata from Dativo job config
  job_metadata = {
    job_name      = "stripe-customers-etl"
    team          = "data-engineering"
    pipeline_type = "ingestion"
    environment   = "prod"
    cost_center   = "data-platform"
  }

  # Default tags applied to all resources
  default_tags = {
    project     = "dativo-platform"
    managed_by  = "terraform"
  }

  # Container configuration
  container_image = "123456789012.dkr.ecr.us-east-1.amazonaws.com/dativo:1.1.0"
  cpu             = "1024"
  memory          = "2048"

  # Networking
  vpc_id             = var.vpc_id
  private_subnet_ids = var.private_subnet_ids

  # Permissions
  s3_bucket_arns = [
    "arn:aws:s3:::acme-data-lake",
    "arn:aws:s3:::acme-data-lake/*"
  ]
}

# Capture outputs for Dativo job config
output "cluster_name" {
  value = module.stripe_customers_runtime.cluster_name
}

output "task_definition_arn" {
  value = module.stripe_customers_runtime.task_definition_arn
}

output "service_name" {
  value = module.stripe_customers_runtime.service_name
}
```

#### Azure Container Apps Example

```hcl
module "hubspot_contacts_runtime" {
  source = "git::ssh://git@github.com/your-org/terraform-modules.git//dativo_runtime/azure_container_apps"

  region = "eastus"

  # Job metadata from Dativo job config
  job_metadata = {
    job_name      = "hubspot-contacts-etl"
    team          = "data-engineering"
    pipeline_type = "ingestion"
    environment   = "prod"
    cost_center   = "data-platform"
  }

  # Container configuration
  container_image = "acmeregistry.azurecr.io/dativo:1.1.0"
  cpu             = 1.0
  memory          = "2Gi"

  # Scaling
  min_replicas = 0
  max_replicas = 1

  # Permissions
  storage_account_ids = [
    "/subscriptions/.../storageAccounts/acmedatalake"
  ]
}

output "cluster_name" {
  value = module.hubspot_contacts_runtime.cluster_name
}

output "service_name" {
  value = module.hubspot_contacts_runtime.service_name
}
```

#### GCP Cloud Run Example

```hcl
module "postgres_orders_runtime" {
  source = "git::ssh://git@github.com/your-org/terraform-modules.git//dativo_runtime/gcp_cloud_run"

  project_id = "acme-data-platform"
  region     = "us-central1"

  # Job metadata from Dativo job config
  job_metadata = {
    job_name      = "postgres-orders-etl"
    team          = "data-engineering"
    pipeline_type = "ingestion"
    environment   = "prod"
    cost_center   = "data-platform"
  }

  # Container configuration
  container_image = "us-central1-docker.pkg.dev/acme-data-platform/dativo/dativo:1.1.0"
  cpu             = "1"
  memory          = "2Gi"

  # Permissions
  storage_bucket_names = ["acme-data-lake"]
}

output "cluster_name" {
  value = module.postgres_orders_runtime.cluster_name
}

output "service_name" {
  value = module.postgres_orders_runtime.service_name
}
```

## Tag Propagation Strategy

### How Tags Flow from Job Config to Infrastructure

1. **Job Definition**: Data team defines tags in job config YAML
2. **Terraform Variables**: Tags passed to Terraform module as `job_metadata` variable
3. **Resource Tagging**: Terraform module applies tags to ALL provisioned resources
4. **Tag Merging**: Module merges `default_tags` + `job_metadata` + module-specific tags

### Tagging Best Practices

#### Required Tags (Enforced by Validation)

- `job_name`: Unique identifier for the Dativo job
- `team`: Owning team (for accountability)
- `pipeline_type`: Category (ingestion, transformation, analytics, etc.)
- `environment`: Deployment environment (dev, staging, prod)
- `cost_center`: Cost allocation identifier (for FinOps)

#### Recommended Additional Tags

- `project`: Project or product name
- `owner`: Owner email or contact
- `version`: Job version
- `criticality`: Business criticality (high, medium, low)
- `compliance`: Compliance requirements (GDPR, HIPAA, SOC2, etc.)

#### Tag Naming Conventions

**AWS:**
- Use PascalCase for tag keys: `CostCenter`, `JobName`
- Maximum 128 characters for keys and 256 for values
- Case-sensitive

**Azure:**
- Use lowercase with hyphens: `cost-center`, `job-name`
- Maximum 512 characters for keys and 256 for values
- Case-insensitive

**GCP:**
- Use lowercase with underscores/hyphens: `cost_center`, `job-name`
- Maximum 63 characters for keys and values
- Only lowercase alphanumeric, underscore, hyphen allowed

**Dativo Approach:** Define tags in job config as `lowercase_underscore` format. Terraform modules handle conversion to cloud-specific format.

### Tag Propagation Example

**Job Config (`stripe_customers_to_iceberg.yaml`):**

```yaml
infrastructure:
  tags:
    job_name: stripe-customers-etl
    team: data-engineering
    pipeline_type: ingestion
    environment: prod
    cost_center: data-platform
    project: dativo-platform
```

**Terraform Module (AWS Fargate):**

```hcl
locals {
  common_tags = merge(
    var.default_tags,
    var.job_metadata,
    {
      "managed_by"     = "terraform"
      "dativo_runtime" = "aws_fargate"
    }
  )
}

# All resources get these tags
resource "aws_ecs_cluster" "dativo_cluster" {
  name = "..."
  tags = local.common_tags  # ← Applied here
}

resource "aws_iam_role" "ecs_task_role" {
  name = "..."
  tags = local.common_tags  # ← And here
}

# ... all other resources
```

**Resulting AWS Tags:**

```
CostCenter:      data-platform
Environment:     prod
JobName:         stripe-customers-etl
ManagedBy:       terraform
PipelineType:    ingestion
Project:         dativo-platform
Team:            data-engineering
DativoRuntime:   aws_fargate
```

## Cloud Provider Support

### AWS Fargate

**Runtime Type:** `aws_fargate`

**Features:**
- ECS Fargate cluster
- Task definitions with configurable CPU/memory
- IAM roles for S3 and Secrets Manager access
- CloudWatch Logs integration
- Optional ECS Service for long-running jobs

**Module Location:** `terraform/modules/aws_fargate/`

**Example Job Config:**

```yaml
infrastructure:
  provider: aws
  runtime:
    type: aws_fargate
    image: "123456789012.dkr.ecr.us-east-1.amazonaws.com/dativo:1.1.0"
    cpu: "1024"
    memory: "2048"
  region: us-east-1
  resource_identifiers:
    cluster_name: "{{terraform_outputs.cluster_name}}"
    task_definition_arn: "{{terraform_outputs.task_definition_arn}}"
  tags:
    job_name: stripe-customers-etl
    team: data-engineering
    pipeline_type: ingestion
    environment: prod
    cost_center: data-platform
```

### Azure Container Apps

**Runtime Type:** `azure_container_apps`

**Features:**
- Container Apps Environment
- Container App or Container App Job
- Managed Identity for Azure resource access
- Log Analytics integration
- Auto-scaling with scale-to-zero

**Module Location:** `terraform/modules/azure_container_apps/`

**Example Job Config:**

```yaml
infrastructure:
  provider: azure
  runtime:
    type: azure_container_apps
    image: "acmeregistry.azurecr.io/dativo:1.1.0"
    cpu: "1.0"
    memory: "2Gi"
  region: eastus
  resource_identifiers:
    cluster_name: "{{terraform_outputs.cluster_name}}"
    service_name: "{{terraform_outputs.service_name}}"
  tags:
    job_name: hubspot-contacts-etl
    team: data-engineering
    pipeline_type: ingestion
    environment: prod
    cost_center: data-platform
```

### GCP Cloud Run

**Runtime Type:** `gcp_cloud_run`

**Features:**
- Cloud Run Service or Job
- Service Account with IAM bindings
- Secret Manager integration
- Cloud Scheduler support
- Scale-to-zero with automatic scaling

**Module Location:** `terraform/modules/gcp_cloud_run/`

**Example Job Config:**

```yaml
infrastructure:
  provider: gcp
  runtime:
    type: gcp_cloud_run
    image: "us-central1-docker.pkg.dev/acme/dativo/dativo:1.1.0"
    cpu: "1"
    memory: "2Gi"
  region: us-central1
  resource_identifiers:
    cluster_name: "{{terraform_outputs.cluster_name}}"
    service_name: "{{terraform_outputs.service_name}}"
  tags:
    job_name: postgres-orders-etl
    team: data-engineering
    pipeline_type: ingestion
    environment: prod
    cost_center: data-platform
```

## End-to-End Workflow

### Step 1: Define Dativo Job with Infrastructure Section

Create job config: `jobs/acme/stripe_customers_to_iceberg.yaml`

```yaml
tenant_id: acme
environment: prod

source_connector: stripe
source_connector_path: /app/connectors/stripe.yaml

target_connector: iceberg
target_connector_path: /app/connectors/iceberg.yaml

asset: stripe_customers
asset_path: /app/assets/stripe/v1.0/customers.yaml

source:
  objects: [customers]

target:
  connection:
    s3:
      bucket: "acme-data-lake"

infrastructure:
  provider: aws
  runtime:
    type: aws_fargate
  region: us-east-1
  resource_identifiers:
    cluster_name: "{{terraform_outputs.cluster_name}}"
  tags:
    job_name: stripe-customers-etl
    team: data-engineering
    pipeline_type: ingestion
    environment: prod
    cost_center: data-platform
```

### Step 2: Extract Tags and Create Terraform Configuration

Create Terraform config: `terraform/dativo_jobs/stripe_customers.tf`

```hcl
module "stripe_customers_runtime" {
  source = "../modules/aws_fargate"

  region = "us-east-1"

  # Tags from job config
  job_metadata = {
    job_name      = "stripe-customers-etl"
    team          = "data-engineering"
    pipeline_type = "ingestion"
    environment   = "prod"
    cost_center   = "data-platform"
  }

  container_image    = "123456789012.dkr.ecr.us-east-1.amazonaws.com/dativo:1.1.0"
  cpu                = "1024"
  memory             = "2048"
  vpc_id             = var.vpc_id
  private_subnet_ids = var.private_subnet_ids
  s3_bucket_arns     = ["arn:aws:s3:::acme-data-lake", "arn:aws:s3:::acme-data-lake/*"]
}

output "stripe_customers_cluster_name" {
  value = module.stripe_customers_runtime.cluster_name
}
```

### Step 3: Run Terraform Apply

```bash
cd terraform/dativo_jobs
terraform init
terraform plan
terraform apply
```

**Terraform Output:**

```json
{
  "stripe_customers_cluster_name": {
    "value": "stripe-customers-etl-prod-cluster"
  }
}
```

### Step 4: Update Job Config with Terraform Outputs

Either manually or via automation, replace placeholders in job config:

```yaml
infrastructure:
  resource_identifiers:
    cluster_name: "stripe-customers-etl-prod-cluster"  # ← Updated
```

### Step 5: Validate and Deploy Dativo Job

```bash
# Validate job config
dativo_ingest run --config jobs/acme/stripe_customers_to_iceberg.yaml --mode cloud --validate-only

# Deploy job
dativo_ingest run --config jobs/acme/stripe_customers_to_iceberg.yaml --mode cloud
```

## CI/CD Integration

See [CI/CD workflow examples](./TERRAFORM_CICD_WORKFLOWS.md) for complete GitHub Actions workflows.

### High-Level CI/CD Flow

```
┌─────────────────┐
│ Developer       │
│ Updates Job     │
│ Config          │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Git Push        │
│ Trigger CI/CD   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────┐
│ CI/CD Pipeline                  │
│ ┌─────────────────────────────┐ │
│ │ 1. Extract tags from job    │ │
│ │    config                   │ │
│ │ 2. Generate Terraform vars  │ │
│ │ 3. Run terraform apply      │ │
│ │ 4. Capture outputs          │ │
│ │ 5. Update job config        │ │
│ │ 6. Deploy Dativo job        │ │
│ └─────────────────────────────┘ │
└─────────────────────────────────┘
```

## Best Practices

### 1. Tag Consistency

✅ **DO:**
- Use consistent tag keys across all jobs
- Enforce required tags via validation
- Document tagging strategy for your organization

❌ **DON'T:**
- Mix naming conventions (e.g., `CostCenter` vs `cost_center`)
- Create ad-hoc tags without documentation
- Omit required tags

### 2. Terraform State Management

✅ **DO:**
- Use remote state backend (S3, Azure Storage, GCS)
- Enable state locking
- Use workspaces for environment isolation

❌ **DON'T:**
- Commit terraform.tfstate to git
- Share state files via file system
- Mix environments in same state

### 3. Security

✅ **DO:**
- Use managed identities (Azure) or service accounts (GCP)
- Store secrets in cloud-native secret managers
- Apply least-privilege IAM policies
- Enable encryption at rest for logs

❌ **DON'T:**
- Hard-code credentials in Terraform
- Grant overly broad IAM permissions
- Store secrets in environment variables

### 4. Cost Optimization

✅ **DO:**
- Enable scale-to-zero for batch jobs
- Right-size CPU/memory allocations
- Configure appropriate log retention
- Use tagging for cost allocation reports

❌ **DON'T:**
- Over-provision resources "just in case"
- Run long-lived services for batch workloads
- Ignore cost allocation tags

### 5. Terraform Module Versioning

✅ **DO:**
- Pin module versions: `source = "...?ref=v1.2.3"`
- Use semantic versioning
- Test module upgrades in non-prod first

❌ **DON'T:**
- Use `ref=main` in production
- Deploy untested module versions

## Troubleshooting

### Validation Errors

**Error:** `Missing required tags: cost_center`

**Solution:** Add all required tags to `infrastructure.tags` section:

```yaml
infrastructure:
  tags:
    job_name: my-job
    team: my-team
    pipeline_type: ingestion
    environment: prod
    cost_center: data-platform  # ← Add this
```

---

**Error:** `Runtime type 'aws_fargate' is not compatible with provider 'azure'`

**Solution:** Match provider with runtime type:

| Provider | Runtime Type |
|----------|--------------|
| `aws` | `aws_fargate` |
| `azure` | `azure_container_apps` |
| `gcp` | `gcp_cloud_run` |

---

**Error:** `Malformed Terraform output placeholder`

**Solution:** Use correct placeholder format:

```yaml
# ❌ Wrong
cluster_name: "{terraform_outputs.cluster_name}"

# ✅ Correct
cluster_name: "{{terraform_outputs.cluster_name}}"
```

### Terraform Errors

**Error:** `job_metadata must contain: job_name, team, ...`

**Solution:** Ensure all required keys present in `job_metadata` variable:

```hcl
job_metadata = {
  job_name      = "my-job"          # Required
  team          = "my-team"         # Required
  pipeline_type = "ingestion"       # Required
  environment   = "prod"            # Required
  cost_center   = "data-platform"   # Required
}
```

---

**Error:** `Error creating ECS Cluster: AccessDeniedException`

**Solution:** Verify Terraform execution role has necessary permissions:
- `ecs:CreateCluster`
- `iam:CreateRole`
- `logs:CreateLogGroup`
- etc.

### Placeholder Resolution Issues

**Problem:** Placeholders not replaced after Terraform apply

**Solution:** Ensure placeholder substitution happens in your workflow:

```bash
# Capture Terraform outputs
terraform output -json > outputs.json

# Replace placeholders (example using jq)
jq -r '.cluster_name.value' outputs.json | \
  sed -i "s/{{terraform_outputs.cluster_name}}/$(cat)/g" job_config.yaml
```

## Additional Resources

- [Terraform Module Documentation](../terraform/modules/)
  - [AWS Fargate Module](../terraform/modules/aws_fargate/README.md)
  - [Azure Container Apps Module](../terraform/modules/azure_container_apps/README.md)
  - [GCP Cloud Run Module](../terraform/modules/gcp_cloud_run/README.md)
- [CI/CD Workflow Examples](./TERRAFORM_CICD_WORKFLOWS.md)
- [Example Job Definitions](../docs/examples/jobs/acme/)
- [AWS Tagging Best Practices](https://docs.aws.amazon.com/whitepapers/latest/tagging-best-practices/tagging-best-practices.html)
- [Azure Tagging Strategy](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-tagging)
- [GCP Labeling Best Practices](https://cloud.google.com/resource-manager/docs/creating-managing-labels)

## Support

For issues or questions:
1. Check [Troubleshooting](#troubleshooting) section
2. Review module-specific README files
3. Open an issue on the repository
4. Contact the Dativo platform team
