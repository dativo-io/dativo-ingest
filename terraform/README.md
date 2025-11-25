# Dativo Infrastructure Terraform Modules

This directory contains Terraform modules for deploying Dativo ETL jobs on AWS and GCP with comprehensive tag propagation for cost allocation, compliance, and resource traceability.

## Structure

```
terraform/
├── modules/
│   ├── aws/
│   │   └── dativo-job/      # AWS ECS Fargate module
│   └── gcp/
│       └── dativo-job/        # GCP Cloud Run module
├── examples/
│   ├── aws/                  # AWS deployment examples
│   └── gcp/                  # GCP deployment examples
└── README.md                 # This file
```

## Quick Start

### 1. Generate Terraform Configuration

Use the generation script to create Terraform configurations from job definitions:

```bash
python3 scripts/generate_terraform.py \
  jobs/acme/hubspot_contacts.yaml \
  --cloud aws \
  --resource-type ecs_fargate \
  --output-dir terraform/generated
```

### 2. Review Generated Configuration

The script generates:
- `{tenant}-{asset}.tf` - HCL Terraform configuration
- `{tenant}-{asset}.tf.json` - JSON Terraform configuration (alternative)

### 3. Deploy

```bash
cd terraform/generated
terraform init
terraform plan
terraform apply
```

## Modules

### AWS Module (`modules/aws/dativo-job`)

Provisions infrastructure for Dativo jobs on AWS using ECS Fargate.

**Features:**
- ECS Task Definition with configurable CPU/memory
- ECS Service for manual or scheduled execution
- CloudWatch Log Group for centralized logging
- EventBridge integration for scheduled execution
- Comprehensive tag propagation

**Usage:**
```hcl
module "my_job" {
  source = "../../modules/aws/dativo-job"

  job_name         = "hubspot-contacts"
  tenant_id        = "acme"
  image_uri        = "dativo/dativo-ingest:latest"
  cpu              = 1024
  memory           = 2048
  ecs_cluster_name = "dativo-cluster"
  subnet_ids       = ["subnet-12345"]
  security_group_ids = ["sg-12345"]
  aws_region       = "us-east-1"

  tags = {
    finops_cost_center = "ENG-001"
    # ... more tags
  }
}
```

### GCP Module (`modules/gcp/dativo-job`)

Provisions infrastructure for Dativo jobs on GCP using Cloud Run.

**Features:**
- Cloud Run Service with configurable CPU/memory
- Cloud Scheduler integration for scheduled execution
- IAM integration for secure execution
- Comprehensive label propagation (GCP format)

**Usage:**
```hcl
module "my_job" {
  source = "../../modules/gcp/dativo-job"

  job_name      = "hubspot-contacts"
  tenant_id     = "acme"
  image_uri     = "gcr.io/dativo/dativo-ingest:latest"
  cpu           = "1"
  memory        = "2Gi"
  region        = "us-central1"
  project_id    = "my-project"

  labels = {
    finops_cost_center = "eng-001"
    # ... more labels
  }
}
```

## Examples

See `examples/` directory for complete working examples:
- `examples/aws/` - AWS deployment examples
- `examples/gcp/` - GCP deployment examples

## Tag Propagation

Tags are automatically extracted from:
1. Job configuration (`infrastructure.metadata`, `finops`, `governance_overrides`)
2. Asset definition (`finops`, `compliance`, `team`)
3. Source system metadata (if available)

### Tag Categories

- **FinOps**: Cost allocation (`finops_cost_center`, `finops_business_tags`, etc.)
- **Compliance**: Regulatory tracking (`compliance_classification`, `compliance_regulations`, etc.)
- **Governance**: Ownership and lineage (`governance_owner`, `governance_domain`, etc.)
- **Asset**: Resource identification (`asset_name`, `asset_version`, etc.)

See [INFRASTRUCTURE_INTEGRATION.md](../docs/INFRASTRUCTURE_INTEGRATION.md) for detailed tag documentation.

## Requirements

- Terraform >= 1.0
- AWS Provider >= 5.0 (for AWS deployments)
- GCP Provider >= 5.0 (for GCP deployments)

## Documentation

For comprehensive documentation, see:
- [INFRASTRUCTURE_INTEGRATION.md](../docs/INFRASTRUCTURE_INTEGRATION.md) - Complete integration guide
- [CONFIG_REFERENCE.md](../docs/CONFIG_REFERENCE.md) - Job configuration reference
- [TAG_PROPAGATION.md](../docs/TAG_PROPAGATION.md) - Tag propagation details

## Support

For issues or questions:
1. Check the documentation in `docs/`
2. Review examples in `examples/`
3. Open an issue on GitHub
