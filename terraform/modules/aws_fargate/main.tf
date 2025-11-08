terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0.0"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = var.default_tags
  }
}

locals {
  merged_tags      = merge(var.default_tags, var.tags)
  normalized_name  = substr(regexreplace(lower(var.tags["job_name"]), "[^a-z0-9-]", "-"), 0, 50)
  cluster_name     = coalesce(var.existing_cluster_name, "${local.normalized_name}-cluster")
  service_name     = coalesce(var.existing_service_name, "${local.normalized_name}-service")
  service_endpoint = coalesce(
    var.service_endpoint_override,
    format("https://%s.%s.amazonaws.com", local.service_name, var.region)
  )
}

resource "aws_ecs_cluster" "example" {
  count = var.deploy_example_resources ? 1 : 0
  name  = local.cluster_name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = local.merged_tags
}

# -----------------------------------------------------------------------------
# Add the actual runtime resources (e.g., ECS service, task definition, ALB, IAM
# roles) in your implementation. Every resource should include:
#   tags = local.merged_tags
# This ensures FinOps and ownership metadata from the job definition propagates
# into every AWS object.
# -----------------------------------------------------------------------------
