"""Catalog manager for routing to appropriate catalog implementation."""

import logging
from typing import Any, Dict, List, Optional

from ..config import AssetDefinition, JobConfig, TargetConfig

logger = logging.getLogger(__name__)


class CatalogManager:
    """Manages catalog integrations and routes to appropriate implementation."""

    def __init__(
        self,
        job_config: JobConfig,
        asset_definition: AssetDefinition,
        target_config: TargetConfig,
    ):
        """Initialize catalog manager.

        Args:
            job_config: Complete job configuration
            asset_definition: Asset definition
            target_config: Target configuration
        """
        self.job_config = job_config
        self.asset_definition = asset_definition
        self.target_config = target_config
        self._catalog = None

    def _get_catalog(self):
        """Get or create catalog instance."""
        if self._catalog is not None:
            return self._catalog

        if not self.job_config.catalog or not self.job_config.catalog.enabled:
            return None

        catalog_type = self.job_config.catalog.type
        catalog_config = self.job_config.catalog.connection

        try:
            if catalog_type == "aws_glue":
                from .aws_glue import AWSGlueCatalog

                self._catalog = AWSGlueCatalog(
                    catalog_config=catalog_config,
                    job_config=self.job_config,
                    asset_definition=self.asset_definition,
                    target_config=self.target_config,
                )
            elif catalog_type == "databricks_unity":
                from .databricks_unity import DatabricksUnityCatalog

                self._catalog = DatabricksUnityCatalog(
                    catalog_config=catalog_config,
                    job_config=self.job_config,
                    asset_definition=self.asset_definition,
                    target_config=self.target_config,
                )
            elif catalog_type == "nessie":
                from .nessie import NessieCatalog

                self._catalog = NessieCatalog(
                    catalog_config=catalog_config,
                    job_config=self.job_config,
                    asset_definition=self.asset_definition,
                    target_config=self.target_config,
                )
            elif catalog_type == "openmetadata":
                from .openmetadata import OpenMetadataCatalog

                self._catalog = OpenMetadataCatalog(
                    catalog_config=catalog_config,
                    job_config=self.job_config,
                    asset_definition=self.asset_definition,
                    target_config=self.target_config,
                )
            else:
                logger.warning(
                    f"Unknown catalog type: {catalog_type}. Skipping catalog integration."
                )
                return None
        except ImportError as e:
            logger.warning(
                f"Failed to import catalog implementation for {catalog_type}: {e}. "
                "Skipping catalog integration."
            )
            return None
        except Exception as e:
            logger.error(
                f"Failed to initialize catalog {catalog_type}: {e}",
                exc_info=True,
            )
            return None

        return self._catalog

    def push_lineage(
        self,
        source_entities: Optional[List[Dict[str, Any]]] = None,
        target_entity: Optional[Dict[str, Any]] = None,
        operation: str = "ingest",
    ) -> Optional[Dict[str, Any]]:
        """Push lineage information to catalog.

        Args:
            source_entities: Optional list of source entities (auto-extracted if None)
            target_entity: Optional target entity (auto-extracted if None)
            operation: Operation type

        Returns:
            Lineage push result or None if catalog not configured
        """
        catalog = self._get_catalog()
        if not catalog:
            return None

        try:
            if source_entities is None:
                source_entities = catalog._extract_source_entities()
            if target_entity is None:
                target_entity = catalog._extract_target_entity()

            return catalog.push_lineage(source_entities, target_entity, operation)
        except Exception as e:
            logger.error(
                f"Failed to push lineage to catalog: {e}",
                exc_info=True,
            )
            return None

    def push_metadata(
        self,
        entity: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Push metadata to catalog entity.

        Args:
            entity: Optional entity (auto-extracted if None)
            metadata: Optional metadata (auto-extracted if None)

        Returns:
            Metadata push result or None if catalog not configured
        """
        catalog = self._get_catalog()
        if not catalog:
            return None

        try:
            if entity is None:
                entity = catalog._extract_target_entity()
            if metadata is None:
                metadata = catalog._extract_metadata()

            return catalog.push_metadata(entity, metadata)
        except Exception as e:
            logger.error(
                f"Failed to push metadata to catalog: {e}",
                exc_info=True,
            )
            return None

    def ensure_entity_exists(
        self,
        entity: Optional[Dict[str, Any]] = None,
        schema: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Ensure entity exists in catalog.

        Args:
            entity: Optional entity (auto-extracted if None)
            schema: Optional schema definition

        Returns:
            Entity information or None if catalog not configured
        """
        catalog = self._get_catalog()
        if not catalog:
            return None

        try:
            if entity is None:
                entity = catalog._extract_target_entity()

            return catalog.ensure_entity_exists(entity, schema)
        except Exception as e:
            logger.error(
                f"Failed to ensure entity exists in catalog: {e}",
                exc_info=True,
            )
            return None
