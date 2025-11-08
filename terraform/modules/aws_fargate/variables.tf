# AWS Fargate Module Variables

variable "region" {
  description = "AWS region for deployment"
  type        = string
}

variable "job_metadata" {
  description = "Job metadata tags from Dativo job config (job_name, team, pipeline_type, environment, cost_center)"
  type        = map(string)

  validation {
    condition = alltrue([
      contains(keys(var.job_metadata), "job_name"),
      contains(keys(var.job_metadata), "team"),
      contains(keys(var.job_metadata), "pipeline_type"),
      contains(keys(var.job_metadata), "environment"),
      contains(keys(var.job_metadata), "cost_center")
    ])
    error_message = "job_metadata must contain: job_name, team, pipeline_type, environment, cost_center"
  }
}

variable "default_tags" {
  description = "Default tags to apply to all resources"
  type        = map(string)
  default     = {}
}

variable "container_image" {
  description = "Docker container image URI (e.g., ECR repository URI)"
  type        = string
}

variable "cpu" {
  description = "Fargate task CPU units (256, 512, 1024, 2048, 4096)"
  type        = string
  default     = "1024"

  validation {
    condition     = contains(["256", "512", "1024", "2048", "4096"], var.cpu)
    error_message = "CPU must be one of: 256, 512, 1024, 2048, 4096"
  }
}

variable "memory" {
  description = "Fargate task memory in MiB (must be compatible with CPU)"
  type        = string
  default     = "2048"
}

variable "vpc_id" {
  description = "VPC ID for Fargate tasks"
  type        = string
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for Fargate tasks"
  type        = list(string)
}

variable "assign_public_ip" {
  description = "Assign public IP to Fargate tasks (required if using public subnets)"
  type        = bool
  default     = false
}

variable "s3_bucket_arns" {
  description = "List of S3 bucket ARNs that tasks need access to"
  type        = list(string)
  default     = []
}

variable "secrets_arns" {
  description = "List of AWS Secrets Manager secret ARNs"
  type        = list(string)
  default     = []
}

variable "environment_variables" {
  description = "Environment variables for the container"
  type = list(object({
    name  = string
    value = string
  }))
  default = []
}

variable "secrets_from_ssm" {
  description = "Secrets from AWS Secrets Manager or SSM Parameter Store"
  type = list(object({
    name      = string
    valueFrom = string
  }))
  default = []
}

variable "enable_container_insights" {
  description = "Enable CloudWatch Container Insights for the cluster"
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention period in days"
  type        = number
  default     = 30
}

variable "create_service" {
  description = "Create an ECS Service (for long-running jobs). Set to false for scheduled/batch jobs."
  type        = bool
  default     = false
}

variable "service_desired_count" {
  description = "Desired number of tasks for the ECS Service (if create_service is true)"
  type        = number
  default     = 1
}
