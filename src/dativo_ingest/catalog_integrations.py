"""Data catalog integrations for lineage tracking and metadata management.

Supports AWS Glue, Databricks Unity Catalog, Nessie, and OpenMetadata.
"""

import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .config import AssetDefinition, CatalogConfig, SourceConfig, TargetConfig
from .tag_derivation import derive_tags_from_asset


class LineageInfo:
    """Container for lineage information."""

    def __init__(
        self,
        source_type: str,
        source_name: str,
        target_type: str,
        target_name: str,
        asset_definition: AssetDefinition,
        record_count: int,
        file_count: int,
        total_bytes: int,
        file_paths: List[str],
        execution_time: datetime,
        classification_overrides: Optional[Dict[str, str]] = None,
        finops: Optional[Dict[str, Any]] = None,
        governance_overrides: Optional[Dict[str, Any]] = None,
        source_tags: Optional[Dict[str, str]] = None,
    ):
        """Initialize lineage info.

        Args:
            source_type: Source connector type (e.g., 'stripe', 'postgres')
            source_name: Source object name
            target_type: Target connector type (e.g., 'iceberg', 's3')
            target_name: Target table/path name
            asset_definition: Asset definition with schema and governance
            record_count: Number of records processed
            file_count: Number of files written
            total_bytes: Total bytes written
            file_paths: List of file paths written
            execution_time: Execution timestamp
            classification_overrides: Field-level classification overrides
            finops: FinOps metadata
            governance_overrides: Governance metadata overrides
            source_tags: Source system tags (LOWEST priority)
        """
        self.source_type = source_type
        self.source_name = source_name
        self.target_type = target_type
        self.target_name = target_name
        self.asset_definition = asset_definition
        self.record_count = record_count
        self.file_count = file_count
        self.total_bytes = total_bytes
        self.file_paths = file_paths
        self.execution_time = execution_time
        self.classification_overrides = classification_overrides
        self.finops = finops
        self.governance_overrides = governance_overrides
        self.source_tags = source_tags


class BaseCatalogClient(ABC):
    """Abstract base class for data catalog clients."""

    def __init__(self, catalog_config: CatalogConfig):
        """Initialize catalog client.

        Args:
            catalog_config: Catalog configuration
        """
        self.catalog_config = catalog_config
        self.logger = logging.getLogger(__name__)

    @abstractmethod
    def push_lineage(self, lineage_info: LineageInfo) -> Dict[str, Any]:
        """Push lineage information to the catalog.

        Args:
            lineage_info: Lineage information to push

        Returns:
            Dictionary with push status and metadata

        Raises:
            Exception: If push fails
        """
        pass

    @abstractmethod
    def create_or_update_table(
        self, table_name: str, schema: List[Dict[str, Any]], metadata: Dict[str, str]
    ) -> Dict[str, Any]:
        """Create or update table metadata in catalog.

        Args:
            table_name: Fully qualified table name
            schema: Table schema definition
            metadata: Table metadata (tags, owners, etc.)

        Returns:
            Dictionary with operation status

        Raises:
            Exception: If operation fails
        """
        pass

    def _derive_table_properties(self, lineage_info: LineageInfo) -> Dict[str, str]:
        """Derive table properties from lineage info using tag derivation.

        Args:
            lineage_info: Lineage information

        Returns:
            Dictionary of table properties/tags
        """
        # Derive all tags using tag derivation module
        tags = derive_tags_from_asset(
            asset_definition=lineage_info.asset_definition,
            classification_overrides=lineage_info.classification_overrides,
            finops=lineage_info.finops,
            governance_overrides=lineage_info.governance_overrides,
            source_tags=lineage_info.source_tags,
        )

        # Add lineage-specific metadata
        tags["source_type"] = lineage_info.source_type
        tags["source_name"] = lineage_info.source_name
        tags["target_type"] = lineage_info.target_type
        tags["last_ingestion_time"] = lineage_info.execution_time.isoformat()
        tags["last_record_count"] = str(lineage_info.record_count)
        tags["last_file_count"] = str(lineage_info.file_count)
        tags["last_total_bytes"] = str(lineage_info.total_bytes)

        return tags


