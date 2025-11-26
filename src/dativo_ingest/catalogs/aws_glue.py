"""AWS Glue Data Catalog integration."""

import logging
import os
from typing import Any, Dict, List, Optional

from .base import BaseCatalogClient, CatalogConfig, LineageInfo

logger = logging.getLogger(__name__)


class GlueCatalogClient(BaseCatalogClient):
    """AWS Glue Data Catalog client."""
    
    def __init__(self, config: CatalogConfig):
        """Initialize Glue catalog client.
        
        Args:
            config: Catalog configuration
        """
        super().__init__(config)
        self._client = None
    
    def _validate_config(self) -> None:
        """Validate Glue-specific configuration."""
        if not self.config.aws_region:
            # Try to get from environment
            self.config.aws_region = os.getenv("AWS_REGION", "us-east-1")
        
        if not self.config.aws_account_id:
            # Optional - will use default account if not specified
            self.config.aws_account_id = os.getenv("AWS_ACCOUNT_ID")
    
    def _get_client(self):
        """Get or create Glue client."""
        if self._client is None:
            try:
                import boto3
            except ImportError:
                raise ImportError(
                    "boto3 is required for AWS Glue integration. "
                    "Install with: pip install boto3"
                )
            
            self._client = boto3.client(
                "glue",
                region_name=self.config.aws_region,
            )
        return self._client
    
    def register_dataset(
        self,
        dataset_name: str,
        schema: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Register or update a table in AWS Glue Data Catalog.
        
        Args:
            dataset_name: Table name (format: "database.table")
            schema: List of field definitions
            metadata: Additional metadata (tags, owner, description, etc.)
        
        Returns:
            Dictionary with registration result
        """
        client = self._get_client()
        metadata = metadata or {}
        
        # Parse dataset name
        parts = dataset_name.split(".")
        if len(parts) >= 2:
            database_name = parts[0]
            table_name = ".".join(parts[1:])
        else:
            database_name = "default"
            table_name = dataset_name
        
        # Convert schema to Glue format
        glue_columns = []
        for field in schema:
            column = {
                "Name": field.get("name", ""),
                "Type": self._map_type_to_glue(field.get("type", "string")),
            }
            if field.get("description"):
                column["Comment"] = field["description"]
            glue_columns.append(column)
        
        # Build table input
        table_input = {
            "Name": table_name,
            "StorageDescriptor": {
                "Columns": glue_columns,
                "Location": metadata.get("location", ""),
                "InputFormat": metadata.get("input_format", "org.apache.hadoop.mapred.TextInputFormat"),
                "OutputFormat": metadata.get("output_format", "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"),
                "SerdeInfo": {
                    "SerializationLibrary": metadata.get(
                        "serde_library",
                        "org.apache.hadoop.hive.serde2.lazy.LazySimpleSerDe"
                    ),
                },
            },
            "PartitionKeys": metadata.get("partition_keys", []),
        }
        
        # Add description
        if metadata.get("description"):
            table_input["Description"] = metadata["description"]
        
        # Add parameters (custom metadata)
        parameters = {}
        if metadata.get("owner"):
            parameters["owner"] = metadata["owner"]
        if metadata.get("team"):
            parameters["team"] = metadata["team"]
        if metadata.get("classification"):
            parameters["classification"] = ",".join(metadata["classification"]) if isinstance(metadata["classification"], list) else metadata["classification"]
        if metadata.get("custom_metadata"):
            parameters.update(metadata["custom_metadata"])
        
        if parameters:
            table_input["Parameters"] = parameters
        
        # Ensure database exists
        self._ensure_database_exists(database_name)
        
        # Try to update existing table, create if doesn't exist
        try:
            client.update_table(
                DatabaseName=database_name,
                TableInput=table_input,
            )
            action = "updated"
        except client.exceptions.EntityNotFoundException:
            client.create_table(
                DatabaseName=database_name,
                TableInput=table_input,
            )
            action = "created"
        
        # Add tags if provided
        if metadata.get("tags") and self.config.push_metadata:
            self._add_tags(database_name, table_name, metadata["tags"])
        
        logger.info(f"Successfully {action} Glue table: {database_name}.{table_name}")
        
        return {
            "status": "success",
            "action": action,
            "database": database_name,
            "table": table_name,
            "catalog": "glue",
        }
    
    def publish_lineage(
        self,
        lineage_info: LineageInfo,
    ) -> Dict[str, Any]:
        """Publish lineage information to AWS Glue.
        
        Note: AWS Glue doesn't have native lineage API. This stores lineage
        information as table parameters and CloudWatch events.
        
        Args:
            lineage_info: Lineage information
        
        Returns:
            Dictionary with lineage publication result
        """
        if not self.config.push_lineage:
            return {"status": "skipped", "reason": "lineage push disabled"}
        
        # Store lineage as table parameters
        parts = lineage_info.target_dataset.split(".")
        if len(parts) >= 2:
            database_name = parts[0]
            table_name = ".".join(parts[1:])
        else:
            database_name = "default"
            table_name = lineage_info.target_dataset
        
        lineage_params = {
            "lineage.source_type": lineage_info.source_type,
            "lineage.pipeline_name": lineage_info.pipeline_name,
            "lineage.execution_time": lineage_info.execution_time.isoformat(),
        }
        
        if lineage_info.source_name:
            lineage_params["lineage.source_name"] = lineage_info.source_name
        if lineage_info.source_dataset:
            lineage_params["lineage.source_dataset"] = lineage_info.source_dataset
        if lineage_info.records_processed:
            lineage_params["lineage.records_processed"] = str(lineage_info.records_processed)
        
        try:
            client = self._get_client()
            
            # Get current table
            response = client.get_table(
                DatabaseName=database_name,
                Name=table_name,
            )
            
            table = response["Table"]
            table_input = {
                "Name": table["Name"],
                "StorageDescriptor": table["StorageDescriptor"],
            }
            
            # Merge lineage parameters
            current_params = table.get("Parameters", {})
            current_params.update(lineage_params)
            table_input["Parameters"] = current_params
            
            if "Description" in table:
                table_input["Description"] = table["Description"]
            if "PartitionKeys" in table:
                table_input["PartitionKeys"] = table["PartitionKeys"]
            
            # Update table
            client.update_table(
                DatabaseName=database_name,
                TableInput=table_input,
            )
            
            logger.info(f"Published lineage to Glue table: {database_name}.{table_name}")
            
            return {
                "status": "success",
                "database": database_name,
                "table": table_name,
                "lineage_params": lineage_params,
            }
        except Exception as e:
            logger.error(f"Failed to publish lineage to Glue: {e}")
            return {
                "status": "failed",
                "error": str(e),
            }
    
    def update_metadata(
        self,
        dataset_name: str,
        tags: Optional[List[str]] = None,
        owner: Optional[str] = None,
        classification: Optional[List[str]] = None,
        custom_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Update dataset metadata in Glue catalog.
        
        Args:
            dataset_name: Fully qualified table name
            tags: List of tags
            owner: Owner email/username
            classification: Data classification labels
            custom_metadata: Additional metadata
        
        Returns:
            Dictionary with update result
        """
        if not self.config.push_metadata:
            return {"status": "skipped", "reason": "metadata push disabled"}
        
        client = self._get_client()
        
        # Parse dataset name
        parts = dataset_name.split(".")
        if len(parts) >= 2:
            database_name = parts[0]
            table_name = ".".join(parts[1:])
        else:
            database_name = "default"
            table_name = dataset_name
        
        try:
            # Get current table
            response = client.get_table(
                DatabaseName=database_name,
                Name=table_name,
            )
            
            table = response["Table"]
            table_input = {
                "Name": table["Name"],
                "StorageDescriptor": table["StorageDescriptor"],
            }
            
            # Update parameters
            current_params = table.get("Parameters", {})
            
            if owner:
                current_params["owner"] = owner
            if classification:
                current_params["classification"] = ",".join(classification) if isinstance(classification, list) else classification
            if custom_metadata:
                current_params.update(custom_metadata)
            
            table_input["Parameters"] = current_params
            
            if "Description" in table:
                table_input["Description"] = table["Description"]
            if "PartitionKeys" in table:
                table_input["PartitionKeys"] = table["PartitionKeys"]
            
            # Update table
            client.update_table(
                DatabaseName=database_name,
                TableInput=table_input,
            )
            
            # Add tags
            if tags:
                self._add_tags(database_name, table_name, tags)
            
            logger.info(f"Updated metadata for Glue table: {database_name}.{table_name}")
            
            return {
                "status": "success",
                "database": database_name,
                "table": table_name,
            }
        except Exception as e:
            logger.error(f"Failed to update metadata in Glue: {e}")
            return {
                "status": "failed",
                "error": str(e),
            }
    
    def test_connection(self) -> bool:
        """Test connection to AWS Glue.
        
        Returns:
            True if connection successful
        """
        try:
            client = self._get_client()
            # Try to list databases to test connection
            client.get_databases(MaxResults=1)
            logger.info("Successfully connected to AWS Glue")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to AWS Glue: {e}")
            return False
    
    def _ensure_database_exists(self, database_name: str) -> None:
        """Ensure Glue database exists, create if it doesn't.
        
        Args:
            database_name: Database name
        """
        client = self._get_client()
        
        try:
            client.get_database(Name=database_name)
        except client.exceptions.EntityNotFoundException:
            # Create database
            client.create_database(
                DatabaseInput={
                    "Name": database_name,
                    "Description": f"Database created by Dativo ingestion platform",
                }
            )
            logger.info(f"Created Glue database: {database_name}")
    
    def _add_tags(self, database_name: str, table_name: str, tags: List[str]) -> None:
        """Add tags to Glue table.
        
        Args:
            database_name: Database name
            table_name: Table name
            tags: List of tags (key=value format)
        """
        client = self._get_client()
        
        # Build ARN for table
        account_id = self.config.aws_account_id
        if not account_id:
            # Try to get from STS
            try:
                import boto3
                sts = boto3.client("sts")
                account_id = sts.get_caller_identity()["Account"]
            except Exception:
                logger.warning("Could not determine AWS account ID, skipping tags")
                return
        
        table_arn = f"arn:aws:glue:{self.config.aws_region}:{account_id}:table/{database_name}/{table_name}"
        
        # Convert tags to Glue format
        tag_dict = {}
        for tag in tags:
            if "=" in tag:
                key, value = tag.split("=", 1)
                tag_dict[key] = value
            else:
                tag_dict[tag] = "true"
        
        try:
            client.tag_resource(
                ResourceArn=table_arn,
                TagsToAdd=tag_dict,
            )
        except Exception as e:
            logger.warning(f"Failed to add tags to Glue table: {e}")
    
    def _map_type_to_glue(self, field_type: str) -> str:
        """Map field type to Glue type.
        
        Args:
            field_type: Field type from asset definition
        
        Returns:
            Glue data type string
        """
        type_mapping = {
            "string": "string",
            "integer": "bigint",
            "long": "bigint",
            "float": "double",
            "double": "double",
            "boolean": "boolean",
            "date": "date",
            "timestamp": "timestamp",
            "datetime": "timestamp",
            "array": "array<string>",
            "object": "struct",
        }
        return type_mapping.get(field_type.lower(), "string")
