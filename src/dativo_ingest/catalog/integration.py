"""Catalog integration helper for job execution."""

from typing import Any, Dict, List, Optional

from .base import CatalogLineage, CatalogMetadata
from .factory import CatalogFactory

from ..config import AssetDefinition, JobConfig, SourceConfig, TargetConfig


def push_to_catalog(
    job_config: JobConfig,
    asset_definition: AssetDefinition,
    source_config: SourceConfig,
    target_config: TargetConfig,
    output_location: str,
    source_entities: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Push lineage and metadata to configured catalog.

    Args:
        job_config: Job configuration
        asset_definition: Asset definition
        source_config: Source configuration
        target_config: Target configuration
        output_location: Output location (S3 path, etc.)
        source_entities: Optional list of source entity references

    Raises:
        Exception: If catalog push fails
    """
    if not job_config.catalog:
        return

    catalog_config = job_config.catalog

    # Create catalog instance
    catalog = CatalogFactory.create(
        catalog_type=catalog_config.type,
        connection=catalog_config.connection,
        database=catalog_config.database,
    )

    # Determine table name
    table_name = catalog_config.table_name or asset_definition.name.lower().replace(
        "-", "_"
    ).replace(" ", "_")

    # Build metadata from asset definition
    metadata = CatalogMetadata(
        name=table_name,
        description=asset_definition.description.purpose
        if asset_definition.description
        else asset_definition.name,
        tags=asset_definition.tags or [],
        owners=[asset_definition.team.owner] if asset_definition.team else [],
        schema=asset_definition.schema,
        classification=asset_definition.compliance.classification
        if asset_definition.compliance
        else None,
        cost_center=asset_definition.finops.cost_center if asset_definition.finops else None,
        business_tags=asset_definition.finops.business_tags if asset_definition.finops else None,
        project=asset_definition.finops.project if asset_definition.finops else None,
        environment=job_config.environment,
        custom_properties={
            "domain": asset_definition.domain,
            "dataProduct": asset_definition.dataProduct,
            "tenant": job_config.tenant_id,
            "source_type": asset_definition.source_type,
        },
    )

    # Push metadata
    try:
        catalog.push_metadata(table_name, metadata, output_location)
    except Exception as e:
        # Log error but don't fail the job
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(
            f"Failed to push metadata to catalog: {e}",
            extra={"catalog_type": catalog_config.type, "table_name": table_name},
        )

    # Build lineage if source entities are provided
    if source_entities:
        # Build source entity references
        source_refs = []
        for source_entity in source_entities:
            source_refs.append(
                {
                    "database": source_entity.get("database", "default"),
                    "table": source_entity.get("table", ""),
                    "fqn": source_entity.get("fqn"),
                }
            )

        # Build target entity reference
        target_ref = {
            "database": catalog_config.database or "default",
            "table": table_name,
            "fqn": f"{catalog_config.database or 'default'}.{table_name}",
        }

        # Create lineage
        lineage = CatalogLineage(
            source_entities=source_refs,
            target_entity=target_ref,
            process_name=f"{job_config.tenant_id}_{asset_definition.name}",
            process_type="etl",
        )

        # Push lineage
        try:
            catalog.push_lineage(lineage)
        except Exception as e:
            # Log error but don't fail the job
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                f"Failed to push lineage to catalog: {e}",
                extra={"catalog_type": catalog_config.type, "table_name": table_name},
            )
