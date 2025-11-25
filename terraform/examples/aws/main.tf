# Example AWS Terraform configuration for Dativo ETL jobs
#
# This example shows how to use the Dativo job module to provision
# infrastructure for multiple jobs with comprehensive tag propagation.

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Example: Job 1 - HubSpot Contacts to Iceberg
module "hubspot_contacts_job" {
  source = "../../modules/aws/dativo-job"

  job_name         = "hubspot-contacts"
  tenant_id        = "acme"
  image_uri        = var.image_uri
  cpu              = 1024
  memory           = 2048
  ecs_cluster_name = var.ecs_cluster_name
  subnet_ids       = var.subnet_ids
  security_group_ids = var.security_group_ids
  aws_region       = var.aws_region

  # Tags extracted from job configuration
  tags = {
    # FinOps tags
    finops_cost_center   = "ENG-001"
    finops_business_tags = "sales,crm"
    finops_project       = "data-platform"
    finops_environment   = "production"

    # Compliance tags
    compliance_classification = "PII"
    compliance_regulations    = "GDPR,CCPA"
    compliance_retention_days = "365"

    # Governance tags
    governance_owner    = "data-team@acme.com"
    governance_domain    = "sales"
    governance_data_product = "customer-data"

    # Asset metadata
    asset_name    = "hubspot_contacts"
    asset_version = "1.0"

    # Infrastructure metadata
    managed_by = "dativo-terraform"
  }
}

# Example: Job 2 - Stripe Customers to S3
module "stripe_customers_job" {
  source = "../../modules/aws/dativo-job"

  job_name         = "stripe-customers"
  tenant_id        = "acme"
  image_uri        = var.image_uri
  cpu              = 2048
  memory           = 4096
  ecs_cluster_name = var.ecs_cluster_name
  subnet_ids       = var.subnet_ids
  security_group_ids = var.security_group_ids
  aws_region       = var.aws_region

  # Scheduled execution (daily at 2 AM UTC)
  schedule_expression = "cron(0 2 * * ? *)"
  ecs_cluster_arn     = var.ecs_cluster_arn

  tags = {
    finops_cost_center   = "FIN-001"
    finops_business_tags = "payments,revenue"
    finops_project       = "financial-data"
    finops_environment    = "production"

    compliance_classification = "SENSITIVE"
    compliance_regulations    = "PCI-DSS,GDPR"
    compliance_retention_days = "730"

    governance_owner = "finance-team@acme.com"
    asset_name      = "stripe_customers"
    asset_version   = "1.0"

    managed_by = "dativo-terraform"
  }
}
