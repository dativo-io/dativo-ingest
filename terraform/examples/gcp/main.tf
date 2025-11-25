# Example GCP Terraform configuration for Dativo ETL jobs
#
# This example shows how to use the Dativo job module to provision
# infrastructure for multiple jobs with comprehensive tag propagation.

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Example: Job 1 - HubSpot Contacts to Iceberg
module "hubspot_contacts_job" {
  source = "../../modules/gcp/dativo-job"

  job_name      = "hubspot-contacts"
  tenant_id     = "acme"
  image_uri     = var.image_uri
  cpu           = "1"
  memory        = "2Gi"
  timeout_seconds = 3600
  region        = var.region
  project_id    = var.project_id

  # Labels extracted from job configuration (GCP format)
  labels = {
    # FinOps labels
    finops_cost_center   = "eng-001"
    finops_business_tags  = "sales-crm"
    finops_project        = "data-platform"
    finops_environment     = "production"

    # Compliance labels
    compliance_classification = "pii"
    compliance_regulations   = "gdpr-ccpa"
    compliance_retention_days = "365"

    # Governance labels
    governance_owner      = "data-team-acme-com"
    governance_domain     = "sales"
    governance_data_product = "customer-data"

    # Asset metadata
    asset_name    = "hubspot-contacts"
    asset_version = "1-0"

    # Infrastructure metadata
    managed_by = "dativo-terraform"
  }
}

# Example: Job 2 - Stripe Customers to Cloud Storage
module "stripe_customers_job" {
  source = "../../modules/gcp/dativo-job"

  job_name      = "stripe-customers"
  tenant_id     = "acme"
  image_uri     = var.image_uri
  cpu           = "2"
  memory        = "4Gi"
  timeout_seconds = 7200
  region        = var.region
  project_id    = var.project_id

  # Scheduled execution (daily at 2 AM UTC)
  schedule_cron = "0 2 * * *"
  timezone      = "UTC"
  service_account_email = var.service_account_email

  labels = {
    finops_cost_center   = "fin-001"
    finops_business_tags = "payments-revenue"
    finops_project       = "financial-data"
    finops_environment    = "production"

    compliance_classification = "sensitive"
    compliance_regulations   = "pci-dss-gdpr"
    compliance_retention_days = "730"

    governance_owner = "finance-team-acme-com"
    asset_name      = "stripe-customers"
    asset_version   = "1-0"

    managed_by = "dativo-terraform"
  }
}
