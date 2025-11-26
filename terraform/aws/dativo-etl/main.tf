# Terraform module for Dativo ETL infrastructure on AWS
# Provisions S3 buckets, IAM roles, and Glue catalog for Iceberg tables

terraform {
  required_version = ">= 1.3.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# ============================================================================
# Variables
# ============================================================================

variable "tenant_id" {
  description = "Tenant identifier for multi-tenancy"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "region" {
  description = "AWS region for resources"
  type        = string
}

variable "s3_bucket_name" {
  description = "Name for the S3 bucket (must be globally unique)"
  type        = string
}

variable "enable_versioning" {
  description = "Enable S3 bucket versioning"
  type        = bool
  default     = true
}

variable "enable_encryption" {
  description = "Enable S3 bucket encryption"
  type        = bool
  default     = true
}

variable "enable_glue_catalog" {
  description = "Enable AWS Glue catalog for Iceberg tables"
  type        = bool
  default     = true
}

variable "glue_database_name" {
  description = "Name for the Glue database"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

# ============================================================================
# Local Variables
# ============================================================================

locals {
  common_tags = merge(
    var.tags,
    {
      ManagedBy   = "Terraform"
      TenantId    = var.tenant_id
      Environment = var.environment
      Component   = "DativoETL"
    }
  )
  
  glue_db_name = var.glue_database_name != "" ? var.glue_database_name : "${var.tenant_id}_iceberg"
}

# ============================================================================
# S3 Bucket for Dativo Data Lake
# ============================================================================

resource "aws_s3_bucket" "data_lake" {
  bucket = var.s3_bucket_name
  tags   = local.common_tags

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "data_lake" {
  count  = var.enable_versioning ? 1 : 0
  bucket = aws_s3_bucket.data_lake.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data_lake" {
  count  = var.enable_encryption ? 1 : 0
  bucket = aws_s3_bucket.data_lake.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ============================================================================
# IAM Role for Dativo ETL Job
# ============================================================================

resource "aws_iam_role" "dativo_etl" {
  name = "${var.tenant_id}-dativo-etl-role-${var.environment}"
  tags = local.common_tags

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      },
      {
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

data "aws_caller_identity" "current" {}

# IAM Policy for S3 access
resource "aws_iam_role_policy" "s3_access" {
  name = "s3-access"
  role = aws_iam_role.dativo_etl.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
          "s3:GetBucketLocation"
        ]
        Resource = [
          aws_s3_bucket.data_lake.arn,
          "${aws_s3_bucket.data_lake.arn}/*"
        ]
      }
    ]
  })
}

# IAM Policy for Glue catalog access (if enabled)
resource "aws_iam_role_policy" "glue_access" {
  count = var.enable_glue_catalog ? 1 : 0
  name  = "glue-catalog-access"
  role  = aws_iam_role.dativo_etl.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "glue:GetDatabase",
          "glue:GetTable",
          "glue:GetTables",
          "glue:CreateTable",
          "glue:UpdateTable",
          "glue:DeleteTable",
          "glue:GetPartition",
          "glue:GetPartitions",
          "glue:CreatePartition",
          "glue:UpdatePartition",
          "glue:DeletePartition",
          "glue:BatchCreatePartition",
          "glue:BatchDeletePartition",
          "glue:BatchGetPartition"
        ]
        Resource = [
          "arn:aws:glue:${var.region}:${data.aws_caller_identity.current.account_id}:catalog",
          "arn:aws:glue:${var.region}:${data.aws_caller_identity.current.account_id}:database/${local.glue_db_name}",
          "arn:aws:glue:${var.region}:${data.aws_caller_identity.current.account_id}:table/${local.glue_db_name}/*"
        ]
      }
    ]
  })
}

# ============================================================================
# Glue Catalog Database for Iceberg Tables
# ============================================================================

resource "aws_glue_catalog_database" "iceberg" {
  count       = var.enable_glue_catalog ? 1 : 0
  name        = local.glue_db_name
  description = "Iceberg catalog database for ${var.tenant_id}"
  
  tags = local.common_tags

  location_uri = "s3://${aws_s3_bucket.data_lake.bucket}/${var.tenant_id}/"
}

# ============================================================================
# Outputs
# ============================================================================

output "s3_bucket_name" {
  description = "Name of the S3 bucket"
  value       = aws_s3_bucket.data_lake.bucket
}

output "s3_bucket_arn" {
  description = "ARN of the S3 bucket"
  value       = aws_s3_bucket.data_lake.arn
}

output "s3_bucket_region" {
  description = "Region of the S3 bucket"
  value       = aws_s3_bucket.data_lake.region
}

output "iam_role_arn" {
  description = "ARN of the IAM role for Dativo ETL jobs"
  value       = aws_iam_role.dativo_etl.arn
}

output "iam_role_name" {
  description = "Name of the IAM role"
  value       = aws_iam_role.dativo_etl.name
}

output "glue_database_name" {
  description = "Name of the Glue catalog database"
  value       = var.enable_glue_catalog ? aws_glue_catalog_database.iceberg[0].name : ""
}

output "glue_database_arn" {
  description = "ARN of the Glue catalog database"
  value       = var.enable_glue_catalog ? aws_glue_catalog_database.iceberg[0].arn : ""
}

output "aws_region" {
  description = "AWS region"
  value       = var.region
}

output "tenant_id" {
  description = "Tenant ID"
  value       = var.tenant_id
}

output "environment" {
  description = "Environment name"
  value       = var.environment
}
