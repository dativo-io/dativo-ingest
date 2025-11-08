# AWS Fargate Runtime Module for Dativo ETL Jobs
# This module provisions ECS Fargate infrastructure for running Dativo containerized workloads

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Local variables for consistent naming and tagging
locals {
  # Merge default tags with job-specific metadata
  common_tags = merge(
    var.default_tags,
    var.job_metadata,
    {
      "managed_by"     = "terraform"
      "dativo_runtime" = "aws_fargate"
    }
  )

  # Resource naming convention
  name_prefix = "${var.job_metadata["job_name"]}-${var.job_metadata["environment"]}"
}

# ECS Cluster for Dativo jobs
resource "aws_ecs_cluster" "dativo_cluster" {
  name = "${local.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = var.enable_container_insights ? "enabled" : "disabled"
  }

  tags = local.common_tags
}

# CloudWatch Log Group for ECS task logs
resource "aws_cloudwatch_log_group" "dativo_logs" {
  name              = "/ecs/${local.name_prefix}"
  retention_in_days = var.log_retention_days

  tags = local.common_tags
}

# IAM Role for ECS Task Execution (pulls images, writes logs)
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

# Attach standard ECS execution policy
resource "aws_iam_role_policy_attachment" "ecs_task_execution_role_policy" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# IAM Role for ECS Task (application permissions)
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

# Attach custom policies for Dativo job (S3, Secrets Manager, etc.)
resource "aws_iam_role_policy" "dativo_job_policy" {
  name = "${local.name_prefix}-job-policy"
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ]
        Resource = var.s3_bucket_arns
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = var.secrets_arns
      }
    ]
  })
}

# ECS Task Definition
resource "aws_ecs_task_definition" "dativo_task" {
  family                   = local.name_prefix
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name      = "dativo-etl"
      image     = var.container_image
      essential = true

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.dativo_logs.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      environment = var.environment_variables

      # Secrets from AWS Secrets Manager
      secrets = var.secrets_from_ssm
    }
  ])

  tags = local.common_tags
}

# Security Group for Fargate tasks
resource "aws_security_group" "dativo_task_sg" {
  name        = "${local.name_prefix}-task-sg"
  description = "Security group for Dativo Fargate tasks"
  vpc_id      = var.vpc_id

  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    local.common_tags,
    {
      Name = "${local.name_prefix}-task-sg"
    }
  )
}

# Optional: ECS Service (for long-running jobs)
resource "aws_ecs_service" "dativo_service" {
  count = var.create_service ? 1 : 0

  name            = "${local.name_prefix}-service"
  cluster         = aws_ecs_cluster.dativo_cluster.id
  task_definition = aws_ecs_task_definition.dativo_task.arn
  desired_count   = var.service_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.dativo_task_sg.id]
    assign_public_ip = var.assign_public_ip
  }

  tags = local.common_tags
}
