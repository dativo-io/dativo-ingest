"""Nessie catalog client implementation."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseCatalogClient, LineageInfo, TableMetadata

logger = logging.getLogger(__name__)


class NessieClient(BaseCatalogClient):
    """Nessie catalog client for lineage and metadata tracking.
    
    This wraps the Iceberg catalog operations for Nessie.
    """

    def connect(self) -> None:
        """Establish connection to Nessie catalog."""
        try:
            from pyiceberg.catalog import load_catalog
        except ImportError as e:
            raise ImportError(
                "pyiceberg is required for Nessie integration. "
                "Install with: pip install pyiceberg"
            ) from e

        connection_config = self.config.connection

        try:
            # Build catalog properties
            properties = {
                "type": "rest",
                "uri": connection_config.get("uri", "http://localhost:19120"),
                "ref": connection_config.get("branch", "main"),
                "warehouse": connection_config.get("warehouse", "s3://lake/"),
            }

            # Add S3 configuration if provided
            if "s3_endpoint" in connection_config:
                properties["s3.endpoint"] = connection_config["s3_endpoint"]
            if "s3_access_key_id" in connection_config:
                properties["s3.access-key-id"] = connection_config["s3_access_key_id"]
            if "s3_secret_access_key" in connection_config:
                properties["s3.secret-access-key"] = connection_config[
                    "s3_secret_access_key"
                ]
            if "s3_region" in connection_config:
                properties["s3.region"] = connection_config["s3_region"]

            catalog_name = connection_config.get("catalog_name", "nessie")
            self._client = load_catalog(catalog_name, **properties)
            logger.info("Connected to Nessie catalog")
        except Exception as e:
            logger.error(f"Failed to connect to Nessie: {e}")
            raise

    def create_or_update_table(self, metadata: TableMetadata) -> None:
        """Create or update table metadata in Nessie.

        Args:
            metadata: Table metadata to create or update
        """
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first.")

        try:
            from pyiceberg.schema import Schema
            from pyiceberg.types import (
                BooleanType,
                DateType,
                DoubleType,
                LongType,
                NestedField,
                StringType,
                TimestampType,
            )

            namespace = metadata.schema or metadata.database or "default"
            table_name = metadata.name

            # Build schema
            fields = []
            for idx, col in enumerate(metadata.columns):
                col_type = col.get("type", "string").lower()
                
                # Map to PyIceberg types
                if col_type == "string":
                    iceberg_type = StringType()
                elif col_type in ["integer", "long"]:
                    iceberg_type = LongType()
                elif col_type in ["float", "double"]:
                    iceberg_type = DoubleType()
                elif col_type == "boolean":
                    iceberg_type = BooleanType()
                elif col_type in ["timestamp", "datetime"]:
                    iceberg_type = TimestampType()
                elif col_type == "date":
                    iceberg_type = DateType()
                else:
                    iceberg_type = StringType()

                field = NestedField(
                    field_id=idx + 1,
                    name=col["name"],
                    field_type=iceberg_type,
                    required=col.get("required", False),
                )
                fields.append(field)

            schema = Schema(*fields)

            # Build table properties
            properties = {
                **metadata.properties,
                **{f"tag.{k}": v for k, v in metadata.tags.items()},
            }
            if metadata.description:
                properties["comment"] = metadata.description
            if metadata.owner:
                properties["owner"] = metadata.owner

            # Check if table exists
            try:
                table = self._client.load_table((namespace, table_name))
                
                # Update table properties
                with table.transaction() as txn:
                    for key, value in properties.items():
                        txn.set_properties(**{key: value})
                
                logger.info(
                    f"Updated table in Nessie: {namespace}.{table_name}"
                )
            except Exception:
                # Create new table
                self._client.create_table(
                    identifier=(namespace, table_name),
                    schema=schema,
                    properties=properties,
                )
                logger.info(
                    f"Created table in Nessie: {namespace}.{table_name}"
                )

        except Exception as e:
            logger.error(f"Failed to create/update table in Nessie: {e}")
            raise

    def push_lineage(self, lineage: LineageInfo) -> None:
        """Push lineage information to Nessie.

        Note: Nessie/Iceberg stores lineage as table properties.

        Args:
            lineage: Lineage information to push
        """
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first.")

        try:
            # Parse target FQN (expected: namespace.table)
            parts = lineage.target_fqn.split(".")
            if len(parts) >= 2:
                namespace = parts[-2]
                table_name = parts[-1]
            else:
                logger.warning(
                    f"Invalid target FQN format: {lineage.target_fqn}. Expected: namespace.table"
                )
                return

            # Get table and update properties
            try:
                table = self._client.load_table((namespace, table_name))
                
                lineage_properties = {
                    "lineage.source": lineage.source_fqn,
                    "lineage.pipeline": lineage.pipeline_name,
                    "lineage.last_update": datetime.utcnow().isoformat(),
                }
                
                if lineage.records_written:
                    lineage_properties["lineage.records_written"] = str(
                        lineage.records_written
                    )

                with table.transaction() as txn:
                    for key, value in lineage_properties.items():
                        txn.set_properties(**{key: value})

                logger.info(
                    f"Lineage information stored in Nessie: {lineage.target_fqn}"
                )
            except Exception as table_error:
                logger.warning(
                    f"Failed to update lineage for table {lineage.target_fqn}: {table_error}"
                )

        except Exception as e:
            logger.warning(f"Failed to push lineage to Nessie: {e}")
            # Don't raise - lineage is optional

    def add_tags(self, table_fqn: str, tags: Dict[str, str]) -> None:
        """Add or update tags for a table.

        Args:
            table_fqn: Fully qualified name of the table (namespace.table)
            tags: Dictionary of tags to add/update
        """
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first.")

        try:
            # Parse FQN
            parts = table_fqn.split(".")
            if len(parts) >= 2:
                namespace = parts[-2]
                table_name = parts[-1]
            else:
                logger.warning(f"Invalid FQN format: {table_fqn}. Expected: namespace.table")
                return

            # Get table and update properties
            table = self._client.load_table((namespace, table_name))
            
            tag_properties = {f"tag.{k}": v for k, v in tags.items()}
            
            with table.transaction() as txn:
                for key, value in tag_properties.items():
                    txn.set_properties(**{key: value})

            logger.info(f"Tags added to Nessie table: {table_fqn}")

        except Exception as e:
            logger.warning(f"Failed to add tags to Nessie: {e}")
            # Don't raise - tags are optional

    def set_owner(self, table_fqn: str, owner: str) -> None:
        """Set owner for a table.

        Args:
            table_fqn: Fully qualified name of the table (namespace.table)
            owner: Owner identifier
        """
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first.")

        try:
            # Parse FQN
            parts = table_fqn.split(".")
            if len(parts) >= 2:
                namespace = parts[-2]
                table_name = parts[-1]
            else:
                logger.warning(f"Invalid FQN format: {table_fqn}. Expected: namespace.table")
                return

            # Get table and update owner property
            table = self._client.load_table((namespace, table_name))
            
            with table.transaction() as txn:
                txn.set_properties(owner=owner)

            logger.info(f"Owner set for Nessie table: {table_fqn}")

        except Exception as e:
            logger.warning(f"Failed to set owner in Nessie: {e}")
            # Don't raise - owner is optional
