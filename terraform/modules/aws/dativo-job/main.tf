# Dativo ETL Job - AWS ECS Fargate Module
#
# This module provisions infrastructure for a Dativo ETL job on AWS using ECS Fargate.
# It includes comprehensive tag propagation for cost allocation, compliance, and resource traceability.

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Variables
variable "job_name" {
  description = "Name of the Dativo job"
  type        = string
}

variable "tenant_id" {
  description = "Tenant identifier"
  type        = string
}

variable "image_uri" {
  description = "Docker image URI for the job"
  type        = string
}

variable "cpu" {
  description = "CPU units for the task (1024 = 1 vCPU)"
  type        = number
  default     = 1024
}

variable "memory" {
  description = "Memory in MB for the task"
  type        = number
  default     = 2048
}

variable "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  type        = string
}

variable "subnet_ids" {
  description = "List of subnet IDs for the task"
  type        = list(string)
}

variable "security_group_ids" {
  description = "List of security group IDs"
  type        = list(string)
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "job_config_path" {
  description = "Path to job configuration file in container"
  type        = string
  default     = "/app/jobs"
}

variable "environment_variables" {
  description = "Additional environment variables"
  type        = map(string)
  default     = {}
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

# ECS Task Definition
resource "aws_ecs_task_definition" "job" {
  family                   = "${var.tenant_id}-${var.job_name}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.cpu
  memory                   = var.memory

  container_definitions = jsonencode([{
    name      = var.job_name
    image     = var.image_uri
    essential = true

    environment = concat(
      [
        {
          name  = "TENANT_ID"
          value = var.tenant_id
        },
        {
          name  = "JOB_CONFIG_PATH"
          value = "${var.job_config_path}/${var.tenant_id}/${var.job_name}.yaml"
        }
      ],
      [for k, v in var.environment_variables : {
        name  = k
        value = v
      }]
    )

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.job.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }
  }])

  tags = merge(
    var.tags,
    {
      Name        = "${var.tenant_id}-${var.job_name}"
      ManagedBy    = "dativo-terraform"
      ResourceType = "ecs-task-definition"
    }
  )
}

# ECS Service
resource "aws_ecs_service" "job" {
  name            = "${var.tenant_id}-${var.job_name}-service"
  cluster         = var.ecs_cluster_name
  task_definition = aws_ecs_task_definition.job.arn
  desired_count   = 0 # Manual trigger or via EventBridge
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = var.security_group_ids
    assign_public_ip = false
  }

  tags = merge(
    var.tags,
    {
      Name        = "${var.tenant_id}-${var.job_name}-service"
      ManagedBy    = "dativo-terraform"
      ResourceType = "ecs-service"
    }
  )
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "job" {
  name              = "/ecs/${var.tenant_id}-${var.job_name}"
  retention_in_days = 14

  tags = merge(
    var.tags,
    {
      Name        = "${var.tenant_id}-${var.job_name}-logs"
      ManagedBy    = "dativo-terraform"
      ResourceType = "cloudwatch-log-group"
    }
  )
}

# EventBridge Rule (optional - for scheduled execution)
resource "aws_cloudwatch_event_rule" "job_schedule" {
  count               = var.schedule_expression != null ? 1 : 0
  name                = "${var.tenant_id}-${var.job_name}-schedule"
  description         = "Schedule for ${var.tenant_id}/${var.job_name}"
  schedule_expression = var.schedule_expression

  tags = merge(
    var.tags,
    {
      Name        = "${var.tenant_id}-${var.job_name}-schedule"
      ManagedBy    = "dativo-terraform"
      ResourceType = "eventbridge-rule"
    }
  )
}

resource "aws_cloudwatch_event_target" "job_target" {
  count     = var.schedule_expression != null && var.ecs_cluster_arn != null ? 1 : 0
  rule      = aws_cloudwatch_event_rule.job_schedule[0].name
  target_id = "${var.tenant_id}-${var.job_name}-target"
  arn       = var.ecs_cluster_arn
  role_arn  = aws_iam_role.eventbridge_role[0].arn

  ecs_target {
    task_count          = 1
    task_definition_arn = aws_ecs_task_definition.job.arn
    launch_type         = "FARGATE"

    network_configuration {
      subnets          = var.subnet_ids
      security_groups  = var.security_group_ids
      assign_public_ip = false
    }
  }
}

# IAM Role for EventBridge (if scheduling is enabled)
resource "aws_iam_role" "eventbridge_role" {
  count = var.schedule_expression != null && var.ecs_cluster_arn != null ? 1 : 0
  name  = "${var.tenant_id}-${var.job_name}-eventbridge-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "events.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = merge(
    var.tags,
    {
      Name        = "${var.tenant_id}-${var.job_name}-eventbridge-role"
      ManagedBy    = "dativo-terraform"
      ResourceType = "iam-role"
    }
  )
}

resource "aws_iam_role_policy" "eventbridge_policy" {
  count = var.schedule_expression != null && var.ecs_cluster_arn != null ? 1 : 0
  name  = "${var.tenant_id}-${var.job_name}-eventbridge-policy"
  role  = aws_iam_role.eventbridge_role[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ecs:RunTask"
      ]
      Resource = aws_ecs_task_definition.job.arn
    }, {
      Effect = "Allow"
      Action = [
        "iam:PassRole"
      ]
      Resource = "*"
      Condition = {
        StringEquals = {
          "iam:PassedToService" = "ecs-tasks.amazonaws.com"
        }
      }
    }]
  })
}

# Outputs
output "task_definition_arn" {
  description = "ARN of the ECS task definition"
  value       = aws_ecs_task_definition.job.arn
}

output "service_name" {
  description = "Name of the ECS service"
  value       = aws_ecs_service.job.name
}

output "log_group_name" {
  description = "Name of the CloudWatch log group"
  value       = aws_cloudwatch_log_group.job.name
}
