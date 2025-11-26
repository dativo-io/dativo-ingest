"""OpenMetadata catalog integration."""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from .base import BaseCatalogClient, CatalogConfig, LineageInfo

logger = logging.getLogger(__name__)


class OpenMetadataCatalogClient(BaseCatalogClient):
    """OpenMetadata catalog client."""
    
    def __init__(self, config: CatalogConfig):
        """Initialize OpenMetadata catalog client.
        
        Args:
            config: Catalog configuration
        """
        super().__init__(config)
        self._client = None
        self._metadata = None
    
    def _validate_config(self) -> None:
        """Validate OpenMetadata-specific configuration."""
        if not self.config.uri:
            # Use default local OpenMetadata URI
            self.config.uri = "http://localhost:8585/api"
        
        # Server config is optional - will use defaults if not provided
        if not self.config.server_config:
            self.config.server_config = {
                "hostPort": self.config.uri,
                "authProvider": "no-auth" if not self.config.token else "openmetadata",
            }
            
            if self.config.token:
                self.config.server_config["securityConfig"] = {
                    "jwtToken": self.config.token
                }
    
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
                    "Install with: pip install openmetadata-ingestion"
                )
            
            # Build connection config
            server_config = self.config.server_config or {}
            
            if self.config.token:
                # JWT authentication
                security_config = OpenMetadataJWTClientConfig(
                    jwtToken=self.config.token
                )
                connection = OpenMetadataConnection(
                    hostPort=self.config.uri,
                    authProvider="openmetadata",
                    securityConfig=security_config,
                )
            else:
                # No authentication (local development)
                connection = OpenMetadataConnection(
                    hostPort=self.config.uri,
                    authProvider="no-auth",
                )
            
            self._client = OpenMetadata(connection)
            
        return self._client
    
    def register_dataset(
        self,
        dataset_name: str,
        schema: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Register or update a table in OpenMetadata.
        
        Args:
            dataset_name: Table name (format: "service.database.schema.table")
            schema: List of field definitions
            metadata: Additional metadata
        
        Returns:
            Dictionary with registration result
        """
        try:
            from metadata.generated.schema.entity.data.table import Table, Column, DataType
            from metadata.generated.schema.type.entityReference import EntityReference
        except ImportError:
            raise ImportError(
                "openmetadata-ingestion is required. Install with: pip install openmetadata-ingestion"
            )
        
        client = self._get_client()
        metadata = metadata or {}
        
        # Parse dataset name
        parts = dataset_name.split(".")
        if len(parts) >= 3:
            service_name = parts[0]
            database_name = parts[1]
            table_name = ".".join(parts[2:])
            schema_name = None
        elif len(parts) == 2:
            service_name = metadata.get("service_name", "dativo_service")
            database_name = parts[0]
            schema_name = None
            table_name = parts[1]
        else:
            service_name = metadata.get("service_name", "dativo_service")
            database_name = "default"
            schema_name = None
            table_name = dataset_name
        
        # Ensure service exists
        service_entity = self._ensure_service_exists(
            service_name,
            metadata.get("service_type", "databaseService")
        )
        
        # Ensure database exists
        database_entity = self._ensure_database_exists(
            service_name, database_name
        )
        
        # Convert schema to OpenMetadata format
        om_columns = []
        for field in schema:
            column = Column(
                name=field.get("name", ""),
                dataType=self._map_type_to_openmetadata(field.get("type", "string")),
                description=field.get("description"),
            )
            om_columns.append(column)
        
        # Build table entity
        table_fqn = f"{service_name}.{database_name}.{table_name}"
        
        table_entity = Table(
            name=table_name,
            fullyQualifiedName=table_fqn,
            columns=om_columns,
            database=EntityReference(
                id=database_entity.id,
                type="database",
                fullyQualifiedName=database_entity.fullyQualifiedName,
            ),
        )
        
        if metadata.get("description"):
            table_entity.description = metadata["description"]
        
        try:
            # Try to create or update table
            created_table = client.create_or_update(table_entity)
            action = "created_or_updated"
            
            # Add tags if provided
            if metadata.get("tags") and self.config.push_metadata:
                self._add_tags(table_fqn, metadata["tags"])
            
            # Add owner if provided
            if metadata.get("owner") and self.config.push_metadata:
                self._set_owner(created_table, metadata["owner"])
            
            logger.info(f"Successfully registered table in OpenMetadata: {table_fqn}")
            
            return {
                "status": "success",
                "action": action,
                "service": service_name,
                "database": database_name,
                "table": table_name,
                "fqn": table_fqn,
                "id": str(created_table.id) if hasattr(created_table, "id") else None,
            }
        except Exception as e:
            logger.error(f"Failed to register table in OpenMetadata: {e}")
            return {
                "status": "failed",
                "error": str(e),
            }
    
    def publish_lineage(
        self,
        lineage_info: LineageInfo,
    ) -> Dict[str, Any]:
        """Publish lineage information to OpenMetadata.
        
        Args:
            lineage_info: Lineage information
        
        Returns:
            Dictionary with lineage publication result
        """
        if not self.config.push_lineage:
            return {"status": "skipped", "reason": "lineage push disabled"}
        
        try:
            from metadata.generated.schema.entity.data.table import Table
            from metadata.generated.schema.type.entityLineage import (
                EntitiesEdge,
                LineageDetails,
            )
            from metadata.generated.schema.type.entityReference import EntityReference
        except ImportError:
            raise ImportError(
                "openmetadata-ingestion is required. Install with: pip install openmetadata-ingestion"
            )
        
        client = self._get_client()
        
        # Get target table entity
        target_fqn = self._build_fqn(lineage_info.target_dataset, lineage_info.target_type)
        
        try:
            target_table = client.get_by_name(
                entity=Table,
                fqn=target_fqn,
            )
            
            # Build source entity reference
            source_fqn = None
            if lineage_info.source_dataset:
                source_fqn = self._build_fqn(
                    lineage_info.source_dataset,
                    lineage_info.source_type,
                )
            
            # Create lineage edge
            if source_fqn:
                try:
                    source_table = client.get_by_name(
                        entity=Table,
                        fqn=source_fqn,
                    )
                    
                    # Add lineage edge
                    lineage_edge = EntitiesEdge(
                        fromEntity=EntityReference(
                            id=source_table.id,
                            type="table",
                            fullyQualifiedName=source_fqn,
                        ),
                        toEntity=EntityReference(
                            id=target_table.id,
                            type="table",
                            fullyQualifiedName=target_fqn,
                        ),
                        lineageDetails=LineageDetails(
                            pipeline=EntityReference(
                                type="pipeline",
                                fullyQualifiedName=lineage_info.pipeline_name,
                            ),
                            description=f"Ingestion from {lineage_info.source_type} to {lineage_info.target_type}",
                        ),
                    )
                    
                    # Add lineage using API
                    client.add_lineage(lineage_edge)
                    
                    logger.info(
                        f"Published lineage in OpenMetadata: {source_fqn} -> {target_fqn}"
                    )
                    
                    return {
                        "status": "success",
                        "source_fqn": source_fqn,
                        "target_fqn": target_fqn,
                    }
                except Exception as e:
                    logger.warning(f"Could not create lineage edge: {e}")
                    return {
                        "status": "partial",
                        "error": str(e),
                        "note": "Target registered but lineage edge not created",
                    }
            else:
                return {
                    "status": "success",
                    "target_fqn": target_fqn,
                    "note": "No source dataset provided, lineage edge not created",
                }
        except Exception as e:
            logger.error(f"Failed to publish lineage to OpenMetadata: {e}")
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
        """Update dataset metadata in OpenMetadata.
        
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
        
        try:
            from metadata.generated.schema.entity.data.table import Table
        except ImportError:
            raise ImportError(
                "openmetadata-ingestion is required. Install with: pip install openmetadata-ingestion"
            )
        
        client = self._get_client()
        
        try:
            # Get table entity
            table = client.get_by_name(
                entity=Table,
                fqn=dataset_name,
            )
            
            # Add tags
            if tags:
                self._add_tags(dataset_name, tags)
            
            # Set owner
            if owner:
                self._set_owner(table, owner)
            
            # Add classification tags
            if classification:
                self._add_tags(dataset_name, classification)
            
            logger.info(f"Updated metadata for OpenMetadata table: {dataset_name}")
            
            return {
                "status": "success",
                "fqn": dataset_name,
            }
        except Exception as e:
            logger.error(f"Failed to update metadata in OpenMetadata: {e}")
            return {
                "status": "failed",
                "error": str(e),
            }
    
    def test_connection(self) -> bool:
        """Test connection to OpenMetadata.
        
        Returns:
            True if connection successful
        """
        try:
            client = self._get_client()
            # Try to get server version to test connection
            health = client.health_check()
            logger.info("Successfully connected to OpenMetadata")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to OpenMetadata: {e}")
            return False
    
    def _ensure_service_exists(
        self,
        service_name: str,
        service_type: str = "databaseService",
    ) -> Any:
        """Ensure database service exists in OpenMetadata.
        
        Args:
            service_name: Service name
            service_type: Service type
        
        Returns:
            Service entity
        """
        try:
            from metadata.generated.schema.entity.services.databaseService import (
                DatabaseService,
                DatabaseConnection,
                DatabaseServiceType,
            )
            from metadata.generated.schema.entity.services.connections.database.common.basicAuth import (
                BasicAuth,
            )
        except ImportError:
            raise ImportError(
                "openmetadata-ingestion is required. Install with: pip install openmetadata-ingestion"
            )
        
        client = self._get_client()
        
        try:
            # Try to get existing service
            service = client.get_by_name(
                entity=DatabaseService,
                fqn=service_name,
            )
            return service
        except Exception:
            # Service doesn't exist, create it
            service = DatabaseService(
                name=service_name,
                serviceType=DatabaseServiceType.CustomDatabase,
                connection=DatabaseConnection(),
            )
            
            created_service = client.create_or_update(service)
            logger.info(f"Created OpenMetadata service: {service_name}")
            return created_service
    
    def _ensure_database_exists(
        self,
        service_name: str,
        database_name: str,
    ) -> Any:
        """Ensure database exists in OpenMetadata.
        
        Args:
            service_name: Service name
            database_name: Database name
        
        Returns:
            Database entity
        """
        try:
            from metadata.generated.schema.entity.data.database import Database
            from metadata.generated.schema.entity.services.databaseService import DatabaseService
            from metadata.generated.schema.type.entityReference import EntityReference
        except ImportError:
            raise ImportError(
                "openmetadata-ingestion is required. Install with: pip install openmetadata-ingestion"
            )
        
        client = self._get_client()
        
        database_fqn = f"{service_name}.{database_name}"
        
        try:
            # Try to get existing database
            database = client.get_by_name(
                entity=Database,
                fqn=database_fqn,
            )
            return database
        except Exception:
            # Database doesn't exist, create it
            service = client.get_by_name(
                entity=DatabaseService,
                fqn=service_name,
            )
            
            database = Database(
                name=database_name,
                fullyQualifiedName=database_fqn,
                service=EntityReference(
                    id=service.id,
                    type="databaseService",
                    fullyQualifiedName=service_name,
                ),
            )
            
            created_database = client.create_or_update(database)
            logger.info(f"Created OpenMetadata database: {database_fqn}")
            return created_database
    
    def _add_tags(self, table_fqn: str, tags: List[str]) -> None:
        """Add tags to a table in OpenMetadata.
        
        Args:
            table_fqn: Table fully qualified name
            tags: List of tags
        """
        try:
            from metadata.generated.schema.entity.data.table import Table
            from metadata.generated.schema.type.tagLabel import TagLabel
        except ImportError:
            return
        
        client = self._get_client()
        
        try:
            # Get table
            table = client.get_by_name(
                entity=Table,
                fqn=table_fqn,
            )
            
            # Build tag labels
            tag_labels = []
            for tag in tags:
                tag_labels.append(
                    TagLabel(
                        tagFQN=f"Dativo.{tag}",
                        source="Classification",
                    )
                )
            
            # Update table with tags
            table.tags = tag_labels
            client.create_or_update(table)
            
        except Exception as e:
            logger.warning(f"Failed to add tags to OpenMetadata table: {e}")
    
    def _set_owner(self, table: Any, owner: str) -> None:
        """Set owner for a table in OpenMetadata.
        
        Args:
            table: Table entity
            owner: Owner email/username
        """
        try:
            from metadata.generated.schema.type.entityReference import EntityReference
        except ImportError:
            return
        
        client = self._get_client()
        
        try:
            # Set owner
            table.owner = EntityReference(
                type="user",
                fullyQualifiedName=owner,
            )
            client.create_or_update(table)
        except Exception as e:
            logger.warning(f"Failed to set owner in OpenMetadata: {e}")
    
    def _build_fqn(self, dataset_name: str, dataset_type: str) -> str:
        """Build fully qualified name for a dataset.
        
        Args:
            dataset_name: Dataset name
            dataset_type: Dataset type (source or target type)
        
        Returns:
            Fully qualified name
        """
        # Map dataset type to service name
        service_name = f"{dataset_type}_service"
        
        # If dataset name already has service prefix, use it
        if "." in dataset_name:
            return dataset_name
        
        # Otherwise, build FQN with default structure
        return f"{service_name}.default.{dataset_name}"
    
    def _map_type_to_openmetadata(self, field_type: str) -> str:
        """Map field type to OpenMetadata DataType.
        
        Args:
            field_type: Field type from asset definition
        
        Returns:
            OpenMetadata DataType enum value
        """
        try:
            from metadata.generated.schema.entity.data.table import DataType
        except ImportError:
            return "STRING"
        
        type_mapping = {
            "string": DataType.STRING,
            "integer": DataType.BIGINT,
            "long": DataType.BIGINT,
            "float": DataType.DOUBLE,
            "double": DataType.DOUBLE,
            "boolean": DataType.BOOLEAN,
            "date": DataType.DATE,
            "timestamp": DataType.TIMESTAMP,
            "datetime": DataType.TIMESTAMP,
            "array": DataType.ARRAY,
            "object": DataType.STRUCT,
        }
        return type_mapping.get(field_type.lower(), DataType.STRING)
