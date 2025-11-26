# Infrastructure Integration Examples

This directory contains example job configurations demonstrating external infrastructure integration with Dativo ETL.

## Examples

### 1. AWS ECS Deployment

**File**: [stripe_customers_aws.yaml](./stripe_customers_aws.yaml)

Complete example of deploying a Stripe ETL job on AWS ECS with:
- ECS Fargate runtime
- Full networking configuration (VPC, subnets, security groups)
- Compute resources (CPU: 2 vCPU, Memory: 4GB)
- S3 storage with KMS encryption
- Comprehensive infrastructure tags for cost allocation
- Terraform module reference
- Dagster orchestration configuration
- FinOps metadata with business tags
- Classification and governance overrides

**Use this example for**:
- Production AWS deployments
- Jobs requiring dedicated compute resources
- Workloads with specific networking requirements
- Compliance-heavy workloads requiring encryption

### 2. GCP Cloud Run Deployment

**File**: [stripe_customers_gcp.yaml](./stripe_customers_gcp.yaml)

Complete example of deploying a Stripe ETL job on GCP Cloud Run with:
- Cloud Run serverless runtime
- VPC connector for private networking
- Compute resources with GCP-native format
- GCS storage with Cloud KMS encryption
- GCP-compliant labels (lowercase with hyphens)
- Terraform module reference
- Dagster orchestration configuration

**Use this example for**:
- Serverless GCP deployments
- Variable workloads that benefit from auto-scaling
- Cost-optimized workloads (pay-per-use)
- Workloads requiring GCP-native services

### 3. Kubernetes Deployment

**File**: [hubspot_contacts_kubernetes.yaml](./hubspot_contacts_kubernetes.yaml)

Complete example of deploying a HubSpot ETL job on Kubernetes with:
- Cloud-agnostic Kubernetes runtime
- EKS/GKE/AKS compatibility
- Standard Kubernetes resource format (CPU: "2", Memory: "4Gi")
- Namespace-based isolation
- Service account configuration
- Minimal networking (uses cluster defaults)

**Use this example for**:
- Cloud-agnostic deployments
- Organizations already using Kubernetes
- Workloads requiring horizontal scaling
- Multi-cloud strategies

### 4. Multi-Tenant Shared Infrastructure

**File**: [multi_tenant_shared_infrastructure.yaml](./multi_tenant_shared_infrastructure.yaml)

Complete example of multi-tenant deployment with shared infrastructure:
- Dynamic tenant ID from environment variable
- Shared ECS cluster with tenant-specific namespaces
- Tenant-specific storage paths for data isolation
- Tenant-specific IAM roles
- Shared networking and security groups
- Cost tracking per tenant
- Terraform workspace per tenant

**Use this example for**:
- SaaS platforms with multiple tenants
- Cost-optimized shared infrastructure
- Workloads requiring tenant isolation without dedicated infrastructure
- Simplified infrastructure management

## Common Patterns

### Infrastructure Block Structure

All examples follow this structure:

```yaml
infrastructure:
  provider: aws | gcp | azure
  
  runtime:
    type: ecs | cloud_run | kubernetes | dagster | airflow
    cluster_name: <cluster-name>
    namespace: <namespace>
    service_account: <iam-role-or-service-account>
  
  compute:
    cpu: <cpu-request>
    memory: <memory-request>
    instance_type: <optional-instance-type>
    max_runtime_seconds: <timeout>
  
  networking:
    vpc_id: <vpc-id>
    subnet_ids: [<subnet-ids>]
    security_group_ids: [<security-group-ids>]
    private_networking: true | false
  
  storage:
    bucket: <bucket-name>
    prefix: <storage-prefix>
    kms_key_id: <kms-key-id>
  
  tags:
    <key>: <value>
  
  terraform:
    module_source: <terraform-module-source>
    module_version: <version>
    workspace: <terraform-workspace>
    backend_config:
      <backend-config>
  
  dagster:
    code_location: <code-location>
    repository: <repository>
```

### Tag Propagation

All examples demonstrate comprehensive tag propagation:

1. **Infrastructure tags** (highest priority)
   ```yaml
   infrastructure:
     tags:
       CostCenter: HR-001
       Environment: production
   ```

2. **FinOps metadata**
   ```yaml
   finops:
     cost_center: HR-001
     business_tags: [payments, revenue]
     project: data-platform
   ```

3. **Classification overrides**
   ```yaml
   classification_overrides:
     email: high_pii
     phone: high_pii
   ```

4. **Governance overrides**
   ```yaml
   governance_overrides:
     retention_days: 365
     owner: data-team@acme.com
   ```

### Resource Sizing

#### Small Workload (< 1GB data)
```yaml
compute:
  cpu: "1024"      # 1 vCPU (ECS) or "1" (Kubernetes)
  memory: "2048"   # 2GB (ECS) or "2Gi" (Kubernetes)
```

#### Medium Workload (1-10GB data)
```yaml
compute:
  cpu: "2048"      # 2 vCPU (ECS) or "2" (Kubernetes)
  memory: "4096"   # 4GB (ECS) or "4Gi" (Kubernetes)
```

#### Large Workload (> 10GB data)
```yaml
compute:
  cpu: "4096"      # 4 vCPU (ECS) or "4" (Kubernetes)
  memory: "8192"   # 8GB (ECS) or "8Gi" (Kubernetes)
```

