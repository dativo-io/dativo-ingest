# Infrastructure Block - Quick Reference

Quick reference for adding infrastructure configuration to job definitions.

## Minimal Examples

### Terraform + EMR Cluster

```yaml
infrastructure:
  provider: terraform
  terraform:
    module_source: "git::https://github.com/org/infra.git//modules/emr"
    module_version: "v2.1.0"
  runtime:
    platform: emr
    compute:
      cluster_id: "${EMR_CLUSTER_ID}"
  metadata:
    tags:
      CostCenter: "data-engineering"
```

### Kubernetes

```yaml
infrastructure:
  provider: terraform
  runtime:
    platform: kubernetes
    namespace: "data-pipelines"
    service_account: "dativo-runner"
  metadata:
    labels:
      app: "dativo-ingestion"
      tenant: "acme"
```

### Databricks

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
```

### Manual Resources

```yaml
infrastructure:
  provider: manual
  resources:
    database:
      endpoint: "db.cluster.us-east-1.rds.amazonaws.com"
      port: 5432
    secrets:
      secret_manager_arn: "arn:aws:secretsmanager:..."
```

## Common Fields

| Field | Purpose | Example |
|-------|---------|---------|
| `provider` | IaC tool | `terraform`, `cloudformation`, `pulumi`, `manual` |
| `terraform.module_source` | Module location | `git::https://...//modules/emr` |
| `terraform.workspace` | TF workspace | `prod`, `staging`, `dev` |
| `runtime.platform` | Execution platform | `kubernetes`, `emr`, `databricks`, `ecs` |
| `runtime.compute.cluster_id` | Pre-provisioned cluster | `${EMR_CLUSTER_ID}` (from env) |
| `runtime.namespace` | K8s namespace | `data-pipelines-prod` |
| `metadata.tags` | Resource tags | Cost center, project, environment |
| `metadata.labels` | K8s labels | App, team, component |
| `metadata.variables` | Custom vars | Passed to Terraform/IaC |

## Environment Variable Pattern

Reference Terraform outputs via environment variables:

```bash
# After terraform apply
export EMR_CLUSTER_ID=$(terraform output -raw cluster_id)
export VPC_ID=$(terraform output -raw vpc_id)

# Job config references them
infrastructure:
  runtime:
    compute:
      cluster_id: "${EMR_CLUSTER_ID}"
    network:
      vpc_id: "${VPC_ID}"
```

## Platform-Specific Patterns

### AWS EMR

```yaml
infrastructure:
  runtime:
    platform: emr
    compute:
      cluster_id: "${EMR_CLUSTER_ID}"
      instance_type: "r5.2xlarge"
      instance_count: 8
    network:
      vpc_id: "vpc-xxx"
      subnet_ids: ["subnet-abc", "subnet-def"]
      security_group_ids: ["sg-xyz"]
    service_account: "arn:aws:iam::123456789:role/EMRRole"
```

### AWS ECS/Fargate

```yaml
infrastructure:
  runtime:
    platform: fargate
    compute:
      instance_type: "fargate"
    network:
      vpc_id: "vpc-xxx"
      subnet_ids: ["subnet-abc"]
      security_group_ids: ["sg-xyz"]
    service_account: "arn:aws:iam::123456789:role/ECSTaskRole"
```

### Kubernetes (GKE/EKS/AKS)

```yaml
infrastructure:
  runtime:
    platform: kubernetes
    namespace: "data-pipelines"
    service_account: "dativo-runner"
    compute:
      instance_type: "n2-standard-4"
      instance_count: 3
  metadata:
    labels:
      app: "dativo"
      tier: "data-platform"
    annotations:
      prometheus.io/scrape: "true"
```

### Databricks

```yaml
infrastructure:
  runtime:
    platform: databricks
    compute:
      cluster_id: "0123-456789-abc123"
      auto_scaling:
        enabled: true
        min_instances: 2
        max_instances: 10
  metadata:
    variables:
      spark_version: "13.3.x-scala2.12"
      spot_bid_price_percent: 80
```

## Metadata for Cost Allocation

Standard tags for cost tracking and governance:

```yaml
infrastructure:
  metadata:
    tags:
      CostCenter: "data-engineering"
      Project: "customer-analytics"
      Environment: "production"
      ManagedBy: "terraform"
      Owner: "data-team@company.com"
      BusinessUnit: "analytics"
```

## Pre-Provisioned Resources

Reference existing infrastructure:

```yaml
infrastructure:
  resources:
    database:
      endpoint: "prod-db.cluster.us-east-1.rds.amazonaws.com"
      port: 5432
      database_name: "metadata"
      instance_id: "prod-db"
    
    cache:
      endpoint: "redis.cache.amazonaws.com"
      cluster_id: "redis-cluster"
    
    queue:
      url: "https://sqs.us-east-1.amazonaws.com/123/queue"
      arn: "arn:aws:sqs:us-east-1:123:queue"
    
    secrets:
      secret_manager_arn: "arn:aws:secretsmanager:us-east-1:123:secret:app"
      kms_key_id: "arn:aws:kms:us-east-1:123:key/abc-123"
```

## Complete Example

```yaml
tenant_id: acme
environment: prod

source_connector: postgres
source_connector_path: /app/connectors/postgres.yaml

target_connector: iceberg
target_connector_path: /app/connectors/iceberg.yaml

asset: postgres_orders
asset_path: /app/assets/postgres/v1.0/db_orders.yaml

# Infrastructure block
infrastructure:
  provider: terraform
  terraform:
    module_source: "git::https://github.com/org/infra.git//emr"
    module_version: "v3.2.1"
    workspace: "prod"
  runtime:
    platform: emr
    compute:
      cluster_id: "${EMR_CLUSTER_ID}"
      instance_type: "r5.2xlarge"
      instance_count: 8
    storage:
      bucket: "acme-data-lake"
    network:
      vpc_id: "vpc-xxx"
      subnet_ids: ["subnet-abc"]
  metadata:
    tags:
      CostCenter: "data-engineering"
      Environment: "production"
  resources:
    secrets:
      secret_manager_arn: "arn:aws:secretsmanager:..."

# Standard job config continues...
source:
  connection:
    host: "${POSTGRES_HOST}"
  tables:
    - name: orders

target:
  warehouse: "s3://acme-data-lake/warehouse/"
```

## See Also

- [Complete Infrastructure Documentation](../INFRASTRUCTURE.md)
- [Job Configuration Reference](../CONFIG_REFERENCE.md)
- [Example Jobs](jobs/acme/)
