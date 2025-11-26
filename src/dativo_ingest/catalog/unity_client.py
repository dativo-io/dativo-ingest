"""Databricks Unity Catalog client implementation."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseCatalogClient, LineageInfo, TableMetadata

logger = logging.getLogger(__name__)


class UnityClient(BaseCatalogClient):
    """Databricks Unity Catalog client for lineage and metadata tracking."""

    def connect(self) -> None:
        """Establish connection to Databricks Unity Catalog."""
        try:
            from databricks.sdk import WorkspaceClient
            from databricks.sdk.service import catalog
        except ImportError as e:
            raise ImportError(
                "databricks-sdk is required for Unity Catalog integration. "
                "Install with: pip install databricks-sdk"
            ) from e

        connection_config = self.config.connection

        try:
            # Create workspace client
            client_kwargs = {}
            if "host" in connection_config:
                client_kwargs["host"] = connection_config["host"]
            if "token" in connection_config:
                client_kwargs["token"] = connection_config["token"]

            self._client = WorkspaceClient(**client_kwargs)
            logger.info("Connected to Databricks Unity Catalog")
        except Exception as e:
            logger.error(f"Failed to connect to Unity Catalog: {e}")
            raise

    def create_or_update_table(self, metadata: TableMetadata) -> None:
        """Create or update table metadata in Unity Catalog.

        Args:
            metadata: Table metadata to create or update
        """
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first.")

        try:
            from databricks.sdk.service.catalog import (
                ColumnInfo,
                ColumnTypeName,
                TableInfo,
                TableType,
            )

            catalog_name = self.config.connection.get("catalog", "main")
            schema_name = metadata.schema or "default"
            table_name = metadata.name

            # Ensure catalog exists
            try:
                self._client.catalogs.get(catalog_name)
            except Exception:
                logger.warning(
                    f"Catalog '{catalog_name}' may not exist. Tables may fail to create."
                )

            # Ensure schema exists
            try:
                self._client.schemas.get(f"{catalog_name}.{schema_name}")
            except Exception:
                try:
                    self._client.schemas.create(
                        name=schema_name,
                        catalog_name=catalog_name,
                        comment="Dativo ingestion schema",
                    )
                    logger.info(f"Created schema: {catalog_name}.{schema_name}")
                except Exception as schema_error:
                    logger.warning(f"Failed to create schema: {schema_error}")

            # Build columns
            columns = []
            for col in metadata.columns:
                col_type = self._map_column_type(col.get("type", "string"))
                column = ColumnInfo(
                    name=col["name"],
                    type_name=col_type,
                    type_text=col_type.value if hasattr(col_type, "value") else str(col_type),
                    comment=col.get("description"),
                    nullable=not col.get("required", False),
                )
                columns.append(column)

            full_name = f"{catalog_name}.{schema_name}.{table_name}"

            # Build properties
            properties = {
                **metadata.properties,
                **{f"tag.{k}": v for k, v in metadata.tags.items()},
            }
            if metadata.owner:
                properties["owner"] = metadata.owner

            # Check if table exists
            try:
                existing_table = self._client.tables.get(full_name)
                
                # Update table properties
                self._client.tables.update(
                    full_name=full_name,
                    comment=metadata.description,
                    properties=properties,
                )
                logger.info(f"Updated table in Unity Catalog: {full_name}")
                
            except Exception:
                # Create external table (since we're writing to S3/object storage)
                storage_location = metadata.properties.get("location", "")
                
                try:
                    self._client.tables.create(
                        name=table_name,
                        catalog_name=catalog_name,
                        schema_name=schema_name,
                        table_type=TableType.EXTERNAL,
                        data_source_format="PARQUET",
                        columns=columns,
                        storage_location=storage_location,
                        comment=metadata.description,
                        properties=properties,
                    )
                    logger.info(f"Created table in Unity Catalog: {full_name}")
                except Exception as create_error:
                    logger.error(
                        f"Failed to create table in Unity Catalog: {create_error}"
                    )
                    raise

        except Exception as e:
            logger.error(f"Failed to create/update table in Unity Catalog: {e}")
            raise

    def push_lineage(self, lineage: LineageInfo) -> None:
        """Push lineage information to Unity Catalog.

        Note: Unity Catalog has limited lineage API. This stores lineage as table properties.

        Args:
            lineage: Lineage information to push
        """
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first.")

        try:
            # Get existing table properties
            try:
                table = self._client.tables.get(lineage.target_fqn)
                
                # Update properties with lineage information
                properties = table.properties or {}
                properties.update(
                    {
                        "lineage.source": lineage.source_fqn,
                        "lineage.pipeline": lineage.pipeline_name,
                        "lineage.last_update": datetime.utcnow().isoformat(),
                    }
                )

                if lineage.records_written:
                    properties["lineage.records_written"] = str(lineage.records_written)

                # Update table
                self._client.tables.update(
                    full_name=lineage.target_fqn,
                    properties=properties,
                )
                logger.info(
                    f"Lineage information stored in Unity Catalog: {lineage.target_fqn}"
                )

            except Exception as table_error:
                logger.warning(
                    f"Failed to update lineage for table {lineage.target_fqn}: {table_error}"
                )

        except Exception as e:
            logger.warning(f"Failed to push lineage to Unity Catalog: {e}")
            # Don't raise - lineage is optional

    def add_tags(self, table_fqn: str, tags: Dict[str, str]) -> None:
        """Add or update tags for a table.

        Args:
            table_fqn: Fully qualified name of the table (catalog.schema.table)
            tags: Dictionary of tags to add/update
        """
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first.")

        try:
            # Get existing table
            table = self._client.tables.get(table_fqn)

            # Update properties with tags
            properties = table.properties or {}
            for key, value in tags.items():
                properties[f"tag.{key}"] = value

            # Update table
            self._client.tables.update(
                full_name=table_fqn,
                properties=properties,
            )
            logger.info(f"Tags added to Unity Catalog table: {table_fqn}")

        except Exception as e:
            logger.warning(f"Failed to add tags to Unity Catalog: {e}")
            # Don't raise - tags are optional

    def set_owner(self, table_fqn: str, owner: str) -> None:
        """Set owner for a table.

        Args:
            table_fqn: Fully qualified name of the table (catalog.schema.table)
            owner: Owner identifier (username or email)
        """
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first.")

        try:
            # Update table owner
            self._client.tables.update(
                full_name=table_fqn,
                owner=owner,
            )
            logger.info(f"Owner set for Unity Catalog table: {table_fqn}")

        except Exception as e:
            logger.warning(f"Failed to set owner in Unity Catalog: {e}")
            # Don't raise - owner is optional

    def _map_column_type(self, dativo_type: str):
        """Map Dativo column type to Unity Catalog type.

        Args:
            dativo_type: Dativo column type

        Returns:
            Unity Catalog ColumnTypeName
        """
        from databricks.sdk.service.catalog import ColumnTypeName

        type_mapping = {
            "string": ColumnTypeName.STRING,
            "integer": ColumnTypeName.LONG,
            "long": ColumnTypeName.LONG,
            "float": ColumnTypeName.DOUBLE,
            "double": ColumnTypeName.DOUBLE,
            "boolean": ColumnTypeName.BOOLEAN,
            "timestamp": ColumnTypeName.TIMESTAMP,
            "datetime": ColumnTypeName.TIMESTAMP,
            "date": ColumnTypeName.DATE,
        }
        return type_mapping.get(dativo_type.lower(), ColumnTypeName.STRING)