### Networking Patterns

#### Private Networking (Recommended)
```yaml
networking:
  vpc_id: vpc-xxx
  subnet_ids:
    - subnet-xxx-private-1a
    - subnet-xxx-private-1b
  private_networking: true
```

#### Public Networking (Development Only)
```yaml
networking:
  vpc_id: vpc-xxx
  subnet_ids:
    - subnet-xxx-public-1a
    - subnet-xxx-public-1b
  private_networking: false
```

## Quick Start

### 1. Choose an Example

Select the example that matches your infrastructure:
- **AWS ECS**: [stripe_customers_aws.yaml](./stripe_customers_aws.yaml)
- **GCP Cloud Run**: [stripe_customers_gcp.yaml](./stripe_customers_gcp.yaml)
- **Kubernetes**: [hubspot_contacts_kubernetes.yaml](./hubspot_contacts_kubernetes.yaml)
- **Multi-Tenant**: [multi_tenant_shared_infrastructure.yaml](./multi_tenant_shared_infrastructure.yaml)

### 2. Customize Configuration

Update the example with your values:
- Replace `tenant_id` with your tenant ID
- Update `source_connector_path`, `target_connector_path`, `asset_path`
- Configure infrastructure values (VPC IDs, IAM roles, etc.)
- Add your tags for cost allocation

### 3. Validate Configuration

```bash
# Validate job configuration
dativo validate --config jobs/your-job.yaml

# Generate Terraform variables
dativo terraform export \
  --config jobs/your-job.yaml \
  --output terraform.tfvars
```

### 4. Deploy Infrastructure

```bash
# Apply Terraform
cd terraform
terraform init
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

### 5. Run Job

```bash
# Run job with deployed infrastructure
dativo run --config jobs/your-job.yaml --mode self_hosted
```

## Environment Variables

Examples use environment variables for sensitive data:

```bash
export TENANT_ID="acme"
export NESSIE_URI="http://nessie:19120/api/v1"
export S3_BUCKET="acme-data-lake"
```

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `TENANT_ID` | Tenant identifier | `acme` |
| `NESSIE_URI` | Nessie catalog URI | `http://nessie:19120/api/v1` |
| `S3_BUCKET` | S3 bucket name | `acme-data-lake` |
| `S3_ENDPOINT` | S3 endpoint URL | `http://localhost:9000` |

## Cost Estimation

Before deploying, estimate costs:

### AWS ECS (2 vCPU, 4GB, 1 hour/day)
- ECS Fargate: ~$20-30/month
- Data transfer: ~$5-10/month
- S3 storage: ~$2-5/month per TB
- **Total**: ~$30-50/month

### GCP Cloud Run (2 vCPU, 4GB, 1 hour/day)
- Cloud Run: ~$15-25/month
- VPC connector: ~$5/month
- GCS storage: ~$2-5/month per TB
- **Total**: ~$25-40/month

### Kubernetes (2 cores, 4GB, dedicated node)
- Node cost varies by cloud provider
- Typically: ~$50-100/month per node
- Storage: ~$2-5/month per TB

## Best Practices

### 1. Use Private Networking
Always use private networking in production:
```yaml
networking:
  private_networking: true
```

### 2. Enable Encryption
Always enable encryption at rest:
```yaml
storage:
  kms_key_id: <kms-key-arn>
```

### 3. Set Timeouts
Set appropriate timeouts to prevent runaway jobs:
```yaml
compute:
  max_runtime_seconds: 3600  # 1 hour
```

### 4. Use Consistent Tags
Use consistent tags across all jobs:
```yaml
tags:
  CostCenter: <cost-center>
  Project: <project>
  Environment: <environment>
  Team: <team>
  Owner: <owner>
```

### 5. Version Terraform Modules
Always pin Terraform module versions:
```yaml
terraform:
  module_version: "1.2.0"  # Pin to specific version
```

## Troubleshooting

### Job Fails to Start

1. Check IAM roles/service accounts have correct permissions
2. Verify networking configuration (VPC, subnets)
3. Check security group rules allow outbound connectivity
4. Verify container image is accessible

### Insufficient Resources

Increase compute resources:
```yaml
compute:
  cpu: "4096"
  memory: "8192"
```

### Networking Issues

1. Verify NAT Gateway for private subnets
2. Check security group rules
3. Ensure VPC endpoints are configured

### Cost Higher Than Expected

1. Review actual vs. requested resources
2. Check for unused infrastructure
3. Enable auto-scaling
4. Use Spot instances (AWS) or preemptible instances (GCP)

## Additional Resources

- [Infrastructure Integration Documentation](../../../docs/INFRASTRUCTURE_INTEGRATION.md)
- [Terraform Modules](../../terraform/)
- [Tag Propagation Guide](../../../docs/TAG_PROPAGATION.md)
- [Cost Optimization Guide](../../../docs/INFRASTRUCTURE_INTEGRATION.md#cost-optimization)

## Support

For issues or questions:
1. Check [troubleshooting guide](../../../docs/INFRASTRUCTURE_INTEGRATION.md#troubleshooting)
2. Review [GitHub issues](https://github.com/dativo/etl/issues)
3. Contact your infrastructure team

## License

Apache 2.0
