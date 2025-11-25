# Terraform module for Dativo ETL on AWS EMR
# Provisions EMR cluster with comprehensive tag propagation

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "tenant_id" {
  description = "Tenant identifier from Dativo job configuration"
  type        = string
}

variable "environment" {
  description = "Environment name (prod, staging, dev)"
  type        = string
}

variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "tags" {
  description = "Complete tag set from Dativo (includes classification, FinOps, governance)"
  type        = map(string)
  default     = {}
}

variable "classification_tags" {
  description = "Data classification tags for compliance"
  type        = map(string)
  default     = {}
}

variable "finops_tags" {
  description = "FinOps tags for cost allocation"
  type        = map(string)
  default     = {}
}

variable "instance_type" {
  description = "EMR instance type"
  type        = string
  default     = "r5.2xlarge"
}

variable "instance_count" {
  description = "Number of EMR instances"
  type        = number
  default     = 3
}

variable "enable_autoscaling" {
  description = "Enable EMR auto-scaling"
  type        = bool
  default     = false
}

variable "min_instances" {
  description = "Minimum number of instances for auto-scaling"
  type        = number
  default     = 2
}

variable "max_instances" {
  description = "Maximum number of instances for auto-scaling"
  type        = number
  default     = 10
}

variable "vpc_id" {
  description = "VPC ID for EMR cluster"
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs for EMR cluster"
  type        = list(string)
}

variable "s3_bucket" {
  description = "S3 bucket for data storage"
  type        = string
}

variable "enable_spot_instances" {
  description = "Enable spot instances for cost optimization"
  type        = bool
  default     = false
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "enable_encryption" {
  description = "Enable encryption at rest and in transit"
  type        = bool
  default     = true
}

variable "kms_key_alias" {
  description = "KMS key alias for encryption"
  type        = string
  default     = "alias/dativo"
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Merge all tags
locals {
  common_tags = merge(
    var.tags,
    var.classification_tags,
    var.finops_tags,
    {
      "ManagedBy"           = "terraform"
      "TerraformModule"     = "dativo-emr"
      "CreatedAt"           = timestamp()
      "DativoTenant"        = var.tenant_id
      "DativoEnvironment"   = var.environment
    }
  )
  
  cluster_name = "dativo-${var.tenant_id}-${var.environment}"
}

# KMS key for encryption
resource "aws_kms_key" "dativo" {
  count               = var.enable_encryption ? 1 : 0
  description         = "KMS key for Dativo ${var.tenant_id} encryption"
  enable_key_rotation = true
  
  tags = local.common_tags
}

resource "aws_kms_alias" "dativo" {
  count         = var.enable_encryption ? 1 : 0
  name          = var.kms_key_alias
  target_key_id = aws_kms_key.dativo[0].key_id
}

# S3 bucket for logs
resource "aws_s3_bucket" "emr_logs" {
  bucket = "${var.s3_bucket}-emr-logs"
  
  tags = local.common_tags
}

resource "aws_s3_bucket_versioning" "emr_logs" {
  bucket = aws_s3_bucket.emr_logs.id
  
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "emr_logs" {
  count  = var.enable_encryption ? 1 : 0
  bucket = aws_s3_bucket.emr_logs.id
  
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.dativo[0].arn
    }
  }
}

# Security group for EMR
resource "aws_security_group" "emr_master" {
  name        = "${local.cluster_name}-master"
  description = "Security group for EMR master nodes"
  vpc_id      = var.vpc_id
  
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = merge(
    local.common_tags,
    {
      "Name" = "${local.cluster_name}-master"
    }
  )
}

resource "aws_security_group" "emr_slave" {
  name        = "${local.cluster_name}-slave"
  description = "Security group for EMR slave nodes"
  vpc_id      = var.vpc_id
  
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = merge(
    local.common_tags,
    {
      "Name" = "${local.cluster_name}-slave"
    }
  )
}

# IAM role for EMR
resource "aws_iam_role" "emr_service_role" {
  name = "${local.cluster_name}-service-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "elasticmapreduce.amazonaws.com"
        }
      }
    ]
  })
  
  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "emr_service_role" {
  role       = aws_iam_role.emr_service_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonElasticMapReduceRole"
}

