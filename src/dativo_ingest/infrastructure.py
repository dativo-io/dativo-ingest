"""Infrastructure health checks and external infrastructure integration for cloud deployment.

This module provides:
1. Infrastructure health checks for validating dependencies
2. External infrastructure configuration management
3. Cloud-agnostic deployment support via Terraform
4. Tag propagation for cost allocation and compliance
"""

import os
import socket
import json
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from dataclasses import dataclass, field, asdict
from pathlib import Path

import requests
import yaml

from .config import JobConfig


def validate_required_ports(ports: List[int], host: str = "localhost") -> bool:
    """Validate that required ports are open.

    Args:
        ports: List of port numbers to check
        host: Hostname to check (default: localhost)

    Returns:
        True if all ports are accessible

    Raises:
        ValueError: If any port is not accessible
    """
    failed_ports = []
    for port in ports:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((host, port))
            sock.close()
            if result != 0:
                failed_ports.append(port)
        except Exception:
            failed_ports.append(port)

    if failed_ports:
        raise ValueError(f"Ports not accessible on {host}: {failed_ports}")

    return True


def check_nessie_connectivity(uri: str, timeout: int = 5) -> bool:
    """Check Nessie catalog connectivity.

    Args:
        uri: Nessie catalog URI (e.g., "http://localhost:19120/api/v1")
        timeout: Request timeout in seconds (default: 5)

    Returns:
        True if Nessie is accessible

    Raises:
        ValueError: If Nessie is not accessible
    """
    try:
        # Try to reach Nessie API
        # Nessie typically has a /config endpoint
        parsed = urlparse(uri)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        # Try config endpoint
        config_url = f"{base_url}/api/v1/config"
        response = requests.get(config_url, timeout=timeout)
        if response.status_code in [200, 404]:  # 404 is OK, means server is responding
            return True

        # Try base API endpoint
        api_url = f"{base_url}/api/v1"
        response = requests.get(api_url, timeout=timeout)
        if response.status_code in [200, 404, 405]:  # 405 Method Not Allowed is OK
            return True

        raise ValueError(
            f"Nessie connectivity check failed: HTTP {response.status_code}"
        )
    except requests.exceptions.ConnectionError as e:
        raise ValueError(f"Cannot connect to Nessie at {uri}: {e}")
    except requests.exceptions.Timeout:
        raise ValueError(f"Nessie connection timeout at {uri}")
    except Exception as e:
        raise ValueError(f"Nessie connectivity check failed: {e}")


def check_s3_connectivity(
    endpoint: str,
    access_key: Optional[str] = None,
    secret_key: Optional[str] = None,
    region: Optional[str] = None,
    timeout: int = 5,
) -> bool:
    """Check S3/MinIO connectivity.

    Args:
        endpoint: S3 endpoint URL (e.g., "http://localhost:9000")
        access_key: S3 access key (optional for health check)
        secret_key: S3 secret key (optional for health check)
        timeout: Request timeout in seconds (default: 5)

    Returns:
        True if S3 is accessible

    Raises:
        ValueError: If S3 is not accessible
    """
    try:
        # Try to reach S3 endpoint
        parsed = urlparse(endpoint)
        health_url = f"{parsed.scheme}://{parsed.netloc}/minio/health/live"

        # Try MinIO health endpoint first
        try:
            response = requests.get(health_url, timeout=timeout)
            if response.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            pass

        # Try basic connectivity to endpoint
        response = requests.get(endpoint, timeout=timeout)
        # Any response (even 403 Forbidden) means server is reachable
        return True
    except requests.exceptions.ConnectionError as e:
        raise ValueError(f"Cannot connect to S3 at {endpoint}: {e}")
    except requests.exceptions.Timeout:
        raise ValueError(f"S3 connection timeout at {endpoint}")
    except Exception as e:
        raise ValueError(f"S3 connectivity check failed: {e}")


