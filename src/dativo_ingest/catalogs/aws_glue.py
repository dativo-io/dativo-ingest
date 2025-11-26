"""AWS Glue catalog integration for lineage and metadata tracking."""

import logging
from typing import Any, Dict, List, Optional

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = None

from .base import BaseCatalog

logger = logging.getLogger(__name__)


class AWSGlueCatalog(BaseCatalog):
    """AWS Glue catalog integration."""

    def __init__(self, *args, **kwargs):
        """Initialize AWS Glue catalog client."""
        super().__init__(*args, **kwargs)
        if boto3 is None:
            raise ImportError("boto3 is required for AWS Glue integration")

        self.region = self.catalog_config.get("region") or "us-east-1"
        self.aws_access_key_id = self.catalog_config.get("aws_access_key_id")
        self.aws_secret_access_key = self.catalog_config.get("aws_secret_access_key")

        self.glue_client = boto3.client(
            "glue",
            region_name=self.region,
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
        )

    def ensure_entity_exists(
        self,
        entity: Dict[str, Any],
        schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Ensure table exists in AWS Glue."""
        database_name = entity.get("database", "default")
        table_name = entity.get("name")

        # Ensure database exists
        try:
            self.glue_client.get_database(Name=database_name)
        except ClientError as e:
            if e.response["Error"]["Code"] == "EntityNotFoundException":
                # Create database
                self.glue_client.create_database(
                    DatabaseInput={
                        "Name": database_name,
                        "Description": f"Database for {database_name} domain",
                    }
                )
            else:
                raise

        # Check if table exists
        try:
            response = self.glue_client.get_table(DatabaseName=database_name, Name=table_name)
            return response["Table"]
        except ClientError as e:
            if e.response["Error"]["Code"] == "EntityNotFoundException":
                # Create table
                columns = self._convert_schema_to_glue_columns()
                table_input = {
                    "Name": table_name,
                    "StorageDescriptor": {
                        "Columns": columns,
                        "Location": entity.get("path", ""),
                        "InputFormat": "org.apache.hadoop.mapred.TextInputFormat",
                        "OutputFormat": "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
                        "SerdeInfo": {
                            "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
                        },
                    },
                    "Parameters": {},
                }

                # Add description
                if self.asset_definition.description and self.asset_definition.description.purpose:
                    table_input["Description"] = self.asset_definition.description.purpose

                self.glue_client.create_table(
                    DatabaseName=database_name, TableInput=table_input
                )
                return self.glue_client.get_table(DatabaseName=database_name, Name=table_name)[
                    "Table"
                ]
            else:
                raise

    def _convert_schema_to_glue_columns(self) -> List[Dict[str, Any]]:
        """Convert asset schema to AWS Glue column format."""
        columns = []
        for field_def in self.asset_definition.schema:
            field_type = field_def.get("type", "string")
            # Map to Glue data types
            type_map = {
                "string": "string",
                "integer": "bigint",
                "float": "float",
                "double": "double",
                "boolean": "boolean",
                "timestamp": "timestamp",
                "datetime": "timestamp",
                "date": "date",
            }
            glue_type = type_map.get(field_type, "string")

            columns.append(
                {
                    "Name": field_def["name"],
                    "Type": glue_type,
                    "Comment": field_def.get("description", ""),
                }
            )
        return columns

    def push_metadata(
        self,
        entity: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Push metadata to AWS Glue table."""
        database_name = entity.get("database", "default")
        table_name = entity.get("name")

        try:
            # Get existing table
            table = self.glue_client.get_table(DatabaseName=database_name, Name=table_name)["Table"]

            # Update table parameters with metadata
            parameters = table.get("Parameters", {})
            if metadata.get("description"):
                table["Description"] = metadata["description"]

            # Add tags as parameters
            if metadata.get("tags"):
                for idx, tag in enumerate(metadata["tags"][:10]):  # Glue limits parameters
                    parameters[f"tag_{idx}"] = tag

            # Add owners
            if metadata.get("owners"):
                parameters["owners"] = ",".join(metadata["owners"])

            # Update table
            table_input = {
                "Name": table["Name"],
                "StorageDescriptor": table["StorageDescriptor"],
                "Parameters": parameters,
            }
            if "Description" in table:
                table_input["Description"] = table["Description"]

            self.glue_client.update_table(
                DatabaseName=database_name, TableInput=table_input
            )

            return {"status": "success", "database": database_name, "table": table_name}
        except ClientError as e:
            logger.error(f"Failed to update Glue table metadata: {e}")
            return {"status": "error", "error": str(e)}

    def push_lineage(
        self,
        source_entities: List[Dict[str, Any]],
        target_entity: Dict[str, Any],
        operation: str = "ingest",
    ) -> Dict[str, Any]:
        """Push lineage to AWS Glue (via table parameters)."""
        # AWS Glue doesn't have native lineage API, so we store lineage info in table parameters
        database_name = target_entity.get("database", "default")
        table_name = target_entity.get("name")

        try:
            table = self.glue_client.get_table(DatabaseName=database_name, Name=table_name)["Table"]
            parameters = table.get("Parameters", {})

            # Store lineage as JSON in parameters
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

            parameters["lineage"] = json.dumps(lineage_info)

            table_input = {
                "Name": table["Name"],
                "StorageDescriptor": table["StorageDescriptor"],
                "Parameters": parameters,
            }
            if "Description" in table:
                table_input["Description"] = table["Description"]

            self.glue_client.update_table(
                DatabaseName=database_name, TableInput=table_input
            )

            return {"status": "success", "sources": len(source_entities)}
        except ClientError as e:
            logger.error(f"Failed to push lineage to Glue: {e}")
            return {"status": "error", "error": str(e)}
