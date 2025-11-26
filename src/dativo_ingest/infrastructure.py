"""Infrastructure integration for external infrastructure provisioning and validation.

This module provides:
1. Infrastructure health checks for validating dependencies
2. Tag propagation for cost allocation and compliance
3. Integration with Terraform modules for external infrastructure
4. Support for cloud-agnostic deployments (AWS, GCP, Azure)
"""

import json
import os
import socket
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

from .config import InfrastructureConfig, JobConfig


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


def merge_infrastructure_tags(
    job_config: JobConfig,
    asset_definition: Any = None,
) -> Dict[str, str]:
    """Merge tags from multiple sources for infrastructure propagation.

    Tag precedence (highest to lowest):
    1. infrastructure.tags (job-level infrastructure tags)
    2. finops (job-level FinOps metadata)
    3. asset.finops (asset-level FinOps metadata)
    4. asset.compliance (asset-level compliance metadata)
    5. Default tags (tenant_id, environment, job name)

    Args:
        job_config: Job configuration
        asset_definition: Optional asset definition for asset-level tags

    Returns:
        Dictionary of merged tags for infrastructure resources
    """
    tags = {}

    # Level 5: Default tags (lowest priority)
    tags["dativo:tenant"] = job_config.tenant_id
    if job_config.environment:
        tags["dativo:environment"] = job_config.environment

    # Level 4: Asset compliance tags
    if asset_definition and hasattr(asset_definition, "compliance"):
        if asset_definition.compliance:
            if hasattr(asset_definition.compliance, "classification"):
                if asset_definition.compliance.classification:
                    tags["dativo:classification"] = ",".join(
                        asset_definition.compliance.classification
                    )
            if hasattr(asset_definition.compliance, "regulations"):
                if asset_definition.compliance.regulations:
                    tags["dativo:regulations"] = ",".join(
                        asset_definition.compliance.regulations
                    )

    # Level 3: Asset FinOps tags
    if asset_definition and hasattr(asset_definition, "finops"):
        if asset_definition.finops:
            if hasattr(asset_definition.finops, "cost_center"):
                if asset_definition.finops.cost_center:
                    tags["dativo:cost-center"] = asset_definition.finops.cost_center
            if hasattr(asset_definition.finops, "project"):
                if asset_definition.finops.project:
                    tags["dativo:project"] = asset_definition.finops.project

    # Level 2: Job-level FinOps tags (overrides asset-level)
    if job_config.finops:
        finops_data = job_config.finops
        if finops_data.get("cost_center"):
            tags["dativo:cost-center"] = finops_data["cost_center"]
        if finops_data.get("business_tags"):
            business_tags = finops_data["business_tags"]
            if isinstance(business_tags, list):
                tags["dativo:business-tags"] = ",".join(business_tags)
            else:
                tags["dativo:business-tags"] = str(business_tags)
        if finops_data.get("project"):
            tags["dativo:project"] = finops_data["project"]
        if finops_data.get("environment"):
            tags["dativo:environment"] = finops_data["environment"]

    # Level 1: Infrastructure tags (highest priority - overrides all)
    if job_config.infrastructure and job_config.infrastructure.tags:
        tags.update(job_config.infrastructure.tags)

    return tags


def generate_terraform_variables(
    job_config: JobConfig,
    asset_definition: Any = None,
) -> Dict[str, Any]:
    """Generate Terraform variables from job configuration.

    Args:
        job_config: Job configuration
        asset_definition: Optional asset definition

    Returns:
        Dictionary of Terraform variables
    """
    if not job_config.infrastructure:
        return {}

    infra = job_config.infrastructure
    variables = {}

    # Job identification
    variables["job_name"] = (
        job_config.asset if job_config.asset else "dativo-etl-job"
    )
    variables["tenant_id"] = job_config.tenant_id
    variables["environment"] = job_config.environment or "dev"

    # Provider configuration
    if infra.provider:
        variables["provider"] = infra.provider

    # Runtime configuration
    if infra.runtime:
        if infra.runtime.type:
            variables["runtime_type"] = infra.runtime.type
        if infra.runtime.cluster_name:
            variables["runtime_cluster_name"] = infra.runtime.cluster_name
        if infra.runtime.namespace:
            variables["runtime_namespace"] = infra.runtime.namespace
        if infra.runtime.service_account:
            variables["runtime_service_account"] = infra.runtime.service_account

    # Compute configuration
    if infra.compute:
        if infra.compute.cpu:
            variables["compute_cpu"] = infra.compute.cpu
        if infra.compute.memory:
            variables["compute_memory"] = infra.compute.memory
        if infra.compute.instance_type:
            variables["compute_instance_type"] = infra.compute.instance_type
        if infra.compute.max_runtime_seconds:
            variables["compute_max_runtime_seconds"] = (
                infra.compute.max_runtime_seconds
            )

    # Networking configuration
    if infra.networking:
        if infra.networking.vpc_id:
            variables["networking_vpc_id"] = infra.networking.vpc_id
        if infra.networking.subnet_ids:
            variables["networking_subnet_ids"] = infra.networking.subnet_ids
        if infra.networking.security_group_ids:
            variables["networking_security_group_ids"] = (
                infra.networking.security_group_ids
            )
        variables["networking_private_networking"] = (
            infra.networking.private_networking
        )

    # Storage configuration
    if infra.storage:
        if infra.storage.bucket:
            variables["storage_bucket"] = infra.storage.bucket
        if infra.storage.prefix:
            variables["storage_prefix"] = infra.storage.prefix
        if infra.storage.kms_key_id:
            variables["storage_kms_key_id"] = infra.storage.kms_key_id

    # Dagster configuration
    if infra.dagster:
        if infra.dagster.code_location:
            variables["dagster_code_location"] = infra.dagster.code_location
        if infra.dagster.repository:
            variables["dagster_repository"] = infra.dagster.repository

    # Merge infrastructure tags
    tags = merge_infrastructure_tags(job_config, asset_definition)
    variables["tags"] = tags

    # Merge with Terraform custom variables (if provided)
    if infra.terraform and infra.terraform.variables:
        variables.update(infra.terraform.variables)

    return variables


