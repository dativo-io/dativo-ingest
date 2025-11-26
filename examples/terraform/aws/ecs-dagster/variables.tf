# Variables for Dativo ETL job Terraform module (AWS ECS)

# Job identification
variable "job_name" {
  description = "Job name from Dativo configuration"
  type        = string
}

variable "tenant_id" {
  description = "Tenant ID from Dativo configuration"
  type        = string
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
}

# Cloud provider configuration
variable "provider" {
  description = "Cloud provider (should be 'aws' for this module)"
  type        = string
  default     = "aws"
}

# Runtime configuration
variable "runtime_type" {
  description = "Runtime type (ecs, dagster, etc.)"
  type        = string
  default     = "ecs"
}

variable "runtime_cluster_name" {
  description = "ECS cluster name"
  type        = string
}

variable "create_cluster" {
  description = "Whether to create a new ECS cluster or use existing"
  type        = bool
  default     = false
}

# Compute configuration
variable "compute_cpu" {
  description = "CPU request (e.g., '2', '1024', '2048')"
  type        = string
  default     = "1024"
}

variable "compute_memory" {
  description = "Memory request (e.g., '2Gi', '4Gi')"
  type        = string
  default     = "2Gi"
}

variable "compute_instance_type" {
  description = "EC2 instance type (for EC2 launch type)"
  type        = string
  default     = null
}

variable "compute_max_runtime_seconds" {
  description = "Maximum runtime in seconds before timeout"
  type        = number
  default     = 3600
}

# Networking configuration
variable "networking_vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "networking_subnet_ids" {
  description = "Subnet IDs"
  type        = list(string)
}

variable "networking_security_group_ids" {
  description = "Additional security group IDs"
  type        = list(string)
  default     = []
}

variable "networking_private_networking" {
  description = "Whether to use private networking (no public IP)"
  type        = bool
  default     = true
}

# Storage configuration
variable "storage_bucket" {
  description = "S3 bucket name for data output"
  type        = string
}

variable "storage_prefix" {
  description = "S3 prefix/path"
  type        = string
}

variable "storage_kms_key_id" {
  description = "KMS key ARN for encryption"
  type        = string
  default     = null
}

# Container configuration
variable "container_image" {
  description = "Docker container image for Dativo ETL"
  type        = string
  default     = "dativo/etl:latest"
}

variable "additional_environment_variables" {
  description = "Additional environment variables for the container"
  type = list(object({
    name  = string
    value = string
  }))
  default = []
}

variable "secrets_from_ssm" {
  description = "Secrets from AWS Systems Manager Parameter Store"
  type = list(object({
    name      = string
    valueFrom = string
  }))
  default = []
}

# Logging configuration
variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

# Tags
variable "tags" {
  description = "Resource tags for cost allocation and compliance"
  type        = map(string)
  default     = {}
}

# Dagster-specific configuration
variable "dagster_code_location" {
  description = "Dagster code location name"
  type        = string
  default     = null
}

variable "dagster_repository" {
  description = "Dagster repository name"
  type        = string
  default     = null
}
