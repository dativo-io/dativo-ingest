# Additional variables for GCP Dativo job module

variable "schedule_cron" {
  description = "Cron expression for Cloud Scheduler (e.g., '0 2 * * *')"
  type        = string
  default     = null
}

variable "timezone" {
  description = "Timezone for the schedule (e.g., 'America/New_York')"
  type        = string
  default     = "UTC"
}

variable "service_account_email" {
  description = "Service account email for Cloud Run"
  type        = string
  default     = null
}

variable "allow_unauthenticated" {
  description = "Allow unauthenticated invocations"
  type        = bool
  default     = false
}