def validate_infrastructure(job_config: JobConfig) -> None:
    """Validate infrastructure dependencies for a job configuration.

    Args:
        job_config: Job configuration to validate

    Raises:
        ValueError: If infrastructure validation fails
    """
    errors = []
    warnings = []

    # Get target configuration
    try:
        target_config = job_config.get_target()
    except Exception as e:
        errors.append(f"Failed to load target configuration: {e}")
        if errors:
            raise ValueError("; ".join(errors))
        return

    target_type = target_config.type

    # Validate Iceberg/Nessie connectivity (only if catalog is configured)
    if target_type == "iceberg":
        # S3 is always required for storage
        s3_endpoint = os.getenv("S3_ENDPOINT")
        if not s3_endpoint:
            errors.append("S3_ENDPOINT environment variable is not set")
        else:
            try:
                check_s3_connectivity(s3_endpoint)
            except ValueError as e:
                errors.append(f"S3 connectivity failed: {e}")

        # Nessie is only required if catalog is configured
        if target_config.catalog:
            nessie_uri = os.getenv("NESSIE_URI")
            if not nessie_uri:
                errors.append(
                    "NESSIE_URI environment variable is not set (required for catalog)"
                )
            else:
                try:
                    check_nessie_connectivity(nessie_uri)
                except ValueError as e:
                    errors.append(f"Nessie connectivity failed: {e}")

            # Check required ports (Nessie default: 19120, MinIO default: 9000)
            try:
                nessie_port = 19120
                if nessie_uri:
                    parsed = urlparse(nessie_uri)
                    if parsed.port:
                        nessie_port = parsed.port
                validate_required_ports([nessie_port])
            except ValueError as e:
                warnings.append(f"Nessie port check: {e}")
        else:
            warnings.append(
                "No catalog configured - Iceberg metadata operations will be skipped"
            )

        try:
            s3_port = 9000
            if s3_endpoint:
                parsed = urlparse(s3_endpoint)
                if parsed.port:
                    s3_port = parsed.port
            validate_required_ports([s3_port])
        except ValueError as e:
            warnings.append(f"S3 port check: {e}")

    # Validate S3 target connectivity
    elif target_type == "s3":
        s3_endpoint = os.getenv("S3_ENDPOINT")
        if not s3_endpoint:
            errors.append("S3_ENDPOINT environment variable is not set")
        else:
            try:
                check_s3_connectivity(s3_endpoint)
            except ValueError as e:
                errors.append(f"S3 connectivity failed: {e}")

    # Log warnings (non-fatal)
    if warnings:
        import logging

        logger = logging.getLogger(__name__)
        for warning in warnings:
            logger.warning(
                f"Infrastructure warning: {warning}",
                extra={"event_type": "infrastructure_warning", "warning": warning},
            )

    # Raise errors (fatal)
    if errors:
        raise ValueError("; ".join(errors))


# ==============================================================================
# External Infrastructure Integration
# ==============================================================================


@dataclass
class InfrastructureRuntime:
    """Runtime environment configuration for job execution."""

    type: str  # dagster, airflow, kubernetes, ecs, cloud_run, cloud_functions
    compute: Optional[Dict[str, Any]] = None
    scaling: Optional[Dict[str, Any]] = None
    timeout_seconds: Optional[int] = None

    def __post_init__(self):
        """Validate runtime configuration."""
        valid_types = [
            "dagster",
            "airflow",
            "kubernetes",
            "ecs",
            "cloud_run",
            "cloud_functions",
        ]
        if self.type not in valid_types:
            raise ValueError(
                f"Invalid runtime type: {self.type}. Must be one of {valid_types}"
            )


@dataclass
class InfrastructureNetworking:
    """Network configuration for cloud resources."""

    vpc_id: Optional[str] = None
    subnet_ids: Optional[List[str]] = None
    security_group_ids: Optional[List[str]] = None
    private_access: bool = True


@dataclass
class InfrastructureStorage:
    """Storage configuration for state and data."""

    state_bucket: Optional[str] = None
    data_bucket: Optional[str] = None
    encryption: Optional[Dict[str, Any]] = None


@dataclass
class InfrastructureTags:
    """Cloud resource tags for cost allocation, compliance, and traceability."""

    cost_center: Optional[str] = None
    business_unit: Optional[str] = None
    project: Optional[str] = None
    environment: Optional[str] = None  # dev, staging, prod
    owner: Optional[str] = None
    compliance: Optional[List[str]] = None
    data_classification: Optional[str] = None
    custom: Optional[Dict[str, str]] = None

    def to_flat_dict(self) -> Dict[str, str]:
        """Convert tags to flat dictionary for Terraform/cloud provider tags."""
        tags = {}
        if self.cost_center:
            tags["CostCenter"] = self.cost_center
        if self.business_unit:
            tags["BusinessUnit"] = self.business_unit
        if self.project:
            tags["Project"] = self.project
        if self.environment:
            tags["Environment"] = self.environment
        if self.owner:
            tags["Owner"] = self.owner
        if self.compliance:
            tags["Compliance"] = ",".join(self.compliance)
        if self.data_classification:
            tags["DataClassification"] = self.data_classification
        if self.custom:
            # Custom tags are added with Custom prefix
            for key, value in self.custom.items():
                tags[f"Custom_{key}"] = value
        return tags


@dataclass
class InfrastructureTerraform:
    """Terraform-specific configuration."""

    module_source: Optional[str] = None
    module_version: Optional[str] = None
    backend: Optional[Dict[str, Any]] = None
    variables: Optional[Dict[str, Any]] = None


@dataclass
class InfrastructureMonitoring:
    """Monitoring and alerting configuration."""

    enabled: bool = True
    metrics_namespace: Optional[str] = None
    log_group: Optional[str] = None
    alerts: Optional[Dict[str, Any]] = None


