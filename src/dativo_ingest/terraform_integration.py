"""Terraform integration for infrastructure provisioning and tag propagation.

This module provides utilities for:
1. Deriving comprehensive tags from job configuration, asset definitions, and metadata
2. Exporting infrastructure metadata in Terraform-compatible formats
3. Supporting cloud-agnostic deployment (AWS, GCP, Azure)
4. Enabling cost allocation, compliance, and resource traceability via tags
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import InfrastructureConfig, JobConfig
from .tag_derivation import derive_tags_from_asset


def derive_infrastructure_tags(
    job_config: JobConfig,
    asset_definition: Any,
    source_tags: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Derive comprehensive tags for infrastructure resources.

    Combines tags from multiple sources with proper precedence:
    1. Infrastructure block tags (highest priority)
    2. Job config finops/governance metadata
    3. Asset definition tags
    4. Derived tags from tag_derivation module

    Args:
        job_config: Job configuration
        asset_definition: Asset definition instance
        source_tags: Optional source system tags

    Returns:
        Dictionary of tags suitable for cloud resource tagging
    """
    tags = {}

    # Start with derived tags from asset definition
    derived_tags = derive_tags_from_asset(
        asset_definition=asset_definition,
        classification_overrides=job_config.classification_overrides,
        finops=job_config.finops,
        governance_overrides=job_config.governance_overrides,
        source_tags=source_tags,
    )

    # Convert namespaced tags to flat tags for cloud resources
    # Keep namespaced format for internal use, flatten for cloud tags
    for key, value in derived_tags.items():
        # For cloud tags, use simplified keys
        if key.startswith("finops."):
            tag_key = key.replace("finops.", "")
            tags[tag_key] = value
        elif key.startswith("governance."):
            tag_key = key.replace("governance.", "")
            tags[tag_key] = value
        elif key.startswith("classification."):
            # Classification tags can be kept as-is or simplified
            tag_key = key.replace("classification.", "classification_")
            tags[tag_key] = value
        else:
            tags[key] = value

    # Add job-level metadata
    tags["tenant_id"] = job_config.tenant_id
    if job_config.environment:
        tags["environment"] = job_config.environment

    # Add infrastructure-specific tags if present
    if job_config.infrastructure and job_config.infrastructure.tags:
        # Infrastructure tags override derived tags (highest priority)
        tags.update(job_config.infrastructure.tags)

    # Add standard tags for traceability
    if asset_definition:
        if hasattr(asset_definition, "name") and asset_definition.name:
            tags["asset_name"] = asset_definition.name
        if hasattr(asset_definition, "version") and asset_definition.version:
            tags["asset_version"] = asset_definition.version
        if hasattr(asset_definition, "domain") and asset_definition.domain:
            tags["domain"] = asset_definition.domain

    return tags


def format_tags_for_provider(
    tags: Dict[str, str], provider: str
) -> Dict[str, Any]:
    """Format tags for specific cloud provider.

    Different providers have different tag formats:
    - AWS: Simple key-value pairs
    - GCP: Labels with specific restrictions (lowercase, hyphens, underscores)
    - Azure: Tags with similar format to AWS

    Args:
        tags: Dictionary of tags
        provider: Cloud provider ('aws', 'gcp', 'azure')

    Returns:
        Formatted tags dictionary for the provider
    """
    formatted = {}

    for key, value in tags.items():
        # Normalize key for provider requirements
        normalized_key = key.lower().replace(" ", "_").replace(".", "_")

        if provider == "gcp":
            # GCP labels: lowercase, hyphens, underscores, and numbers
            # Max 63 chars, must start with lowercase letter
            normalized_key = normalized_key.replace("_", "-")
            if len(normalized_key) > 63:
                normalized_key = normalized_key[:63]
            if normalized_key and normalized_key[0].isdigit():
                normalized_key = "label-" + normalized_key
            # GCP label values: max 63 chars, must match regex [a-z0-9_-]*
            normalized_value = str(value).lower().replace(" ", "-")
            if len(normalized_value) > 63:
                normalized_value = normalized_value[:63]
            formatted[normalized_key] = normalized_value
        elif provider == "aws":
            # AWS tags: case-sensitive, alphanumeric + : = + - . @
            # Max 128 chars for key, 256 chars for value
            if len(normalized_key) > 128:
                normalized_key = normalized_key[:128]
            if len(str(value)) > 256:
                value = str(value)[:256]
            formatted[normalized_key] = str(value)
        elif provider == "azure":
            # Azure tags: similar to AWS
            if len(normalized_key) > 512:
                normalized_key = normalized_key[:512]
            if len(str(value)) > 256:
                value = str(value)[:256]
            formatted[normalized_key] = str(value)
        else:
            # Default: use as-is
            formatted[normalized_key] = str(value)

    return formatted


