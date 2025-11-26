# ==============================================================================
# Dativo ETL Job Infrastructure - AWS Module
# ==============================================================================
# This module provisions cloud infrastructure for Dativo ETL jobs on AWS
# with comprehensive tag propagation for cost allocation and compliance.
#
# Supports:
# - ECS Fargate tasks for containerized job execution
# - Dagster Cloud integration
# - VPC networking with private/public subnet configuration
# - S3 buckets for data and state storage
# - CloudWatch logging and monitoring
# - IAM roles and policies
# - Comprehensive resource tagging
# ==============================================================================

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# ==============================================================================
# Variables
# ==============================================================================

variable "provider" {
  description = "Cloud provider (should be 'aws')"
  type        = string
  default     = "aws"
}

variable "runtime_type" {
  description = "Runtime orchestration platform (dagster, ecs, kubernetes)"
  type        = string
  
  validation {
    condition     = contains(["dagster", "ecs", "kubernetes", "airflow"], var.runtime_type)
    error_message = "Runtime type must be one of: dagster, ecs, kubernetes, airflow"
  }
}

variable "compute" {
  description = "Compute configuration for job execution"
  type = object({
    cpu        = optional(string, "1024")
    memory     = optional(string, "2048")
    disk_size  = optional(string, "20")
    instance_type = optional(string)
  })
  default = {
    cpu    = "1024"
    memory = "2048"
    disk_size = "20"
  }
}

variable "scaling" {
  description = "Auto-scaling configuration"
  type = object({
    min_instances           = optional(number, 1)
    max_instances           = optional(number, 5)
    target_cpu_utilization = optional(number, 70)
  })
  default = {
    min_instances           = 1
    max_instances           = 5
    target_cpu_utilization = 70
  }
}

variable "timeout_seconds" {
  description = "Maximum execution time in seconds"
  type        = number
  default     = 3600
}

variable "networking" {
  description = "Network configuration"
  type = object({
    vpc_id             = string
    subnet_ids         = list(string)
    security_group_ids = optional(list(string), [])
    private_access     = optional(bool, true)
  })
}

variable "storage" {
  description = "Storage configuration"
  type = object({
    state_bucket = string
    data_bucket  = string
    encryption = optional(object({
      enabled    = optional(bool, true)
      kms_key_id = optional(string)
    }), { enabled = true })
  })
}

variable "monitoring" {
  description = "Monitoring configuration"
  type = object({
    enabled           = optional(bool, true)
    metrics_namespace = optional(string)
    log_group         = optional(string)
    alerts = optional(object({
      channels   = optional(list(string), [])
      thresholds = optional(map(any), {})
    }), { channels = [], thresholds = {} })
  })
  default = {
    enabled = true
  }
}

variable "tags" {
  description = "Resource tags for cost allocation, compliance, and traceability"
  type        = map(string)
  default     = {}
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "job_name" {
  description = "Job name for resource naming"
  type        = string
}

variable "tenant_id" {
  description = "Tenant identifier"
  type        = string
}

variable "docker_image" {
  description = "Docker image for the job"
  type        = string
  default     = "dativo:latest"
}

# ==============================================================================
# Local Variables
# ==============================================================================

locals {
  # Merge provided tags with required tags
  common_tags = merge(
    var.tags,
    {
      Terraform   = "true"
      Module      = "dativo-etl-job"
      JobName     = var.job_name
      TenantId    = var.tenant_id
      RuntimeType = var.runtime_type
    }
  )
  
  # Resource name prefix
  name_prefix = "${var.tenant_id}-${var.job_name}"
  
  # Log group name
  log_group_name = var.monitoring.log_group != null ? var.monitoring.log_group : "/dativo/jobs/${var.tenant_id}/${var.job_name}"
  
  # Metrics namespace
  metrics_namespace = var.monitoring.metrics_namespace != null ? var.monitoring.metrics_namespace : "Dativo/Jobs"
}

# ==============================================================================
# IAM Roles and Policies
# ==============================================================================

# ECS Task Execution Role
resource "aws_iam_role" "ecs_task_execution_role" {
  name = "${local.name_prefix}-ecs-execution-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
  
  tags = local.common_tags
}

# Attach AWS managed policy for ECS task execution
resource "aws_iam_role_policy_attachment" "ecs_task_execution_role_policy" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# ECS Task Role (permissions for the running task)
resource "aws_iam_role" "ecs_task_role" {
  name = "${local.name_prefix}-ecs-task-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
  
  tags = local.common_tags
}

# S3 access policy for data and state buckets
resource "aws_iam_role_policy" "s3_access_policy" {
  name = "${local.name_prefix}-s3-access"
  role = aws_iam_role.ecs_task_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
          "s3:DeleteObject"
        ]
        Resource = [
          "arn:aws:s3:::${var.storage.data_bucket}",
          "arn:aws:s3:::${var.storage.data_bucket}/*",
          "arn:aws:s3:::${var.storage.state_bucket}",
          "arn:aws:s3:::${var.storage.state_bucket}/*"
        ]
      }
    ]
  })
}

