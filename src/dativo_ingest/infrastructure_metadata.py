"""Infrastructure metadata extraction for Terraform integration.

This module extracts infrastructure configuration from job definitions and generates
Terraform-compatible metadata for cloud-agnostic deployment in Dagster. It ensures
comprehensive tag propagation for cost allocation, compliance, and resource traceability.
"""

import json
from typing import Any, Dict, List, Optional

from .config import InfrastructureConfig, JobConfig
from .tag_derivation import TagDerivation, derive_tags_from_asset


def extract_infrastructure_tags(
    job_config: JobConfig,
    asset_definition: Any,
) -> Dict[str, str]:
    """Extract and merge all tags for infrastructure resources.

    Combines tags from:
    1. Infrastructure block tags (highest priority)
    2. FinOps metadata from job config and asset
    3. Compliance metadata from asset
    4. Governance metadata from asset
    5. Job-level metadata (tenant_id, environment)

    Args:
        job_config: Job configuration
        asset_definition: Asset definition instance

    Returns:
        Dictionary of tags suitable for Terraform resource tagging
    """
    tags = {}

    # Start with infrastructure block tags (highest priority)
    if job_config.infrastructure and job_config.infrastructure.tags:
        tags.update(job_config.infrastructure.tags)

    # Derive tags from asset definition and job config
    derived_tags = derive_tags_from_asset(
        asset_definition=asset_definition,
        classification_overrides=job_config.classification_overrides,
        finops=job_config.finops,
        governance_overrides=job_config.governance_overrides,
    )

    # Map derived tags to infrastructure tags
    # FinOps tags
    if "finops.cost_center" in derived_tags:
        tags.setdefault("CostCenter", derived_tags["finops.cost_center"])
    if "finops.project" in derived_tags:
        tags.setdefault("Project", derived_tags["finops.project"])
    if "finops.environment" in derived_tags:
        tags.setdefault("Environment", derived_tags["finops.environment"])
    if "finops.business_tags" in derived_tags:
        # Business tags can be added as comma-separated value or separate tags
        tags.setdefault("BusinessTags", derived_tags["finops.business_tags"])

    # Compliance tags
    if "governance.regulations" in derived_tags:
        tags.setdefault("Regulation", derived_tags["governance.regulations"])
    if "classification.default" in derived_tags:
        tags.setdefault("DataClassification", derived_tags["classification.default"])
        tags.setdefault("Compliance", derived_tags["classification.default"])

    # Governance tags
    if "governance.owner" in derived_tags:
        tags.setdefault("Owner", derived_tags["governance.owner"])
    if "governance.domain" in derived_tags:
        tags.setdefault("Domain", derived_tags["governance.domain"])

    # Job-level metadata
    tags.setdefault("TenantId", job_config.tenant_id)
    if job_config.environment:
        tags.setdefault("Environment", job_config.environment)
    if job_config.asset:
        tags.setdefault("JobName", job_config.asset)
    tags.setdefault("ManagedBy", "Terraform")

    return tags


def extract_runtime_environment_metadata(
    job_config: JobConfig,
) -> Optional[Dict[str, Any]]:
    """Extract runtime environment metadata for Terraform module.

    Args:
        job_config: Job configuration

    Returns:
        Dictionary of runtime environment metadata or None if not configured
    """
    if not job_config.infrastructure or not job_config.infrastructure.runtime_environment:
        return None

    env = job_config.infrastructure.runtime_environment
    metadata = {}

    if env.compute_type:
        metadata["compute_type"] = env.compute_type
    if env.compute_size:
        metadata["compute_size"] = env.compute_size
    if env.memory_mb:
        metadata["memory_mb"] = env.memory_mb
    if env.cpu_units:
        metadata["cpu_units"] = env.cpu_units
    if env.timeout_seconds:
        metadata["timeout_seconds"] = env.timeout_seconds
    if env.service_account:
        metadata["service_account"] = env.service_account

    # Network configuration
    if env.network:
        network_metadata = {}
        if env.network.vpc_id:
            network_metadata["vpc_id"] = env.network.vpc_id
        if env.network.subnet_ids:
            network_metadata["subnet_ids"] = env.network.subnet_ids
        if env.network.security_group_ids:
            network_metadata["security_group_ids"] = env.network.security_group_ids
        if network_metadata:
            metadata["network"] = network_metadata

    # Storage configuration
    if env.storage:
        storage_metadata = {}
        if env.storage.ephemeral_storage_gb:
            storage_metadata["ephemeral_storage_gb"] = env.storage.ephemeral_storage_gb
        if env.storage.persistent_volume is not None:
            storage_metadata["persistent_volume"] = env.storage.persistent_volume
        if storage_metadata:
            metadata["storage"] = storage_metadata

    return metadata if metadata else None


