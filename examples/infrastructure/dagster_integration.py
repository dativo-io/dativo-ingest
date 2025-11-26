"""Dagster integration helpers for external infrastructure metadata.

This module provides utilities for integrating Dativo's infrastructure
configuration with Dagster assets and resources.
"""

from typing import Any, Dict, Optional

from dagster import (
    AssetExecutionContext,
    OpExecutionContext,
    resource,
)

from dativo_ingest.config import JobConfig
from dativo_ingest.infrastructure import (
    get_infrastructure_tags,
    resolve_terraform_outputs,
)


def add_infrastructure_metadata(
    context: AssetExecutionContext, job_config: JobConfig
) -> None:
    """Add infrastructure metadata to Dagster asset.
    
    Args:
        context: Dagster asset execution context
        job_config: Dativo job configuration
    """
    if not job_config.infrastructure:
        return
    
    infrastructure = job_config.infrastructure
    
    # Get infrastructure tags
    infra_tags = get_infrastructure_tags(infrastructure)
    
    # Add basic metadata
    metadata = {
        "tenant_id": job_config.tenant_id,
        "environment": job_config.environment or "prod",
        "provider": infrastructure.provider.provider,
        "region": infrastructure.provider.region or "unknown",
    }
    
    # Add cost allocation metadata
    if infrastructure.tags:
        tags = infrastructure.tags
        if tags.cost_center:
            metadata["cost_center"] = tags.cost_center
        if tags.business_unit:
            metadata["business_unit"] = tags.business_unit
        if tags.project:
            metadata["project"] = tags.project
        if tags.owner:
            metadata["owner"] = tags.owner
        if tags.compliance:
            metadata["compliance"] = ",".join(tags.compliance)
    
    # Add resource metadata
    if infrastructure.provider.resources:
        resource_types = [r.resource_type for r in infrastructure.provider.resources]
        metadata["resources"] = ",".join(resource_types)
        metadata["resource_count"] = len(infrastructure.provider.resources)
    
    # Add Terraform metadata
    if infrastructure.terraform:
        tf = infrastructure.terraform
        if tf.module_path:
            metadata["terraform_module"] = tf.module_path
        if tf.workspace:
            metadata["terraform_workspace"] = tf.workspace
    
    # Add all metadata to context
    context.add_output_metadata(metadata)


def get_infrastructure_resource_config(
    job_config: JobConfig,
) -> Dict[str, Any]:
    """Get infrastructure resource configuration for Dagster resources.
    
    Args:
        job_config: Dativo job configuration
    
    Returns:
        Dictionary of infrastructure resource configuration
    """
    if not job_config.infrastructure:
        return {}
    
    infrastructure = job_config.infrastructure
    provider = infrastructure.provider
    
    config = {
        "provider": provider.provider,
        "region": provider.region,
        "tenant_id": job_config.tenant_id,
        "environment": job_config.environment or "prod",
    }
    
    # Add provider-specific configuration
    if provider.provider == "aws":
        config["aws_region"] = provider.region
        config["aws_account_id"] = provider.account_id
        
        # Extract S3 bucket and IAM role if configured
        if provider.resources:
            for resource in provider.resources:
                if resource.resource_type == "s3_bucket":
                    config["s3_bucket_name"] = resource.resource_name
                    config["s3_bucket_arn"] = resource.resource_id
                elif resource.resource_type == "iam_role":
                    config["iam_role_arn"] = resource.resource_id
                elif resource.resource_type == "glue_catalog":
                    config["glue_database"] = resource.resource_name
    
    elif provider.provider == "gcp":
        config["gcp_project_id"] = provider.project_id
        config["gcp_region"] = provider.region
        
        # Extract GCS bucket and service account if configured
        if provider.resources:
            for resource in provider.resources:
                if resource.resource_type == "gcs_bucket":
                    config["gcs_bucket_name"] = resource.resource_name
                    config["gcs_bucket_uri"] = resource.resource_id
                elif resource.resource_type == "service_account":
                    config["service_account_email"] = resource.resource_id
                elif resource.resource_type == "bigquery_dataset":
                    config["bigquery_dataset_id"] = resource.resource_name
    
    # Add tags
    if infrastructure.tags:
        config["tags"] = get_infrastructure_tags(infrastructure)
    
    return config