class AWSGlueCatalogClient(BaseCatalogClient):
    """AWS Glue Data Catalog client for lineage tracking."""

    def __init__(self, catalog_config: CatalogConfig):
        """Initialize AWS Glue catalog client.

        Args:
            catalog_config: Catalog configuration with AWS connection details
        """
        super().__init__(catalog_config)
        self._client = None

    def _get_client(self):
        """Get or create boto3 Glue client."""
        if self._client is None:
            try:
                import boto3
            except ImportError:
                raise ImportError(
                    "boto3 is required for AWS Glue integration. Install with: pip install boto3"
                )

            connection = self.catalog_config.connection
            region = connection.get("region") or os.getenv("AWS_REGION", "us-east-1")
            aws_access_key_id = connection.get("aws_access_key_id") or os.getenv(
                "AWS_ACCESS_KEY_ID"
            )
            aws_secret_access_key = connection.get(
                "aws_secret_access_key"
            ) or os.getenv("AWS_SECRET_ACCESS_KEY")

            session_kwargs = {"region_name": region}
            if aws_access_key_id and aws_secret_access_key:
                session_kwargs["aws_access_key_id"] = aws_access_key_id
                session_kwargs["aws_secret_access_key"] = aws_secret_access_key

            self._client = boto3.client("glue", **session_kwargs)

        return self._client

    def push_lineage(self, lineage_info: LineageInfo) -> Dict[str, Any]:
        """Push lineage information to AWS Glue catalog.

        Args:
            lineage_info: Lineage information to push

        Returns:
            Dictionary with push status
        """
        client = self._get_client()
        connection = self.catalog_config.connection
        database_name = connection.get("database") or lineage_info.asset_definition.domain or "default"
        table_name = lineage_info.target_name

        # Derive tags/properties
        properties = self._derive_table_properties(lineage_info)

        # Convert schema to Glue format
        columns = []
        for field in lineage_info.asset_definition.schema:
            field_name = field["name"]
            field_type = field.get("type", "string")
            
            # Map to Glue types
            glue_type = {
                "string": "string",
                "integer": "bigint",
                "float": "double",
                "double": "double",
                "boolean": "boolean",
                "timestamp": "timestamp",
                "datetime": "timestamp",
                "date": "date",
            }.get(field_type, "string")

            columns.append({
                "Name": field_name,
                "Type": glue_type,
                "Comment": field.get("description", ""),
            })

        # Create or update table
        table_input = {
            "Name": table_name,
            "StorageDescriptor": {
                "Columns": columns,
                "Location": f"s3://{connection.get('bucket', 'default-bucket')}/{lineage_info.asset_definition.domain}/{lineage_info.target_name}/",
                "InputFormat": "org.apache.hadoop.mapred.TextInputFormat",
                "OutputFormat": "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
                "SerdeInfo": {
                    "SerializationLibrary": "org.apache.hadoop.hive.serde2.lazy.LazySimpleSerDe",
                    "Parameters": {"serialization.format": "1"},
                },
            },
            "Parameters": properties,
        }

        # Add owner if available
        if lineage_info.asset_definition.team and lineage_info.asset_definition.team.owner:
            table_input["Owner"] = lineage_info.asset_definition.team.owner

        try:
            # Try to update existing table
            client.update_table(
                DatabaseName=database_name,
                TableInput=table_input,
            )
            self.logger.info(f"Updated table in AWS Glue: {database_name}.{table_name}")
        except client.exceptions.EntityNotFoundException:
            # Table doesn't exist, create it
            client.create_table(
                DatabaseName=database_name,
                TableInput=table_input,
            )
            self.logger.info(f"Created table in AWS Glue: {database_name}.{table_name}")

        return {
            "status": "success",
            "catalog": "aws_glue",
            "database": database_name,
            "table": table_name,
        }

    def create_or_update_table(
        self, table_name: str, schema: List[Dict[str, Any]], metadata: Dict[str, str]
    ) -> Dict[str, Any]:
        """Create or update table metadata in AWS Glue.

        Args:
            table_name: Fully qualified table name (database.table)
            schema: Table schema definition
            metadata: Table metadata

        Returns:
            Dictionary with operation status
        """
        parts = table_name.split(".", 1)
        if len(parts) == 2:
            database_name, table_name = parts
        else:
            database_name = "default"

        client = self._get_client()

        columns = []
        for field in schema:
            columns.append({
                "Name": field["name"],
                "Type": field.get("type", "string"),
                "Comment": field.get("description", ""),
            })

        table_input = {
            "Name": table_name,
            "StorageDescriptor": {
                "Columns": columns,
                "Location": f"s3://default-bucket/{database_name}/{table_name}/",
                "InputFormat": "org.apache.hadoop.mapred.TextInputFormat",
                "OutputFormat": "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
                "SerdeInfo": {
                    "SerializationLibrary": "org.apache.hadoop.hive.serde2.lazy.LazySimpleSerDe",
                },
            },
            "Parameters": metadata,
        }

        try:
            client.update_table(DatabaseName=database_name, TableInput=table_input)
            return {"status": "updated", "database": database_name, "table": table_name}
        except client.exceptions.EntityNotFoundException:
            client.create_table(DatabaseName=database_name, TableInput=table_input)
            return {"status": "created", "database": database_name, "table": table_name}


