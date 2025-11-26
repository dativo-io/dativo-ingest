"""Lineage tracking and metadata management for data catalogs."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..config import AssetDefinition
from .base import BaseCatalogClient, LineageInfo, TableMetadata

logger = logging.getLogger(__name__)


class LineageTracker:
    """Manages lineage tracking and metadata pushing to data catalogs."""

    def __init__(self, catalog_client: BaseCatalogClient):
        """Initialize lineage tracker.

        Args:
            catalog_client: Catalog client instance
        """
        self.catalog_client = catalog_client
        self._start_time = None
        self._end_time = None

    def start_tracking(self) -> None:
        """Start tracking pipeline execution."""
        self._start_time = datetime.utcnow()
        logger.info("Started lineage tracking")

    def end_tracking(self) -> None:
        """End tracking pipeline execution."""
        self._end_time = datetime.utcnow()
        logger.info("Ended lineage tracking")

    def build_table_metadata(
        self,
        asset_definition: AssetDefinition,
        target_config: Any,
        additional_properties: Optional[Dict[str, Any]] = None,
    ) -> TableMetadata:
        """Build table metadata from asset definition.

        Args:
            asset_definition: Asset definition
            target_config: Target configuration
            additional_properties: Additional properties to include

        Returns:
            TableMetadata instance
        """
        # Build columns list
        columns = []
        for field in asset_definition.schema:
            column = {
                "name": field["name"],
                "type": field.get("type", "string"),
                "description": field.get("description"),
                "required": field.get("required", False),
            }
            columns.append(column)

        # Build tags from asset definition
        tags = {}
        if asset_definition.tags:
            for tag in asset_definition.tags:
                if isinstance(tag, str):
                    # Simple tag without value
                    tags[tag] = ""
                elif isinstance(tag, dict):
                    # Tag with key-value
                    for key, value in tag.items():
                        tags[key] = str(value)

        # Add domain and data product as tags
        if asset_definition.domain:
            tags["domain"] = asset_definition.domain
        if hasattr(asset_definition, "dataProduct") and asset_definition.dataProduct:
            tags["data_product"] = asset_definition.dataProduct

        # Add compliance tags
        if asset_definition.compliance:
            if asset_definition.compliance.classification:
                for classification in asset_definition.compliance.classification:
                    tags[f"classification"] = classification
            if asset_definition.compliance.regulations:
                for regulation in asset_definition.compliance.regulations:
                    tags[f"regulation"] = regulation

        # Build properties
        properties = {
            "source_type": asset_definition.source_type,
            "object": asset_definition.object,
            "version": str(asset_definition.version),
        }

        # Add storage location if available
        if hasattr(target_config, "connection") and target_config.connection:
            s3_config = target_config.connection.get("s3") or target_config.connection.get(
                "minio", {}
            )
            if s3_config:
                bucket = s3_config.get("bucket", "")
                domain = asset_definition.domain or "default"
                data_product = (
                    getattr(asset_definition, "dataProduct", None) or "default"
                )
                table_name = asset_definition.name.lower().replace("-", "_")
                properties["location"] = f"s3://{bucket}/{domain}/{data_product}/{table_name}"

        if additional_properties:
            properties.update(additional_properties)

        # Get description
        description = None
        if asset_definition.description:
            if hasattr(asset_definition.description, "purpose"):
                description = asset_definition.description.purpose
            elif isinstance(asset_definition.description, str):
                description = asset_definition.description

        # Get owner
        owner = None
        if asset_definition.team and asset_definition.team.owner:
            owner = asset_definition.team.owner

        return TableMetadata(
            name=asset_definition.name,
            database=asset_definition.domain,
            schema=getattr(asset_definition, "dataProduct", None) or "default",
            description=description,
            owner=owner,
            tags=tags,
            columns=columns,
            properties=properties,
        )

    def build_lineage_info(
        self,
        source_fqn: str,
        target_fqn: str,
        pipeline_name: str,
        pipeline_description: Optional[str] = None,
        records_read: Optional[int] = None,
        records_written: Optional[int] = None,
        bytes_read: Optional[int] = None,
        bytes_written: Optional[int] = None,
        status: str = "success",
    ) -> LineageInfo:
        """Build lineage information.

        Args:
            source_fqn: Fully qualified name of source
            target_fqn: Fully qualified name of target
            pipeline_name: Pipeline name
            pipeline_description: Pipeline description
            records_read: Number of records read
            records_written: Number of records written
            bytes_read: Number of bytes read
            bytes_written: Number of bytes written
            status: Pipeline status (success, failed, running)

        Returns:
            LineageInfo instance
        """
        return LineageInfo(
            source_fqn=source_fqn,
            target_fqn=target_fqn,
            pipeline_name=pipeline_name,
            pipeline_description=pipeline_description,
            start_time=self._start_time,
            end_time=self._end_time,
            status=status,
            records_read=records_read,
            records_written=records_written,
            bytes_read=bytes_read,
            bytes_written=bytes_written,
        )

    def push_table_metadata(self, metadata: TableMetadata) -> None:
        """Push table metadata to catalog.

        Args:
            metadata: Table metadata to push
        """
        if not self.catalog_client.config.push_metadata:
            logger.info("Metadata pushing is disabled, skipping")
            return

        try:
            self.catalog_client.create_or_update_table(metadata)
            logger.info(f"Pushed table metadata to catalog: {metadata.name}")
        except Exception as e:
            logger.error(f"Failed to push table metadata: {e}", exc_info=True)
            # Don't raise - catalog operations are optional

    def push_lineage(self, lineage: LineageInfo) -> None:
        """Push lineage information to catalog.

        Args:
            lineage: Lineage information to push
        """
        if not self.catalog_client.config.push_lineage:
            logger.info("Lineage pushing is disabled, skipping")
            return

        try:
            self.catalog_client.push_lineage(lineage)
            logger.info(
                f"Pushed lineage to catalog: {lineage.source_fqn} -> {lineage.target_fqn}"
            )
        except Exception as e:
            logger.error(f"Failed to push lineage: {e}", exc_info=True)
            # Don't raise - catalog operations are optional

    def push_tags(self, table_fqn: str, tags: Dict[str, str]) -> None:
        """Push tags to catalog.

        Args:
            table_fqn: Fully qualified name of the table
            tags: Dictionary of tags to push
        """
        if not self.catalog_client.config.push_metadata:
            logger.info("Metadata pushing is disabled, skipping tags")
            return

        try:
            self.catalog_client.add_tags(table_fqn, tags)
            logger.info(f"Pushed tags to catalog for table: {table_fqn}")
        except Exception as e:
            logger.error(f"Failed to push tags: {e}", exc_info=True)
            # Don't raise - catalog operations are optional

    def set_owner(self, table_fqn: str, owner: str) -> None:
        """Set owner in catalog.

        Args:
            table_fqn: Fully qualified name of the table
            owner: Owner identifier
        """
        if not self.catalog_client.config.push_metadata:
            logger.info("Metadata pushing is disabled, skipping owner")
            return

        try:
            self.catalog_client.set_owner(table_fqn, owner)
            logger.info(f"Set owner in catalog for table: {table_fqn}")
        except Exception as e:
            logger.error(f"Failed to set owner: {e}", exc_info=True)
            # Don't raise - catalog operations are optional

    def build_target_fqn(
        self,
        catalog_type: str,
        asset_definition: AssetDefinition,
        catalog_config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build fully qualified name for target table based on catalog type.

        Args:
            catalog_type: Type of catalog (openmetadata, aws_glue, databricks_unity, nessie)
            asset_definition: Asset definition
            catalog_config: Optional catalog configuration

        Returns:
            Fully qualified name of the target table
        """
        table_name = asset_definition.name
        domain = asset_definition.domain or "default"
        data_product = getattr(asset_definition, "dataProduct", None) or "default"

        if catalog_type == "openmetadata":
            # OpenMetadata FQN: service.database.schema.table
            service_name = (
                catalog_config.get("service_name", "dativo_iceberg_service")
                if catalog_config
                else "dativo_iceberg_service"
            )
            return f"{service_name}.{domain}.{data_product}.{table_name}"
        elif catalog_type == "aws_glue":
            # Glue FQN: database.table
            return f"{domain}.{table_name}"
        elif catalog_type == "databricks_unity":
            # Unity Catalog FQN: catalog.schema.table
            catalog_name = (
                catalog_config.get("catalog", "main") if catalog_config else "main"
            )
            return f"{catalog_name}.{data_product}.{table_name}"
        elif catalog_type == "nessie":
            # Nessie FQN: namespace.table
            return f"{domain}.{table_name}"
        else:
            # Default: namespace.table
            return f"{domain}.{table_name}"

    def build_source_fqn(
        self,
        source_type: str,
        source_object: str,
        source_connection: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build fully qualified name for source.

        Args:
            source_type: Type of source (stripe, hubspot, postgres, etc.)
            source_object: Source object name
            source_connection: Optional source connection configuration

        Returns:
            Fully qualified name of the source
        """
        # Build source FQN based on source type
        if source_type in ["stripe", "hubspot"]:
            # SaaS API sources
            return f"{source_type}.{source_object}"
        elif source_type in ["postgres", "mysql"]:
            # Database sources
            if source_connection and "database" in source_connection:
                database = source_connection["database"]
                return f"{source_type}.{database}.{source_object}"
            return f"{source_type}.{source_object}"
        elif source_type == "csv":
            # File sources
            return f"file.{source_object}"
        else:
            # Generic source
            return f"{source_type}.{source_object}"