@resource(
    config_schema={
        "job_config_path": str,
    }
)
def dativo_infrastructure_resource(context):
    """Dagster resource for Dativo infrastructure configuration.
    
    Provides access to infrastructure metadata, resource ARNs,
    and Terraform outputs within Dagster ops and assets.
    
    Example:
        @op(required_resource_keys={"dativo_infra"})
        def my_op(context):
            infra = context.resources.dativo_infra
            s3_bucket = infra["s3_bucket_name"]
            cost_center = infra["tags"]["infrastructure.cost_center"]
    """
    from dativo_ingest.config import JobConfig
    
    job_config_path = context.resource_config["job_config_path"]
    job_config = JobConfig.from_yaml(job_config_path)
    
    return get_infrastructure_resource_config(job_config)


def get_cost_allocation_tags(job_config: JobConfig) -> Dict[str, str]:
    """Extract cost allocation tags from infrastructure configuration.
    
    Args:
        job_config: Dativo job configuration
    
    Returns:
        Dictionary of cost allocation tags
    """
    if not job_config.infrastructure or not job_config.infrastructure.tags:
        return {}
    
    tags = job_config.infrastructure.tags
    cost_tags = {}
    
    if tags.cost_center:
        cost_tags["cost_center"] = tags.cost_center
    if tags.business_unit:
        cost_tags["business_unit"] = tags.business_unit
    if tags.project:
        cost_tags["project"] = tags.project
    if tags.environment:
        cost_tags["environment"] = tags.environment
    
    # Add tenant ID for multi-tenant cost tracking
    cost_tags["tenant_id"] = job_config.tenant_id
    
    return cost_tags


def get_compliance_metadata(job_config: JobConfig) -> Dict[str, Any]:
    """Extract compliance metadata from infrastructure configuration.
    
    Args:
        job_config: Dativo job configuration
    
    Returns:
        Dictionary of compliance metadata
    """
    if not job_config.infrastructure or not job_config.infrastructure.tags:
        return {}
    
    tags = job_config.infrastructure.tags
    compliance = {}
    
    if tags.compliance:
        compliance["regulations"] = tags.compliance
        compliance["compliance_required"] = True
    
    if tags.owner:
        compliance["data_owner"] = tags.owner
    
    # Check for custom compliance tags
    if tags.custom:
        if "data_classification" in tags.custom:
            compliance["data_classification"] = tags.custom["data_classification"]
        if "retention_policy" in tags.custom:
            compliance["retention_policy"] = tags.custom["retention_policy"]
        if "encryption_required" in tags.custom:
            compliance["encryption_required"] = tags.custom["encryption_required"] == "true"
    
    return compliance


# Example Dagster asset with infrastructure integration
def create_dativo_asset_with_infrastructure(
    job_config_path: str,
    asset_name: str,
):
    """Create a Dagster asset with infrastructure integration.
    
    Args:
        job_config_path: Path to Dativo job configuration
        asset_name: Name of the Dagster asset
    
    Returns:
        Dagster asset definition
    """
    from dagster import asset
    from dativo_ingest.config import JobConfig
    
    @asset(name=asset_name)
    def dativo_asset(context: AssetExecutionContext):
        """Dagster asset that runs a Dativo ingestion job with infrastructure metadata."""
        # Load job configuration
        job_config = JobConfig.from_yaml(job_config_path)
        
        # Add infrastructure metadata
        add_infrastructure_metadata(context, job_config)
        
        # Add cost allocation tags
        cost_tags = get_cost_allocation_tags(job_config)
        context.log.info(f"Cost allocation tags: {cost_tags}")
        
        # Add compliance metadata
        compliance = get_compliance_metadata(job_config)
        context.log.info(f"Compliance metadata: {compliance}")
        
        # Run ingestion (placeholder - implement actual ingestion logic)
        context.log.info(f"Running ingestion for {job_config.tenant_id}")
        
        # Return metadata
        return {
            "tenant_id": job_config.tenant_id,
            "provider": job_config.infrastructure.provider.provider if job_config.infrastructure else "unknown",
            "cost_tags": cost_tags,
            "compliance": compliance,
        }
    
    return dativo_asset


# Example: Multi-tenant asset factory
def create_multi_tenant_assets(tenant_configs: Dict[str, str]):
    """Create Dagster assets for multiple tenants with infrastructure integration.
    
    Args:
        tenant_configs: Dictionary mapping tenant IDs to job config paths
    
    Returns:
        List of Dagster asset definitions
    """
    assets = []
    
    for tenant_id, config_path in tenant_configs.items():
        asset_name = f"{tenant_id}_ingestion"
        asset_def = create_dativo_asset_with_infrastructure(
            job_config_path=config_path,
            asset_name=asset_name,
        )
        assets.append(asset_def)
    
    return assets
