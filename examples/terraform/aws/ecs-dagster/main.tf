# Terraform module for Dativo ETL job on AWS ECS with Dagster
# This module provisions infrastructure for running Dativo ETL jobs in AWS
# with comprehensive tag propagation for cost allocation and compliance

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Local variables for tag merging
locals {
  # Merge tags from multiple sources with precedence
  common_tags = merge(
    var.tags,
    {
      "dativo:tenant"      = var.tenant_id
      "dativo:environment" = var.environment
      "dativo:job"         = var.job_name
      "dativo:managed-by"  = "terraform"
      "dativo:provider"    = var.provider
      "dativo:runtime"     = var.runtime_type
    }
  )
  
  # Format container resources
  container_cpu    = tonumber(replace(var.compute_cpu, "m", ""))
  container_memory = tonumber(replace(var.compute_memory, "Gi", "")) * 1024
}

# ECS Cluster (or use existing)
data "aws_ecs_cluster" "existing" {
  count        = var.create_cluster ? 0 : 1
  cluster_name = var.runtime_cluster_name
}

resource "aws_ecs_cluster" "dativo" {
  count = var.create_cluster ? 1 : 0
  name  = var.runtime_cluster_name
  
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
  
  tags = local.common_tags
}

# IAM Role for ECS Task Execution
resource "aws_iam_role" "task_execution" {
  name = "${var.job_name}-task-execution-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
  
  tags = local.common_tags
}

# Attach AWS managed policy for ECS task execution
resource "aws_iam_role_policy_attachment" "task_execution" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# IAM Role for ECS Task (application permissions)
resource "aws_iam_role" "task_role" {
  name = "${var.job_name}-task-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
  
  tags = local.common_tags
}

# Policy for S3 access
resource "aws_iam_role_policy" "s3_access" {
  name = "${var.job_name}-s3-access"
  role = aws_iam_role.task_role.id
  
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
          "arn:aws:s3:::${var.storage_bucket}",
          "arn:aws:s3:::${var.storage_bucket}/*"
        ]
      }
    ]
  })
}

# Policy for KMS access (if KMS key is provided)
resource "aws_iam_role_policy" "kms_access" {
  count = var.storage_kms_key_id != null ? 1 : 0
  
  name = "${var.job_name}-kms-access"
  role = aws_iam_role.task_role.id
  
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
        Resource = [var.storage_kms_key_id]
      }
    ]
  })
}

# Security Group for ECS Tasks
resource "aws_security_group" "ecs_tasks" {
  name        = "${var.job_name}-ecs-tasks"
  description = "Security group for Dativo ECS tasks"
  vpc_id      = var.networking_vpc_id
  
  # Egress to allow outbound connections
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound traffic"
  }
  
  tags = merge(
    local.common_tags,
    {
      Name = "${var.job_name}-ecs-tasks"
    }
  )
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "dativo" {
  name              = "/ecs/dativo/${var.tenant_id}/${var.job_name}"
  retention_in_days = var.log_retention_days
  
  kms_key_id = var.storage_kms_key_id
  
  tags = local.common_tags
}

# ECS Task Definition
resource "aws_ecs_task_definition" "dativo" {
  family                   = "${var.tenant_id}-${var.job_name}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = local.container_cpu
  memory                   = local.container_memory
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task_role.arn
  
  container_definitions = jsonencode([
    {
      name      = "dativo-etl"
      image     = var.container_image
      essential = true
      
      environment = concat(
        [
          {
            name  = "DATIVO_TENANT_ID"
            value = var.tenant_id
          },
          {
            name  = "DATIVO_ENVIRONMENT"
            value = var.environment
          },
          {
            name  = "DATIVO_JOB_NAME"
            value = var.job_name
          },
          {
            name  = "S3_BUCKET"
            value = var.storage_bucket
          },
          {
            name  = "S3_PREFIX"
            value = var.storage_prefix
          }
        ],
        var.additional_environment_variables
      )
      
      secrets = var.secrets_from_ssm
      
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.dativo.name
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "ecs"
        }
      }
      
      command = [
        "dativo",
        "run",
        "--config",
        "/app/jobs/${var.tenant_id}/${var.job_name}.yaml",
        "--mode",
        "self_hosted"
      ]
    }
  ])
  
  tags = local.common_tags
}

# Data source for current AWS region
data "aws_region" "current" {}

# Data source for current AWS account
data "aws_caller_identity" "current" {}

# Outputs for integration with Dagster
output "cluster_arn" {
  description = "ECS cluster ARN"
  value       = var.create_cluster ? aws_ecs_cluster.dativo[0].arn : data.aws_ecs_cluster.existing[0].arn
}

output "task_definition_arn" {
  description = "ECS task definition ARN"
  value       = aws_ecs_task_definition.dativo.arn
}

output "task_role_arn" {
  description = "Task execution role ARN"
  value       = aws_iam_role.task_role.arn
}

output "execution_role_arn" {
  description = "Task execution role ARN"
  value       = aws_iam_role.task_execution.arn
}

output "security_group_id" {
  description = "Security group ID for ECS tasks"
  value       = aws_security_group.ecs_tasks.id
}

output "log_group_name" {
  description = "CloudWatch log group name"
  value       = aws_cloudwatch_log_group.dativo.name
}

output "tags" {
  description = "Applied resource tags"
  value       = local.common_tags
}

# Outputs for Dagster ECS operator
output "dagster_ecs_config" {
  description = "Configuration for Dagster ECS operator"
  value = {
    cluster_arn          = var.create_cluster ? aws_ecs_cluster.dativo[0].arn : data.aws_ecs_cluster.existing[0].arn
    task_definition_arn  = aws_ecs_task_definition.dativo.arn
    execution_role_arn   = aws_iam_role.task_execution.arn
    task_role_arn        = aws_iam_role.task_role.arn
    subnet_ids           = var.networking_subnet_ids
    security_group_ids   = concat([aws_security_group.ecs_tasks.id], var.networking_security_group_ids)
    assign_public_ip     = !var.networking_private_networking
    launch_type          = "FARGATE"
    log_group            = aws_cloudwatch_log_group.dativo.name
  }
}
