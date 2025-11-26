# Infrastructure Integration Quick Start

Get started with cloud-agnostic infrastructure deployment for Dativo ETL jobs in 5 minutes.

## Prerequisites

- Existing Dativo ETL job configuration
- AWS or GCP account with infrastructure provisioned (VPC, IAM roles, etc.)
- Terraform installed (for deployment)

## Step 1: Add Infrastructure Block

Add the `infrastructure` block to your job configuration:

```yaml
# jobs/my_tenant/my_job.yaml
tenant_id: my_tenant
environment: prod

source_connector_path: connectors/stripe.yaml
target_connector_path: connectors/iceberg.yaml
asset_path: assets/stripe/v1.0/customers.yaml

# ... source and target configuration ...

# Add infrastructure block
infrastructure:
  provider: aws  # or gcp
  region: us-east-1
  
  compute:
    type: ecs  # ecs, eks, gke, cloud_run
    cluster_name: my-cluster
    task_cpu: "1024"
    task_memory: "2048"
    execution_role_arn: "arn:aws:iam::123456789012:role/my-execution-role"
    task_role_arn: "arn:aws:iam::123456789012:role/my-task-role"
  
  network:
    vpc_id: "vpc-0abc123"
    subnets:
      - "subnet-0abc123"
      - "subnet-0def456"
    security_groups:
      - "sg-0abc123"
  
  storage:
    bucket: "my-data-lake-prod"
    kms_key_id: "arn:aws:kms:us-east-1:123456789012:key/..."
  
  tags:
    cost_center: "CC-001"
    project: "data-platform"
    environment: "prod"
    owner: "data-team@company.com"
    compliance:
      - SOC2
      - PCI-DSS
  
  monitoring:
    log_group: "/ecs/dativo/my-tenant-prod"
    metrics_namespace: "Dativo/ETL"
    alert_topic_arn: "arn:aws:sns:us-east-1:123456789012:alerts"
```

## Step 2: Validate Configuration

```bash
# Validate infrastructure configuration
dativo validate-infrastructure --config jobs/my_tenant/my_job.yaml

# View infrastructure configuration
dativo show-infrastructure --config jobs/my_tenant/my_job.yaml
```

## Step 3: Generate Terraform

```bash
# Generate Terraform module for single job
dativo generate-terraform \
  --config jobs/my_tenant/my_job.yaml \
  --output terraform/my_tenant

# Or generate for all jobs in directory
dativo generate-terraform \
  --job-dir jobs/my_tenant \
  --output terraform
```

This creates:
```
terraform/my_tenant/
├── main.tf              # Infrastructure resources
├── variables.tf         # Variable declarations
├── terraform.tfvars.json # Variable values
└── outputs.tf           # Output values
```

## Step 4: Deploy with Terraform

```bash
cd terraform/my_tenant

# Initialize Terraform
terraform init

# Review plan
terraform plan

# Deploy infrastructure
terraform apply

# View outputs
terraform output
```

## Step 5: Run Job

```bash
# Run job on deployed infrastructure
dativo run --config jobs/my_tenant/my_job.yaml --mode self_hosted
```

## Tag Propagation

Tags flow automatically from infrastructure config to:
1. **Cloud resources** (ECS tasks, Cloud Run services, etc.)
2. **Iceberg table properties** (for data lineage)
3. **Dagster metadata** (for orchestration)

Tag hierarchy (highest to lowest priority):
1. Infrastructure tags
2. Job config tags (finops)
3. Asset definition tags
4. Source system tags

## Examples

See complete examples in `examples/jobs/`:
- `aws_ecs_example.yaml` - AWS ECS Fargate
- `aws_eks_example.yaml` - AWS EKS Kubernetes
- `gcp_cloud_run_example.yaml` - GCP Cloud Run

## Cost Allocation

Enable cost tracking in AWS:
```bash
# Activate cost allocation tags in AWS Console
1. Go to Billing > Cost Allocation Tags
2. Activate: cost_center, project, environment, owner
```

View costs by tag:
```bash
# AWS CLI
aws ce get-cost-and-usage \
  --time-period Start=2024-01-01,End=2024-01-31 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --group-by Type=TAG,Key=cost_center
```

Enable cost tracking in GCP:
```bash
# GCP labels automatically flow to BigQuery billing export
# Query in BigQuery:
SELECT
  labels.value AS cost_center,
  SUM(cost) AS total_cost
FROM `project.billing_export.gcp_billing_export_v1_*`
WHERE labels.key = 'cost_center'
GROUP BY cost_center
```

## Compliance Tracking

Infrastructure tags support compliance requirements:

```yaml
infrastructure:
  tags:
    compliance:
      - GDPR
      - HIPAA
      - SOC2
    data_residency: "EU"
    encryption_required: "true"
```

These tags:
- Flow to all cloud resources
- Are included in Iceberg table properties
- Can be queried for compliance audits
- Appear in CloudTrail/Cloud Audit Logs

## Troubleshooting

**Issue**: Invalid compute type for provider
```
Error: Invalid compute type 'ecs' for GCP
```
**Solution**: Use provider-appropriate compute types:
- AWS: `ecs`, `eks`
- GCP: `gke`, `cloud_run`

**Issue**: Missing infrastructure block
```
ERROR: Job configuration does not include infrastructure block
```
**Solution**: Add `infrastructure` section to job config

**Issue**: Terraform generation fails
```
ERROR: Failed to generate Terraform: provider not supported
```
**Solution**: Verify `provider` is either `aws` or `gcp`

## Next Steps

- [Full Documentation](docs/INFRASTRUCTURE_INTEGRATION.md) - Complete guide
- [Config Reference](docs/CONFIG_REFERENCE.md) - All configuration options
- [Tag Propagation](docs/TAG_PROPAGATION.md) - Tag hierarchy details

## Support

For issues or questions:
1. Check [docs/INFRASTRUCTURE_INTEGRATION.md](docs/INFRASTRUCTURE_INTEGRATION.md)
2. Review example configurations in `examples/jobs/`
3. Validate configuration with `dativo validate-infrastructure`
