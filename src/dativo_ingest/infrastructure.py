"""Infrastructure health checks and external infrastructure integration for Terraform.

This module provides:
1. Health checks for validating infrastructure dependencies
2. External infrastructure integration for cloud-agnostic deployment via Terraform
3. Tag propagation for cost allocation, compliance, and resource traceability
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


def generate_terraform_vars(
    job_config: JobConfig,
    output_path: Optional[Path] = None,
    format: str = "json",
) -> Dict[str, Any]:
    """Generate Terraform variables from job configuration.

    This function extracts infrastructure configuration from a job config and
    generates Terraform-compatible variables that can be consumed by Terraform
    modules for provisioning external infrastructure.

    Args:
        job_config: Job configuration with optional infrastructure block
        output_path: Optional path to write Terraform variables file
        format: Output format ('json' or 'tfvars')

    Returns:
        Dictionary of Terraform variables

    Raises:
        ValueError: If infrastructure config is missing or invalid
    """
    if not job_config.infrastructure:
        raise ValueError(
            "Job configuration does not include infrastructure block. "
            "Add 'infrastructure' section to job config for Terraform integration."
        )

    infra_config = job_config.infrastructure

    # Get base Terraform variables from infrastructure config
    terraform_vars = infra_config.get_terraform_vars()

    # Add job-level metadata
    terraform_vars["job_metadata"] = {
        "tenant_id": job_config.tenant_id,
        "environment": job_config.environment,
    }

    # Merge tags from asset definition and job config
    asset_definition = job_config._resolve_asset()
    tag_derivation = None

    try:
        from .tag_derivation import TagDerivation

        tag_derivation = TagDerivation(
            asset_definition=asset_definition,
            classification_overrides=job_config.classification_overrides,
            finops=job_config.finops,
            governance_overrides=job_config.governance_overrides,
        )

        # Derive tags from asset
        asset_tags = tag_derivation.derive_all_tags()

        # Convert namespaced tags to flat tags for Terraform
        flat_tags = {}
        for key, value in asset_tags.items():
            # Convert namespaced keys to Terraform-friendly format
            # e.g., "finops.cost_center" -> "CostCenter"
            if key.startswith("finops."):
                tag_key = key.replace("finops.", "").replace("_", "")
                # Capitalize first letter of each word
                tag_key = "".join(word.capitalize() for word in tag_key.split("_"))
                flat_tags[tag_key] = value
            elif key.startswith("governance."):
                tag_key = key.replace("governance.", "").replace("_", "")
                tag_key = "".join(word.capitalize() for word in tag_key.split("_"))
                flat_tags[tag_key] = value
            elif key.startswith("classification."):
                # Classification tags can be kept as-is or mapped
                flat_tags[key] = value

        # Merge with infrastructure tags (infrastructure tags take precedence)
        merged_tags = infra_config.merge_tags(asset_tags=flat_tags)

        # Update Terraform vars with merged tags
        terraform_vars["tags"] = merged_tags

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(
            f"Failed to derive tags from asset definition: {e}",
            extra={"event_type": "tag_derivation_warning"},
        )
        # Continue with infrastructure tags only
        if infra_config.tags:
            terraform_vars["tags"] = infra_config.tags

    # Write to file if output path is provided
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if format == "json":
            with open(output_path, "w") as f:
                json.dump(terraform_vars, f, indent=2)
        elif format == "tfvars":
            # Write as Terraform variable file format
            with open(output_path, "w") as f:
                _write_tfvars(terraform_vars, f)
        else:
            raise ValueError(f"Unsupported format: {format}")

    return terraform_vars


def _write_tfvars(vars_dict: Dict[str, Any], file_handle) -> None:
    """Write Terraform variables in .tfvars format.

    Args:
        vars_dict: Dictionary of Terraform variables
        file_handle: File handle to write to
    """
    for key, value in vars_dict.items():
        if isinstance(value, dict):
            # Nested dict - write as HCL object
            file_handle.write(f'{key} = {{\n')
            for nested_key, nested_value in value.items():
                if isinstance(nested_value, str):
                    file_handle.write(f'  {nested_key} = "{nested_value}"\n')
                elif isinstance(nested_value, list):
                    file_handle.write(f'  {nested_key} = {json.dumps(nested_value)}\n')
                else:
                    file_handle.write(f'  {nested_key} = {nested_value}\n')
            file_handle.write('}\n')
        elif isinstance(value, list):
            file_handle.write(f'{key} = {json.dumps(value)}\n')
        elif isinstance(value, str):
            file_handle.write(f'{key} = "{value}"\n')
        else:
            file_handle.write(f'{key} = {value}\n')


def validate_infrastructure_config(job_config: JobConfig) -> None:
    """Validate infrastructure configuration for Terraform integration.

    Args:
        job_config: Job configuration to validate

    Raises:
        ValueError: If infrastructure configuration is invalid
    """
    if not job_config.infrastructure:
        # Infrastructure is optional, so no error if missing
        return

    infra_config = job_config.infrastructure
    errors = []

    # Validate provider
    if infra_config.provider not in ["aws", "gcp"]:
        errors.append(
            f"Invalid provider: {infra_config.provider}. Must be 'aws' or 'gcp'"
        )

    # Validate runtime configuration
    if infra_config.runtime:
        runtime = infra_config.runtime
        if runtime.compute_type:
            valid_compute_types = {
                "aws": ["ecs_task", "lambda", "batch", "fargate"],
                "gcp": ["cloud_run_job", "dataproc", "cloud_functions"],
            }
            if runtime.compute_type not in valid_compute_types.get(
                infra_config.provider, []
            ):
                errors.append(
                    f"Invalid compute_type '{runtime.compute_type}' for provider '{infra_config.provider}'. "
                    f"Valid types: {valid_compute_types.get(infra_config.provider, [])}"
                )

    # Validate resource references (should be Terraform resource references)
    if infra_config.resources:
        resources = infra_config.resources
        # Check that resource references look like Terraform references
        terraform_ref_patterns = [
            resources.compute_resource,
            resources.execution_role,
            resources.task_role,
            resources.service_account,
            resources.storage_bucket,
            resources.secrets_manager,
        ]

        for ref in terraform_ref_patterns:
            if ref and not (
                ref.startswith("${") or "." in ref or ref.startswith("aws_") or ref.startswith("google_")
            ):
                # Not a strict validation - just a warning
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Resource reference '{ref}' may not be a valid Terraform reference",
                    extra={"event_type": "infrastructure_warning", "reference": ref},
                )

    # Validate tags
    if infra_config.tags:
        # Check for required tags for cost allocation
        recommended_tags = ["CostCenter", "Project", "Environment", "Team"]
        missing_tags = [tag for tag in recommended_tags if tag not in infra_config.tags]
        if missing_tags:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                f"Recommended tags missing for cost allocation: {missing_tags}",
                extra={
                    "event_type": "infrastructure_warning",
                    "missing_tags": missing_tags,
                },
            )

    if errors:
        raise ValueError("; ".join(errors))
