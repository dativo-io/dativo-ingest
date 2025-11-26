# ==============================================================================
# AWS Module Variables
# ==============================================================================

# These variables are automatically populated from the Dativo job configuration
# infrastructure block via the Python infrastructure module.

variable "provider" {
  description = "Cloud provider (should be 'aws')"
  type        = string
  default     = "aws"
}

variable "runtime_type" {
  description = "Runtime orchestration platform"
  type        = string
}

variable "compute" {
  description = "Compute configuration"
  type = object({
    cpu           = optional(string, "1024")
    memory        = optional(string, "2048")
    disk_size     = optional(string, "20")
    instance_type = optional(string)
  })
}

variable "scaling" {
  description = "Auto-scaling configuration"
  type = object({
    min_instances           = optional(number, 1)
    max_instances           = optional(number, 5)
    target_cpu_utilization  = optional(number, 70)
  })
}

variable "timeout_seconds" {
  description = "Maximum execution time in seconds"
  type        = number
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
    }))
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
    }))
  })
}

variable "tags" {
  description = "Resource tags (automatically propagated from job config)"
  type        = map(string)
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "job_name" {
  description = "Job name"
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