def export_terraform_tfvars(
    job_config: JobConfig,
    output_path: Path,
    asset_definition: Any = None,
) -> None:
    """Export Terraform variables to a .tfvars file.

    Args:
        job_config: Job configuration
        output_path: Path to output .tfvars file
        asset_definition: Optional asset definition

    Raises:
        ValueError: If infrastructure configuration is missing
    """
    if not job_config.infrastructure:
        raise ValueError("No infrastructure configuration found in job config")

    variables = generate_terraform_variables(job_config, asset_definition)

    # Convert to Terraform HCL format
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        for key, value in variables.items():
            if isinstance(value, str):
                f.write(f'{key} = "{value}"\n')
            elif isinstance(value, bool):
                f.write(f"{key} = {str(value).lower()}\n")
            elif isinstance(value, (int, float)):
                f.write(f"{key} = {value}\n")
            elif isinstance(value, list):
                if all(isinstance(item, str) for item in value):
                    items = ", ".join(f'"{item}"' for item in value)
                    f.write(f"{key} = [{items}]\n")
                else:
                    # Complex list - use JSON encoding
                    f.write(f"{key} = {json.dumps(value)}\n")
            elif isinstance(value, dict):
                # Write dict as HCL map
                f.write(f"{key} = {{\n")
                for k, v in value.items():
                    if isinstance(v, str):
                        f.write(f'  {k} = "{v}"\n')
                    else:
                        f.write(f"  {k} = {json.dumps(v)}\n")
                f.write("}\n")
            else:
                # Fallback to JSON
                f.write(f"{key} = {json.dumps(value)}\n")


def get_infrastructure_provider_tags(
    job_config: JobConfig,
    provider: Optional[str] = None,
) -> Dict[str, str]:
    """Get infrastructure tags formatted for specific cloud provider.

    Args:
        job_config: Job configuration
        provider: Cloud provider ('aws', 'gcp', 'azure'). If None, inferred from job config.

    Returns:
        Dictionary of provider-formatted tags
    """
    if not job_config.infrastructure:
        return {}

    # Infer provider if not specified
    if provider is None and job_config.infrastructure.provider:
        provider = job_config.infrastructure.provider

    # Get merged tags
    tags = merge_infrastructure_tags(job_config)

    # Format tags based on provider
    if provider == "gcp":
        # GCP labels must be lowercase with hyphens
        formatted_tags = {}
        for key, value in tags.items():
            # Convert to lowercase and replace underscores/colons with hyphens
            formatted_key = key.lower().replace("_", "-").replace(":", "-")
            formatted_value = value.lower().replace("_", "-")
            formatted_tags[formatted_key] = formatted_value
        return formatted_tags
    elif provider == "azure":
        # Azure tags have specific length limits
        formatted_tags = {}
        for key, value in tags.items():
            # Truncate key to 512 chars, value to 256 chars
            formatted_key = key[:512]
            formatted_value = str(value)[:256]
            formatted_tags[formatted_key] = formatted_value
        return formatted_tags
    else:
        # AWS and default - support most tag formats
        return tags


def validate_infrastructure_config(infrastructure: InfrastructureConfig) -> None:
    """Validate infrastructure configuration.

    Args:
        infrastructure: Infrastructure configuration to validate

    Raises:
        ValueError: If configuration is invalid
    """
    errors = []

    # Validate provider
    if infrastructure.provider:
        if infrastructure.provider not in ["aws", "gcp", "azure"]:
            errors.append(
                f"Invalid provider: {infrastructure.provider}. Must be one of: aws, gcp, azure"
            )

    # Validate runtime
    if infrastructure.runtime:
        if infrastructure.runtime.type:
            valid_types = ["dagster", "airflow", "kubernetes", "ecs", "cloud_run"]
            if infrastructure.runtime.type not in valid_types:
                errors.append(
                    f"Invalid runtime type: {infrastructure.runtime.type}. "
                    f"Must be one of: {', '.join(valid_types)}"
                )

    # Validate compute resources
    if infrastructure.compute:
        if infrastructure.compute.cpu:
            # Validate CPU format
            cpu = infrastructure.compute.cpu
            if not (
                cpu.isdigit() or cpu.endswith("m") or cpu.replace(".", "").isdigit()
            ):
                errors.append(
                    f"Invalid CPU format: {cpu}. Use formats like '2', '500m', or '1.5'"
                )

        if infrastructure.compute.memory:
            # Validate memory format
            memory = infrastructure.compute.memory
            if not (memory.endswith("Gi") or memory.endswith("Mi") or memory.endswith("G") or memory.endswith("M")):
                errors.append(
                    f"Invalid memory format: {memory}. Use formats like '4Gi', '2048Mi'"
                )

    # Validate Terraform configuration
    if infrastructure.terraform:
        if infrastructure.terraform.module_source:
            # Basic validation of module source format
            source = infrastructure.terraform.module_source
            if not (
                source.startswith("git::")
                or source.startswith("http://")
                or source.startswith("https://")
                or "/" in source
                or Path(source).exists()
            ):
                errors.append(
                    f"Invalid Terraform module source: {source}. "
                    "Use git::, registry, or local path format"
                )

    if errors:
        raise ValueError("Infrastructure configuration validation failed:\n" + "\n".join(errors))
