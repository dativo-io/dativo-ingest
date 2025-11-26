"""AWS Glue catalog integration for lineage and metadata push."""

import os
from typing import Any, Dict, List, Optional

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = Exception

from ..config import AssetDefinition, CatalogConfig, JobConfig
from .base import BaseCatalog


class AWSGlueCatalog(BaseCatalog):
    """AWS Glue catalog integration."""

    def __init__(
        self,
        catalog_config: CatalogConfig,
        asset_definition: AssetDefinition,
        job_config: JobConfig,
    ):
        """Initialize AWS Glue catalog client.

        Args:
            catalog_config: Catalog configuration
            asset_definition: Asset definition
            job_config: Job configuration
        """
        super().__init__(catalog_config, asset_definition, job_config)

        if boto3 is None:
            raise ImportError(
                "boto3 is required for AWS Glue integration. Install with: pip install boto3"
            )

        connection = catalog_config.connection
        self.region = connection.get("region") or os.getenv("AWS_REGION", "us-east-1")
        self.aws_access_key_id = connection.get("aws_access_key_id") or os.getenv(
            "AWS_ACCESS_KEY_ID"
        )
        self.aws_secret_access_key = connection.get("aws_secret_access_key") or os.getenv(
            "AWS_SECRET_ACCESS_KEY"
        )

        # Create Glue client
        self.glue_client = boto3.client(
            "glue",
            region_name=self.region,
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
        )

    def ensure_entity_exists(
        self,
        entity: Dict[str, Any],
        schema: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Ensure table exists in AWS Glue, create if needed.

        Args:
            entity: Entity dictionary
            schema: Optional schema definition

        Returns:
            Entity information dictionary
        """
        database = entity.get("database") or self.catalog_config.database or "default"
        table_name = entity.get("name") or self.asset_definition.name
        location = entity.get("location", "")

        # Ensure database exists
        try:
            self.glue_client.get_database(Name=database)
        except ClientError as e:
            if e.response["Error"]["Code"] == "EntityNotFoundException":
                # Create database
                self.glue_client.create_database(
                    DatabaseInput={"Name": database, "Description": f"Database for {database}"}
                )

        # Check if table exists
        try:
            response = self.glue_client.get_table(DatabaseName=database, Name=table_name)
            return {
                "entity_id": response["Table"]["Name"],
                "database": database,
                "table": table_name,
            }
        except ClientError as e:
            if e.response["Error"]["Code"] != "EntityNotFoundException":
                raise

        # Create table
        table_input = {
            "Name": table_name,
            "StorageDescriptor": {
                "Location": location,
                "InputFormat": "org.apache.hadoop.mapred.TextInputFormat",
                "OutputFormat": "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
                "SerdeInfo": {
                    "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
                },
            },
            "TableType": "EXTERNAL_TABLE",
        }

        # Add columns if schema provided
        if schema:
            columns = []
            for field in schema:
                columns.append(
                    {
                        "Name": field.get("name"),
                        "Type": self._map_type_to_glue(field.get("type", "string")),
                        "Comment": field.get("description", ""),
                    }
                )
            table_input["StorageDescriptor"]["Columns"] = columns

        # Add parameters for metadata
        parameters = {}
        if self.asset_definition.domain:
            parameters["domain"] = self.asset_definition.domain
        if hasattr(self.asset_definition, "dataProduct") and self.asset_definition.dataProduct:
            parameters["data_product"] = self.asset_definition.dataProduct
        if self.asset_definition.team and self.asset_definition.team.owner:
            parameters["owner"] = self.asset_definition.team.owner

        table_input["Parameters"] = parameters

        try:
            self.glue_client.create_table(DatabaseName=database, TableInput=table_input)
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to create Glue table: {e}")

        return {"database": database, "table": table_name}

    def _map_type_to_glue(self, field_type: str) -> str:
        """Map field type to Glue data type.

        Args:
            field_type: Field type string

        Returns:
            Glue data type
        """
        type_mapping = {
            "string": "string",
            "integer": "bigint",
            "float": "float",
            "double": "double",
            "boolean": "boolean",
            "timestamp": "timestamp",
            "datetime": "timestamp",
            "date": "date",
        }
        return type_mapping.get(field_type.lower(), "string")

    def push_metadata(
        self,
        entity: Dict[str, Any],
        tags: Optional[List[str]] = None,
        owners: Optional[List[str]] = None,
        description: Optional[str] = None,
        custom_properties: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Push metadata to AWS Glue.

        Args:
            entity: Entity dictionary
            tags: List of tags
            owners: List of owners
            description: Description
            custom_properties: Custom properties

        Returns:
            Push result dictionary
        """
        database = entity.get("database") or self.catalog_config.database or "default"
        table_name = entity.get("name") or self.asset_definition.name

        try:
            # Get existing table
            response = self.glue_client.get_table(DatabaseName=database, Name=table_name)
            table_input = response["Table"]

            # Update description
            if description:
                table_input["Description"] = description

            # Update parameters (tags and custom properties)
            parameters = table_input.get("Parameters", {})
            if tags:
                parameters["tags"] = ",".join(tags)
            if owners:
                parameters["owners"] = ",".join(owners)
            if custom_properties:
                parameters.update(custom_properties)

            table_input["Parameters"] = parameters

            # Update table
            self.glue_client.update_table(
                DatabaseName=database, TableInput=table_input
            )

            return {"status": "success", "database": database, "table": table_name}
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to update Glue table metadata: {e}")
            return {"status": "error", "message": str(e)}

    def push_lineage(
        self,
        source_entities: List[Dict[str, Any]],
        target_entity: Dict[str, Any],
        operation: str = "ingest",
    ) -> Dict[str, Any]:
        """Push lineage to AWS Glue (via table parameters).

        Note: AWS Glue doesn't have native lineage support, so we store lineage
        information in table parameters.

        Args:
            source_entities: List of source entities
            target_entity: Target entity
            operation: Operation type

        Returns:
            Lineage push result
        """
        database = target_entity.get("database") or self.catalog_config.database or "default"
        table_name = target_entity.get("name") or self.asset_definition.name

        try:
            response = self.glue_client.get_table(DatabaseName=database, Name=table_name)
            table_input = response["Table"]

            # Store lineage in parameters
            parameters = table_input.get("Parameters", {})
            source_names = [e.get("name") or e.get("location", "") for e in source_entities]
            parameters["lineage_sources"] = ",".join(source_names)
            parameters["lineage_operation"] = operation

            table_input["Parameters"] = parameters

            self.glue_client.update_table(DatabaseName=database, TableInput=table_input)

            return {"status": "success", "sources_count": len(source_entities)}
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to push Glue lineage: {e}")
            return {"status": "error", "message": str(e)}