def export_terraform_variables(
    job_config: JobConfig,
    asset_definition: Any,
    output_path: Optional[Path] = None,
    source_tags: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Export infrastructure metadata as Terraform variables.

    Creates a dictionary of variables that can be passed to Terraform modules
    for provisioning infrastructure resources. Includes:
    - Tags for cost allocation, compliance, and traceability
    - Runtime configuration
    - Resource references
    - Additional metadata

    Args:
        job_config: Job configuration
        asset_definition: Asset definition instance
        output_path: Optional path to write variables JSON file
        source_tags: Optional source system tags

    Returns:
        Dictionary of Terraform variables
    """
    if not job_config.infrastructure:
        return {}

    infra = job_config.infrastructure

    # Derive comprehensive tags
    tags = derive_infrastructure_tags(job_config, asset_definition, source_tags)

    # Format tags for provider
    provider = infra.provider or "aws"  # Default to AWS
    formatted_tags = format_tags_for_provider(tags, provider)

    # Build Terraform variables
    tf_vars = {
        "tags": formatted_tags,
        "tenant_id": job_config.tenant_id,
        "environment": job_config.environment or "default",
    }

    # Add runtime configuration
    if infra.runtime:
        runtime_vars = {}
        if infra.runtime.compute_type:
            runtime_vars["compute_type"] = infra.runtime.compute_type
        if infra.runtime.instance_type:
            runtime_vars["instance_type"] = infra.runtime.instance_type
        if infra.runtime.memory_mb:
            runtime_vars["memory_mb"] = infra.runtime.memory_mb
        if infra.runtime.cpu_units:
            runtime_vars["cpu_units"] = infra.runtime.cpu_units
        if infra.runtime.timeout_seconds:
            runtime_vars["timeout_seconds"] = infra.runtime.timeout_seconds
        if infra.runtime.scaling:
            scaling_vars = {}
            if infra.runtime.scaling.min_instances is not None:
                scaling_vars["min_instances"] = infra.runtime.scaling.min_instances
            if infra.runtime.scaling.max_instances is not None:
                scaling_vars["max_instances"] = infra.runtime.scaling.max_instances
            if infra.runtime.scaling.target_cpu_utilization is not None:
                scaling_vars[
                    "target_cpu_utilization"
                ] = infra.runtime.scaling.target_cpu_utilization
            if scaling_vars:
                runtime_vars["scaling"] = scaling_vars
        if runtime_vars:
            tf_vars["runtime"] = runtime_vars

    # Add resource references
    if infra.resource_refs:
        tf_vars["resource_refs"] = infra.resource_refs

    # Add additional metadata
    if infra.metadata:
        tf_vars["metadata"] = infra.metadata

    # Add provider-specific configuration
    if infra.provider:
        tf_vars["provider"] = infra.provider

    # Write to file if path provided
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(tf_vars, f, indent=2)
        print(f"Terraform variables exported to: {output_path}")

    return tf_vars


def export_terraform_tfvars(
    job_config: JobConfig,
    asset_definition: Any,
    output_path: Path,
    source_tags: Optional[Dict[str, str]] = None,
) -> None:
    """Export Terraform variables in .tfvars format.

    Creates a .tfvars file that can be used with Terraform commands:
    terraform apply -var-file=variables.tfvars

    Args:
        job_config: Job configuration
        asset_definition: Asset definition instance
        output_path: Path to write .tfvars file
        source_tags: Optional source system tags
    """
    tf_vars = export_terraform_variables(
        job_config, asset_definition, None, source_tags
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        f.write("# Terraform variables generated from Dativo job configuration\n")
        f.write(f"# Tenant: {job_config.tenant_id}\n")
        if job_config.environment:
            f.write(f"# Environment: {job_config.environment}\n")
        f.write("\n")

        # Write tags
        if "tags" in tf_vars:
            f.write("tags = {\n")
            for key, value in sorted(tf_vars["tags"].items()):
                # Escape quotes in values
                escaped_value = str(value).replace('"', '\\"')
                f.write(f'  {key} = "{escaped_value}"\n')
            f.write("}\n\n")

        # Write other variables
        for key, value in tf_vars.items():
            if key == "tags":
                continue
            if isinstance(value, dict):
                f.write(f"{key} = {{\n")
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, dict):
                        f.write(f"  {sub_key} = {{\n")
                        for k, v in sub_value.items():
                            f.write(f'    {k} = {json.dumps(v)}\n')
                        f.write("  }\n")
                    else:
                        f.write(f'  {sub_key} = {json.dumps(sub_value)}\n')
                f.write("}\n\n")
            elif isinstance(value, list):
                f.write(f"{key} = {json.dumps(value)}\n\n")
            else:
                f.write(f'{key} = "{value}"\n\n')

    print(f"Terraform .tfvars file exported to: {output_path}")


def get_infrastructure_metadata(
    job_config: JobConfig,
    asset_definition: Any,
    source_tags: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Get infrastructure metadata for Dagster and other orchestration systems.

    Returns a dictionary of metadata that can be used by orchestration systems
    like Dagster to understand the infrastructure requirements and pass them
    to Terraform modules.

    Args:
        job_config: Job configuration
        asset_definition: Asset definition instance
        source_tags: Optional source system tags

    Returns:
        Dictionary of infrastructure metadata
    """
    if not job_config.infrastructure:
        return {}

    metadata = {
        "provider": job_config.infrastructure.provider,
        "module_path": job_config.infrastructure.module_path,
        "tags": derive_infrastructure_tags(job_config, asset_definition, source_tags),
    }

    if job_config.infrastructure.runtime:
        # Support both Pydantic v1 and v2
        if hasattr(job_config.infrastructure.runtime, "model_dump"):
            metadata["runtime"] = job_config.infrastructure.runtime.model_dump(
                exclude_none=True
            )
        elif hasattr(job_config.infrastructure.runtime, "dict"):
            metadata["runtime"] = job_config.infrastructure.runtime.dict(
                exclude_none=True
            )
        else:
            # Fallback: manually extract fields
            runtime = job_config.infrastructure.runtime
            runtime_dict = {}
            for field in ["compute_type", "instance_type", "memory_mb", "cpu_units", "timeout_seconds", "scaling"]:
                value = getattr(runtime, field, None)
                if value is not None:
                    if field == "scaling" and hasattr(value, "dict"):
                        runtime_dict[field] = value.dict(exclude_none=True)
                    elif field == "scaling" and hasattr(value, "model_dump"):
                        runtime_dict[field] = value.model_dump(exclude_none=True)
                    else:
                        runtime_dict[field] = value
            if runtime_dict:
                metadata["runtime"] = runtime_dict

    if job_config.infrastructure.resource_refs:
        metadata["resource_refs"] = job_config.infrastructure.resource_refs

    if job_config.infrastructure.metadata:
        metadata["custom_metadata"] = job_config.infrastructure.metadata

    return metadata
