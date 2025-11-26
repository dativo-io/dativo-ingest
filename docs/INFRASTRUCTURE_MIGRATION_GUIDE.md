# Infrastructure Integration - Migration Guide

This guide helps you migrate existing Dativo ETL jobs to use the new external infrastructure integration feature for cloud-agnostic deployment via Terraform.

## Overview

The infrastructure integration feature enables:

1. **Cloud-agnostic deployment**: Single configuration for AWS, GCP, or Azure
2. **External orchestration**: Integration with Dagster, Airflow, Kubernetes
3. **Comprehensive tagging**: Automatic tag propagation for cost allocation and compliance
4. **Infrastructure as Code**: Manage job infrastructure alongside application code

## Migration Checklist

- [ ] Review existing job configurations
- [ ] Add infrastructure block to job configs
- [ ] Define tags for cost allocation and compliance
- [ ] Generate Terraform variables
- [ ] Review and customize Terraform modules
- [ ] Test infrastructure provisioning
- [ ] Deploy jobs to cloud infrastructure
- [ ] Verify tag propagation
- [ ] Set up cost tracking and compliance reporting

## Step-by-Step Migration

### Step 1: Review Existing Job Configuration

**Before (existing job config):**
```yaml
# jobs/acme/stripe_customers_to_iceberg.yaml
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
  incremental:
    lookback_days: 1

target:
  branch: acme
  warehouse: s3://lake/acme/
  connection:
    nessie:
      uri: "http://nessie.acme.internal:19120/api/v1"
    s3:
      bucket: "acme-data-lake"
      prefix: "raw/stripe/customers"

logging:
  redaction: true
  level: INFO
```

### Step 2: Add Infrastructure Block

**After (with infrastructure block):**
```yaml
# jobs/acme/stripe_customers_to_iceberg.yaml
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
  incremental:
    lookback_days: 1

target:
  branch: acme
  warehouse: s3://lake/acme/
  connection:
    nessie:
      uri: "http://nessie.acme.internal:19120/api/v1"
    s3:
      bucket: "acme-data-lake"
      prefix: "raw/stripe/customers"

# NEW: External infrastructure configuration
infrastructure:
  provider: aws  # or gcp
  
  runtime:
    type: ecs
    compute:
      cpu: "2048"
      memory: "4096"
    timeout_seconds: 7200
  
  networking:
    vpc_id: vpc-12345678
    subnet_ids: [subnet-12345678, subnet-87654321]
    private_access: true
  
  storage:
    state_bucket: dativo-state-acme
    data_bucket: dativo-data-acme
    encryption:
      enabled: true
      kms_key_id: arn:aws:kms:us-east-1:123456789012:key/12345678
  
  tags:
    cost_center: FIN-001
    business_unit: Finance
    project: data-platform
    environment: prod
    owner: data-team@acme.com
    compliance: [GDPR, SOC2]
    data_classification: Confidential
  
  monitoring:
    enabled: true
    log_group: /dativo/jobs/acme/stripe_customers
    metrics_namespace: Dativo/Jobs

logging:
  redaction: true
  level: INFO
```

### Step 3: Validate Configuration

```bash
# Validate the infrastructure configuration
dativo infra validate \
  --job-config jobs/acme/stripe_customers_to_iceberg.yaml

# Expected output:
# ✓ Infrastructure configuration is valid
```

### Step 4: Generate Terraform Variables

```bash
# Generate Terraform variables
dativo infra generate-tfvars \
  --job-config jobs/acme/stripe_customers_to_iceberg.yaml \
  --output terraform/aws/terraform.tfvars.json
```

**Generated `terraform.tfvars.json`:**
```json
{
  "provider": "aws",
  "runtime_type": "ecs",
  "compute": {
    "cpu": "2048",
    "memory": "4096"
  },
  "timeout_seconds": 7200,
  "networking": {
    "vpc_id": "vpc-12345678",
    "subnet_ids": ["subnet-12345678", "subnet-87654321"],
    "private_access": true
  },
  "storage": {
    "state_bucket": "dativo-state-acme",
    "data_bucket": "dativo-data-acme",
    "encryption": {
      "enabled": true,
      "kms_key_id": "arn:aws:kms:us-east-1:123456789012:key/12345678"
    }
  },
  "tags": {
    "CostCenter": "FIN-001",
    "BusinessUnit": "Finance",
    "Project": "data-platform",
    "Environment": "prod",
    "Owner": "data-team@acme.com",
    "Compliance": "GDPR,SOC2",
    "DataClassification": "Confidential",
    "TenantId": "acme",
    "Asset": "stripe_customers",
    "SourceConnector": "stripe",
    "ManagedBy": "dativo",
    "Terraform": "true"
  },
  "job_name": "stripe_customers_to_iceberg",
  "tenant_id": "acme"
}
```