class DatabricksUnityCatalogClient(BaseCatalogClient):
    """Databricks Unity Catalog client for lineage tracking."""

    def __init__(self, catalog_config: CatalogConfig):
        """Initialize Databricks Unity Catalog client.

        Args:
            catalog_config: Catalog configuration with Databricks connection details
        """
        super().__init__(catalog_config)
        self._session = None

    def _get_session(self):
        """Get or create requests session with authentication."""
        if self._session is None:
            try:
                import requests
            except ImportError:
                raise ImportError(
                    "requests is required for Databricks Unity Catalog integration."
                )

            connection = self.catalog_config.connection
            self._workspace_url = connection.get("workspace_url")
            self._token = connection.get("token") or os.getenv("DATABRICKS_TOKEN")

            if not self._workspace_url or not self._token:
                raise ValueError(
                    "Databricks workspace_url and token are required for Unity Catalog"
                )

            self._session = requests.Session()
            self._session.headers.update({
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            })

        return self._session

    def push_lineage(self, lineage_info: LineageInfo) -> Dict[str, Any]:
        """Push lineage information to Databricks Unity Catalog.

        Args:
            lineage_info: Lineage information to push

        Returns:
            Dictionary with push status
        """
        session = self._get_session()
        connection = self.catalog_config.connection
        
        catalog = connection.get("catalog", "main")
        schema = connection.get("schema") or lineage_info.asset_definition.domain or "default"
        table_name = lineage_info.target_name
        full_name = f"{catalog}.{schema}.{table_name}"

        # Derive tags/properties
        properties = self._derive_table_properties(lineage_info)

        # Convert schema to Unity Catalog format
        columns = []
        for field in lineage_info.asset_definition.schema:
            field_name = field["name"]
            field_type = field.get("type", "string").upper()
            
            # Map to Unity Catalog types
            uc_type = {
                "STRING": "STRING",
                "INTEGER": "BIGINT",
                "FLOAT": "DOUBLE",
                "DOUBLE": "DOUBLE",
                "BOOLEAN": "BOOLEAN",
                "TIMESTAMP": "TIMESTAMP",
                "DATETIME": "TIMESTAMP",
                "DATE": "DATE",
            }.get(field_type, "STRING")

            columns.append({
                "name": field_name,
                "type_text": uc_type,
                "type_name": uc_type,
                "position": len(columns),
                "comment": field.get("description", ""),
            })

        # Build table creation/update request
        table_data = {
            "name": table_name,
            "catalog_name": catalog,
            "schema_name": schema,
            "table_type": "EXTERNAL",
            "data_source_format": "PARQUET",
            "columns": columns,
            "storage_location": f"s3://{connection.get('bucket', 'default-bucket')}/{lineage_info.asset_definition.domain}/{lineage_info.target_name}/",
            "properties": properties,
        }

        # Add owner if available
        if lineage_info.asset_definition.team and lineage_info.asset_definition.team.owner:
            table_data["owner"] = lineage_info.asset_definition.team.owner

        # Try to create or update table
        try:
            response = session.post(
                f"{self._workspace_url}/api/2.1/unity-catalog/tables",
                json=table_data,
            )
            
            if response.status_code == 409:
                # Table exists, update it
                response = session.patch(
                    f"{self._workspace_url}/api/2.1/unity-catalog/tables/{full_name}",
                    json={"properties": properties},
                )
                response.raise_for_status()
                self.logger.info(f"Updated table in Unity Catalog: {full_name}")
            else:
                response.raise_for_status()
                self.logger.info(f"Created table in Unity Catalog: {full_name}")

            return {
                "status": "success",
                "catalog": "databricks_unity",
                "full_name": full_name,
            }
        except Exception as e:
            self.logger.error(f"Failed to push to Unity Catalog: {e}")
            raise

    def create_or_update_table(
        self, table_name: str, schema: List[Dict[str, Any]], metadata: Dict[str, str]
    ) -> Dict[str, Any]:
        """Create or update table metadata in Unity Catalog.

        Args:
            table_name: Fully qualified table name (catalog.schema.table)
            schema: Table schema definition
            metadata: Table metadata

        Returns:
            Dictionary with operation status
        """
        session = self._get_session()
        parts = table_name.split(".")
        
        if len(parts) == 3:
            catalog, schema_name, table = parts
        elif len(parts) == 2:
            catalog = "main"
            schema_name, table = parts
        else:
            catalog = "main"
            schema_name = "default"
            table = table_name

        full_name = f"{catalog}.{schema_name}.{table}"

        columns = []
        for field in schema:
            columns.append({
                "name": field["name"],
                "type_text": field.get("type", "STRING").upper(),
                "type_name": field.get("type", "STRING").upper(),
                "position": len(columns),
                "comment": field.get("description", ""),
            })

        table_data = {
            "name": table,
            "catalog_name": catalog,
            "schema_name": schema_name,
            "table_type": "EXTERNAL",
            "data_source_format": "PARQUET",
            "columns": columns,
            "properties": metadata,
        }

        try:
            response = session.post(
                f"{self._workspace_url}/api/2.1/unity-catalog/tables",
                json=table_data,
            )
            
            if response.status_code == 409:
                response = session.patch(
                    f"{self._workspace_url}/api/2.1/unity-catalog/tables/{full_name}",
                    json={"properties": metadata},
                )
                response.raise_for_status()
                return {"status": "updated", "full_name": full_name}
            else:
                response.raise_for_status()
                return {"status": "created", "full_name": full_name}
        except Exception as e:
            self.logger.error(f"Failed to create/update Unity Catalog table: {e}")
            raise


