"""Terraform configuration generator for Dativo ETL jobs.

This module generates Terraform configurations for deploying Dativo ETL jobs
on AWS or GCP infrastructure. It supports cloud-agnostic deployment with
comprehensive tag propagation for cost allocation, compliance, and resource
traceability.

Key Features:
- Cloud-agnostic deployment (AWS ECS/EKS, GCP GKE/Cloud Run)
- Tag propagation from job config to infrastructure resources
- Integration with externally provisioned infrastructure (VPC, subnets, IAM roles)
- Support for Dagster orchestration deployment
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import JobConfig, InfrastructureConfig


class TerraformGenerator:
    """Generate Terraform configurations for Dativo ETL jobs."""

    def __init__(self, job_config: JobConfig):
        """Initialize Terraform generator.

        Args:
            job_config: Job configuration with infrastructure block
        """
        self.job_config = job_config
        self.infrastructure = job_config.infrastructure

        if not self.infrastructure:
            raise ValueError("Job configuration must include infrastructure block")

    def _merge_tags(self) -> Dict[str, str]:
        """Merge tags from multiple sources with proper precedence.

        Tag hierarchy (highest to lowest priority):
        1. Infrastructure tags (from infrastructure.tags)
        2. FinOps tags (from job config)
        3. Governance tags (from asset definition)
        4. Default tags (tenant_id, environment, job_name)

        Returns:
            Merged tag dictionary
        """
        tags = {}

        # Level 4: Default tags
        tags["tenant_id"] = self.job_config.tenant_id
        tags["managed_by"] = "dativo"
        tags["job_type"] = "etl"

        if self.job_config.environment:
            tags["environment"] = self.job_config.environment

        # Level 3: Governance tags from asset definition
        try:
            asset = self.job_config._resolve_asset()
            if asset.team and asset.team.owner:
                tags["owner"] = asset.team.owner
            if asset.domain:
                tags["domain"] = asset.domain
            if asset.compliance and asset.compliance.regulations:
                tags["compliance"] = ",".join(asset.compliance.regulations)
        except Exception:
            pass

        # Level 2: FinOps tags from job config
        if self.job_config.finops:
            if self.job_config.finops.get("cost_center"):
                tags["cost_center"] = self.job_config.finops["cost_center"]
            if self.job_config.finops.get("project"):
                tags["project"] = self.job_config.finops["project"]
            if self.job_config.finops.get("environment"):
                tags["environment"] = self.job_config.finops["environment"]
            if self.job_config.finops.get("business_tags"):
                business_tags = self.job_config.finops["business_tags"]
                if isinstance(business_tags, list):
                    tags["business_tags"] = ",".join(business_tags)
                else:
                    tags["business_tags"] = str(business_tags)

        # Level 1: Infrastructure tags (HIGHEST priority)
        if self.infrastructure.tags:
            infra_tags_dict = self.infrastructure.tags.model_dump(exclude_none=True)
            for key, value in infra_tags_dict.items():
                if key == "compliance" and isinstance(value, list):
                    tags["compliance"] = ",".join(value)
                else:
                    tags[key] = str(value)

        return tags

    def generate_aws_ecs_task_definition(self) -> Dict[str, Any]:
        """Generate AWS ECS task definition.

        Returns:
            ECS task definition as dictionary
        """
        if self.infrastructure.provider != "aws":
            raise ValueError("AWS ECS requires provider='aws'")

        if not self.infrastructure.compute or self.infrastructure.compute.type != "ecs":
            raise ValueError("ECS task definition requires compute.type='ecs'")

        tags = self._merge_tags()

        # Convert tags to ECS format (list of key-value pairs)
        ecs_tags = [{"key": k, "value": v} for k, v in tags.items()]

        task_def = {
            "family": f"dativo-{self.job_config.tenant_id}",
            "networkMode": "awsvpc",
            "requiresCompatibilities": ["FARGATE"],
            "cpu": self.infrastructure.compute.task_cpu or "256",
            "memory": self.infrastructure.compute.task_memory or "512",
            "executionRoleArn": self.infrastructure.compute.execution_role_arn,
            "taskRoleArn": self.infrastructure.compute.task_role_arn,
            "containerDefinitions": [
                {
                    "name": "dativo-etl",
                    "image": "${var.container_image}",
                    "essential": True,
                    "command": [
                        "run",
                        "--config",
                        "/app/jobs/${var.job_config_path}",
                        "--mode",
                        "self_hosted",
                    ],
                    "environment": [
                        {"name": "TENANT_ID", "value": self.job_config.tenant_id},
                        {
                            "name": "ENVIRONMENT",
                            "value": self.job_config.environment or "prod",
                        },
                    ],
                    "logConfiguration": {
                        "logDriver": "awslogs",
                        "options": {
                            "awslogs-group": self.infrastructure.monitoring.log_group
                            if self.infrastructure.monitoring
                            else f"/ecs/dativo/{self.job_config.tenant_id}",
                            "awslogs-region": self.infrastructure.region,
                            "awslogs-stream-prefix": "ecs",
                        },
                    },
                }
            ],
            "tags": ecs_tags,
        }

        # Add storage configuration if specified
        if self.infrastructure.storage and self.infrastructure.storage.bucket:
            task_def["containerDefinitions"][0]["environment"].append(
                {"name": "S3_BUCKET", "value": self.infrastructure.storage.bucket}
            )

        return task_def

    def generate_gcp_cloud_run_service(self) -> Dict[str, Any]:
        """Generate GCP Cloud Run service configuration.

        Returns:
            Cloud Run service as dictionary
        """
        if self.infrastructure.provider != "gcp":
            raise ValueError("GCP Cloud Run requires provider='gcp'")

        if (
            not self.infrastructure.compute
            or self.infrastructure.compute.type != "cloud_run"
        ):
            raise ValueError("Cloud Run service requires compute.type='cloud_run'")

        tags = self._merge_tags()

        # Convert tags to GCP labels format (lowercase, alphanumeric + hyphens/underscores)
        gcp_labels = {}
        for key, value in tags.items():
            label_key = key.lower().replace(".", "_").replace(" ", "_")
            label_value = value.lower().replace(".", "_").replace(" ", "_")
            # GCP labels must be 63 chars or less
            gcp_labels[label_key[:63]] = label_value[:63]

        service = {
            "apiVersion": "serving.knative.dev/v1",
            "kind": "Service",
            "metadata": {
                "name": f"dativo-{self.job_config.tenant_id}",
                "labels": gcp_labels,
            },
            "spec": {
                "template": {
                    "metadata": {"labels": gcp_labels},
                    "spec": {
                        "serviceAccountName": self.infrastructure.compute.service_account,
                        "containers": [
                            {
                                "image": "${var.container_image}",
                                "command": [
                                    "python",
                                    "-m",
                                    "dativo_ingest.cli",
                                    "run",
                                    "--config",
                                    "/app/jobs/${var.job_config_path}",
                                    "--mode",
                                    "self_hosted",
                                ],
                                "env": [
                                    {
                                        "name": "TENANT_ID",
                                        "value": self.job_config.tenant_id,
                                    },
                                    {
                                        "name": "ENVIRONMENT",
                                        "value": self.job_config.environment or "prod",
                                    },
                                ],
                                "resources": {
                                    "limits": {
                                        "cpu": self.infrastructure.compute.task_cpu
                                        or "1000m",
                                        "memory": f"{self.infrastructure.compute.task_memory or '512'}Mi",
                                    }
                                },
                            }
                        ],
                    },
                },
            },
        }

        # Add storage configuration if specified
        if self.infrastructure.storage and self.infrastructure.storage.bucket:
            service["spec"]["template"]["spec"]["containers"][0]["env"].append(
                {"name": "GCS_BUCKET", "value": self.infrastructure.storage.bucket}
            )

        return service

    def generate_terraform_variables(self) -> Dict[str, Any]:
        """Generate Terraform variables file content.

        Returns:
            Terraform variables as dictionary
        """
        variables = self.infrastructure.to_terraform_vars()

        # Add job-specific variables
        variables["tenant_id"] = self.job_config.tenant_id
        variables["environment"] = self.job_config.environment or "prod"
        variables["job_name"] = f"dativo-{self.job_config.tenant_id}"

        # Add merged tags
        variables["tags"] = self._merge_tags()

        return variables

    def generate_terraform_module(self, output_dir: Path) -> None:
        """Generate complete Terraform module for deployment.

        Args:
            output_dir: Directory to write Terraform files
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate main.tf
        main_tf_content = self._generate_main_tf()
        (output_dir / "main.tf").write_text(main_tf_content)

        # Generate variables.tf
        variables_tf_content = self._generate_variables_tf()
        (output_dir / "variables.tf").write_text(variables_tf_content)

        # Generate terraform.tfvars
        tfvars_content = self._generate_tfvars()
        (output_dir / "terraform.tfvars.json").write_text(
            json.dumps(tfvars_content, indent=2)
        )

        # Generate outputs.tf
        outputs_tf_content = self._generate_outputs_tf()
        (output_dir / "outputs.tf").write_text(outputs_tf_content)

    def _generate_main_tf(self) -> str:
        """Generate main.tf content."""
        if self.infrastructure.provider == "aws":
            return self._generate_aws_main_tf()
        elif self.infrastructure.provider == "gcp":
            return self._generate_gcp_main_tf()
        else:
            raise ValueError(f"Unsupported provider: {self.infrastructure.provider}")

    def _generate_aws_main_tf(self) -> str:
        """Generate AWS main.tf content."""
        content = f"""# Terraform configuration for Dativo ETL job
# Provider: AWS
# Generated from job config: {self.job_config.tenant_id}

terraform {{
  required_version = ">= 1.0"
  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }}
  }}
}}

provider "aws" {{
  region = var.region
  
  default_tags {{
    tags = var.tags
  }}
}}

# ECS Task Definition
resource "aws_ecs_task_definition" "dativo_etl" {{
  family                   = var.job_name
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.compute.task_cpu
  memory                   = var.compute.task_memory
  execution_role_arn       = var.compute.execution_role_arn
  task_role_arn            = var.compute.task_role_arn

  container_definitions = jsonencode([
    {{
      name      = "dativo-etl"
      image     = var.container_image
      essential = true
      command = [
        "run",
        "--config",
        "/app/jobs/${{var.job_config_path}}",
        "--mode",
        "self_hosted"
      ]
      environment = [
        {{
          name  = "TENANT_ID"
          value = var.tenant_id
        }},
        {{
          name  = "ENVIRONMENT"
          value = var.environment
        }},
        {{
          name  = "S3_BUCKET"
          value = var.storage.bucket
        }}
      ]
      logConfiguration = {{
        logDriver = "awslogs"
        options = {{
          "awslogs-group"         = var.monitoring.log_group
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "ecs"
        }}
      }}
    }}
  ])

  tags = var.tags
}}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "dativo_etl" {{
  name              = var.monitoring.log_group
  retention_in_days = 30

  tags = var.tags
}}

# ECS Service (optional, for scheduled execution)
resource "aws_ecs_service" "dativo_etl" {{
  count           = var.enable_service ? 1 : 0
  name            = var.job_name
  cluster         = var.compute.cluster_name
  task_definition = aws_ecs_task_definition.dativo_etl.arn
  desired_count   = 0  # Runs on-demand via Dagster

  network_configuration {{
    subnets          = var.network.subnets
    security_groups  = var.network.security_groups
    assign_public_ip = false
  }}

  tags = var.tags
}}
"""
        return content

    def _generate_gcp_main_tf(self) -> str:
        """Generate GCP main.tf content."""
        content = f"""# Terraform configuration for Dativo ETL job
# Provider: GCP
# Generated from job config: {self.job_config.tenant_id}

terraform {{
  required_version = ">= 1.0"
  required_providers {{
    google = {{
      source  = "hashicorp/google"
      version = "~> 5.0"
    }}
  }}
}}

provider "google" {{
  project = var.project_id
  region  = var.region
}}

# Cloud Run Service
resource "google_cloud_run_service" "dativo_etl" {{
  name     = var.job_name
  location = var.region

  template {{
    spec {{
      service_account_name = var.compute.service_account
      
      containers {{
        image = var.container_image
        command = [
          "python",
          "-m",
          "dativo_ingest.cli",
          "run",
          "--config",
          "/app/jobs/${{var.job_config_path}}",
          "--mode",
          "self_hosted"
        ]
        
        env {{
          name  = "TENANT_ID"
          value = var.tenant_id
        }}
        
        env {{
          name  = "ENVIRONMENT"
          value = var.environment
        }}
        
        env {{
          name  = "GCS_BUCKET"
          value = var.storage.bucket
        }}
        
        resources {{
          limits = {{
            cpu    = var.compute.task_cpu
            memory = "${{var.compute.task_memory}}Mi"
          }}
        }}
      }}
    }}
    
    metadata {{
      labels = var.tags
    }}
  }}
  
  metadata {{
    labels = var.tags
  }}

  traffic {{
    percent         = 100
    latest_revision = true
  }}
}}

# Cloud Scheduler Job (optional, for scheduled execution)
resource "google_cloud_scheduler_job" "dativo_etl" {{
  count       = var.enable_scheduler ? 1 : 0
  name        = "${{var.job_name}}-scheduler"
  description = "Scheduled execution for Dativo ETL job"
  schedule    = var.schedule_cron
  time_zone   = "UTC"
  region      = var.region

  http_target {{
    http_method = "POST"
    uri         = google_cloud_run_service.dativo_etl.status[0].url
    
    oidc_token {{
      service_account_email = var.compute.service_account
    }}
  }}
}}
"""
        return content

    def _generate_variables_tf(self) -> str:
        """Generate variables.tf content."""
        content = """# Terraform variables for Dativo ETL job

variable "region" {
  description = "Cloud region"
  type        = string
}

variable "tenant_id" {
  description = "Tenant identifier"
  type        = string
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "job_name" {
  description = "Job name"
  type        = string
}

variable "container_image" {
  description = "Docker container image"
  type        = string
  default     = "dativo:latest"
}

variable "job_config_path" {
  description = "Path to job configuration file"
  type        = string
}

variable "compute" {
  description = "Compute configuration"
  type = object({
    type                = string
    cluster_name        = optional(string)
    task_cpu            = optional(string)
    task_memory         = optional(string)
    execution_role_arn  = optional(string)
    task_role_arn       = optional(string)
    service_account     = optional(string)
  })
}

variable "network" {
  description = "Network configuration"
  type = object({
    vpc_id          = optional(string)
    subnets         = optional(list(string))
    security_groups = optional(list(string))
  })
}

variable "storage" {
  description = "Storage configuration"
  type = object({
    bucket     = optional(string)
    kms_key_id = optional(string)
  })
}

variable "tags" {
  description = "Resource tags for cost allocation and compliance"
  type        = map(string)
}

variable "monitoring" {
  description = "Monitoring configuration"
  type = object({
    log_group         = optional(string)
    metrics_namespace = optional(string)
    alert_topic_arn   = optional(string)
    alert_topic       = optional(string)
  })
}

variable "enable_service" {
  description = "Enable ECS service (AWS only)"
  type        = bool
  default     = false
}

variable "enable_scheduler" {
  description = "Enable Cloud Scheduler (GCP only)"
  type        = bool
  default     = false
}

variable "schedule_cron" {
  description = "Cron schedule for execution"
  type        = string
  default     = "0 */6 * * *"
}

variable "project_id" {
  description = "GCP project ID (GCP only)"
  type        = string
  default     = ""
}
"""
        return content

    def _generate_tfvars(self) -> Dict[str, Any]:
        """Generate terraform.tfvars.json content."""
        return self.generate_terraform_variables()

    def _generate_outputs_tf(self) -> str:
        """Generate outputs.tf content."""
        if self.infrastructure.provider == "aws":
            content = """# Terraform outputs

output "task_definition_arn" {
  description = "ECS task definition ARN"
  value       = aws_ecs_task_definition.dativo_etl.arn
}

output "task_definition_family" {
  description = "ECS task definition family"
  value       = aws_ecs_task_definition.dativo_etl.family
}

output "log_group_name" {
  description = "CloudWatch log group name"
  value       = aws_cloudwatch_log_group.dativo_etl.name
}

output "tags" {
  description = "Applied resource tags"
  value       = var.tags
}
"""
        else:  # GCP
            content = """# Terraform outputs

output "service_url" {
  description = "Cloud Run service URL"
  value       = google_cloud_run_service.dativo_etl.status[0].url
}

output "service_name" {
  description = "Cloud Run service name"
  value       = google_cloud_run_service.dativo_etl.name
}

output "labels" {
  description = "Applied resource labels"
  value       = google_cloud_run_service.dativo_etl.metadata[0].labels
}
"""
        return content


def generate_terraform_for_job(job_config: JobConfig, output_dir: Path) -> None:
    """Generate Terraform module for a job configuration.

    Args:
        job_config: Job configuration with infrastructure block
        output_dir: Directory to write Terraform files

    Raises:
        ValueError: If job config doesn't include infrastructure block
    """
    generator = TerraformGenerator(job_config)
    generator.generate_terraform_module(output_dir)


def generate_terraform_for_jobs(
    job_configs: List[JobConfig], output_base_dir: Path
) -> None:
    """Generate Terraform modules for multiple job configurations.

    Creates a separate Terraform module for each job under output_base_dir.

    Args:
        job_configs: List of job configurations
        output_base_dir: Base directory for Terraform modules
    """
    for job_config in job_configs:
        if not job_config.infrastructure:
            continue

        # Create subdirectory for each tenant
        job_output_dir = output_base_dir / job_config.tenant_id
        generate_terraform_for_job(job_config, job_output_dir)