### Step 5: Review Terraform Module

```bash
cd terraform/aws
cat main.tf
```

Review the Terraform module and customize if needed:
- Adjust resource naming conventions
- Add custom security groups
- Configure additional monitoring
- Add custom IAM policies

### Step 6: Apply Terraform

```bash
# Initialize Terraform
terraform init

# Review planned changes
terraform plan -var-file=terraform.tfvars.json

# Apply infrastructure
terraform apply -var-file=terraform.tfvars.json
```

### Step 7: Deploy Job

Once infrastructure is provisioned, deploy the job using your orchestration platform:

**Dagster:**
```bash
dativo start orchestrated --runner-config configs/runner.yaml
```

**Manual Run:**
```bash
dativo run \
  --config jobs/acme/stripe_customers_to_iceberg.yaml \
  --mode self_hosted
```

### Step 8: Verify Tag Propagation

**AWS:**
```bash
# Check ECS cluster tags
aws ecs describe-clusters \
  --clusters acme-stripe-customers-to-iceberg-cluster \
  --include TAGS

# Check CloudWatch log group tags
aws logs list-tags-log-group \
  --log-group-name /dativo/jobs/acme/stripe_customers
```

**GCP:**
```bash
# Check Cloud Run job labels
gcloud run jobs describe acme-stripe-customers-to-iceberg \
  --format="value(metadata.labels)"
```

### Step 9: Set Up Cost Tracking

**AWS Cost Explorer:**
1. Navigate to AWS Cost Explorer
2. Enable cost allocation tags
3. Create cost report filtered by `ManagedBy=dativo`
4. Group by `CostCenter`, `TenantId`, `Project`

**GCP Billing:**
1. Enable BigQuery billing export
2. Query by labels:
   ```sql
   SELECT 
     SUM(cost) as total_cost,
     labels.value as cost_center
   FROM `project.dataset.gcp_billing_export_v1_XXXXXX`
   CROSS JOIN UNNEST(labels) as labels
   WHERE labels.key = 'managed_by' AND labels.value = 'dativo'
   GROUP BY cost_center
   ```

## Migration Patterns

### Pattern 1: Minimal Migration (Start Small)

Add minimal infrastructure configuration:

```yaml
infrastructure:
  provider: aws
  runtime:
    type: ecs
  storage:
    state_bucket: dativo-state-acme
    data_bucket: dativo-data-acme
  tags:
    cost_center: DATA-001
    owner: data-team@acme.com
```

### Pattern 2: Full Migration (Production Ready)

Add comprehensive infrastructure configuration:

```yaml
infrastructure:
  provider: aws
  runtime:
    type: ecs
    compute:
      cpu: "2048"
      memory: "4096"
    scaling:
      min_instances: 1
      max_instances: 5
    timeout_seconds: 7200
  networking:
    vpc_id: vpc-12345678
    subnet_ids: [subnet-12345678, subnet-87654321]
    security_group_ids: [sg-12345678]
    private_access: true
  storage:
    state_bucket: dativo-state-acme
    data_bucket: dativo-data-acme
    encryption:
      enabled: true
      kms_key_id: arn:aws:kms:...
  tags:
    cost_center: DATA-001
    business_unit: DataPlatform
    project: data-warehouse
    environment: prod
    owner: data-team@acme.com
    compliance: [GDPR, SOC2]
    data_classification: Confidential
  terraform:
    module_source: git::https://github.com/acme/terraform-dativo.git
    module_version: v1.0.0
    backend:
      type: s3
      config:
        bucket: terraform-state
        key: dativo/jobs/stripe_customers.tfstate
  monitoring:
    enabled: true
    alerts:
      channels: [arn:aws:sns:...]
```

### Pattern 3: Multi-Environment Migration

Use environment-specific configurations:

**Development:**
```yaml
environment: dev
infrastructure:
  provider: aws
  runtime:
    type: ecs
    compute:
      cpu: "1024"
      memory: "2048"
  tags:
    environment: dev
    cost_center: DEV-001
```

**Production:**
```yaml
environment: prod
infrastructure:
  provider: aws
  runtime:
    type: ecs
    compute:
      cpu: "4096"
      memory: "8192"
    scaling:
      min_instances: 2
      max_instances: 10
  tags:
    environment: prod
    cost_center: PROD-001
```