class NessieCatalogClient(BaseCatalogClient):
    """Nessie catalog client for lineage tracking."""

    def __init__(self, catalog_config: CatalogConfig):
        """Initialize Nessie catalog client.

        Args:
            catalog_config: Catalog configuration with Nessie connection details
        """
        super().__init__(catalog_config)
        self._client = None

    def _get_client(self):
        """Get or create Nessie client."""
        if self._client is None:
            try:
                from pynessie import init
            except ImportError:
                raise ImportError(
                    "pynessie is required for Nessie integration. Install with: pip install pynessie"
                )

            connection = self.catalog_config.connection
            uri = connection.get("uri") or os.getenv("NESSIE_URI", "http://localhost:19120/api/v1")
            
            # Expand environment variables
            if uri and "${" in uri:
                uri = os.path.expandvars(uri)

            self._client = init(uri)

        return self._client

    def push_lineage(self, lineage_info: LineageInfo) -> Dict[str, Any]:
        """Push lineage information to Nessie catalog.

        Args:
            lineage_info: Lineage information to push

        Returns:
            Dictionary with push status
        """
        client = self._get_client()
        connection = self.catalog_config.connection
        
        branch = connection.get("branch", "main")
        namespace = lineage_info.asset_definition.domain or "default"
        table_name = lineage_info.target_name

        # Derive tags/properties
        properties = self._derive_table_properties(lineage_info)

        # Create Nessie table content
        from pynessie.model import IcebergTable, Content, ContentKey

        key = ContentKey([namespace, table_name])
        
        # Get current branch reference
        try:
            ref = client.get_reference(branch)
        except Exception:
            # Branch doesn't exist, create it
            from pynessie.model import Branch
            client.create_reference(Branch(name=branch, hash_=None))
            ref = client.get_reference(branch)

        # Create or update table metadata
        metadata_location = f"s3://{connection.get('bucket', 'default-bucket')}/{namespace}/{table_name}/metadata/"
        
        table_content = IcebergTable(
            metadata_location=metadata_location,
            snapshot_id=-1,
            schema_id=-1,
            spec_id=-1,
            sort_order_id=-1,
        )

        try:
            # Try to update existing table
            client.commit(
                branch=branch,
                message=f"Update table metadata for {namespace}.{table_name}",
                put={key: table_content},
            )
            self.logger.info(f"Updated table in Nessie: {namespace}.{table_name} on branch {branch}")
        except Exception as e:
            self.logger.warning(f"Failed to commit to Nessie (may already exist): {e}")

        return {
            "status": "success",
            "catalog": "nessie",
            "branch": branch,
            "namespace": namespace,
            "table": table_name,
        }

    def create_or_update_table(
        self, table_name: str, schema: List[Dict[str, Any]], metadata: Dict[str, str]
    ) -> Dict[str, Any]:
        """Create or update table metadata in Nessie.

        Args:
            table_name: Fully qualified table name (namespace.table)
            schema: Table schema definition
            metadata: Table metadata

        Returns:
            Dictionary with operation status
        """
        client = self._get_client()
        parts = table_name.split(".", 1)
        
        if len(parts) == 2:
            namespace, table = parts
        else:
            namespace = "default"
            table = table_name

        from pynessie.model import IcebergTable, ContentKey

        key = ContentKey([namespace, table])
        metadata_location = f"s3://default-bucket/{namespace}/{table}/metadata/"
        
        table_content = IcebergTable(
            metadata_location=metadata_location,
            snapshot_id=-1,
            schema_id=-1,
            spec_id=-1,
            sort_order_id=-1,
        )

        try:
            client.commit(
                branch="main",
                message=f"Create/update table {namespace}.{table}",
                put={key: table_content},
            )
            return {"status": "success", "namespace": namespace, "table": table}
        except Exception as e:
            self.logger.error(f"Failed to create/update Nessie table: {e}")
            raise


