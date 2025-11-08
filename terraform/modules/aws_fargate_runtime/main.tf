terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

locals {
  merged_tags    = merge(var.default_tags, var.tags)
  runtime_suffix = replace(var.runtime_type, "aws_", "")
  cluster_name = var.cluster_name_override != ""
    ? var.cluster_name_override
    : format("%s-%s-cluster", var.tags["job_name"], local.runtime_suffix)
  service_name = var.service_name_override != ""
    ? var.service_name_override
    : format("%s-%s-service", var.tags["job_name"], local.runtime_suffix)
  endpoint_url = var.endpoint_url_override != ""
    ? var.endpoint_url_override
    : format("https://%s.%s.amazonaws.com", local.service_name, var.region)
}

# -------------------------------------------------------------------
# Replace the following examples with actual infrastructure resources
# (ECS cluster, IAM roles, load balancers, etc). Ensure every resource
# sets tags = local.merged_tags so cost allocation and governance
# metadata from the Dativo job definition propagate consistently.
# -------------------------------------------------------------------

# Example:
# resource "aws_ecs_cluster" "runtime" {
#   name = local.cluster_name
#   tags = local.merged_tags
# }
#
# resource "aws_ecs_service" "runtime" {
#   name            = local.service_name
#   cluster         = aws_ecs_cluster.runtime.id
#   launch_type     = "FARGATE"
#   desired_count   = 1
#   task_definition = aws_ecs_task_definition.runtime.arn
#   tags            = local.merged_tags
# }
