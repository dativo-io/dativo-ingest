variable "region" {
  description = "AWS region where the Fargate runtime should be provisioned."
  type        = string
}

variable "runtime_type" {
  description = "Runtime selector. Must be set to \"aws_fargate\" when using this module."
  type        = string
  default     = "aws_fargate"

  validation {
    condition     = var.runtime_type == "aws_fargate"
    error_message = "runtime_type must be \"aws_fargate\" for the AWS Fargate module."
  }
}

variable "tags" {
  description = "Job metadata propagated from Dativo job configuration. Required keys: job_name, team, pipeline_type, environment, cost_center."
  type        = map(string)
}

variable "default_tags" {
  description = "Default tags applied to every resource by the platform/infrastructure team."
  type        = map(string)
  default     = {}
}

variable "cluster_name_override" {
  description = "Optional override for the ECS cluster name. Leave blank to derive from tags."
  type        = string
  default     = ""
}

variable "service_name_override" {
  description = "Optional override for the ECS/Fargate service name. Leave blank to derive from tags."
  type        = string
  default     = ""
}

variable "endpoint_url_override" {
  description = "Optional override for a service endpoint URL. Leave blank to derive from tags."
  type        = string
  default     = ""
}