@dataclass
class InfrastructureConfig:
    """External infrastructure configuration for cloud deployment.

    This configuration enables jobs to reference infrastructure provisioned
    outside of Dativo (e.g., via Terraform) and provides metadata that flows
    into the Terraform module for cloud-agnostic deployment.
    """

    provider: str  # aws, gcp, azure
    runtime: InfrastructureRuntime
    networking: Optional[InfrastructureNetworking] = None
    storage: Optional[InfrastructureStorage] = None
    tags: Optional[InfrastructureTags] = None
    terraform: Optional[InfrastructureTerraform] = None
    monitoring: Optional[InfrastructureMonitoring] = None

    def __post_init__(self):
        """Validate infrastructure configuration."""
        valid_providers = ["aws", "gcp", "azure"]
        if self.provider not in valid_providers:
            raise ValueError(
                f"Invalid provider: {self.provider}. Must be one of {valid_providers}"
            )

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> "InfrastructureConfig":
        """Create infrastructure config from dictionary."""
        # Parse nested objects
        runtime = InfrastructureRuntime(**config["runtime"])
        networking = (
            InfrastructureNetworking(**config["networking"])
            if config.get("networking")
            else None
        )
        storage = (
            InfrastructureStorage(**config["storage"])
            if config.get("storage")
            else None
        )
        tags = InfrastructureTags(**config["tags"]) if config.get("tags") else None
        terraform = (
            InfrastructureTerraform(**config["terraform"])
            if config.get("terraform")
            else None
        )
        monitoring = (
            InfrastructureMonitoring(**config["monitoring"])
            if config.get("monitoring")
            else None
        )

        return cls(
            provider=config["provider"],
            runtime=runtime,
            networking=networking,
            storage=storage,
            tags=tags,
            terraform=terraform,
            monitoring=monitoring,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert infrastructure config to dictionary."""
        result = {
            "provider": self.provider,
            "runtime": asdict(self.runtime),
        }
        if self.networking:
            result["networking"] = asdict(self.networking)
        if self.storage:
            result["storage"] = asdict(self.storage)
        if self.tags:
            result["tags"] = asdict(self.tags)
        if self.terraform:
            result["terraform"] = asdict(self.terraform)
        if self.monitoring:
            result["monitoring"] = asdict(self.monitoring)
        return result

    def generate_terraform_vars(
        self, job_config: JobConfig, asset_tags: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Generate Terraform variables from infrastructure config and job metadata.

        This method propagates tags from multiple sources:
        1. Infrastructure tags (cost_center, business_unit, etc.)
        2. Job configuration metadata (tenant_id, environment)
        3. Asset tags (from tag_derivation module)

        Args:
            job_config: Job configuration
            asset_tags: Optional asset-derived tags (from tag_derivation module)

        Returns:
            Dictionary of Terraform variables with propagated tags
        """
        tf_vars = {
            "provider": self.provider,
            "runtime_type": self.runtime.type,
        }

        # Add runtime configuration
        if self.runtime.compute:
            tf_vars["compute"] = self.runtime.compute
        if self.runtime.scaling:
            tf_vars["scaling"] = self.runtime.scaling
        if self.runtime.timeout_seconds:
            tf_vars["timeout_seconds"] = self.runtime.timeout_seconds

        # Add networking configuration
        if self.networking:
            tf_vars["networking"] = asdict(self.networking)

        # Add storage configuration
        if self.storage:
            tf_vars["storage"] = asdict(self.storage)

        # Add monitoring configuration
        if self.monitoring:
            tf_vars["monitoring"] = asdict(self.monitoring)

        # Propagate tags from multiple sources
        all_tags = {}

        # 1. Infrastructure tags
        if self.tags:
            all_tags.update(self.tags.to_flat_dict())

        # 2. Job metadata tags
        all_tags["TenantId"] = job_config.tenant_id
        if hasattr(job_config, "environment") and job_config.environment:
            all_tags["Environment"] = job_config.environment
        if hasattr(job_config, "asset") and job_config.asset:
            all_tags["Asset"] = job_config.asset
        if hasattr(job_config, "source_connector") and job_config.source_connector:
            all_tags["SourceConnector"] = job_config.source_connector

        # 3. Asset tags (from tag_derivation module)
        if asset_tags:
            # Add asset-derived classification tags
            for key, value in asset_tags.items():
                if key.startswith("classification."):
                    # Convert classification.fields.email -> Classification_email
                    tag_name = key.replace("classification.", "Classification_").replace(
                        ".", "_"
                    )
                    all_tags[tag_name] = value
                elif key.startswith("governance."):
                    tag_name = key.replace("governance.", "Governance_").replace(
                        ".", "_"
                    )
                    all_tags[tag_name] = value
                elif key.startswith("finops."):
                    tag_name = key.replace("finops.", "FinOps_").replace(".", "_")
                    all_tags[tag_name] = value

        # Add ManagedBy tag
        all_tags["ManagedBy"] = "dativo"

        tf_vars["tags"] = all_tags

        # Add custom terraform variables if specified
        if self.terraform and self.terraform.variables:
            tf_vars.update(self.terraform.variables)

        return tf_vars

    def export_terraform_vars(
        self,
        output_path: Path,
        job_config: JobConfig,
        asset_tags: Optional[Dict[str, str]] = None,
        format: str = "json",
    ) -> None:
        """Export Terraform variables to file.

        Args:
            output_path: Path to output file
            job_config: Job configuration
            asset_tags: Optional asset-derived tags
            format: Output format ('json' or 'tfvars')
        """
        tf_vars = self.generate_terraform_vars(job_config, asset_tags)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        if format == "json":
            with open(output_path, "w") as f:
                json.dump(tf_vars, f, indent=2)
        elif format == "tfvars":
            with open(output_path, "w") as f:
                for key, value in tf_vars.items():
                    if isinstance(value, str):
                        f.write(f'{key} = "{value}"\n')
                    elif isinstance(value, dict):
                        f.write(f"{key} = {json.dumps(value)}\n")
                    elif isinstance(value, list):
                        f.write(f"{key} = {json.dumps(value)}\n")
                    else:
                        f.write(f"{key} = {value}\n")
        else:
            raise ValueError(f"Unsupported format: {format}. Use 'json' or 'tfvars'")

    def validate_infrastructure_config(self) -> List[str]:
        """Validate infrastructure configuration and return warnings.

        Returns:
            List of validation warnings (empty if valid)
        """
        warnings = []

        # Validate runtime configuration
        if self.runtime.type in ["ecs", "cloud_run"] and not self.runtime.compute:
            warnings.append(
                f"Runtime type '{self.runtime.type}' typically requires compute configuration"
            )

        # Validate networking configuration
        if self.provider == "aws" and self.networking:
            if self.networking.vpc_id and not self.networking.subnet_ids:
                warnings.append("VPC ID specified but no subnet IDs provided")
            if self.networking.subnet_ids and not self.networking.vpc_id:
                warnings.append("Subnet IDs specified but no VPC ID provided")

        # Validate storage configuration
        if self.storage and self.storage.encryption:
            if (
                self.storage.encryption.get("enabled")
                and not self.storage.encryption.get("kms_key_id")
            ):
                warnings.append("Encryption enabled but no KMS key ID specified")

        # Validate tags for compliance
        if not self.tags:
            warnings.append(
                "No tags specified - consider adding tags for cost allocation and compliance"
            )
        elif self.tags:
            if not self.tags.cost_center:
                warnings.append("No cost_center tag specified")
            if not self.tags.owner:
                warnings.append("No owner tag specified")
            if not self.tags.environment:
                warnings.append("No environment tag specified")

        return warnings


def load_infrastructure_config(
    config_dict: Optional[Dict[str, Any]]
) -> Optional[InfrastructureConfig]:
    """Load infrastructure configuration from dictionary.

    Args:
        config_dict: Dictionary containing infrastructure configuration

    Returns:
        InfrastructureConfig or None if no infrastructure specified
    """
    if not config_dict:
        return None

    try:
        return InfrastructureConfig.from_dict(config_dict)
    except Exception as e:
        raise ValueError(f"Invalid infrastructure configuration: {e}")


def validate_infrastructure_for_job(
    job_config: JobConfig, infrastructure: Optional[InfrastructureConfig] = None
) -> None:
    """Validate infrastructure dependencies and configuration for a job.

    This function performs both:
    1. Health checks for existing infrastructure (Nessie, S3, etc.)
    2. Validation of external infrastructure configuration

    Args:
        job_config: Job configuration to validate
        infrastructure: Optional external infrastructure configuration

    Raises:
        ValueError: If infrastructure validation fails
    """
    # Perform existing health checks
    validate_infrastructure(job_config)

    # Validate external infrastructure configuration
    if infrastructure:
        import logging

        logger = logging.getLogger(__name__)

        warnings = infrastructure.validate_infrastructure_config()
        for warning in warnings:
            logger.warning(
                f"Infrastructure configuration warning: {warning}",
                extra={
                    "event_type": "infrastructure_config_warning",
                    "warning": warning,
                    "provider": infrastructure.provider,
                    "runtime_type": infrastructure.runtime.type,
                },
            )

        logger.info(
            "External infrastructure configuration validated",
            extra={
                "event_type": "infrastructure_config_validated",
                "provider": infrastructure.provider,
                "runtime_type": infrastructure.runtime.type,
            },
        )
