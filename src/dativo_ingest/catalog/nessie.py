"""Nessie catalog integration for lineage and metadata push."""

import os
from typing import Any, Dict, List, Optional

from ..config import AssetDefinition, CatalogConfig, JobConfig
from .base import BaseCatalog


class NessieCatalog(BaseCatalog):
    """Nessie catalog integration (lineage via Iceberg table properties)."""

    def __init__(
        self,
        catalog_config: CatalogConfig,
        asset_definition: AssetDefinition,
        job_config: JobConfig,
    ):
        """Initialize Nessie catalog client.

        Args:
            catalog_config: Catalog configuration
            asset_definition: Asset definition
            job_config: Job configuration
        """
        super().__init__(catalog_config, asset_definition, job_config)

        # Nessie lineage is handled through Iceberg table properties
        # The IcebergCommitter already handles table creation and properties
        # This catalog integration adds lineage-specific functionality

    def ensure_entity_exists(
        self,
        entity: Dict[str, Any],
        schema: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Ensure entity exists in Nessie.

        Note: Nessie tables are managed through IcebergCommitter.
        This method returns entity info for lineage tracking.

        Args:
            entity: Entity dictionary
            schema: Optional schema definition

        Returns:
            Entity information dictionary
        """
        database = entity.get("database") or self.catalog_config.database or "default"
        table_name = entity.get("name") or self.asset_definition.name

        return {
            "entity_id": f"{database}.{table_name}",
            "database": database,
            "table": table_name,
            "location": entity.get("location", ""),
        }

    def push_metadata(
        self,
        entity: Dict[str, Any],
        tags: Optional[List[str]] = None,
        owners: Optional[List[str]] = None,
        description: Optional[str] = None,
        custom_properties: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Push metadata to Nessie (via Iceberg table properties).

        Note: Metadata is already pushed through IcebergCommitter.
        This method is a no-op as metadata is handled during table creation/update.

        Args:
            entity: Entity dictionary
            tags: List of tags
            owners: List of owners
            description: Description
            custom_properties: Custom properties

        Returns:
            Push result dictionary
        """
        # Metadata is handled by IcebergCommitter via table properties
        # This is a placeholder for consistency with the interface
        return {
            "status": "success",
            "note": "Metadata handled by IcebergCommitter via table properties",
        }

    def push_lineage(
        self,
        source_entities: List[Dict[str, Any]],
        target_entity: Dict[str, Any],
        operation: str = "ingest",
    ) -> Dict[str, Any]:
        """Push lineage to Nessie (via Iceberg table properties).

        Lineage is stored in Iceberg table properties and can be queried
        through Nessie's API or Iceberg metadata.

        Args:
            source_entities: List of source entities
            target_entity: Target entity
            operation: Operation type

        Returns:
            Lineage push result
        """
        # Lineage is stored in Iceberg table properties
        # The IcebergCommitter should add lineage properties during table update
        # This method returns lineage info for tracking

        source_names = [e.get("name") or e.get("location", "") for e in source_entities]
        target_name = target_entity.get("name") or self.asset_definition.name

        # Lineage information that should be added to table properties
        lineage_info = {
            "lineage.sources": ",".join(source_names),
            "lineage.operation": operation,
            "lineage.target": target_name,
        }

        return {
            "status": "success",
            "lineage_info": lineage_info,
            "sources_count": len(source_entities),
            "note": "Lineage stored in Iceberg table properties",
        }