# CloudWatch Logs policy
resource "aws_iam_role_policy" "cloudwatch_logs_policy" {
  count = var.monitoring.enabled ? 1 : 0
  
  name = "${local.name_prefix}-cloudwatch-logs"
  role = aws_iam_role.ecs_task_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.job_logs[0].arn}:*"
      }
    ]
  })
}

# KMS policy (if encryption is enabled with KMS)
resource "aws_iam_role_policy" "kms_policy" {
  count = var.storage.encryption.enabled && var.storage.encryption.kms_key_id != null ? 1 : 0
  
  name = "${local.name_prefix}-kms-access"
  role = aws_iam_role.ecs_task_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:Encrypt",
          "kms:GenerateDataKey"
        ]
        Resource = var.storage.encryption.kms_key_id
      }
    ]
  })
}

# ==============================================================================
# Security Group (if not provided)
# ==============================================================================

resource "aws_security_group" "job_sg" {
  count = length(var.networking.security_group_ids) == 0 ? 1 : 0
  
  name        = "${local.name_prefix}-sg"
  description = "Security group for Dativo ETL job ${var.job_name}"
  vpc_id      = var.networking.vpc_id
  
  # Egress to internet (for API calls, S3, etc.)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = merge(
    local.common_tags,
    {
      Name = "${local.name_prefix}-sg"
    }
  )
}

locals {
  security_group_ids = length(var.networking.security_group_ids) > 0 ? var.networking.security_group_ids : [aws_security_group.job_sg[0].id]
}

# ==============================================================================
# ECS Cluster and Task Definition
# ==============================================================================

resource "aws_ecs_cluster" "job_cluster" {
  name = "${local.name_prefix}-cluster"
  
  setting {
    name  = "containerInsights"
    value = var.monitoring.enabled ? "enabled" : "disabled"
  }
  
  tags = local.common_tags
}

resource "aws_ecs_task_definition" "job_task" {
  family                   = "${local.name_prefix}-task"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.compute.cpu
  memory                   = var.compute.memory
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn
  
  container_definitions = jsonencode([
    {
      name      = "dativo-job"
      image     = var.docker_image
      essential = true
      
      environment = [
        {
          name  = "DATIVO_TENANT_ID"
          value = var.tenant_id
        },
        {
          name  = "DATIVO_JOB_NAME"
          value = var.job_name
        },
        {
          name  = "DATIVO_RUNTIME_TYPE"
          value = var.runtime_type
        }
      ]
      
      logConfiguration = var.monitoring.enabled ? {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = local.log_group_name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "ecs"
        }
      } : null
    }
  ])
  
  tags = local.common_tags
}

# ==============================================================================
# CloudWatch Logs
# ==============================================================================

resource "aws_cloudwatch_log_group" "job_logs" {
  count = var.monitoring.enabled ? 1 : 0
  
  name              = local.log_group_name
  retention_in_days = 30
  
  tags = local.common_tags
}

# ==============================================================================
# CloudWatch Metrics and Alarms
# ==============================================================================

# Custom metric filters for job execution
resource "aws_cloudwatch_log_metric_filter" "job_errors" {
  count = var.monitoring.enabled ? 1 : 0
  
  name           = "${local.name_prefix}-errors"
  log_group_name = aws_cloudwatch_log_group.job_logs[0].name
  pattern        = "[time, request_id, event_type=*ERROR*, ...]"
  
  metric_transformation {
    name      = "JobErrors"
    namespace = local.metrics_namespace
    value     = "1"
    
    dimensions = {
      JobName  = var.job_name
      TenantId = var.tenant_id
    }
  }
}

resource "aws_cloudwatch_log_metric_filter" "job_success" {
  count = var.monitoring.enabled ? 1 : 0
  
  name           = "${local.name_prefix}-success"
  log_group_name = aws_cloudwatch_log_group.job_logs[0].name
  pattern        = "[time, request_id, event_type=job_finished, status=success, ...]"
  
  metric_transformation {
    name      = "JobSuccess"
    namespace = local.metrics_namespace
    value     = "1"
    
    dimensions = {
      JobName  = var.job_name
      TenantId = var.tenant_id
    }
  }
}

# ==============================================================================
# S3 Buckets (if they don't exist)
# ==============================================================================

# Note: In production, buckets are typically created separately.
# This is optional and controlled by create_buckets variable.

# ==============================================================================
# Outputs
# ==============================================================================

output "ecs_cluster_arn" {
  description = "ARN of the ECS cluster"
  value       = aws_ecs_cluster.job_cluster.arn
}

output "ecs_task_definition_arn" {
  description = "ARN of the ECS task definition"
  value       = aws_ecs_task_definition.job_task.arn
}

output "ecs_task_execution_role_arn" {
  description = "ARN of the ECS task execution role"
  value       = aws_iam_role.ecs_task_execution_role.arn
}

output "ecs_task_role_arn" {
  description = "ARN of the ECS task role"
  value       = aws_iam_role.ecs_task_role.arn
}

output "security_group_ids" {
  description = "Security group IDs for the job"
  value       = local.security_group_ids
}

output "log_group_name" {
  description = "CloudWatch log group name"
  value       = var.monitoring.enabled ? aws_cloudwatch_log_group.job_logs[0].name : null
}

output "resource_tags" {
  description = "All resource tags applied"
  value       = local.common_tags
}
