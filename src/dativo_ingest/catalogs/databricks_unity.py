"""Databricks Unity Catalog integration for lineage and metadata tracking."""

import logging
from typing import Any, Dict, List, Optional

try:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.catalog import (
        ColumnInfo,
        DataSourceType,
        TableInfo,
        TableType,
    )
except ImportError:
    WorkspaceClient = None
    ColumnInfo = None
    DataSourceType = None
    TableInfo = None
    TableType = None

from .base import BaseCatalog

logger = logging.getLogger(__name__)


class DatabricksUnityCatalog(BaseCatalog):
    """Databricks Unity Catalog integration."""

    def __init__(self, *args, **kwargs):
        """Initialize Databricks Unity Catalog client."""
        super().__init__(*args, **kwargs)
        if WorkspaceClient is None:
            raise ImportError(
                "databricks-sdk is required for Databricks Unity Catalog integration. "
                "Install with: pip install databricks-sdk"
            )

        self.host = self.catalog_config.get("host") or self.catalog_config.get(
            "workspace_url"
        )
        self.token = self.catalog_config.get("token") or self.catalog_config.get(
            "personal_access_token"
        )

        self.client = WorkspaceClient(host=self.host, token=self.token)

    def ensure_entity_exists(
        self,
        entity: Dict[str, Any],
        schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Ensure table exists in Unity Catalog."""
        catalog_name = entity.get("database", "default")
        schema_name = entity.get("schema", "default")
        table_name = entity.get("name")

        # Ensure catalog exists
        try:
            self.client.catalogs.get(catalog_name)
        except Exception:
            # Create catalog
            self.client.catalogs.create(name=catalog_name, comment=f"Catalog for {catalog_name}")

        # Ensure schema exists
        schema_full_name = f"{catalog_name}.{schema_name}"
        try:
            self.client.schemas.get(schema_full_name)
        except Exception:
            # Create schema
            self.client.schemas.create(
                name=schema_name, catalog_name=catalog_name, comment=f"Schema for {schema_name}"
            )

        # Check if table exists
        table_full_name = f"{catalog_name}.{schema_name}.{table_name}"
        try:
            return self.client.tables.get(table_full_name).as_dict()
        except Exception:
            # Create table
            columns = self._convert_schema_to_unity_columns()
            table_info = TableInfo(
                name=table_name,
                catalog_name=catalog_name,
                schema_name=schema_name,
                table_type=TableType.MANAGED,
                data_source_format="DELTA",  # Unity Catalog typically uses Delta
                columns=columns,
                storage_location=entity.get("path", ""),
                comment=(
                    self.asset_definition.description.purpose
                    if self.asset_definition.description
                    and self.asset_definition.description.purpose
                    else f"Table for {table_name}"
                ),
            )

            self.client.tables.create(table_info.as_dict())
            return self.client.tables.get(table_full_name).as_dict()

    def _convert_schema_to_unity_columns(self) -> List[ColumnInfo]:
        """Convert asset schema to Unity Catalog column format."""
        columns = []
        for field_def in self.asset_definition.schema:
            field_type = field_def.get("type", "string")
            # Map to Unity Catalog data types
            type_map = {
                "string": "STRING",
                "integer": "INT",
                "float": "FLOAT",
                "double": "DOUBLE",
                "boolean": "BOOLEAN",
                "timestamp": "TIMESTAMP",
                "datetime": "TIMESTAMP",
                "date": "DATE",
            }
            unity_type = type_map.get(field_type, "STRING")

            columns.append(
                ColumnInfo(
                    name=field_def["name"],
                    type_text=unity_type,
                    type_name=unity_type,
                    comment=field_def.get("description", ""),
                    nullable=not field_def.get("required", False),
                )
            )
        return columns

    def push_metadata(
        self,
        entity: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Push metadata to Unity Catalog table."""
        catalog_name = entity.get("database", "default")
        schema_name = entity.get("schema", "default")
        table_name = entity.get("name")
        table_full_name = f"{catalog_name}.{schema_name}.{table_name}"

        try:
            table = self.client.tables.get(table_full_name)

            # Update properties
            properties = table.properties or {}
            if metadata.get("tags"):
                properties["tags"] = ",".join(metadata["tags"])
            if metadata.get("owners"):
                properties["owners"] = ",".join(metadata["owners"])

            # Update table
            table_info = TableInfo(
                name=table_name,
                catalog_name=catalog_name,
                schema_name=schema_name,
                properties=properties,
                comment=metadata.get("description") or table.comment,
            )

            self.client.tables.update(table_full_name, table_info.as_dict())

            return {"status": "success", "table": table_full_name}
        except Exception as e:
            logger.error(f"Failed to update Unity Catalog table metadata: {e}")
            return {"status": "error", "error": str(e)}

    def push_lineage(
        self,
        source_entities: List[Dict[str, Any]],
        target_entity: Dict[str, Any],
        operation: str = "ingest",
    ) -> Dict[str, Any]:
        """Push lineage to Unity Catalog."""
        # Unity Catalog lineage is managed through the Lineage API
        catalog_name = target_entity.get("database", "default")
        schema_name = target_entity.get("schema", "default")
        table_name = target_entity.get("name")
        target_fqn = f"{catalog_name}.{schema_name}.{table_name}"

        try:
            # Unity Catalog lineage is typically managed through table properties
            # or via the Lineage API (which requires additional setup)
            # For now, we'll store lineage info in table properties
            table = self.client.tables.get(target_fqn)
            properties = table.properties or {}

            lineage_info = {
                "sources": [
                    {
                        "type": src.get("type"),
                        "name": src.get("name"),
                        "source_type": src.get("source_type"),
                    }
                    for src in source_entities
                ],
                "operation": operation,
            }

            import json

            properties["lineage"] = json.dumps(lineage_info)

            table_info = TableInfo(
                name=table_name,
                catalog_name=catalog_name,
                schema_name=schema_name,
                properties=properties,
            )

            self.client.tables.update(target_fqn, table_info.as_dict())

            return {"status": "success", "sources": len(source_entities)}
        except Exception as e:
            logger.error(f"Failed to push lineage to Unity Catalog: {e}")
            return {"status": "error", "error": str(e)}
