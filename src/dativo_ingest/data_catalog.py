"""Data catalog integration for lineage and metadata management.

Supports multiple data catalog systems:
- AWS Glue Data Catalog
- Databricks Unity Catalog
- Nessie Catalog
- OpenMetadata
"""

import abc
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from .config import AssetDefinition


logger = logging.getLogger(__name__)


class CatalogLineage:
    """Represents lineage information for a data pipeline."""

    def __init__(
        self,
        source_type: str,
        source_object: str,
        target_table: str,
        target_database: str,
        job_id: str,
        tenant_id: str,
        execution_time: Optional[datetime] = None,
        upstream_tables: Optional[List[str]] = None,
        downstream_tables: Optional[List[str]] = None,
        records_written: int = 0,
        files_written: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Initialize lineage information.

        Args:
            source_type: Source connector type (e.g., 'stripe', 'postgres')
            source_object: Source object name (e.g., 'customers', 'orders')
            target_table: Target table name
            target_database: Target database/catalog name
            job_id: Unique job identifier
            tenant_id: Tenant identifier
            execution_time: Job execution time
            upstream_tables: List of upstream tables
            downstream_tables: List of downstream tables
            records_written: Number of records written
            files_written: Number of files written
            metadata: Additional metadata
        """
        self.source_type = source_type
        self.source_object = source_object
        self.target_table = target_table
        self.target_database = target_database
        self.job_id = job_id
        self.tenant_id = tenant_id
        self.execution_time = execution_time or datetime.utcnow()
        self.upstream_tables = upstream_tables or []
        self.downstream_tables = downstream_tables or []
        self.records_written = records_written
        self.files_written = files_written
        self.metadata = metadata or {}


class BaseCatalogClient(abc.ABC):
    """Base class for data catalog clients."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize catalog client.

        Args:
            config: Catalog-specific configuration
        """
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abc.abstractmethod
    def create_or_update_table(
        self,
        database: str,
        table_name: str,
        schema: List[Dict[str, Any]],
        location: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create or update table in catalog.

        Args:
            database: Database/catalog name
            table_name: Table name
            schema: Table schema definition
            location: Storage location (S3 path, etc.)
            metadata: Additional metadata

        Returns:
            Result dictionary with table information
        """
        pass

    @abc.abstractmethod
    def push_lineage(self, lineage: CatalogLineage) -> Dict[str, Any]:
        """Push lineage information to catalog.

        Args:
            lineage: Lineage information

        Returns:
            Result dictionary with lineage push status
        """
        pass

    @abc.abstractmethod
    def add_tags(
        self, database: str, table_name: str, tags: Dict[str, str]
    ) -> Dict[str, Any]:
        """Add tags to table in catalog.

        Args:
            database: Database/catalog name
            table_name: Table name
            tags: Tags to add (key-value pairs)

        Returns:
            Result dictionary with tag update status
        """
        pass

    @abc.abstractmethod
    def add_owners(
        self, database: str, table_name: str, owners: List[str]
    ) -> Dict[str, Any]:
        """Add owners to table in catalog.

        Args:
            database: Database/catalog name
            table_name: Table name
            owners: List of owner identifiers

        Returns:
            Result dictionary with owner update status
        """
        pass

    def _expand_env_vars(self, value: str) -> str:
        """Expand environment variables in string.

        Args:
            value: String with environment variables

        Returns:
            Expanded string
        """
        if isinstance(value, str) and "${" in value:
            return os.path.expandvars(value)
        return value


class AWSGlueCatalogClient(BaseCatalogClient):
    """AWS Glue Data Catalog client."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize AWS Glue client.

        Args:
            config: Glue-specific configuration
                - region: AWS region
                - database: Database name
                - Additional boto3 parameters
        """
        super().__init__(config)
        self.region = config.get("region") or os.getenv("AWS_REGION", "us-east-1")
        self.database = config.get("database", "default")

        try:
            import boto3

            self.glue_client = boto3.client("glue", region_name=self.region)
        except ImportError:
            raise ImportError(
                "boto3 is required for AWS Glue integration. Install with: pip install boto3"
            )

    def create_or_update_table(
        self,
        database: str,
        table_name: str,
        schema: List[Dict[str, Any]],
        location: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create or update table in AWS Glue Data Catalog.

        Args:
            database: Glue database name
            table_name: Table name
            schema: Table schema
            location: S3 location
            metadata: Additional metadata

        Returns:
            Result dictionary
        """
        metadata = metadata or {}

        # Convert schema to Glue format
        glue_columns = []
        for field in schema:
            glue_type = self._map_to_glue_type(field.get("type", "string"))
            glue_columns.append(
                {
                    "Name": field["name"],
                    "Type": glue_type,
                    "Comment": field.get("description", ""),
                }
            )

        # Build table input
        table_input = {
            "Name": table_name,
            "StorageDescriptor": {
                "Columns": glue_columns,
                "Location": location,
                "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
                "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
                "SerdeInfo": {
                    "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
                },
            },
            "Parameters": {
                "classification": "parquet",
                "ingest_timestamp": datetime.utcnow().isoformat(),
                **{k: str(v) for k, v in metadata.items()},
            },
        }

        # Add description if available
        if metadata.get("description"):
            table_input["Description"] = metadata["description"]

        # Try to update existing table, create if doesn't exist
        try:
            self.glue_client.update_table(
                DatabaseName=database, TableInput=table_input
            )
            self.logger.info(f"Updated table {database}.{table_name} in AWS Glue")
            return {"status": "updated", "database": database, "table": table_name}
        except self.glue_client.exceptions.EntityNotFoundException:
            # Table doesn't exist, create it
            self.glue_client.create_table(
                DatabaseName=database, TableInput=table_input
            )
            self.logger.info(f"Created table {database}.{table_name} in AWS Glue")
            return {"status": "created", "database": database, "table": table_name}

    def push_lineage(self, lineage: CatalogLineage) -> Dict[str, Any]:
        """Push lineage to AWS Glue.

        Note: AWS Glue doesn't have native lineage tracking.
        We store lineage information in table parameters.

        Args:
            lineage: Lineage information

        Returns:
            Result dictionary
        """
        try:
            # Get current table
            response = self.glue_client.get_table(
                DatabaseName=lineage.target_database, Name=lineage.target_table
            )
            table = response["Table"]

            # Update parameters with lineage info
            parameters = table.get("Parameters", {})
            parameters.update(
                {
                    "source_type": lineage.source_type,
                    "source_object": lineage.source_object,
                    "job_id": lineage.job_id,
                    "last_execution": lineage.execution_time.isoformat(),
                    "records_written": str(lineage.records_written),
                    "files_written": str(lineage.files_written),
                }
            )

            if lineage.upstream_tables:
                parameters["upstream_tables"] = ",".join(lineage.upstream_tables)

            # Update table
            table_input = {
                "Name": table["Name"],
                "StorageDescriptor": table["StorageDescriptor"],
                "Parameters": parameters,
            }

            if "Description" in table:
                table_input["Description"] = table["Description"]

            self.glue_client.update_table(
                DatabaseName=lineage.target_database, TableInput=table_input
            )

            self.logger.info(
                f"Pushed lineage to AWS Glue for {lineage.target_database}.{lineage.target_table}"
            )
            return {"status": "success", "lineage_pushed": True}
        except Exception as e:
            self.logger.error(f"Failed to push lineage to AWS Glue: {e}")
            return {"status": "error", "error": str(e)}

    def add_tags(
        self, database: str, table_name: str, tags: Dict[str, str]
    ) -> Dict[str, Any]:
        """Add tags to table in AWS Glue.

        Args:
            database: Database name
            table_name: Table name
            tags: Tags to add

        Returns:
            Result dictionary
        """
        try:
            # Get table ARN
            response = self.glue_client.get_table(
                DatabaseName=database, Name=table_name
            )
            # Construct table ARN (Glue doesn't return ARN in get_table)
            account_id = os.getenv("AWS_ACCOUNT_ID", "123456789012")
            table_arn = f"arn:aws:glue:{self.region}:{account_id}:table/{database}/{table_name}"

            # Add tags
            self.glue_client.tag_resource(ResourceArn=table_arn, TagsToAdd=tags)

            self.logger.info(f"Added {len(tags)} tags to {database}.{table_name}")
            return {"status": "success", "tags_added": len(tags)}
        except Exception as e:
            self.logger.error(f"Failed to add tags to AWS Glue: {e}")
            return {"status": "error", "error": str(e)}

    def add_owners(
        self, database: str, table_name: str, owners: List[str]
    ) -> Dict[str, Any]:
        """Add owners to table in AWS Glue.

        Note: AWS Glue doesn't have native owner support.
        We store owners in table parameters.

        Args:
            database: Database name
            table_name: Table name
            owners: List of owners

        Returns:
            Result dictionary
        """
        try:
            # Get current table
            response = self.glue_client.get_table(
                DatabaseName=database, Name=table_name
            )
            table = response["Table"]

            # Update parameters with owners
            parameters = table.get("Parameters", {})
            parameters["owners"] = ",".join(owners)

            # Update table
            table_input = {
                "Name": table["Name"],
                "StorageDescriptor": table["StorageDescriptor"],
                "Parameters": parameters,
            }

            if "Description" in table:
                table_input["Description"] = table["Description"]

            self.glue_client.update_table(
                DatabaseName=database, TableInput=table_input
            )

            self.logger.info(f"Added {len(owners)} owners to {database}.{table_name}")
            return {"status": "success", "owners_added": len(owners)}
        except Exception as e:
            self.logger.error(f"Failed to add owners to AWS Glue: {e}")
            return {"status": "error", "error": str(e)}

    def _map_to_glue_type(self, dativo_type: str) -> str:
        """Map Dativo type to AWS Glue type.

        Args:
            dativo_type: Dativo type

        Returns:
            Glue type
        """
        type_mapping = {
            "string": "string",
            "integer": "bigint",
            "float": "double",
            "double": "double",
            "boolean": "boolean",
            "timestamp": "timestamp",
            "datetime": "timestamp",
            "date": "date",
        }
        return type_mapping.get(dativo_type, "string")


class DatabricksUnityCatalogClient(BaseCatalogClient):
    """Databricks Unity Catalog client."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize Databricks Unity Catalog client.

        Args:
            config: Unity Catalog configuration
                - workspace_url: Databricks workspace URL
                - token: Personal access token
                - catalog: Catalog name
        """
        super().__init__(config)
        self.workspace_url = self._expand_env_vars(
            config.get("workspace_url") or os.getenv("DATABRICKS_WORKSPACE_URL", "")
        )
        self.token = self._expand_env_vars(
            config.get("token") or os.getenv("DATABRICKS_TOKEN", "")
        )
        self.catalog = config.get("catalog", "main")

        if not self.workspace_url or not self.token:
            raise ValueError(
                "workspace_url and token are required for Databricks Unity Catalog"
            )

        # Initialize HTTP session
        import requests

        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        )
        self.api_base = f"{self.workspace_url}/api/2.1/unity-catalog"

    def create_or_update_table(
        self,
        database: str,
        table_name: str,
        schema: List[Dict[str, Any]],
        location: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create or update table in Unity Catalog.

        Args:
            database: Schema name
            table_name: Table name
            schema: Table schema
            location: Storage location
            metadata: Additional metadata

        Returns:
            Result dictionary
        """
        metadata = metadata or {}

        # Convert schema to Unity Catalog format
        columns = []
        for field in schema:
            uc_type = self._map_to_unity_type(field.get("type", "string"))
            columns.append(
                {
                    "name": field["name"],
                    "type_text": uc_type,
                    "type_name": uc_type.upper(),
                    "position": len(columns),
                    "nullable": not field.get("required", False),
                    "comment": field.get("description", ""),
                }
            )

        # Build table request
        table_request = {
            "catalog_name": self.catalog,
            "schema_name": database,
            "name": table_name,
            "table_type": "EXTERNAL",
            "data_source_format": "PARQUET",
            "storage_location": location,
            "columns": columns,
            "properties": {
                "ingest_timestamp": datetime.utcnow().isoformat(),
                **{k: str(v) for k, v in metadata.items()},
            },
        }

        if metadata.get("description"):
            table_request["comment"] = metadata["description"]

        # Try to update, create if doesn't exist
        full_table_name = f"{self.catalog}.{database}.{table_name}"
        try:
            response = self.session.get(f"{self.api_base}/tables/{full_table_name}")
            if response.status_code == 200:
                # Table exists, update it
                response = self.session.patch(
                    f"{self.api_base}/tables/{full_table_name}", json=table_request
                )
                response.raise_for_status()
                self.logger.info(f"Updated table {full_table_name} in Unity Catalog")
                return {"status": "updated", "table": full_table_name}
        except Exception:
            pass

        # Create new table
        response = self.session.post(f"{self.api_base}/tables", json=table_request)
        response.raise_for_status()
        self.logger.info(f"Created table {full_table_name} in Unity Catalog")
        return {"status": "created", "table": full_table_name}

    def push_lineage(self, lineage: CatalogLineage) -> Dict[str, Any]:
        """Push lineage to Unity Catalog.

        Args:
            lineage: Lineage information

        Returns:
            Result dictionary
        """
        try:
            full_table_name = (
                f"{self.catalog}.{lineage.target_database}.{lineage.target_table}"
            )

            # Unity Catalog lineage API
            lineage_request = {
                "table_name": full_table_name,
                "upstream_tables": [
                    {"table_name": t} for t in lineage.upstream_tables
                ],
                "notebook_id": lineage.job_id,
                "execution_time": lineage.execution_time.isoformat(),
            }

            response = self.session.post(
                f"{self.api_base}/lineage", json=lineage_request
            )
            response.raise_for_status()

            self.logger.info(f"Pushed lineage to Unity Catalog for {full_table_name}")
            return {"status": "success", "lineage_pushed": True}
        except Exception as e:
            self.logger.error(f"Failed to push lineage to Unity Catalog: {e}")
            return {"status": "error", "error": str(e)}

    def add_tags(
        self, database: str, table_name: str, tags: Dict[str, str]
    ) -> Dict[str, Any]:
        """Add tags to table in Unity Catalog.

        Args:
            database: Schema name
            table_name: Table name
            tags: Tags to add

        Returns:
            Result dictionary
        """
        try:
            full_table_name = f"{self.catalog}.{database}.{table_name}"

            # Update table properties with tags
            response = self.session.patch(
                f"{self.api_base}/tables/{full_table_name}",
                json={"properties": {f"tag_{k}": v for k, v in tags.items()}},
            )
            response.raise_for_status()

            self.logger.info(f"Added {len(tags)} tags to {full_table_name}")
            return {"status": "success", "tags_added": len(tags)}
        except Exception as e:
            self.logger.error(f"Failed to add tags to Unity Catalog: {e}")
            return {"status": "error", "error": str(e)}

    def add_owners(
        self, database: str, table_name: str, owners: List[str]
    ) -> Dict[str, Any]:
        """Add owners to table in Unity Catalog.

        Args:
            database: Schema name
            table_name: Table name
            owners: List of owners

        Returns:
            Result dictionary
        """
        try:
            full_table_name = f"{self.catalog}.{database}.{table_name}"

            # Unity Catalog owner API
            for owner in owners:
                response = self.session.patch(
                    f"{self.api_base}/tables/{full_table_name}",
                    json={"owner": owner},
                )
                response.raise_for_status()

            self.logger.info(f"Added {len(owners)} owners to {full_table_name}")
            return {"status": "success", "owners_added": len(owners)}
        except Exception as e:
            self.logger.error(f"Failed to add owners to Unity Catalog: {e}")
            return {"status": "error", "error": str(e)}

    def _map_to_unity_type(self, dativo_type: str) -> str:
        """Map Dativo type to Unity Catalog type.

        Args:
            dativo_type: Dativo type

        Returns:
            Unity Catalog type
        """
        type_mapping = {
            "string": "string",
            "integer": "bigint",
            "float": "double",
            "double": "double",
            "boolean": "boolean",
            "timestamp": "timestamp",
            "datetime": "timestamp",
            "date": "date",
        }
        return type_mapping.get(dativo_type, "string")


class NessieCatalogClient(BaseCatalogClient):
    """Nessie Catalog client for lineage tracking."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize Nessie client.

        Args:
            config: Nessie configuration
                - uri: Nessie API endpoint
                - branch: Branch name (default: main)
        """
        super().__init__(config)
        self.uri = self._expand_env_vars(
            config.get("uri") or os.getenv("NESSIE_URI", "http://localhost:19120")
        )
        self.branch = config.get("branch", "main")

        # Remove /api/v1 suffix if present
        if self.uri.endswith("/api/v1"):
            self.base_uri = self.uri
            self.uri = self.uri[:-7]
        else:
            self.base_uri = f"{self.uri}/api/v1"

        import requests

        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def create_or_update_table(
        self,
        database: str,
        table_name: str,
        schema: List[Dict[str, Any]],
        location: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create or update table metadata in Nessie.

        Note: Nessie is primarily a catalog, not a metadata store.
        This method creates/updates table references in Nessie.

        Args:
            database: Database/namespace
            table_name: Table name
            schema: Table schema
            location: Storage location
            metadata: Additional metadata

        Returns:
            Result dictionary
        """
        metadata = metadata or {}

        try:
            # Create content for table
            table_content = {
                "type": "ICEBERG_TABLE",
                "metadataLocation": f"{location}/metadata/v1.metadata.json",
                "snapshotId": metadata.get("snapshot_id", -1),
                "schemaId": metadata.get("schema_id", -1),
                "specId": metadata.get("spec_id", -1),
                "sortOrderId": metadata.get("sort_order_id", -1),
            }

            # Commit table to Nessie
            key_parts = [database, table_name]
            commit_meta = {
                "message": f"Update table {database}.{table_name}",
                "properties": {
                    "source": "dativo-ingest",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            }

            response = self.session.post(
                f"{self.base_uri}/trees/branch/{self.branch}/commit",
                json={
                    "commitMeta": commit_meta,
                    "operations": [
                        {"type": "PUT", "key": {"elements": key_parts}, "content": table_content}
                    ],
                },
            )

            if response.status_code in [200, 201]:
                self.logger.info(f"Updated table {database}.{table_name} in Nessie")
                return {"status": "success", "table": f"{database}.{table_name}"}
            else:
                self.logger.warning(
                    f"Failed to update table in Nessie: {response.status_code}"
                )
                return {
                    "status": "error",
                    "error": f"HTTP {response.status_code}",
                }
        except Exception as e:
            self.logger.error(f"Failed to create/update table in Nessie: {e}")
            return {"status": "error", "error": str(e)}

    def push_lineage(self, lineage: CatalogLineage) -> Dict[str, Any]:
        """Push lineage information to Nessie.

        Note: Nessie doesn't have native lineage tracking.
        We store lineage as commit metadata.

        Args:
            lineage: Lineage information

        Returns:
            Result dictionary
        """
        try:
            commit_meta = {
                "message": f"Lineage for {lineage.target_database}.{lineage.target_table}",
                "properties": {
                    "lineage.source_type": lineage.source_type,
                    "lineage.source_object": lineage.source_object,
                    "lineage.job_id": lineage.job_id,
                    "lineage.execution_time": lineage.execution_time.isoformat(),
                    "lineage.records_written": str(lineage.records_written),
                    "lineage.files_written": str(lineage.files_written),
                },
            }

            if lineage.upstream_tables:
                commit_meta["properties"]["lineage.upstream_tables"] = ",".join(
                    lineage.upstream_tables
                )

            # Create a commit with lineage metadata
            response = self.session.get(f"{self.base_uri}/trees/tree/{self.branch}")
            if response.status_code == 200:
                self.logger.info(f"Stored lineage metadata in Nessie commit")
                return {"status": "success", "lineage_stored": True}

            return {"status": "warning", "message": "Branch not found"}
        except Exception as e:
            self.logger.error(f"Failed to push lineage to Nessie: {e}")
            return {"status": "error", "error": str(e)}

    def add_tags(
        self, database: str, table_name: str, tags: Dict[str, str]
    ) -> Dict[str, Any]:
        """Add tags to table in Nessie.

        Note: Nessie doesn't have native tag support for tables.
        Tags are stored in commit metadata.

        Args:
            database: Database name
            table_name: Table name
            tags: Tags to add

        Returns:
            Result dictionary
        """
        try:
            commit_meta = {
                "message": f"Add tags to {database}.{table_name}",
                "properties": {f"tag.{k}": v for k, v in tags.items()},
            }

            self.logger.info(
                f"Tags stored in Nessie commit metadata for {database}.{table_name}"
            )
            return {"status": "success", "tags_added": len(tags)}
        except Exception as e:
            self.logger.error(f"Failed to add tags to Nessie: {e}")
            return {"status": "error", "error": str(e)}

    def add_owners(
        self, database: str, table_name: str, owners: List[str]
    ) -> Dict[str, Any]:
        """Add owners to table in Nessie.

        Note: Nessie doesn't have native owner support.
        Owners are stored in commit metadata.

        Args:
            database: Database name
            table_name: Table name
            owners: List of owners

        Returns:
            Result dictionary
        """
        try:
            self.logger.info(
                f"Owners stored in Nessie commit metadata for {database}.{table_name}"
            )
            return {"status": "success", "owners_added": len(owners)}
        except Exception as e:
            self.logger.error(f"Failed to add owners to Nessie: {e}")
            return {"status": "error", "error": str(e)}


class OpenMetadataCatalogClient(BaseCatalogClient):
    """OpenMetadata catalog client."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize OpenMetadata client.

        Args:
            config: OpenMetadata configuration
                - uri: OpenMetadata API endpoint
                - token: JWT token for authentication
                - api_version: API version (default: v1)
        """
        super().__init__(config)
        self.uri = self._expand_env_vars(
            config.get("uri") or os.getenv("OPENMETADATA_URI", "http://localhost:8585")
        )
        self.token = self._expand_env_vars(
            config.get("token") or os.getenv("OPENMETADATA_TOKEN", "")
        )
        self.api_version = config.get("api_version", "v1")
        self.api_base = f"{self.uri}/api/{self.api_version}"

        # Initialize session
        import requests

        self.session = requests.Session()
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self.session.headers.update(headers)

    def create_or_update_table(
        self,
        database: str,
        table_name: str,
        schema: List[Dict[str, Any]],
        location: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create or update table in OpenMetadata.

        Args:
            database: Database/schema name
            table_name: Table name
            schema: Table schema
            location: Storage location
            metadata: Additional metadata

        Returns:
            Result dictionary
        """
        metadata = metadata or {}

        # Convert schema to OpenMetadata format
        columns = []
        for field in schema:
            om_type = self._map_to_openmetadata_type(field.get("type", "string"))
            columns.append(
                {
                    "name": field["name"],
                    "dataType": om_type,
                    "dataTypeDisplay": om_type,
                    "description": field.get("description", ""),
                    "ordinalPosition": len(columns) + 1,
                }
            )

        # Build table request
        table_fqn = f"default.{database}.{table_name}"
        table_request = {
            "name": table_name,
            "displayName": table_name,
            "databaseSchema": f"default.{database}",
            "columns": columns,
            "tableType": "External",
            "description": metadata.get("description", ""),
            "extension": {
                "storage_location": location,
                "ingest_timestamp": datetime.utcnow().isoformat(),
                **metadata,
            },
        }

        try:
            # Try to get existing table
            response = self.session.get(f"{self.api_base}/tables/name/{table_fqn}")
            if response.status_code == 200:
                # Table exists, update it
                existing_table = response.json()
                table_id = existing_table["id"]
                response = self.session.put(
                    f"{self.api_base}/tables", json=table_request
                )
                response.raise_for_status()
                self.logger.info(f"Updated table {table_fqn} in OpenMetadata")
                return {"status": "updated", "table": table_fqn, "id": table_id}
        except Exception:
            pass

        # Create new table
        try:
            response = self.session.post(f"{self.api_base}/tables", json=table_request)
            response.raise_for_status()
            result = response.json()
            self.logger.info(f"Created table {table_fqn} in OpenMetadata")
            return {"status": "created", "table": table_fqn, "id": result.get("id")}
        except Exception as e:
            self.logger.error(f"Failed to create table in OpenMetadata: {e}")
            return {"status": "error", "error": str(e)}

    def push_lineage(self, lineage: CatalogLineage) -> Dict[str, Any]:
        """Push lineage to OpenMetadata.

        Args:
            lineage: Lineage information

        Returns:
            Result dictionary
        """
        try:
            table_fqn = f"default.{lineage.target_database}.{lineage.target_table}"

            # Build lineage edges
            edges = []
            for upstream in lineage.upstream_tables:
                edges.append(
                    {
                        "fromEntity": {
                            "id": upstream,
                            "type": "table",
                        },
                        "toEntity": {
                            "id": table_fqn,
                            "type": "table",
                        },
                        "lineageDetails": {
                            "sqlQuery": "",
                            "source": lineage.source_type,
                            "description": f"Data from {lineage.source_object}",
                        },
                    }
                )

            # Push lineage
            lineage_request = {"edges": edges}
            response = self.session.put(
                f"{self.api_base}/lineage", json=lineage_request
            )
            response.raise_for_status()

            self.logger.info(f"Pushed lineage to OpenMetadata for {table_fqn}")
            return {"status": "success", "lineage_pushed": True, "edges": len(edges)}
        except Exception as e:
            self.logger.error(f"Failed to push lineage to OpenMetadata: {e}")
            return {"status": "error", "error": str(e)}

    def add_tags(
        self, database: str, table_name: str, tags: Dict[str, str]
    ) -> Dict[str, Any]:
        """Add tags to table in OpenMetadata.

        Args:
            database: Database name
            table_name: Table name
            tags: Tags to add

        Returns:
            Result dictionary
        """
        try:
            table_fqn = f"default.{database}.{table_name}"

            # OpenMetadata tags format
            om_tags = [{"tagFQN": f"User.{k}", "labelType": "Manual", "state": "Confirmed"} for k, v in tags.items()]

            # Add tags to table
            response = self.session.patch(
                f"{self.api_base}/tables/name/{table_fqn}",
                json={"tags": om_tags},
            )
            response.raise_for_status()

            self.logger.info(f"Added {len(tags)} tags to {table_fqn} in OpenMetadata")
            return {"status": "success", "tags_added": len(tags)}
        except Exception as e:
            self.logger.error(f"Failed to add tags to OpenMetadata: {e}")
            return {"status": "error", "error": str(e)}

    def add_owners(
        self, database: str, table_name: str, owners: List[str]
    ) -> Dict[str, Any]:
        """Add owners to table in OpenMetadata.

        Args:
            database: Database name
            table_name: Table name
            owners: List of owner identifiers

        Returns:
            Result dictionary
        """
        try:
            table_fqn = f"default.{database}.{table_name}"

            # OpenMetadata owners format
            om_owners = [{"id": owner, "type": "user"} for owner in owners]

            # Add owners to table
            response = self.session.patch(
                f"{self.api_base}/tables/name/{table_fqn}",
                json={"owners": om_owners},
            )
            response.raise_for_status()

            self.logger.info(
                f"Added {len(owners)} owners to {table_fqn} in OpenMetadata"
            )
            return {"status": "success", "owners_added": len(owners)}
        except Exception as e:
            self.logger.error(f"Failed to add owners to OpenMetadata: {e}")
            return {"status": "error", "error": str(e)}

    def _map_to_openmetadata_type(self, dativo_type: str) -> str:
        """Map Dativo type to OpenMetadata type.

        Args:
            dativo_type: Dativo type

        Returns:
            OpenMetadata type
        """
        type_mapping = {
            "string": "VARCHAR",
            "integer": "BIGINT",
            "float": "DOUBLE",
            "double": "DOUBLE",
            "boolean": "BOOLEAN",
            "timestamp": "TIMESTAMP",
            "datetime": "TIMESTAMP",
            "date": "DATE",
        }
        return type_mapping.get(dativo_type, "VARCHAR")


class CatalogManager:
    """Manages data catalog integrations and orchestrates lineage/metadata pushing."""

    def __init__(self, catalog_config: Dict[str, Any], asset_definition: AssetDefinition):
        """Initialize catalog manager.

        Args:
            catalog_config: Catalog configuration from job config
            asset_definition: Asset definition for metadata
        """
        self.catalog_config = catalog_config
        self.asset_definition = asset_definition
        self.logger = logging.getLogger(__name__)

        # Initialize catalog client
        catalog_type = catalog_config.get("type")
        catalog_client_config = catalog_config.get("config", {})

        if catalog_type == "aws_glue":
            self.client = AWSGlueCatalogClient(catalog_client_config)
        elif catalog_type == "databricks_unity":
            self.client = DatabricksUnityCatalogClient(catalog_client_config)
        elif catalog_type == "nessie":
            self.client = NessieCatalogClient(catalog_client_config)
        elif catalog_type == "openmetadata":
            self.client = OpenMetadataCatalogClient(catalog_client_config)
        else:
            raise ValueError(f"Unsupported catalog type: {catalog_type}")

        self.logger.info(f"Initialized {catalog_type} catalog client")

    def sync_table_metadata(
        self,
        database: str,
        table_name: str,
        location: str,
        additional_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Sync table metadata to catalog.

        Args:
            database: Database/schema name
            table_name: Table name
            location: Storage location
            additional_metadata: Additional metadata to include

        Returns:
            Result dictionary
        """
        # Build metadata from asset definition
        metadata = {
            "source_type": self.asset_definition.source_type,
            "object": self.asset_definition.object,
            "version": str(self.asset_definition.version),
            "domain": self.asset_definition.domain,
        }

        if hasattr(self.asset_definition, "dataProduct"):
            metadata["data_product"] = self.asset_definition.dataProduct

        if self.asset_definition.description:
            if hasattr(self.asset_definition.description, "purpose"):
                metadata["description"] = self.asset_definition.description.purpose
            else:
                metadata["description"] = str(self.asset_definition.description)

        # Add catalog-specific metadata
        catalog_metadata = self.catalog_config.get("metadata", {})
        metadata.update(catalog_metadata)

        # Add additional metadata
        if additional_metadata:
            metadata.update(additional_metadata)

        # Create or update table
        result = self.client.create_or_update_table(
            database=database,
            table_name=table_name,
            schema=self.asset_definition.schema,
            location=location,
            metadata=metadata,
        )

        return result

    def push_lineage(
        self,
        source_type: str,
        source_object: str,
        target_database: str,
        target_table: str,
        job_id: str,
        tenant_id: str,
        records_written: int = 0,
        files_written: int = 0,
    ) -> Dict[str, Any]:
        """Push lineage information to catalog.

        Args:
            source_type: Source connector type
            source_object: Source object name
            target_database: Target database
            target_table: Target table
            job_id: Job identifier
            tenant_id: Tenant identifier
            records_written: Number of records written
            files_written: Number of files written

        Returns:
            Result dictionary
        """
        # Get upstream/downstream tables from config
        lineage_config = self.catalog_config.get("lineage", {})
        enabled = lineage_config.get("enabled", True)

        if not enabled:
            self.logger.info("Lineage tracking is disabled")
            return {"status": "disabled"}

        upstream_tables = lineage_config.get("upstream_tables", [])
        downstream_tables = lineage_config.get("downstream_tables", [])

        # Create lineage object
        lineage = CatalogLineage(
            source_type=source_type,
            source_object=source_object,
            target_table=target_table,
            target_database=target_database,
            job_id=job_id,
            tenant_id=tenant_id,
            upstream_tables=upstream_tables,
            downstream_tables=downstream_tables,
            records_written=records_written,
            files_written=files_written,
        )

        # Push to catalog
        result = self.client.push_lineage(lineage)
        return result

    def sync_tags(self, database: str, table_name: str) -> Dict[str, Any]:
        """Sync tags to catalog.

        Args:
            database: Database name
            table_name: Table name

        Returns:
            Result dictionary
        """
        # Collect tags from asset definition
        tags = {}

        # Asset tags
        if self.asset_definition.tags:
            if isinstance(self.asset_definition.tags, list):
                for i, tag in enumerate(self.asset_definition.tags):
                    tags[f"asset_tag_{i}"] = str(tag)
            elif isinstance(self.asset_definition.tags, dict):
                tags.update({f"asset_{k}": str(v) for k, v in self.asset_definition.tags.items()})

        # Domain and data product
        if self.asset_definition.domain:
            tags["domain"] = self.asset_definition.domain
        if hasattr(self.asset_definition, "dataProduct") and self.asset_definition.dataProduct:
            tags["data_product"] = self.asset_definition.dataProduct

        # Compliance tags
        if self.asset_definition.compliance:
            if self.asset_definition.compliance.classification:
                tags["classification"] = ",".join(
                    self.asset_definition.compliance.classification
                )

        # Catalog-specific tags
        catalog_tags = self.catalog_config.get("metadata", {}).get("tags", {})
        tags.update(catalog_tags)

        # Add tier if specified
        tier = self.catalog_config.get("metadata", {}).get("tier")
        if tier:
            tags["tier"] = tier

        # Push tags
        if tags:
            result = self.client.add_tags(database, table_name, tags)
            return result

        return {"status": "skipped", "reason": "no tags to sync"}

    def sync_owners(self, database: str, table_name: str) -> Dict[str, Any]:
        """Sync owners to catalog.

        Args:
            database: Database name
            table_name: Table name

        Returns:
            Result dictionary
        """
        owners = []

        # Owner from asset definition
        if self.asset_definition.team and self.asset_definition.team.owner:
            owners.append(self.asset_definition.team.owner)

        # Additional owners from catalog config
        catalog_owners = self.catalog_config.get("metadata", {}).get("owners", [])
        owners.extend(catalog_owners)

        # Remove duplicates
        owners = list(set(owners))

        # Push owners
        if owners:
            result = self.client.add_owners(database, table_name, owners)
            return result

        return {"status": "skipped", "reason": "no owners to sync"}