def generate_terraform_variables(
    job_config: JobConfig,
    asset_definition: Any,
) -> Dict[str, Any]:
    """Generate Terraform variables from job configuration.

    This function extracts all metadata needed for Terraform module invocation,
    including tags, runtime environment, and resource references.

    Args:
        job_config: Job configuration
        asset_definition: Asset definition instance

    Returns:
        Dictionary of Terraform variables
    """
    variables = {}

    # Cloud provider
    if job_config.infrastructure and job_config.infrastructure.cloud_provider:
        variables["cloud_provider"] = job_config.infrastructure.cloud_provider

    # Runtime environment
    runtime_env = extract_runtime_environment_metadata(job_config)
    if runtime_env:
        variables["runtime_environment"] = runtime_env

    # Tags
    tags = extract_infrastructure_tags(job_config, asset_definition)
    if tags:
        variables["tags"] = tags

    # Resource references
    if (
        job_config.infrastructure
        and job_config.infrastructure.terraform
        and job_config.infrastructure.terraform.resource_refs
    ):
        variables["resource_refs"] = job_config.infrastructure.terraform.resource_refs

    # Additional Terraform variables
    if (
        job_config.infrastructure
        and job_config.infrastructure.terraform
        and job_config.infrastructure.terraform.variables
    ):
        variables.update(job_config.infrastructure.terraform.variables)

    # Job metadata
    variables["job_metadata"] = {
        "tenant_id": job_config.tenant_id,
        "environment": job_config.environment,
        "asset_name": job_config.asset,
        "source_connector": job_config.source_connector,
        "target_connector": job_config.target_connector,
    }

    return variables


def generate_terraform_output(
    job_config: JobConfig,
    asset_definition: Any,
    format: str = "json",
) -> str:
    """Generate Terraform-compatible output for infrastructure provisioning.

    Args:
        job_config: Job configuration
        asset_definition: Asset definition instance
        format: Output format ('json' or 'hcl')

    Returns:
        Terraform variables in specified format
    """
    variables = generate_terraform_variables(job_config, asset_definition)

    if format == "json":
        return json.dumps(variables, indent=2)
    elif format == "hcl":
        # Simple HCL generation (for basic use cases)
        # For complex HCL, consider using hcl2 library
        lines = []
        for key, value in variables.items():
            if isinstance(value, dict):
                lines.append(f"{key} = {{")
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, str):
                        lines.append(f'  {sub_key} = "{sub_value}"')
                    elif isinstance(sub_value, list):
                        lines.append(f"  {sub_key} = {json.dumps(sub_value)}")
                    else:
                        lines.append(f"  {sub_key} = {sub_value}")
                lines.append("}")
            elif isinstance(value, str):
                lines.append(f'{key} = "{value}"')
            elif isinstance(value, list):
                lines.append(f"{key} = {json.dumps(value)}")
            else:
                lines.append(f"{key} = {value}")
        return "\n".join(lines)
    else:
        raise ValueError(f"Unsupported format: {format}. Use 'json' or 'hcl'")


def get_infrastructure_metadata_summary(
    job_config: JobConfig,
    asset_definition: Any,
) -> Dict[str, Any]:
    """Get a summary of infrastructure metadata for logging/debugging.

    Args:
        job_config: Job configuration
        asset_definition: Asset definition instance

    Returns:
        Dictionary with infrastructure metadata summary
    """
    summary = {
        "has_infrastructure": job_config.infrastructure is not None,
    }

    if job_config.infrastructure:
        infra = job_config.infrastructure
        summary["cloud_provider"] = infra.cloud_provider
        summary["has_runtime_environment"] = infra.runtime_environment is not None
        summary["has_tags"] = infra.tags is not None
        summary["has_terraform_config"] = infra.terraform is not None

        if infra.runtime_environment:
            summary["compute_type"] = infra.runtime_environment.compute_type
            summary["compute_size"] = infra.runtime_environment.compute_size

        tags = extract_infrastructure_tags(job_config, asset_definition)
        summary["tag_count"] = len(tags)
        summary["tags"] = tags

    return summary
