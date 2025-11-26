"""AWS Glue Data Catalog client implementation."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseCatalogClient, LineageInfo, TableMetadata

logger = logging.getLogger(__name__)


class GlueClient(BaseCatalogClient):
    """AWS Glue Data Catalog client for lineage and metadata tracking."""

    def connect(self) -> None:
        """Establish connection to AWS Glue."""
        try:
            import boto3
        except ImportError as e:
            raise ImportError(
                "boto3 is required for AWS Glue integration. "
                "Install with: pip install boto3"
            ) from e

        connection_config = self.config.connection

        # Create Glue client
        try:
            session_kwargs = {}
            if "region" in connection_config:
                session_kwargs["region_name"] = connection_config["region"]
            if "aws_access_key_id" in connection_config:
                session_kwargs["aws_access_key_id"] = connection_config[
                    "aws_access_key_id"
                ]
            if "aws_secret_access_key" in connection_config:
                session_kwargs["aws_secret_access_key"] = connection_config[
                    "aws_secret_access_key"
                ]

            self._client = boto3.client("glue", **session_kwargs)
            logger.info("Connected to AWS Glue Data Catalog")
        except Exception as e:
            logger.error(f"Failed to connect to AWS Glue: {e}")
            raise

    def create_or_update_table(self, metadata: TableMetadata) -> None:
        """Create or update table metadata in Glue.

        Args:
            metadata: Table metadata to create or update
        """
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first.")

        try:
            database_name = metadata.database or "default"

            # Ensure database exists
            try:
                self._client.get_database(Name=database_name)
            except self._client.exceptions.EntityNotFoundException:
                self._client.create_database(
                    DatabaseInput={"Name": database_name, "Description": "Dativo ingestion database"}
                )
                logger.info(f"Created Glue database: {database_name}")

            # Build table input
            table_input = {
                "Name": metadata.name,
                "Description": metadata.description or "",
                "StorageDescriptor": {
                    "Columns": [
                        {
                            "Name": col["name"],
                            "Type": self._map_column_type(col.get("type", "string")),
                            "Comment": col.get("description", ""),
                        }
                        for col in metadata.columns
                    ],
                    "Location": metadata.properties.get("location", ""),
                    "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
                    "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
                    "SerdeInfo": {
                        "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe",
                        "Parameters": {"serialization.format": "1"},
                    },
                },
                "Parameters": {
                    **metadata.properties,
                    **{f"tag:{k}": v for k, v in metadata.tags.items()},
                },
            }

            # Add owner if provided
            if metadata.owner:
                table_input["Owner"] = metadata.owner

            # Check if table exists
            try:
                self._client.get_table(DatabaseName=database_name, Name=metadata.name)
                # Update existing table
                self._client.update_table(
                    DatabaseName=database_name, TableInput=table_input
                )
                logger.info(
                    f"Updated table in Glue: {database_name}.{metadata.name}"
                )
            except self._client.exceptions.EntityNotFoundException:
                # Create new table
                self._client.create_table(
                    DatabaseName=database_name, TableInput=table_input
                )
                logger.info(
                    f"Created table in Glue: {database_name}.{metadata.name}"
                )

        except Exception as e:
            logger.error(f"Failed to create/update table in Glue: {e}")
            raise

    def push_lineage(self, lineage: LineageInfo) -> None:
        """Push lineage information to Glue.

        Note: Glue doesn't have native lineage API. This stores lineage as table properties.

        Args:
            lineage: Lineage information to push
        """
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first.")

        try:
            # Extract database and table from target FQN
            # Expected format: database.table or catalog.database.table
            parts = lineage.target_fqn.split(".")
            if len(parts) >= 2:
                database_name = parts[-2]
                table_name = parts[-1]
            else:
                logger.warning(
                    f"Invalid target FQN format: {lineage.target_fqn}. Expected: database.table"
                )
                return

            # Get existing table
            try:
                response = self._client.get_table(
                    DatabaseName=database_name, Name=table_name
                )
                table_input = response["Table"]

                # Remove read-only fields
                table_input.pop("DatabaseName", None)
                table_input.pop("CreateTime", None)
                table_input.pop("UpdateTime", None)
                table_input.pop("CreatedBy", None)
                table_input.pop("IsRegisteredWithLakeFormation", None)
                table_input.pop("CatalogId", None)
                table_input.pop("VersionId", None)

                # Add lineage information as properties
                if "Parameters" not in table_input:
                    table_input["Parameters"] = {}

                table_input["Parameters"].update(
                    {
                        "lineage:source": lineage.source_fqn,
                        "lineage:pipeline": lineage.pipeline_name,
                        "lineage:last_update": datetime.utcnow().isoformat(),
                    }
                )

                if lineage.records_written:
                    table_input["Parameters"]["lineage:records_written"] = str(
                        lineage.records_written
                    )

                # Update table
                self._client.update_table(
                    DatabaseName=database_name, TableInput=table_input
                )
                logger.info(
                    f"Lineage information stored in Glue table properties: {lineage.target_fqn}"
                )

            except self._client.exceptions.EntityNotFoundException:
                logger.warning(
                    f"Table not found in Glue, cannot push lineage: {lineage.target_fqn}"
                )

        except Exception as e:
            logger.warning(f"Failed to push lineage to Glue: {e}")
            # Don't raise - lineage is optional

    def add_tags(self, table_fqn: str, tags: Dict[str, str]) -> None:
        """Add or update tags for a table.

        Args:
            table_fqn: Fully qualified name of the table (database.table)
            tags: Dictionary of tags to add/update
        """
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first.")

        try:
            # Parse FQN
            parts = table_fqn.split(".")
            if len(parts) >= 2:
                database_name = parts[-2]
                table_name = parts[-1]
            else:
                logger.warning(f"Invalid FQN format: {table_fqn}. Expected: database.table")
                return

            # Get existing table
            response = self._client.get_table(
                DatabaseName=database_name, Name=table_name
            )
            table_input = response["Table"]

            # Remove read-only fields
            table_input.pop("DatabaseName", None)
            table_input.pop("CreateTime", None)
            table_input.pop("UpdateTime", None)
            table_input.pop("CreatedBy", None)
            table_input.pop("IsRegisteredWithLakeFormation", None)
            table_input.pop("CatalogId", None)
            table_input.pop("VersionId", None)

            # Add tags as properties (Glue stores tags as table properties)
            if "Parameters" not in table_input:
                table_input["Parameters"] = {}

            for key, value in tags.items():
                table_input["Parameters"][f"tag:{key}"] = value

            # Update table
            self._client.update_table(
                DatabaseName=database_name, TableInput=table_input
            )
            logger.info(f"Tags added to Glue table: {table_fqn}")

        except Exception as e:
            logger.warning(f"Failed to add tags to Glue: {e}")
            # Don't raise - tags are optional

    def set_owner(self, table_fqn: str, owner: str) -> None:
        """Set owner for a table.

        Args:
            table_fqn: Fully qualified name of the table (database.table)
            owner: Owner identifier
        """
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first.")

        try:
            # Parse FQN
            parts = table_fqn.split(".")
            if len(parts) >= 2:
                database_name = parts[-2]
                table_name = parts[-1]
            else:
                logger.warning(f"Invalid FQN format: {table_fqn}. Expected: database.table")
                return

            # Get existing table
            response = self._client.get_table(
                DatabaseName=database_name, Name=table_name
            )
            table_input = response["Table"]

            # Remove read-only fields
            table_input.pop("DatabaseName", None)
            table_input.pop("CreateTime", None)
            table_input.pop("UpdateTime", None)
            table_input.pop("CreatedBy", None)
            table_input.pop("IsRegisteredWithLakeFormation", None)
            table_input.pop("CatalogId", None)
            table_input.pop("VersionId", None)

            # Set owner
            table_input["Owner"] = owner

            # Update table
            self._client.update_table(
                DatabaseName=database_name, TableInput=table_input
            )
            logger.info(f"Owner set for Glue table: {table_fqn}")

        except Exception as e:
            logger.warning(f"Failed to set owner in Glue: {e}")
            # Don't raise - owner is optional

    def _map_column_type(self, dativo_type: str) -> str:
        """Map Dativo column type to Glue/Hive type.

        Args:
            dativo_type: Dativo column type

        Returns:
            Glue/Hive column type
        """
        type_mapping = {
            "string": "string",
            "integer": "bigint",
            "long": "bigint",
            "float": "double",
            "double": "double",
            "boolean": "boolean",
            "timestamp": "timestamp",
            "datetime": "timestamp",
            "date": "date",
            "array": "array<string>",
            "map": "map<string,string>",
        }
        return type_mapping.get(dativo_type.lower(), "string")
