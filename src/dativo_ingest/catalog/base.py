"""Base catalog interface for lineage and metadata push."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..config import AssetDefinition, CatalogConfig, JobConfig


class BaseCatalog(ABC):
    """Base interface for data catalog integrations."""

    def __init__(
        self,
        catalog_config: CatalogConfig,
        asset_definition: AssetDefinition,
        job_config: JobConfig,
    ):
        """Initialize catalog client.

        Args:
            catalog_config: Catalog configuration
            asset_definition: Asset definition with schema and metadata
            job_config: Job configuration for context
        """
        self.catalog_config = catalog_config
        self.asset_definition = asset_definition
        self.job_config = job_config

    @abstractmethod
    def push_lineage(
        self,
        source_entities: List[Dict[str, Any]],
        target_entity: Dict[str, Any],
        operation: str = "ingest",
    ) -> Dict[str, Any]:
        """Push lineage information to catalog.

        Args:
            source_entities: List of source entity dictionaries with 'name', 'type', 'location', etc.
            target_entity: Target entity dictionary with 'name', 'type', 'location', etc.
            operation: Operation type (e.g., 'ingest', 'transform')

        Returns:
            Dictionary with push result (status, lineage_id, etc.)
        """
        pass

    @abstractmethod
    def push_metadata(
        self,
        entity: Dict[str, Any],
        tags: Optional[List[str]] = None,
        owners: Optional[List[str]] = None,
        description: Optional[str] = None,
        custom_properties: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Push metadata (tags, owners, description, etc.) to catalog.

        Args:
            entity: Entity dictionary with 'name', 'type', 'location', etc.
            tags: List of tags to apply
            owners: List of owner emails/names
            description: Entity description
            custom_properties: Custom properties dictionary

        Returns:
            Dictionary with push result (status, entity_id, etc.)
        """
        pass

    @abstractmethod
    def ensure_entity_exists(
        self,
        entity: Dict[str, Any],
        schema: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Ensure entity (table/dataset) exists in catalog, create if needed.

        Args:
            entity: Entity dictionary with 'name', 'type', 'location', etc.
            schema: Optional schema definition

        Returns:
            Dictionary with entity information (entity_id, name, etc.)
        """
        pass

    def _extract_source_entities(self) -> List[Dict[str, Any]]:
        """Extract source entity information from job configuration.

        Returns:
            List of source entity dictionaries
        """
        source_config = self.job_config.get_source()
        source_entities = []

        # Extract source information based on source type
        if source_config.type == "postgres" or source_config.type == "mysql":
            # Database source
            connection = source_config.connection or {}
            db_config = connection.get("postgres") or connection.get("mysql", {})
            database = db_config.get("database") or db_config.get("dbname")
            host = db_config.get("host") or db_config.get("hostname")
            port = db_config.get("port")

            if source_config.tables:
                for table_config in source_config.tables:
                    table_name = table_config.get("name") or table_config.get("table")
                    schema = table_config.get("schema") or "public"
                    source_entities.append(
                        {
                            "name": f"{database}.{schema}.{table_name}",
                            "type": "table",
                            "location": f"{source_config.type}://{host}:{port}/{database}/{schema}/{table_name}",
                            "database": database,
                            "schema": schema,
                            "table": table_name,
                        }
                    )
        elif source_config.type == "csv":
            # File source
            if source_config.files:
                for file_config in source_config.files:
                    file_path = file_config.get("path")
                    source_entities.append(
                        {
                            "name": file_path,
                            "type": "file",
                            "location": f"file://{file_path}",
                            "format": "csv",
                        }
                    )
        elif source_config.type in ["stripe", "hubspot"]:
            # API source
            source_entities.append(
                {
                    "name": f"{source_config.type}_{self.asset_definition.object}",
                    "type": "api",
                    "location": f"api://{source_config.type}/{self.asset_definition.object}",
                    "source_type": source_config.type,
                    "object": self.asset_definition.object,
                }
            )
        else:
            # Generic source
            source_entities.append(
                {
                    "name": f"{source_config.type}_{self.asset_definition.object}",
                    "type": "source",
                    "location": f"{source_config.type}://{self.asset_definition.object}",
                }
            )

        return source_entities

    def _extract_target_entity(self) -> Dict[str, Any]:
        """Extract target entity information from job configuration.

        Returns:
            Target entity dictionary
        """
        target_config = self.job_config.get_target()
        connection = target_config.connection or {}
        s3_config = connection.get("s3") or connection.get("minio", {})

        # Build S3 path
        bucket = s3_config.get("bucket") or "default-bucket"
        domain = self.asset_definition.domain or "default"
        data_product = getattr(self.asset_definition, "dataProduct", None) or "default"
        table_name = (
            self.asset_definition.name.lower().replace("-", "_").replace(" ", "_")
        )

        s3_path = f"s3://{bucket}/{domain}/{data_product}/{table_name}"

        table_name_override = (
            self.catalog_config.table_name or self.asset_definition.name
        )
        database = self.catalog_config.database or domain

        return {
            "name": table_name_override,
            "type": "table",
            "location": s3_path,
            "database": database,
            "schema": data_product,
            "table": table_name_override,
            "format": "parquet",
        }

    def _extract_tags(self) -> List[str]:
        """Extract tags from asset definition and job config.

        Returns:
            List of tag strings
        """
        tags = []

        # Tags from asset definition
        if self.asset_definition.tags:
            tags.extend(self.asset_definition.tags)

        # Domain tag
        if self.asset_definition.domain:
            tags.append(f"domain:{self.asset_definition.domain}")

        # Data product tag
        if (
            hasattr(self.asset_definition, "dataProduct")
            and self.asset_definition.dataProduct
        ):
            tags.append(f"data-product:{self.asset_definition.dataProduct}")

        # Source type tag
        tags.append(f"source-type:{self.asset_definition.source_type}")

        # Compliance classification tags
        if (
            self.asset_definition.compliance
            and self.asset_definition.compliance.classification
        ):
            for classification in self.asset_definition.compliance.classification:
                tags.append(f"classification:{classification}")

        # FinOps tags
        if self.job_config.finops:
            if self.job_config.finops.get("cost_center"):
                tags.append(f"cost-center:{self.job_config.finops['cost_center']}")
            if self.job_config.finops.get("business_tags"):
                tags.extend(self.job_config.finops["business_tags"])

        return tags

    def _extract_owners(self) -> List[str]:
        """Extract owners from asset definition.

        Returns:
            List of owner emails/names
        """
        owners = []
        if self.asset_definition.team and self.asset_definition.team.owner:
            owners.append(self.asset_definition.team.owner)

            # Add team roles as owners
            if self.asset_definition.team.roles:
                for role in self.asset_definition.team.roles:
                    if role.email:
                        owners.append(role.email)

        return owners

    def _extract_description(self) -> Optional[str]:
        """Extract description from asset definition.

        Returns:
            Description string or None
        """
        if self.asset_definition.description:
            parts = []
            # Handle both DescriptionModel object and dict
            desc = self.asset_definition.description
            if isinstance(desc, dict):
                purpose = desc.get("purpose")
                usage = desc.get("usage")
                limitations = desc.get("limitations")
            else:
                purpose = desc.purpose if hasattr(desc, "purpose") else None
                usage = desc.usage if hasattr(desc, "usage") else None
                limitations = desc.limitations if hasattr(desc, "limitations") else None

            if purpose:
                parts.append(f"Purpose: {purpose}")
            if usage:
                parts.append(f"Usage: {usage}")
            if limitations:
                parts.append(f"Limitations: {limitations}")
            return "\n\n".join(parts) if parts else None
        return None