## Common Migration Scenarios

### Scenario 1: Moving from Self-Hosted to Cloud

**Current:** Running jobs on self-hosted infrastructure  
**Goal:** Move to AWS ECS with Terraform

**Steps:**
1. Add infrastructure block to job config
2. Generate Terraform variables
3. Apply Terraform to provision ECS infrastructure
4. Test job execution on ECS
5. Update Dagster/orchestrator to use ECS
6. Decommission self-hosted infrastructure

### Scenario 2: Multi-Cloud Deployment

**Current:** Running jobs on AWS  
**Goal:** Also deploy to GCP for redundancy

**Steps:**
1. Duplicate job config with GCP provider
2. Generate Terraform variables for GCP
3. Apply GCP Terraform module
4. Set up cross-cloud monitoring
5. Configure failover logic in orchestrator

### Scenario 3: Adding Cost Tracking

**Current:** No cost tracking or tagging  
**Goal:** Track costs by tenant and project

**Steps:**
1. Add comprehensive tags to infrastructure block
2. Generate and apply Terraform
3. Enable cost allocation tags in cloud provider
4. Set up cost dashboards
5. Create cost alerts and budgets

## Backward Compatibility

The infrastructure block is **optional**. Existing jobs without infrastructure configuration will continue to work:

- Jobs without `infrastructure` block run as before
- No breaking changes to existing configurations
- Infrastructure validation only runs if infrastructure block is present

## Best Practices

1. **Start with dev environment**: Test infrastructure configuration in dev before production
2. **Use version control**: Store Terraform state in version-controlled backends
3. **Tag consistently**: Establish tagging standards across all teams
4. **Monitor costs**: Set up cost alerts early
5. **Test thoroughly**: Validate infrastructure before deploying production jobs
6. **Document changes**: Keep infrastructure documentation up to date

## Troubleshooting

### Issue: Tags not appearing on resources

**Solution:**
1. Verify tags are defined in job configuration
2. Generate fresh Terraform variables
3. Apply Terraform changes
4. Check cloud provider console (may take 24 hours to propagate)

### Issue: Terraform apply fails

**Solution:**
1. Verify AWS/GCP credentials are configured
2. Check Terraform state lock status
3. Verify VPC/subnet IDs are correct
4. Review Terraform error messages
5. Check IAM permissions for Terraform

### Issue: Job fails to run on cloud infrastructure

**Solution:**
1. Verify IAM role/service account has required permissions
2. Check networking configuration (VPC, subnets, security groups)
3. Review CloudWatch/Cloud Logging logs
4. Verify container image is accessible
5. Check resource quotas and limits

## Support

For issues or questions:

1. Review [Infrastructure Integration Documentation](INFRASTRUCTURE_INTEGRATION.md)
2. Check [Troubleshooting Guide](INFRASTRUCTURE_INTEGRATION.md#troubleshooting)
3. Review example configurations in `examples/jobs/`
4. Open an issue on GitHub

## Next Steps

After migration:

1. **Set up cost dashboards**: Create dashboards in AWS Cost Explorer or GCP Billing
2. **Configure alerts**: Set up alerts for job failures and cost overruns
3. **Optimize resources**: Right-size compute resources based on actual usage
4. **Document infrastructure**: Keep infrastructure documentation up to date
5. **Automate deployments**: Set up CI/CD pipelines for infrastructure changes

## Appendix: Quick Reference

### CLI Commands

```bash
# Generate Terraform variables
dativo infra generate-tfvars \
  --job-config jobs/acme/job.yaml \
  --output terraform/aws/terraform.tfvars.json

# Validate infrastructure config
dativo infra validate \
  --job-config jobs/acme/job.yaml

# Export tag report
dativo infra tag-report \
  --job-config jobs/acme/job.yaml \
  --output tags-report.json
```

### Terraform Commands

```bash
# Initialize
terraform init

# Plan
terraform plan -var-file=terraform.tfvars.json

# Apply
terraform apply -var-file=terraform.tfvars.json

# Destroy
terraform destroy -var-file=terraform.tfvars.json
```

### Tag Query Commands

**AWS:**
```bash
aws resourcegroupstaggingapi get-resources \
  --tag-filters Key=ManagedBy,Values=dativo
```

**GCP:**
```bash
gcloud run jobs list \
  --filter="metadata.labels.managed_by:dativo"
```

## License

Apache 2.0 - See LICENSE file for details