resource "aws_iam_role" "emr_ec2_role" {
  name = "${local.cluster_name}-ec2-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })
  
  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "emr_ec2_role" {
  role       = aws_iam_role.emr_ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonElasticMapReduceforEC2Role"
}

# S3 access policy
resource "aws_iam_role_policy" "emr_s3_access" {
  name = "${local.cluster_name}-s3-access"
  role = aws_iam_role.emr_ec2_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${var.s3_bucket}",
          "arn:aws:s3:::${var.s3_bucket}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_instance_profile" "emr_ec2" {
  name = "${local.cluster_name}-ec2-profile"
  role = aws_iam_role.emr_ec2_role.name
  
  tags = local.common_tags
}

# EMR Cluster
resource "aws_emr_cluster" "dativo" {
  name          = local.cluster_name
  release_label = "emr-6.15.0"
  applications  = ["Spark", "Hadoop", "Hive"]
  
  service_role = aws_iam_role.emr_service_role.arn
  
  ec2_attributes {
    subnet_id                         = var.subnet_ids[0]
    emr_managed_master_security_group = aws_security_group.emr_master.id
    emr_managed_slave_security_group  = aws_security_group.emr_slave.id
    instance_profile                  = aws_iam_instance_profile.emr_ec2.arn
  }
  
  master_instance_group {
    instance_type  = var.instance_type
    instance_count = 1
  }
  
  core_instance_group {
    instance_type  = var.instance_type
    instance_count = var.instance_count
    
    dynamic "ebs_config" {
      for_each = var.enable_encryption ? [1] : []
      content {
        size                 = 100
        type                 = "gp3"
        volumes_per_instance = 1
      }
    }
  }
  
  dynamic "core_instance_group" {
    for_each = var.enable_autoscaling ? [1] : []
    content {
      autoscaling_policy = jsonencode({
        Constraints = {
          MinCapacity = var.min_instances
          MaxCapacity = var.max_instances
        }
        Rules = [
          {
            Name = "ScaleUpOnYARNMemory"
            Action = {
              SimpleScalingPolicyConfiguration = {
                AdjustmentType = "CHANGE_IN_CAPACITY"
                ScalingAdjustment = 1
                CoolDown = 300
              }
            }
            Trigger = {
              CloudWatchAlarmDefinition = {
                ComparisonOperator = "LESS_THAN"
                EvaluationPeriods = 1
                MetricName = "YARNMemoryAvailablePercentage"
                Namespace = "AWS/ElasticMapReduce"
                Period = 300
                Statistic = "AVERAGE"
                Threshold = 25
                Unit = "PERCENT"
              }
            }
          }
        ]
      })
    }
  }
  
  configurations_json = jsonencode([
    {
      Classification = "spark-defaults"
      Properties = {
        "spark.executor.memory"    = "10g"
        "spark.executor.cores"     = "4"
        "spark.driver.memory"      = "10g"
        "spark.sql.adaptive.enabled" = "true"
      }
    }
  ])
  
  log_uri = "s3://${aws_s3_bucket.emr_logs.id}/logs/"
  
  tags = local.common_tags
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "dativo" {
  name              = "/aws/emr/${local.cluster_name}"
  retention_in_days = var.log_retention_days
  
  tags = local.common_tags
}

# Outputs
output "emr_cluster_id" {
  description = "EMR cluster ID"
  value       = aws_emr_cluster.dativo.id
}

output "emr_cluster_arn" {
  description = "EMR cluster ARN"
  value       = aws_emr_cluster.dativo.arn
}

output "emr_master_public_dns" {
  description = "EMR master node public DNS"
  value       = aws_emr_cluster.dativo.master_public_dns
}

output "emr_log_bucket" {
  description = "S3 bucket for EMR logs"
  value       = aws_s3_bucket.emr_logs.id
}

output "applied_tags" {
  description = "All tags applied to resources"
  value       = local.common_tags
}

output "classification_tags" {
  description = "Classification tags for compliance"
  value       = var.classification_tags
}

output "finops_tags" {
  description = "FinOps tags for cost allocation"
  value       = var.finops_tags
}