class OpenMetadataCatalogClient(BaseCatalogClient):
    """OpenMetadata catalog client for lineage tracking."""

    def __init__(self, catalog_config: CatalogConfig):
        """Initialize OpenMetadata catalog client.

        Args:
            catalog_config: Catalog configuration with OpenMetadata connection details
        """
        super().__init__(catalog_config)
        self._client = None

    def _get_client(self):
        """Get or create OpenMetadata client."""
        if self._client is None:
            try:
                from metadata.ingestion.ometa.ometa_api import OpenMetadata
                from metadata.generated.schema.entity.services.connections.metadata.openMetadataConnection import (
                    OpenMetadataConnection,
                )
                from metadata.generated.schema.security.client.openMetadataJWTClientConfig import (
                    OpenMetadataJWTClientConfig,
                )
            except ImportError:
                raise ImportError(
                    "openmetadata-ingestion is required for OpenMetadata integration. "
                    "Install with: pip install 'openmetadata-ingestion~=1.3.0'"
                )

            connection = self.catalog_config.connection
            host_port = connection.get("host_port") or os.getenv(
                "OPENMETADATA_HOST_PORT", "http://localhost:8585/api"
            )
            jwt_token = connection.get("jwt_token") or os.getenv("OPENMETADATA_JWT_TOKEN")

            if jwt_token:
                server_config = OpenMetadataConnection(
                    hostPort=host_port,
                    authProvider="openmetadata",
                    securityConfig=OpenMetadataJWTClientConfig(jwtToken=jwt_token),
                )
            else:
                # Use no-auth for local development
                server_config = OpenMetadataConnection(
                    hostPort=host_port,
                    authProvider="no-auth",
                )

            self._client = OpenMetadata(server_config)

        return self._client

    def push_lineage(self, lineage_info: LineageInfo) -> Dict[str, Any]:
        """Push lineage information to OpenMetadata.

        Args:
            lineage_info: Lineage information to push

        Returns:
            Dictionary with push status
        """
        client = self._get_client()
        
        try:
            from metadata.generated.schema.entity.data.table import Table, Column, DataType
            from metadata.generated.schema.type.entityReference import EntityReference
            from metadata.generated.schema.api.data.createTable import CreateTableRequest
            from metadata.generated.schema.entity.services.databaseService import DatabaseService
            from metadata.generated.schema.api.services.createDatabaseService import (
                CreateDatabaseServiceRequest,
            )
            from metadata.generated.schema.entity.services.connections.database.common.basicAuth import (
                BasicAuth,
            )
            from metadata.generated.schema.entity.services.connections.database.customDatabaseConnection import (
                CustomDatabaseConnection,
            )
            from metadata.generated.schema.entity.data.database import Database
            from metadata.generated.schema.api.data.createDatabase import CreateDatabaseRequest
            from metadata.generated.schema.entity.data.databaseSchema import DatabaseSchema
            from metadata.generated.schema.api.data.createDatabaseSchema import (
                CreateDatabaseSchemaRequest,
            )
            from metadata.generated.schema.type.tagLabel import TagLabel, LabelType, TagSource
        except ImportError as e:
            self.logger.error(f"Failed to import OpenMetadata schemas: {e}")
            raise

        connection = self.catalog_config.connection
        database_service_name = connection.get("service_name", "dativo_ingestion")
        database_name = connection.get("database") or lineage_info.asset_definition.domain or "default"
        schema_name = connection.get("schema", "default")
        table_name = lineage_info.target_name

        # Derive tags/properties
        properties = self._derive_table_properties(lineage_info)

        # 1. Create or get database service
        try:
            service = client.get_by_name(
                entity=DatabaseService,
                fqn=database_service_name,
            )
        except Exception:
            # Service doesn't exist, create it
            service_connection = CustomDatabaseConnection(
                type="CustomDatabase",
                sourcePythonClass="dativo_ingest.catalog_integrations.OpenMetadataCatalogClient",
                connectionOptions={},
            )
            
            create_service = CreateDatabaseServiceRequest(
                name=database_service_name,
                serviceType="CustomDatabase",
                connection=service_connection,
            )
            service = client.create_or_update(create_service)
            self.logger.info(f"Created database service: {database_service_name}")

        # 2. Create or get database
        database_fqn = f"{database_service_name}.{database_name}"
        try:
            database = client.get_by_name(
                entity=Database,
                fqn=database_fqn,
            )
        except Exception:
            create_db = CreateDatabaseRequest(
                name=database_name,
                service=EntityReference(id=service.id, type="databaseService"),
            )
            database = client.create_or_update(create_db)
            self.logger.info(f"Created database: {database_fqn}")

        # 3. Create or get schema
        schema_fqn = f"{database_fqn}.{schema_name}"
        try:
            db_schema = client.get_by_name(
                entity=DatabaseSchema,
                fqn=schema_fqn,
            )
        except Exception:
            create_schema = CreateDatabaseSchemaRequest(
                name=schema_name,
                database=EntityReference(id=database.id, type="database"),
            )
            db_schema = client.create_or_update(create_schema)
            self.logger.info(f"Created schema: {schema_fqn}")

        # 4. Create or update table
        table_fqn = f"{schema_fqn}.{table_name}"
        
        # Convert schema to OpenMetadata format
        columns = []
        for field in lineage_info.asset_definition.schema:
            field_name = field["name"]
            field_type = field.get("type", "string").upper()
            
            # Map to OpenMetadata DataType
            om_type = {
                "STRING": DataType.STRING,
                "INTEGER": DataType.BIGINT,
                "FLOAT": DataType.DOUBLE,
                "DOUBLE": DataType.DOUBLE,
                "BOOLEAN": DataType.BOOLEAN,
                "TIMESTAMP": DataType.TIMESTAMP,
                "DATETIME": DataType.TIMESTAMP,
                "DATE": DataType.DATE,
            }.get(field_type, DataType.STRING)

            column = Column(
                name=field_name,
                dataType=om_type,
                description=field.get("description", ""),
            )
            
            # Add classification tags if available
            if lineage_info.classification_overrides and field_name in lineage_info.classification_overrides:
                classification = lineage_info.classification_overrides[field_name]
                column.tags = [
                    TagLabel(
                        tagFQN=f"PII.{classification}",
                        labelType=LabelType.Automated,
                        source=TagSource.Classification,
                    )
                ]
            
            columns.append(column)

        # Build table properties/tags
        table_tags = []
        
        # Add governance tags
        if lineage_info.asset_definition.team and lineage_info.asset_definition.team.owner:
            table_tags.append(
                TagLabel(
                    tagFQN=f"Owner.{lineage_info.asset_definition.team.owner}",
                    labelType=LabelType.Automated,
                    source=TagSource.Tag,
                )
            )

        # Add asset tags
        if lineage_info.asset_definition.tags:
            for tag in lineage_info.asset_definition.tags:
                table_tags.append(
                    TagLabel(
                        tagFQN=f"Asset.{tag}",
                        labelType=LabelType.Automated,
                        source=TagSource.Tag,
                    )
                )

        # Create or update table
        create_table = CreateTableRequest(
            name=table_name,
            databaseSchema=EntityReference(id=db_schema.id, type="databaseSchema"),
            columns=columns,
            tags=table_tags if table_tags else None,
        )

        try:
            table = client.create_or_update(create_table)
            self.logger.info(f"Created/updated table in OpenMetadata: {table_fqn}")

            # Add lineage information
            # TODO: Implement lineage edges once we have source entity FQN
            
            return {
                "status": "success",
                "catalog": "openmetadata",
                "table_fqn": table_fqn,
                "table_id": str(table.id.__root__) if hasattr(table.id, "__root__") else str(table.id),
            }
        except Exception as e:
            self.logger.error(f"Failed to create/update table in OpenMetadata: {e}", exc_info=True)
            raise

    def create_or_update_table(
        self, table_name: str, schema: List[Dict[str, Any]], metadata: Dict[str, str]
    ) -> Dict[str, Any]:
        """Create or update table metadata in OpenMetadata.

        Args:
            table_name: Fully qualified table name (service.database.schema.table)
            schema: Table schema definition
            metadata: Table metadata

        Returns:
            Dictionary with operation status
        """
        # This method is implemented via push_lineage for OpenMetadata
        # since it requires a full LineageInfo object
        raise NotImplementedError(
            "Use push_lineage() for OpenMetadata table operations"
        )


def create_catalog_client(catalog_config: CatalogConfig) -> BaseCatalogClient:
    """Factory function to create the appropriate catalog client.

    Args:
        catalog_config: Catalog configuration

    Returns:
        Catalog client instance

    Raises:
        ValueError: If catalog type is not supported
    """
    catalog_type = catalog_config.type.lower()

    if catalog_type == "aws_glue":
        return AWSGlueCatalogClient(catalog_config)
    elif catalog_type == "databricks_unity":
        return DatabricksUnityCatalogClient(catalog_config)
    elif catalog_type == "nessie":
        return NessieCatalogClient(catalog_config)
    elif catalog_type == "openmetadata":
        return OpenMetadataCatalogClient(catalog_config)
    else:
        raise ValueError(
            f"Unsupported catalog type: {catalog_type}. "
            f"Supported types: aws_glue, databricks_unity, nessie, openmetadata"
        )
