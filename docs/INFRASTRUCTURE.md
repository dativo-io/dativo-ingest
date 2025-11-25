# Infrastructure Configuration

Job definitions can reference infrastructure provisioned outside of Dativo (e.g., via Terraform, CloudFormation, or Pulumi). The `infrastructure` block describes the runtime environment and metadata that flows into infrastructure-as-code modules.

## Table of Contents

1. [Overview](#overview)
2. [Use Cases](#use-cases)
3. [Schema Reference](#schema-reference)
4. [Examples](#examples)
5. [Integration Patterns](#integration-patterns)
6. [Best Practices](#best-practices)

---

## Overview

The `infrastructure` block enables Dativo to:
- **Reference pre-provisioned resources** (compute clusters, VPCs, storage buckets)
- **Pass metadata to infrastructure-as-code** (Terraform variables, tags, labels)
- **Specify runtime requirements** (platform, compute specs, networking)
- **Track infrastructure dependencies** (Terraform modules, workspaces, backends)

This decouples job definitions from infrastructure provisioning while maintaining clear contracts between data pipelines and underlying resources.

---

## Use Cases

### 1. Terraform-Provisioned EMR Cluster
Reference an EMR cluster provisioned by Terraform, passing job-specific metadata:

```yaml
infrastructure:
  provider: terraform
  terraform:
    module_source: "git::https://github.com/org/infra.git//modules/emr"
    module_version: "v2.1.0"
    workspace: "prod"
  runtime:
    platform: emr
    compute:
      cluster_id: "${EMR_CLUSTER_ID}"  # From Terraform output
      instance_type: "m5.xlarge"
      instance_count: 5
  metadata:
    tags:
      CostCenter: "data-engineering"
      Project: "customer-analytics"
      Environment: "production"
```

### 2. Kubernetes Namespace with Network Policies
Run jobs in a pre-provisioned Kubernetes namespace with network isolation:

```yaml
infrastructure:
  provider: terraform
  runtime:
    platform: kubernetes
    namespace: "data-pipelines-prod"
    service_account: "dativo-job-runner"
    network:
      vpc_id: "vpc-0a1b2c3d"
      subnet_ids: ["subnet-abc123", "subnet-def456"]
      security_group_ids: ["sg-xyz789"]
  metadata:
    labels:
      app: "dativo-ingestion"
      team: "data-platform"
      tenant: "acme"
```

### 3. Databricks Job with Pre-Provisioned Cluster
Reference a Databricks cluster with auto-scaling:

```yaml
infrastructure:
  provider: databricks
  runtime:
    platform: databricks
    compute:
      cluster_id: "0123-456789-abc123"
      auto_scaling:
        enabled: true
        min_instances: 2
        max_instances: 10
  metadata:
    tags:
      Owner: "data-team@company.com"
      Workload: "batch-ingestion"
```

### 4. Manual Infrastructure with Resource References
Document manually provisioned resources:

```yaml
infrastructure:
  provider: manual
  runtime:
    platform: ecs
    compute:
      instance_type: "fargate"
  resources:
    database:
      endpoint: "prod-db.cluster-abc.us-east-1.rds.amazonaws.com"
      port: 5432
      database_name: "dativo_state"
      instance_id: "prod-db-instance"
    cache:
      endpoint: "prod-redis.abc123.cache.amazonaws.com"
      cluster_id: "prod-redis-cluster"
    secrets:
      secret_manager_arn: "arn:aws:secretsmanager:us-east-1:123456789:secret:dativo-prod"
      kms_key_id: "arn:aws:kms:us-east-1:123456789:key/abc-123"
```

---

## Schema Reference

### Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `provider` | string | No | Infrastructure provisioning tool (`terraform`, `cloudformation`, `pulumi`, `manual`) |
| `terraform` | object | No | Terraform-specific configuration |
| `runtime` | object | No | Runtime environment specifications |
| `metadata` | object | No | Metadata and variables for infrastructure provisioning |
| `resources` | object | No | Pre-provisioned resource identifiers |
| `outputs` | object | No | Expected outputs from infrastructure provisioning |

### `terraform` Object

| Field | Type | Description |
|-------|------|-------------|
| `module_source` | string | Terraform module source (e.g., `git::https://...` or `./modules/local`) |
| `module_version` | string | Version or ref of the Terraform module |
| `workspace` | string | Terraform workspace name |
| `backend_config` | object | Terraform backend configuration reference |

### `runtime` Object

| Field | Type | Description |
|-------|------|-------------|
| `platform` | string | Execution platform (`kubernetes`, `ecs`, `fargate`, `emr`, `databricks`, `spark`, `ray`, `dask`) |
| `compute` | object | Compute resource specifications |
| `storage` | object | Storage resource specifications |
| `network` | object | Network configuration |
| `namespace` | string | Kubernetes namespace or logical grouping |
| `service_account` | string | Service account or IAM role for execution |

#### `runtime.compute` Object

| Field | Type | Description |
|-------|------|-------------|
| `cluster_id` | string | Pre-provisioned cluster identifier |
| `instance_type` | string | Instance/node type |
| `instance_count` | integer | Number of instances/nodes |
| `auto_scaling` | object | Auto-scaling configuration |
| `auto_scaling.enabled` | boolean | Enable auto-scaling |
| `auto_scaling.min_instances` | integer | Minimum instance count |
| `auto_scaling.max_instances` | integer | Maximum instance count |

#### `runtime.storage` Object

| Field | Type | Description |
|-------|------|-------------|
| `bucket` | string | Pre-provisioned storage bucket name |
| `volume_id` | string | Pre-provisioned volume identifier |
| `mount_path` | string | Mount path for volumes |

#### `runtime.network` Object

| Field | Type | Description |
|-------|------|-------------|
| `vpc_id` | string | VPC identifier |
| `subnet_ids` | array | Subnet identifiers |
| `security_group_ids` | array | Security group identifiers |

### `metadata` Object

| Field | Type | Description |
|-------|------|-------------|
| `tags` | object | Resource tags for infrastructure (key-value pairs) |
| `labels` | object | Kubernetes-style labels (key-value pairs) |
| `annotations` | object | Additional annotations (key-value pairs) |
| `variables` | object | Custom variables passed to infrastructure as code |

### `resources` Object

Pre-provisioned resource identifiers with platform-specific fields:

| Field | Type | Description |
|-------|------|-------------|
| `database` | object | Database configuration (`endpoint`, `port`, `database_name`, `instance_id`) |
| `cache` | object | Cache configuration (`endpoint`, `cluster_id`) |
| `queue` | object | Queue configuration (`url`, `arn`) |
| `secrets` | object | Secrets management (`secret_manager_arn`, `kms_key_id`) |

The `resources` object supports custom fields via `additionalProperties: true`.

---

## Examples

### Complete Terraform + EMR Example

```yaml
tenant_id: acme
environment: prod

source_connector: postgres
source_connector_path: /app/connectors/postgres.yaml

target_connector: iceberg
target_connector_path: /app/connectors/iceberg.yaml

asset: postgres_orders
asset_path: /app/assets/postgres/v1.0/db_orders.yaml

# Infrastructure configuration
infrastructure:
  provider: terraform
  
  # Terraform module configuration
  terraform:
    module_source: "git::https://github.com/acme/infra.git//modules/data-ingestion"
    module_version: "v3.2.1"
    workspace: "prod-data-platform"
    backend_config:
      bucket: "acme-terraform-state"
      key: "data-ingestion/prod/dativo.tfstate"
      region: "us-east-1"
  
  # Runtime environment
  runtime:
    platform: emr
    
    compute:
      cluster_id: "${EMR_CLUSTER_ID}"  # Injected from Terraform output
      instance_type: "r5.2xlarge"
      instance_count: 8
      auto_scaling:
        enabled: true
        min_instances: 4
        max_instances: 12
    
    storage:
      bucket: "acme-data-lake-prod"
      mount_path: "/mnt/data"
    
    network:
      vpc_id: "vpc-0a1b2c3d"
      subnet_ids:
        - "subnet-abc123"
        - "subnet-def456"
      security_group_ids:
        - "sg-ingress-xyz"
        - "sg-egress-abc"
    
    service_account: "arn:aws:iam::123456789:role/DativoEMRRole"
  
  # Metadata for Terraform variables and resource tagging
  metadata:
    tags:
      CostCenter: "data-engineering"
      Project: "customer-analytics"
      Environment: "production"
      ManagedBy: "terraform"
      Owner: "data-team@acme.com"
    
    variables:
      enable_spot_instances: true
      log_retention_days: 30
      enable_encryption: true
      kms_key_alias: "alias/dativo-prod"
  
  # Pre-provisioned resources
  resources:
    database:
      endpoint: "prod-metadata.cluster-abc.us-east-1.rds.amazonaws.com"
      port: 5432
      database_name: "dativo_metadata"
      instance_id: "prod-metadata-db"
    
    secrets:
      secret_manager_arn: "arn:aws:secretsmanager:us-east-1:123456789:secret:dativo/prod"
      kms_key_id: "arn:aws:kms:us-east-1:123456789:key/abc-123-def-456"
  
  # Expected outputs from Terraform
  outputs:
    cluster_dns: "output.emr_cluster_dns"
    master_public_dns: "output.emr_master_public_dns"
    log_bucket: "output.emr_log_bucket"

# Standard job configuration
source:
  connection:
    host: "${POSTGRES_HOST}"
    port: 5432
    database: "orders_db"
  tables:
    - name: orders
      object: orders

target:
  warehouse: "s3://acme-data-lake-prod/warehouse/"
  connection:
    s3:
      bucket: "acme-data-lake-prod"
      prefix: "raw/orders"

logging:
  level: INFO
  redaction: true
```

### Kubernetes Job with GitOps

```yaml
tenant_id: platform
environment: prod

source_connector: stripe
source_connector_path: /app/connectors/stripe.yaml

target_connector: iceberg
target_connector_path: /app/connectors/iceberg.yaml

asset: stripe_customers
asset_path: /app/assets/stripe/v1.0/customers.yaml

# Kubernetes-native infrastructure
infrastructure:
  provider: terraform
  
  terraform:
    module_source: "git::https://github.com/platform/k8s-infra.git//data-pipelines"
    module_version: "v1.5.0"
    workspace: "prod-k8s"
  
  runtime:
    platform: kubernetes
    namespace: "data-ingestion"
    service_account: "dativo-runner"
    
    compute:
      instance_type: "n2-standard-4"
      instance_count: 3
    
    network:
      vpc_id: "projects/acme/global/networks/prod-vpc"
      subnet_ids: ["projects/acme/regions/us-central1/subnetworks/data-subnet"]
  
  metadata:
    labels:
      app: "dativo-ingestion"
      component: "stripe-sync"
      tier: "data-platform"
      managed-by: "terraform"
    
    annotations:
      prometheus.io/scrape: "true"
      prometheus.io/port: "8080"
      fluentd.io/include: "true"
    
    variables:
      resource_requests_cpu: "2000m"
      resource_requests_memory: "8Gi"
      resource_limits_cpu: "4000m"
      resource_limits_memory: "16Gi"

source:
  objects: [customers]
  incremental:
    strategy: updated_at
    lookback_days: 1

target:
  warehouse: "gs://platform-data-lake/warehouse/"
  connection:
    gcs:
      bucket: "platform-data-lake"
      prefix: "raw/stripe/customers"
```

### Pulumi + Ray Cluster

```yaml
tenant_id: analytics
environment: staging

source_connector: csv
source_connector_path: /app/connectors/csv.yaml

target_connector: s3
target_connector_path: /app/connectors/s3.yaml

asset: large_dataset
asset_path: /app/assets/csv/v1.0/sales_order_header.yaml

# Pulumi-managed Ray cluster
infrastructure:
  provider: pulumi
  
  runtime:
    platform: ray
    
    compute:
      cluster_id: "ray-cluster-staging-abc123"
      instance_type: "m5.4xlarge"
      instance_count: 10
      auto_scaling:
        enabled: true
        min_instances: 5
        max_instances: 20
    
    service_account: "arn:aws:iam::123456789:role/RayWorkerRole"
  
  metadata:
    tags:
      Team: "analytics"
      CostCenter: "analytics-001"
      Environment: "staging"
    
    variables:
      ray_version: "2.9.0"
      object_store_memory: "20GB"
      enable_autoscaler: true

source:
  files:
    - path: "s3://analytics-raw/sales/*.csv"
      object: sales_orders

target:
  connection:
    s3:
      bucket: "analytics-processed"
      prefix: "staging/sales_orders"
```

---

## Integration Patterns

### Pattern 1: Terraform Module Integration

**Terraform Module** (`modules/data-ingestion/main.tf`):

```hcl
variable "tenant_id" {
  description = "Tenant identifier from job config"
  type        = string
}

variable "environment" {
  description = "Environment from job config"
  type        = string
}

variable "metadata_tags" {
  description = "Tags from infrastructure.metadata.tags"
  type        = map(string)
  default     = {}
}

variable "variables" {
  description = "Custom variables from infrastructure.metadata.variables"
  type        = map(any)
  default     = {}
}

resource "aws_emr_cluster" "dativo_cluster" {
  name          = "dativo-${var.tenant_id}-${var.environment}"
  release_label = "emr-6.15.0"
  
  tags = merge(
    var.metadata_tags,
    {
      Name = "dativo-${var.tenant_id}-${var.environment}"
    }
  )
  
  # Use custom variables
  enable_spot_fleet = lookup(var.variables, "enable_spot_instances", false)
  
  # ... additional configuration
}

output "emr_cluster_id" {
  value = aws_emr_cluster.dativo_cluster.id
}

output "emr_cluster_dns" {
  value = aws_emr_cluster.dativo_cluster.master_public_dns
}
```

**Job Definition** references Terraform outputs:

```yaml
infrastructure:
  provider: terraform
  terraform:
    module_source: "./modules/data-ingestion"
  runtime:
    platform: emr
    compute:
      cluster_id: "${EMR_CLUSTER_ID}"  # From terraform output
  metadata:
    tags:
      CostCenter: "data-team"
    variables:
      enable_spot_instances: true
```

### Pattern 2: Environment Variable Injection

Use environment variables to pass Terraform outputs to jobs:

```bash
# After terraform apply
export EMR_CLUSTER_ID=$(terraform output -raw emr_cluster_id)
export EMR_CLUSTER_DNS=$(terraform output -raw emr_cluster_dns)
export S3_BUCKET=$(terraform output -raw data_lake_bucket)

# Run Dativo job with interpolated values
dativo run --config jobs/acme/job.yaml --mode self_hosted
```

### Pattern 3: State File Parsing

Programmatically parse Terraform state or outputs:

```python
import json
import subprocess

# Get Terraform outputs
result = subprocess.run(
    ["terraform", "output", "-json"],
    capture_output=True,
    text=True,
    cwd="./terraform"
)
outputs = json.loads(result.stdout)

# Inject into job config
os.environ["EMR_CLUSTER_ID"] = outputs["emr_cluster_id"]["value"]
os.environ["VPC_ID"] = outputs["vpc_id"]["value"]
```

### Pattern 4: GitOps with ArgoCD / Flux

Store job definitions with infrastructure blocks in Git:

```yaml
# k8s/dativo-jobs/prod/stripe-sync.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: dativo-stripe-job
  namespace: data-ingestion
data:
  job.yaml: |
    tenant_id: acme
    infrastructure:
      provider: terraform
      runtime:
        platform: kubernetes
        namespace: data-ingestion
        service_account: dativo-runner
      metadata:
        labels:
          argocd.argoproj.io/instance: dativo-jobs
    # ... rest of job config
```

---

## Best Practices

### 1. Use Environment Variable Interpolation

Reference dynamic values (Terraform outputs) via environment variables:

```yaml
infrastructure:
  runtime:
    compute:
      cluster_id: "${EMR_CLUSTER_ID}"  # From Terraform output
    network:
      vpc_id: "${VPC_ID}"
      subnet_ids: ["${SUBNET_1}", "${SUBNET_2}"]
```

### 2. Version Terraform Modules

Always pin module versions for reproducibility:

```yaml
infrastructure:
  terraform:
    module_source: "git::https://github.com/org/modules.git//data-ingestion"
    module_version: "v2.3.1"  # Pin to specific version
```

### 3. Separate Infrastructure from Jobs

- **Infrastructure Repository**: Terraform modules, VPCs, clusters
- **Job Repository**: Dativo job definitions with infrastructure references

This separation enables:
- Independent infrastructure updates
- Job portability across environments
- Clear ownership boundaries

### 4. Use Workspaces for Multi-Environment

```yaml
infrastructure:
  terraform:
    workspace: "prod-data-platform"  # prod, staging, dev
  metadata:
    tags:
      Environment: "production"
```

### 5. Document Expected Outputs

Use the `outputs` field to document required Terraform outputs:

```yaml
infrastructure:
  outputs:
    cluster_id: "module.emr_cluster.cluster_id"
    cluster_dns: "module.emr_cluster.master_public_dns"
    security_group: "module.emr_cluster.master_security_group_id"
```

### 6. Apply Consistent Tagging

Use `metadata.tags` for cost allocation and resource management:

```yaml
infrastructure:
  metadata:
    tags:
      CostCenter: "data-engineering"
      Project: "customer-analytics"
      Environment: "production"
      ManagedBy: "terraform"
      Owner: "data-team@company.com"
```

### 7. Security Best Practices

- **Never hardcode secrets** in job definitions
- Use `resources.secrets` to reference secret managers:

```yaml
infrastructure:
  resources:
    secrets:
      secret_manager_arn: "arn:aws:secretsmanager:us-east-1:123456789:secret:dativo/prod"
      kms_key_id: "arn:aws:kms:us-east-1:123456789:key/abc-123"
```

### 8. Resource Naming Conventions

Use consistent naming for infrastructure resources:

```yaml
infrastructure:
  runtime:
    namespace: "data-ingestion-${TENANT_ID}-${ENVIRONMENT}"
    service_account: "dativo-${TENANT_ID}-runner"
  metadata:
    tags:
      Name: "dativo-${TENANT_ID}-${ENVIRONMENT}-cluster"
```

---

## Related Documentation

- [Job Configuration Reference](CONFIG_REFERENCE.md) - Complete job configuration guide
- [Secret Management](SECRET_MANAGEMENT.md) - Managing credentials and secrets
- [Setup and Onboarding](SETUP_AND_ONBOARDING.md) - Getting started with Dativo
