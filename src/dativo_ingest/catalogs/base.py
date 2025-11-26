"""Base catalog interface for data catalog integrations."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..config import AssetDefinition, JobConfig, TargetConfig


class BaseCatalog(ABC):
    """Base interface for data catalog integrations."""

    def __init__(
        self,
        catalog_config: Dict[str, Any],
        job_config: JobConfig,
        asset_definition: AssetDefinition,
        target_config: TargetConfig,
    ):
        """Initialize catalog client.

        Args:
            catalog_config: Catalog configuration from job config
            job_config: Complete job configuration
            asset_definition: Asset definition with schema and metadata
            target_config: Target configuration with storage details
        """
        self.catalog_config = catalog_config
        self.job_config = job_config
        self.asset_definition = asset_definition
        self.target_config = target_config

    @abstractmethod
    def push_lineage(
        self,
        source_entities: List[Dict[str, Any]],
        target_entity: Dict[str, Any],
        operation: str = "ingest",
    ) -> Dict[str, Any]:
        """Push lineage information to catalog.

        Args:
            source_entities: List of source entity metadata (e.g., database tables, API endpoints)
            target_entity: Target entity metadata (e.g., Iceberg table, S3 path)
            operation: Operation type (e.g., 'ingest', 'transform')

        Returns:
            Dictionary with lineage push result (e.g., lineage_id, status)
        """
        pass

    @abstractmethod
    def push_metadata(
        self,
        entity: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Push metadata (tags, owners, descriptions) to catalog entity.

        Args:
            entity: Entity metadata (identifier, type, name)
            metadata: Metadata to push (tags, owners, descriptions, etc.)

        Returns:
            Dictionary with metadata push result
        """
        pass

    @abstractmethod
    def ensure_entity_exists(
        self,
        entity: Dict[str, Any],
        schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Ensure entity exists in catalog, create if it doesn't.

        Args:
            entity: Entity metadata (identifier, type, name)
            schema: Optional schema definition

        Returns:
            Dictionary with entity information
        """
        pass

    def _extract_source_entities(self) -> List[Dict[str, Any]]:
        """Extract source entity metadata from job configuration.

        Returns:
            List of source entity dictionaries
        """
        source_entities = []
        source_config = self.job_config.get_source()

        # Extract source type and identifier
        source_type = source_config.type
        source_identifier = None

        if source_type in ["postgres", "mysql"]:
            # Database source
            connection = source_config.connection or {}
            database = connection.get("database") or connection.get("dbname")
            tables = source_config.tables or []
            for table in tables:
                table_name = table.get("name") or table.get("table")
                source_entities.append(
                    {
                        "type": "table",
                        "database": database,
                        "schema": connection.get("schema", "public"),
                        "name": table_name,
                        "source_type": source_type,
                    }
                )
        elif source_type in ["stripe", "hubspot"]:
            # API source
            objects = source_config.objects or []
            for obj in objects:
                source_entities.append(
                    {
                        "type": "api_endpoint",
                        "source_type": source_type,
                        "name": obj,
                    }
                )
        elif source_type in ["csv", "gdrive_csv", "google_sheets"]:
            # File source
            if source_config.files:
                for file_info in source_config.files:
                    source_entities.append(
                        {
                            "type": "file",
                            "source_type": source_type,
                            "path": file_info.get("path"),
                            "name": file_info.get("object", "file"),
                        }
                    )
            elif source_config.sheets:
                for sheet_info in source_config.sheets:
                    source_entities.append(
                        {
                            "type": "spreadsheet",
                            "source_type": source_type,
                            "spreadsheet_id": sheet_info.get("spreadsheet_id"),
                            "name": sheet_info.get("name", "sheet"),
                        }
                    )

        return source_entities

    def _extract_target_entity(self) -> Dict[str, Any]:
        """Extract target entity metadata from job configuration.

        Returns:
            Target entity dictionary
        """
        # Extract storage path
        connection = self.target_config.connection or {}
        s3_config = connection.get("s3") or connection.get("minio", {})
        bucket = s3_config.get("bucket") or "default"

        # Build standard path structure
        domain = self.asset_definition.domain or "default"
        data_product = getattr(self.asset_definition, "dataProduct", None) or "default"
        table_name = self.asset_definition.name.lower().replace("-", "_").replace(" ", "_")

        # Full path
        full_path = f"s3://{bucket}/{domain}/{data_product}/{table_name}"

        return {
            "type": "table" if self.target_config.catalog else "dataset",
            "database": domain,
            "schema": data_product,
            "name": table_name,
            "path": full_path,
            "catalog": self.target_config.catalog,
        }

    def _extract_metadata(self) -> Dict[str, Any]:
        """Extract metadata from asset definition and job config.

        Returns:
            Dictionary with tags, owners, descriptions, etc.
        """
        from ..tag_derivation import derive_tags_from_asset

        # Derive tags
        tags = derive_tags_from_asset(
            asset_definition=self.asset_definition,
            classification_overrides=self.job_config.classification_overrides,
            finops=self.job_config.finops,
            governance_overrides=self.job_config.governance_overrides,
            source_tags=None,  # Source tags not available at catalog level
        )

        # Extract owners
        owners = []
        if self.asset_definition.team and self.asset_definition.team.owner:
            owners.append(self.asset_definition.team.owner)
            if self.asset_definition.team.roles:
                for role in self.asset_definition.team.roles:
                    if role.email:
                        owners.append(role.email)

        # Extract description
        description = None
        if self.asset_definition.description:
            desc_parts = []
            if self.asset_definition.description.purpose:
                desc_parts.append(f"Purpose: {self.asset_definition.description.purpose}")
            if self.asset_definition.description.usage:
                desc_parts.append(f"Usage: {self.asset_definition.description.usage}")
            if self.asset_definition.description.limitations:
                desc_parts.append(f"Limitations: {self.asset_definition.description.limitations}")
            description = "\n\n".join(desc_parts) if desc_parts else None

        # Extract tags list
        tag_list = []
        if self.asset_definition.tags:
            tag_list.extend(
                self.asset_definition.tags
                if isinstance(self.asset_definition.tags, list)
                else [self.asset_definition.tags]
            )

        # Add derived tags to tag list
        for key, value in tags.items():
            if value:
                tag_list.append(f"{key}:{value}")

        return {
            "tags": tag_list,
            "owners": owners,
            "description": description,
            "domain": self.asset_definition.domain,
            "data_product": getattr(self.asset_definition, "dataProduct", None),
            "version": str(self.asset_definition.version),
            "source_type": self.asset_definition.source_type,
            "compliance": (
                {
                    "classification": self.asset_definition.compliance.classification
                    if self.asset_definition.compliance
                    and self.asset_definition.compliance.classification
                    else None,
                    "retention_days": (
                        self.asset_definition.compliance.retention_days
                        if self.asset_definition.compliance
                        else None
                    ),
                }
                if self.asset_definition.compliance
                else None
            ),
            "finops": self.job_config.finops,
        }
