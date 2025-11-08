variable "region" {
  description = "AWS region where the runtime infrastructure is deployed."
  type        = string
}

variable "runtime_type" {
  description = "Runtime identifier propagated from the Dativo job configuration."
  type        = string
  default     = "aws_fargate"

  validation {
    condition     = var.runtime_type == "aws_fargate"
    error_message = "This module only supports the aws_fargate runtime."
  }
}

variable "tags" {
  description = "Job metadata tags propagated from the Dativo job definition."
  type        = map(string)
}

variable "default_tags" {
  description = "Baseline infrastructure tags applied by the platform/organization."
  type        = map(string)
  default     = {}
}

variable "existing_cluster_name" {
  description = "Optional pre-created ECS cluster name (skip cluster creation when provided)."
  type        = string
  default     = null
}

variable "existing_service_name" {
  description = "Optional pre-created ECS service name (skip service scaffolding when provided)."
  type        = string
  default     = null
}

variable "service_endpoint_override" {
  description = "Optional service endpoint override when managed outside of this module."
  type        = string
  default     = null
}

variable "deploy_example_resources" {
  description = "Set to true to provision the example ECS cluster demonstrating tag propagation."
  type        = bool
  default     = false
}

