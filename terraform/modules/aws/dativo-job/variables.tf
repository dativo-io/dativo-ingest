# Additional variables for AWS Dativo job module

variable "schedule_expression" {
  description = "EventBridge schedule expression (e.g., 'cron(0 2 * * ? *)')"
  type        = string
  default     = null
}

variable "ecs_cluster_arn" {
  description = "ARN of the ECS cluster"
  type        = string
  default     = null
}
