"""Nessie catalog integration."""

import json
from typing import Any, Dict, List, Optional

from pynessie import NessieClient
from pynessie.model import ContentKey, IcebergTable, Reference

from .base import BaseCatalog, CatalogLineage, CatalogMetadata


class NessieCatalog(BaseCatalog):
    """Nessie catalog integration."""

    def __init__(self, connection: Dict[str, Any], database: Optional[str] = None):
        """Initialize Nessie catalog connection.

        Args:
            connection: Connection configuration with:
                - uri: Nessie server URI (e.g., http://localhost:19120/api/v1)
                - branch: Branch name (default: main)
                - auth_token: Optional authentication token
            database: Namespace/database name (default: default)
        """
        super().__init__(connection, database)
        self.uri = connection.get("uri", "http://localhost:19120/api/v1")
        self.branch = connection.get("branch", "main")
        self.auth_token = connection.get("auth_token")
        self.namespace = database or self.database or "default"

        # Create Nessie client
        if self.auth_token:
            self.client = NessieClient(
                base_url=self.uri, bearer_token=self.auth_token
            )
        else:
            self.client = NessieClient(base_url=self.uri)

    def table_exists(self, table_name: str, database: Optional[str] = None) -> bool:
        """Check if a table exists in Nessie."""
        namespace = database or self.namespace
        content_key = ContentKey.from_path_string(f"{namespace}.{table_name}")

        try:
            ref = Reference.branch(self.branch)
            content = self.client.get_content(content_key, ref)
            return content is not None
        except Exception:
            return False

    def create_table_if_not_exists(
        self,
        table_name: str,
        schema: List[Dict[str, Any]],
        location: Optional[str] = None,
        metadata: Optional[CatalogMetadata] = None,
    ) -> None:
        """Create a table in Nessie if it doesn't exist."""
        namespace = self.namespace
        content_key = ContentKey.from_path_string(f"{namespace}.{table_name}")

        if self.table_exists(table_name, namespace):
            # Update existing table metadata
            self.push_metadata(table_name, metadata or CatalogMetadata(name=table_name), location)
            return

        # Create Iceberg table
        if not location:
            raise ValueError("location is required for Nessie table creation")

        # Create table metadata
        table_metadata = {
            "schema": {
                "type": "struct",
                "fields": [
                    {
                        "id": i,
                        "name": field.get("name", ""),
                        "type": self._map_data_type(field.get("type", "string")),
                        "required": not field.get("nullable", True),
                        "doc": field.get("description"),
                    }
                    for i, field in enumerate(schema)
                ],
            },
            "location": location,
        }

        if metadata and metadata.description:
            table_metadata["description"] = metadata.description

        # Create Iceberg table content
        iceberg_table = IcebergTable(
            id="table-id",
            metadata_location=location,
            snapshot_id=1,
            schema_id=1,
            spec_id=1,
            sort_order_id=1,
        )

        try:
            ref = Reference.branch(self.branch)
            self.client.set_content(content_key, iceberg_table, ref, "Create table")
        except Exception as e:
            raise Exception(f"Failed to create table in Nessie: {e}") from e

    def push_metadata(
        self, table_name: str, metadata: CatalogMetadata, location: Optional[str] = None
    ) -> None:
        """Push metadata to Nessie."""
        namespace = self.namespace
        content_key = ContentKey.from_path_string(f"{namespace}.{table_name}")

        try:
            ref = Reference.branch(self.branch)
            content = self.client.get_content(content_key, ref)

            if not content:
                # Table doesn't exist, create it
                self.create_table_if_not_exists(
                    table_name, metadata.schema or [], location, metadata
                )
                return

            # Nessie stores metadata in table properties
            # Update metadata by committing new table version
            # Note: This is a simplified implementation
            # In practice, you'd update the Iceberg table metadata

        except Exception as e:
            raise Exception(f"Failed to update table metadata in Nessie: {e}") from e

    def push_lineage(self, lineage: CatalogLineage) -> None:
        """Push lineage information to Nessie."""
        # Nessie doesn't have native lineage support
        # We can store lineage in table metadata or as a separate entity
        target_table = lineage.target_entity.get("table", "")
        namespace = self.namespace
        content_key = ContentKey.from_path_string(f"{namespace}.{target_table}")

        try:
            ref = Reference.branch(self.branch)
            content = self.client.get_content(content_key, ref)

            if not content:
                raise Exception(f"Table not found: {target_table}")

            # Store lineage in table metadata
            # This would require updating the Iceberg table metadata
            # For now, we'll log a warning
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                "Nessie lineage storage requires Iceberg metadata updates. "
                "Lineage information: %s",
                lineage,
            )

        except Exception as e:
            raise Exception(f"Failed to push lineage to Nessie: {e}") from e

    def _map_data_type(self, data_type: str) -> str:
        """Map common data types to Iceberg/Nessie types."""
        type_mapping = {
            "string": "string",
            "varchar": "string",
            "text": "string",
            "int": "int",
            "integer": "int",
            "bigint": "long",
            "float": "float",
            "double": "double",
            "decimal": "decimal(38,18)",
            "boolean": "boolean",
            "date": "date",
            "timestamp": "timestamp",
            "array": "list<string>",
            "struct": "struct",
            "map": "map<string,string>",
        }
        return type_mapping.get(data_type.lower(), "string")
