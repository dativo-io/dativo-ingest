"""AWS Glue catalog integration."""

import json
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

from .base import BaseCatalog, CatalogLineage, CatalogMetadata


class AWSGlueCatalog(BaseCatalog):
    """AWS Glue catalog integration."""

    def __init__(self, connection: Dict[str, Any], database: Optional[str] = None):
        """Initialize AWS Glue catalog connection.

        Args:
            connection: Connection configuration with:
                - region: AWS region (default: us-east-1)
                - access_key_id: AWS access key (optional, can use IAM role)
                - secret_access_key: AWS secret key (optional, can use IAM role)
            database: Database name (default: default)
        """
        super().__init__(connection, database)
        self.region = connection.get("region", "us-east-1")
        self.access_key_id = connection.get("access_key_id")
        self.secret_access_key = connection.get("secret_access_key")

        # Create Glue client
        if self.access_key_id and self.secret_access_key:
            self.glue_client = boto3.client(
                "glue",
                region_name=self.region,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
            )
        else:
            # Use IAM role or default credentials
            self.glue_client = boto3.client("glue", region_name=self.region)

        self.database_name = database or self.database or "default"

    def table_exists(self, table_name: str, database: Optional[str] = None) -> bool:
        """Check if a table exists in AWS Glue."""
        db_name = database or self.database_name
        try:
            self.glue_client.get_table(DatabaseName=db_name, Name=table_name)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "EntityNotFoundException":
                return False
            raise

    def create_table_if_not_exists(
        self,
        table_name: str,
        schema: List[Dict[str, Any]],
        location: Optional[str] = None,
        metadata: Optional[CatalogMetadata] = None,
    ) -> None:
        """Create a table in AWS Glue if it doesn't exist."""
        db_name = self.database_name

        if self.table_exists(table_name, db_name):
            # Update existing table metadata
            self.push_metadata(table_name, metadata or CatalogMetadata(name=table_name), location)
            return

        # Ensure database exists
        try:
            self.glue_client.get_database(Name=db_name)
        except ClientError as e:
            if e.response["Error"]["Code"] == "EntityNotFoundException":
                # Create database
                self.glue_client.create_database(
                    DatabaseInput={"Name": db_name, "Description": f"Database for {db_name}"}
                )

        # Convert schema to Glue format
        columns = []
        for field in schema:
            column = {
                "Name": field.get("name", ""),
                "Type": self._map_data_type(field.get("type", "string")),
                "Comment": field.get("description"),
            }
            columns.append(column)

        # Create table input
        table_input = {
            "Name": table_name,
            "StorageDescriptor": {
                "Columns": columns,
                "Location": location or "",
                "InputFormat": "org.apache.hadoop.mapred.TextInputFormat",
                "OutputFormat": "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
                "SerdeInfo": {
                    "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
                },
            },
            "TableType": "EXTERNAL_TABLE",
        }

        if metadata and metadata.description:
            table_input["Description"] = metadata.description

        # Add custom properties as parameters
        if metadata and metadata.custom_properties:
            table_input["Parameters"] = {}
            for key, value in metadata.custom_properties.items():
                table_input["Parameters"][f"custom.{key}"] = str(value)

        try:
            self.glue_client.create_table(DatabaseName=db_name, TableInput=table_input)
        except ClientError as e:
            raise Exception(f"Failed to create table in AWS Glue: {e}") from e

    def push_metadata(
        self, table_name: str, metadata: CatalogMetadata, location: Optional[str] = None
    ) -> None:
        """Push metadata to AWS Glue."""
        db_name = self.database_name

        try:
            # Get existing table
            table_response = self.glue_client.get_table(DatabaseName=db_name, Name=table_name)
            table_input = table_response["Table"]

            # Update metadata
            if metadata.description:
                table_input["Description"] = metadata.description

            # Add tags as parameters
            if metadata.tags:
                if "Parameters" not in table_input:
                    table_input["Parameters"] = {}
                table_input["Parameters"]["tags"] = ",".join(metadata.tags)

            # Add custom properties as parameters
            if metadata.custom_properties:
                if "Parameters" not in table_input:
                    table_input["Parameters"] = {}
                for key, value in metadata.custom_properties.items():
                    table_input["Parameters"][f"custom.{key}"] = str(value)

            # Update table
            self.glue_client.update_table(
                DatabaseName=db_name, TableInput=table_input
            )

        except ClientError as e:
            if e.response["Error"]["Code"] == "EntityNotFoundException":
                # Table doesn't exist, create it
                self.create_table_if_not_exists(
                    table_name, metadata.schema or [], location, metadata
                )
            else:
                raise Exception(f"Failed to update table metadata in AWS Glue: {e}") from e

    def push_lineage(self, lineage: CatalogLineage) -> None:
        """Push lineage information to AWS Glue."""
        # AWS Glue doesn't have native lineage support
        # We can store lineage information as table parameters
        target_table = lineage.target_entity.get("table", "")
        target_db = lineage.target_entity.get("database", self.database_name)

        try:
            table_response = self.glue_client.get_table(
                DatabaseName=target_db, Name=target_table
            )
            table_input = table_response["Table"]

            if "Parameters" not in table_input:
                table_input["Parameters"] = {}

            # Store lineage as JSON in parameters
            lineage_data = {
                "process_name": lineage.process_name,
                "process_type": lineage.process_type,
                "sources": lineage.source_entities,
            }
            table_input["Parameters"]["lineage"] = json.dumps(lineage_data)

            self.glue_client.update_table(
                DatabaseName=target_db, TableInput=table_input
            )

        except ClientError as e:
            raise Exception(f"Failed to push lineage to AWS Glue: {e}") from e

    def _map_data_type(self, data_type: str) -> str:
        """Map common data types to AWS Glue types."""
        type_mapping = {
            "string": "string",
            "varchar": "string",
            "text": "string",
            "int": "int",
            "integer": "int",
            "bigint": "bigint",
            "float": "float",
            "double": "double",
            "decimal": "decimal",
            "boolean": "boolean",
            "date": "date",
            "timestamp": "timestamp",
            "array": "array<string>",
            "struct": "struct",
            "map": "map<string,string>",
        }
        return type_mapping.get(data_type.lower(), "string")
