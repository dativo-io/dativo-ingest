"""Infrastructure integration for Terraform deployment.

This module extracts infrastructure requirements and tags from job configurations
and generates Terraform-compatible configurations for AWS and GCP deployments.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import AssetDefinition, JobConfig
from .tag_derivation import TagDerivation


class InfrastructureTagExtractor:
    """Extract infrastructure tags from job configurations for Terraform."""

    def __init__(self, job_config: JobConfig):
        """Initialize tag extractor with job configuration.

        Args:
            job_config: Job configuration instance
        """
        self.job_config = job_config
        self.asset_definition = job_config._resolve_asset()

    def extract_all_tags(self) -> Dict[str, str]:
        """Extract all tags for infrastructure resources.

        Combines tags from:
        - Asset definition (finops, compliance, team)
        - Job configuration (finops, governance_overrides)
        - Infrastructure metadata

        Returns:
            Dictionary of tags suitable for Terraform resource tagging
        """
        tags = {}

        # Extract tags using TagDerivation
        tag_derivation = TagDerivation(
            asset_definition=self.asset_definition,
            classification_overrides=self.job_config.classification_overrides,
            finops=self.job_config.finops,
            governance_overrides=self.job_config.governance_overrides,
        )

        # Get all derived tags
        derived_tags = tag_derivation.derive_all_tags()

        # Convert namespaced tags to flat structure for Terraform
        # Terraform tags are typically flat key-value pairs
        for key, value in derived_tags.items():
            # Convert namespaced keys to Terraform-friendly format
            terraform_key = key.replace(".", "_").replace("-", "_")
            tags[terraform_key] = value

        # Add job-level metadata
        tags["tenant_id"] = self.job_config.tenant_id
        if self.job_config.environment:
            tags["environment"] = self.job_config.environment

        # Add asset metadata
        tags["asset_name"] = self.asset_definition.name
        tags["asset_version"] = self.asset_definition.version
        if self.asset_definition.domain:
            tags["domain"] = self.asset_definition.domain
        if self.asset_definition.dataProduct:
            tags["data_product"] = self.asset_definition.dataProduct

        # Add team owner
        if self.asset_definition.team and self.asset_definition.team.owner:
            tags["owner"] = self.asset_definition.team.owner

        # Add infrastructure metadata if present
        if self.job_config.infrastructure and self.job_config.infrastructure.metadata:
            for key, value in self.job_config.infrastructure.metadata.items():
                terraform_key = key.replace(".", "_").replace("-", "_")
                tags[f"infra_{terraform_key}"] = str(value)

        return tags

    def extract_finops_tags(self) -> Dict[str, str]:
        """Extract FinOps tags for cost allocation.

        Returns:
            Dictionary of FinOps tags
        """
        tag_derivation = TagDerivation(
            asset_definition=self.asset_definition,
            finops=self.job_config.finops,
        )
        finops_tags = tag_derivation.derive_finops_tags()

        # Convert to Terraform format
        terraform_tags = {}
        for key, value in finops_tags.items():
            terraform_key = key.replace(".", "_")
            terraform_tags[terraform_key] = value

        return terraform_tags

    def extract_compliance_tags(self) -> Dict[str, str]:
        """Extract compliance tags for regulatory tracking.

        Returns:
            Dictionary of compliance tags
        """
        tags = {}

        if self.asset_definition.compliance:
            if self.asset_definition.compliance.classification:
                tags["classification"] = ",".join(
                    self.asset_definition.compliance.classification
                )

            if self.asset_definition.compliance.regulations:
                tags["regulations"] = ",".join(
                    self.asset_definition.compliance.regulations
                )

            if self.asset_definition.compliance.retention_days is not None:
                tags["retention_days"] = str(
                    self.asset_definition.compliance.retention_days
                )

            if self.asset_definition.compliance.security:
                if self.asset_definition.compliance.security.encryption_required:
                    tags["encryption_required"] = "true"
                if self.asset_definition.compliance.security.access_control:
                    tags["access_control"] = (
                        self.asset_definition.compliance.security.access_control
                    )

        return tags

    def extract_runtime_config(self) -> Dict[str, Any]:
        """Extract runtime configuration from infrastructure block.

        Returns:
            Dictionary of runtime configuration
        """
        if not self.job_config.infrastructure:
            return {}

        return self.job_config.infrastructure.runtime or {}

    def extract_metadata(self) -> Dict[str, Any]:
        """Extract metadata from infrastructure block.

        Returns:
            Dictionary of metadata
        """
        if not self.job_config.infrastructure:
            return {}

        return self.job_config.infrastructure.metadata or {}


class TerraformGenerator:
    """Generate Terraform configurations for AWS and GCP."""

    def __init__(self, job_config: JobConfig, cloud_provider: str = "aws"):
        """Initialize Terraform generator.

        Args:
            job_config: Job configuration instance
            cloud_provider: Cloud provider ('aws' or 'gcp')
        """
        self.job_config = job_config
        self.cloud_provider = cloud_provider.lower()
        self.tag_extractor = InfrastructureTagExtractor(job_config)

        if self.cloud_provider not in ["aws", "gcp"]:
            raise ValueError(f"Unsupported cloud provider: {cloud_provider}")

    def generate_tags(self) -> Dict[str, str]:
        """Generate tags for Terraform resources.

        Returns:
            Dictionary of tags
        """
        return self.tag_extractor.extract_all_tags()

    def generate_aws_ecs_fargate(
        self,
        task_family: Optional[str] = None,
        cpu: Optional[int] = None,
        memory: Optional[int] = None,
        image_uri: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate AWS ECS Fargate Terraform configuration.

        Args:
            task_family: Task family name (defaults to job name)
            cpu: CPU units (defaults to 1024)
            memory: Memory in MB (defaults to 2048)
            image_uri: Docker image URI

        Returns:
            Terraform configuration dictionary
        """
        runtime_config = self.tag_extractor.extract_runtime_config()
        tags = self.generate_tags()

        task_family = task_family or f"{self.job_config.tenant_id}-{self.asset_definition.name}"
        cpu = cpu or runtime_config.get("cpu", 1024)
        memory = memory or runtime_config.get("memory", 2048)
        image_uri = image_uri or runtime_config.get("image_uri", "dativo/dativo-ingest:latest")

        return {
            "resource": {
                "aws_ecs_task_definition": {
                    task_family: {
                        "family": task_family,
                        "network_mode": "awsvpc",
                        "requires_compatibilities": ["FARGATE"],
                        "cpu": str(cpu),
                        "memory": str(memory),
                        "container_definitions": json.dumps([
                            {
                                "name": task_family,
                                "image": image_uri,
                                "essential": True,
                                "environment": [
                                    {"name": "TENANT_ID", "value": self.job_config.tenant_id},
                                    {"name": "JOB_CONFIG_PATH", "value": f"/app/jobs/{self.job_config.tenant_id}/{self.asset_definition.name}.yaml"},
                                ],
                                "logConfiguration": {
                                    "logDriver": "awslogs",
                                    "options": {
                                        "awslogs-group": f"/ecs/{task_family}",
                                        "awslogs-region": "${var.aws_region}",
                                        "awslogs-stream-prefix": "ecs",
                                    },
                                },
                            }
                        ]),
                        "tags": tags,
                    }
                },
                "aws_ecs_service": {
                    f"{task_family}_service": {
                        "name": f"{task_family}-service",
                        "cluster": "${var.ecs_cluster_name}",
                        "task_definition": f"${{aws_ecs_task_definition.{task_family}.arn}}",
                        "desired_count": 0,  # Manual trigger or via EventBridge
                        "launch_type": "FARGATE",
                        "network_configuration": {
                            "subnets": "${var.subnet_ids}",
                            "security_groups": "${var.security_group_ids}",
                            "assign_public_ip": False,
                        },
                        "tags": tags,
                    }
                },
            }
        }

    def generate_aws_lambda(
        self,
        function_name: Optional[str] = None,
        timeout: Optional[int] = None,
        memory_size: Optional[int] = None,
        image_uri: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate AWS Lambda Terraform configuration.

        Args:
            function_name: Function name (defaults to job name)
            timeout: Timeout in seconds (defaults to 900)
            memory_size: Memory in MB (defaults to 2048)
            image_uri: Docker image URI

        Returns:
            Terraform configuration dictionary
        """
        runtime_config = self.tag_extractor.extract_runtime_config()
        tags = self.generate_tags()

        function_name = function_name or f"{self.job_config.tenant_id}-{self.asset_definition.name}"
        timeout = timeout or runtime_config.get("timeout", 900)
        memory_size = memory_size or runtime_config.get("memory", 2048)
        image_uri = image_uri or runtime_config.get("image_uri", "dativo/dativo-ingest:latest")

        return {
            "resource": {
                "aws_lambda_function": {
                    function_name: {
                        "function_name": function_name,
                        "package_type": "Image",
                        "image_uri": image_uri,
                        "timeout": timeout,
                        "memory_size": memory_size,
                        "role": "${aws_iam_role.lambda_role.arn}",
                        "environment": {
                            "variables": {
                                "TENANT_ID": self.job_config.tenant_id,
                                "JOB_CONFIG_PATH": f"/app/jobs/{self.job_config.tenant_id}/{self.asset_definition.name}.yaml",
                            }
                        },
                        "tags": tags,
                    }
                },
                "aws_cloudwatch_log_group": {
                    f"{function_name}_logs": {
                        "name": f"/aws/lambda/{function_name}",
                        "retention_in_days": 14,
                        "tags": tags,
                    }
                },
            }
        }

    def generate_gcp_cloud_run(
        self,
        service_name: Optional[str] = None,
        cpu: Optional[str] = None,
        memory: Optional[str] = None,
        image_uri: Optional[str] = None,
        region: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate GCP Cloud Run Terraform configuration.

        Args:
            service_name: Service name (defaults to job name)
            cpu: CPU allocation (defaults to "1")
            memory: Memory allocation (defaults to "2Gi")
            image_uri: Container image URI
            region: GCP region (defaults to "us-central1")

        Returns:
            Terraform configuration dictionary
        """
        runtime_config = self.tag_extractor.extract_runtime_config()
        tags = self.generate_tags()

        service_name = service_name or f"{self.job_config.tenant_id}-{self.asset_definition.name}"
        cpu = cpu or runtime_config.get("cpu", "1")
        memory = memory or runtime_config.get("memory", "2Gi")
        image_uri = image_uri or runtime_config.get("image_uri", "gcr.io/dativo/dativo-ingest:latest")
        region = region or runtime_config.get("region", "us-central1")

        # Convert tags to GCP labels format (lowercase, hyphens, max 63 chars)
        labels = {}
        for key, value in tags.items():
            # GCP label constraints
            label_key = key.lower().replace("_", "-")[:63]
            label_value = str(value).lower().replace("_", "-")[:63]
            labels[label_key] = label_value

        return {
            "resource": {
                "google_cloud_run_service": {
                    service_name: {
                        "name": service_name,
                        "location": region,
                        "template": {
                            "spec": {
                                "containers": [
                                    {
                                        "image": image_uri,
                                        "env": [
                                            {
                                                "name": "TENANT_ID",
                                                "value": self.job_config.tenant_id,
                                            },
                                            {
                                                "name": "JOB_CONFIG_PATH",
                                                "value": f"/app/jobs/{self.job_config.tenant_id}/{self.asset_definition.name}.yaml",
                                            },
                                        ],
                                        "resources": {
                                            "limits": {
                                                "cpu": cpu,
                                                "memory": memory,
                                            },
                                        },
                                    }
                                ],
                                "timeout_seconds": runtime_config.get("timeout", 3600),
                            },
                        },
                        "traffic": [
                            {
                                "percent": 100,
                                "latest_revision": True,
                            }
                        ],
                        "labels": labels,
                    }
                },
            }
        }

    def generate_gcp_cloud_function(
        self,
        function_name: Optional[str] = None,
        runtime: Optional[str] = None,
        timeout: Optional[int] = None,
        memory: Optional[str] = None,
        region: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate GCP Cloud Function Terraform configuration.

        Args:
            function_name: Function name (defaults to job name)
            runtime: Runtime (defaults to "python311")
            timeout: Timeout in seconds (defaults to 540)
            memory: Memory allocation (defaults to "2Gi")
            region: GCP region (defaults to "us-central1")

        Returns:
            Terraform configuration dictionary
        """
        runtime_config = self.tag_extractor.extract_runtime_config()
        tags = self.generate_tags()

        function_name = function_name or f"{self.job_config.tenant_id}-{self.asset_definition.name}"
        runtime = runtime or runtime_config.get("runtime", "python311")
        timeout = timeout or runtime_config.get("timeout", 540)
        memory = memory or runtime_config.get("memory", "256MB")
        region = region or runtime_config.get("region", "us-central1")

        # Convert tags to GCP labels format
        labels = {}
        for key, value in tags.items():
            label_key = key.lower().replace("_", "-")[:63]
            label_value = str(value).lower().replace("_", "-")[:63]
            labels[label_key] = label_value

        return {
            "resource": {
                "google_cloudfunctions_function": {
                    function_name: {
                        "name": function_name,
                        "runtime": runtime,
                        "timeout": timeout,
                        "available_memory_mb": memory,
                        "region": region,
                        "entry_point": "main",
                        "environment_variables": {
                            "TENANT_ID": self.job_config.tenant_id,
                            "JOB_CONFIG_PATH": f"/app/jobs/{self.job_config.tenant_id}/{self.asset_definition.name}.yaml",
                        },
                        "labels": labels,
                    }
                },
            }
        }

    def generate_terraform_config(
        self,
        resource_type: str = "ecs_fargate",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Generate Terraform configuration for specified resource type.

        Args:
            resource_type: Resource type ('ecs_fargate', 'lambda', 'cloud_run', 'cloud_function')
            **kwargs: Additional arguments for resource generation

        Returns:
            Terraform configuration dictionary
        """
        if self.cloud_provider == "aws":
            if resource_type == "ecs_fargate":
                return self.generate_aws_ecs_fargate(**kwargs)
            elif resource_type == "lambda":
                return self.generate_aws_lambda(**kwargs)
            else:
                raise ValueError(f"Unsupported AWS resource type: {resource_type}")

        elif self.cloud_provider == "gcp":
            if resource_type == "cloud_run":
                return self.generate_gcp_cloud_run(**kwargs)
            elif resource_type == "cloud_function":
                return self.generate_gcp_cloud_function(**kwargs)
            else:
                raise ValueError(f"Unsupported GCP resource type: {resource_type}")

        else:
            raise ValueError(f"Unsupported cloud provider: {self.cloud_provider}")

    def write_terraform_file(
        self,
        output_path: Path,
        resource_type: str = "ecs_fargate",
        **kwargs: Any,
    ) -> None:
        """Write Terraform configuration to file.

        Args:
            output_path: Path to output Terraform file
            resource_type: Resource type
            **kwargs: Additional arguments for resource generation
        """
        config = self.generate_terraform_config(resource_type=resource_type, **kwargs)

        # Convert to HCL format (simplified - in production, use hcl2 library)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # For now, write as JSON (Terraform can read JSON)
        with open(output_path.with_suffix(".tf.json"), "w") as f:
            json.dump(config, f, indent=2)

        # Also write a basic HCL template
        self._write_hcl_template(output_path, config, resource_type)

    def _write_hcl_template(
        self,
        output_path: Path,
        config: Dict[str, Any],
        resource_type: str,
    ) -> None:
        """Write HCL template (simplified version).

        Args:
            output_path: Path to output file
            config: Terraform configuration
            resource_type: Resource type
        """
        tags = self.generate_tags()

        # Generate basic HCL template
        hcl_content = f'''# Terraform configuration for {self.job_config.tenant_id}/{self.asset_definition.name}
# Generated from job configuration
# Resource type: {resource_type}
# Cloud provider: {self.cloud_provider}

# Tags for all resources
locals {{
  common_tags = {{
'''
        for key, value in tags.items():
            hcl_content += f'    {key} = "{value}"\n'

        hcl_content += "  }\n}\n\n"

        # Add resource-specific configuration
        if self.cloud_provider == "aws" and resource_type == "ecs_fargate":
            runtime_config = self.tag_extractor.extract_runtime_config()
            cpu = runtime_config.get("cpu", 1024)
            memory = runtime_config.get("memory", 2048)

            hcl_content += f'''resource "aws_ecs_task_definition" "{self.asset_definition.name}" {{
  family                   = "{self.job_config.tenant_id}-{self.asset_definition.name}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "{cpu}"
  memory                   = "{memory}"
  
  container_definitions = jsonencode([{{
    name      = "{self.asset_definition.name}"
    image     = var.image_uri
    essential = true
    
    environment = [
      {{ name = "TENANT_ID", value = "{self.job_config.tenant_id}" }},
      {{ name = "JOB_CONFIG_PATH", value = "/app/jobs/{self.job_config.tenant_id}/{self.asset_definition.name}.yaml" }}
    ]
    
    logConfiguration = {{
      logDriver = "awslogs"
      options = {{
        "awslogs-group"         = "/ecs/{self.job_config.tenant_id}-{self.asset_definition.name}"
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }}
    }}
  }}])
  
  tags = local.common_tags
}}

resource "aws_ecs_service" "{self.asset_definition.name}_service" {{
  name            = "{self.job_config.tenant_id}-{self.asset_definition.name}-service"
  cluster         = var.ecs_cluster_name
  task_definition = aws_ecs_task_definition.{self.asset_definition.name}.arn
  desired_count   = 0
  launch_type      = "FARGATE"
  
  network_configuration {{
    subnets          = var.subnet_ids
    security_groups  = var.security_group_ids
    assign_public_ip = false
  }}
  
  tags = local.common_tags
}}
'''

        elif self.cloud_provider == "gcp" and resource_type == "cloud_run":
            runtime_config = self.tag_extractor.extract_runtime_config()
            cpu = runtime_config.get("cpu", "1")
            memory = runtime_config.get("memory", "2Gi")
            region = runtime_config.get("region", "us-central1")

            hcl_content += f'''resource "google_cloud_run_service" "{self.asset_definition.name}" {{
  name     = "{self.job_config.tenant_id}-{self.asset_definition.name}"
  location = "{region}"
  
  template {{
    spec {{
      containers {{
        image = var.image_uri
        
        env {{
          name  = "TENANT_ID"
          value = "{self.job_config.tenant_id}"
        }}
        env {{
          name  = "JOB_CONFIG_PATH"
          value = "/app/jobs/{self.job_config.tenant_id}/{self.asset_definition.name}.yaml"
        }}
        
        resources {{
          limits = {{
            cpu    = "{cpu}"
            memory = "{memory}"
          }}
        }}
      }}
      
      timeout_seconds = {runtime_config.get("timeout", 3600)}
    }}
  }}
  
  traffic {{
    percent         = 100
    latest_revision = true
  }}
  
  labels = local.common_tags
}}
'''

        with open(output_path, "w") as f:
            f.write(hcl_content)
