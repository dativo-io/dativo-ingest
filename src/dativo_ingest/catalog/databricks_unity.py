"""Databricks Unity Catalog integration."""

import json
from typing import Any, Dict, List, Optional

import requests

from .base import BaseCatalog, CatalogLineage, CatalogMetadata


class DatabricksUnityCatalog(BaseCatalog):
    """Databricks Unity Catalog integration."""

    def __init__(self, connection: Dict[str, Any], database: Optional[str] = None):
        """Initialize Databricks Unity Catalog connection.

        Args:
            connection: Connection configuration with:
                - workspace_url: Databricks workspace URL (e.g., https://workspace.cloud.databricks.com)
                - access_token: Databricks personal access token or OAuth token
                - catalog: Catalog name (optional, defaults to 'main')
            database: Schema name (default: default)
        """
        super().__init__(connection, database)
        self.workspace_url = connection.get("workspace_url", "").rstrip("/")
        self.access_token = connection.get("access_token")
        self.catalog_name = connection.get("catalog", "main")
        self.schema_name = database or self.database or "default"

        if not self.workspace_url:
            raise ValueError("workspace_url is required for Databricks Unity Catalog")
        if not self.access_token:
            raise ValueError("access_token is required for Databricks Unity Catalog")

        self.api_url = f"{self.workspace_url}/api/2.1/unity-catalog"

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def table_exists(self, table_name: str, database: Optional[str] = None) -> bool:
        """Check if a table exists in Databricks Unity Catalog."""
        schema = database or self.schema_name
        full_name = f"{self.catalog_name}.{schema}.{table_name}"

        try:
            response = requests.get(
                f"{self.api_url}/tables/{full_name}",
                headers=self._get_headers(),
                timeout=10,
            )
            return response.status_code == 200
        except Exception:
            return False

    def create_table_if_not_exists(
        self,
        table_name: str,
        schema: List[Dict[str, Any]],
        location: Optional[str] = None,
        metadata: Optional[CatalogMetadata] = None,
    ) -> None:
        """Create a table in Databricks Unity Catalog if it doesn't exist."""
        schema_name = self.schema_name
        full_name = f"{self.catalog_name}.{schema_name}.{table_name}"

        if self.table_exists(table_name, schema_name):
            # Update existing table metadata
            self.push_metadata(table_name, metadata or CatalogMetadata(name=table_name), location)
            return

        # Ensure schema exists
        try:
            requests.get(
                f"{self.api_url}/schemas/{self.catalog_name}.{schema_name}",
                headers=self._get_headers(),
                timeout=10,
            )
        except requests.exceptions.RequestException:
            # Create schema
            schema_payload = {
                "name": schema_name,
                "catalog_name": self.catalog_name,
            }
            try:
                response = requests.post(
                    f"{self.api_url}/schemas",
                    json=schema_payload,
                    headers=self._get_headers(),
                    timeout=30,
                )
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                raise Exception(f"Failed to create schema in Databricks: {e}") from e

        # Convert schema to Unity Catalog format
        columns = []
        for field in schema:
            column = {
                "name": field.get("name", ""),
                "type_name": self._map_data_type(field.get("type", "string")),
                "type_text": self._map_data_type(field.get("type", "string")),
                "comment": field.get("description"),
            }
            columns.append(column)

        # Create table
        table_payload = {
            "name": table_name,
            "catalog_name": self.catalog_name,
            "schema_name": schema_name,
            "table_type": "EXTERNAL",
            "data_source_format": "DELTA",
            "columns": columns,
        }

        if location:
            table_payload["storage_location"] = location

        if metadata and metadata.description:
            table_payload["comment"] = metadata.description

        try:
            response = requests.post(
                f"{self.api_url}/tables",
                json=table_payload,
                headers=self._get_headers(),
                timeout=30,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to create table in Databricks Unity Catalog: {e}") from e

    def push_metadata(
        self, table_name: str, metadata: CatalogMetadata, location: Optional[str] = None
    ) -> None:
        """Push metadata to Databricks Unity Catalog."""
        schema_name = self.schema_name
        full_name = f"{self.catalog_name}.{schema_name}.{table_name}"

        try:
            # Get existing table
            response = requests.get(
                f"{self.api_url}/tables/{full_name}",
                headers=self._get_headers(),
                timeout=10,
            )

            if response.status_code != 200:
                # Table doesn't exist, create it
                self.create_table_if_not_exists(
                    table_name, metadata.schema or [], location, metadata
                )
                return

            table_data = response.json()

            # Update metadata
            updates = {}
            if metadata.description:
                updates["comment"] = metadata.description

            # Add properties
            properties = table_data.get("properties", {})
            if metadata.tags:
                properties["tags"] = ",".join(metadata.tags)
            if metadata.custom_properties:
                properties.update(metadata.custom_properties)
            if properties:
                updates["properties"] = properties

            if updates:
                # Patch table
                response = requests.patch(
                    f"{self.api_url}/tables/{full_name}",
                    json=updates,
                    headers=self._get_headers(),
                    timeout=30,
                )
                response.raise_for_status()

        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to update table metadata in Databricks: {e}") from e

    def push_lineage(self, lineage: CatalogLineage) -> None:
        """Push lineage information to Databricks Unity Catalog."""
        # Databricks Unity Catalog stores lineage in table properties
        target_table = lineage.target_entity.get("table", "")
        target_schema = lineage.target_entity.get("database", self.schema_name)
        full_name = f"{self.catalog_name}.{target_schema}.{target_table}"

        try:
            # Get existing table
            response = requests.get(
                f"{self.api_url}/tables/{full_name}",
                headers=self._get_headers(),
                timeout=10,
            )

            if response.status_code != 200:
                raise Exception(f"Table not found: {full_name}")

            table_data = response.json()
            properties = table_data.get("properties", {})

            # Store lineage as JSON in properties
            lineage_data = {
                "process_name": lineage.process_name,
                "process_type": lineage.process_type,
                "sources": lineage.source_entities,
            }
            properties["lineage"] = json.dumps(lineage_data)

            # Update table
            response = requests.patch(
                f"{self.api_url}/tables/{full_name}",
                json={"properties": properties},
                headers=self._get_headers(),
                timeout=30,
            )
            response.raise_for_status()

        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to push lineage to Databricks Unity Catalog: {e}") from e

    def _map_data_type(self, data_type: str) -> str:
        """Map common data types to Databricks Unity Catalog types."""
        type_mapping = {
            "string": "STRING",
            "varchar": "STRING",
            "text": "STRING",
            "int": "INT",
            "integer": "INT",
            "bigint": "BIGINT",
            "float": "FLOAT",
            "double": "DOUBLE",
            "decimal": "DECIMAL",
            "boolean": "BOOLEAN",
            "date": "DATE",
            "timestamp": "TIMESTAMP",
            "array": "ARRAY<STRING>",
            "struct": "STRUCT",
            "map": "MAP<STRING,STRING>",
        }
        return type_mapping.get(data_type.lower(), "STRING")
