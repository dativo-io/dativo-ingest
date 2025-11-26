"""OpenMetadata catalog client implementation."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseCatalogClient, LineageInfo, TableMetadata

logger = logging.getLogger(__name__)


class OpenMetadataClient(BaseCatalogClient):
    """OpenMetadata catalog client for lineage and metadata tracking."""

    def connect(self) -> None:
        """Establish connection to OpenMetadata."""
        try:
            from metadata.ingestion.ometa.ometa_api import OpenMetadata
            from metadata.generated.schema.entity.services.connections.metadata.openMetadataConnection import (
                OpenMetadataConnection,
                AuthProvider,
            )
            from metadata.generated.schema.security.client.openMetadataJWTClientConfig import (
                OpenMetadataJWTClientConfig,
            )
        except ImportError as e:
            raise ImportError(
                "OpenMetadata Python SDK is required for OpenMetadata integration. "
                "Install with: pip install 'openmetadata-ingestion[metadata]>=0.13.0'"
            ) from e

        connection_config = self.config.connection
        server_config = OpenMetadataConnection(
            hostPort=connection_config.get("host_port", "http://localhost:8585/api"),
            authProvider=AuthProvider.openmetadata,
        )

        # Add authentication if provided
        if "jwt_token" in connection_config:
            server_config.securityConfig = OpenMetadataJWTClientConfig(
                jwtToken=connection_config["jwt_token"]
            )

        try:
            self._client = OpenMetadata(server_config)
            logger.info("Connected to OpenMetadata catalog")
        except Exception as e:
            logger.error(f"Failed to connect to OpenMetadata: {e}")
            raise

    def create_or_update_table(self, metadata: TableMetadata) -> None:
        """Create or update table metadata in OpenMetadata.

        Args:
            metadata: Table metadata to create or update
        """
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first.")

        try:
            from metadata.generated.schema.entity.data.table import Table, Column
            from metadata.generated.schema.type.entityReference import EntityReference
            from metadata.generated.schema.api.data.createTable import CreateTableRequest
            from metadata.utils.fqn import build

            # Build fully qualified name
            service_name = self.config.connection.get(
                "service_name", "dativo_iceberg_service"
            )
            database_name = metadata.database or "default"
            schema_name = metadata.schema or "default"

            fqn = build(
                self._client,
                entity_type=Table,
                service_name=service_name,
                database_name=database_name,
                schema_name=schema_name,
                table_name=metadata.name,
            )

            # Check if table exists
            existing_table = None
            try:
                existing_table = self._client.get_by_name(
                    entity=Table, fqn=fqn, fields=["tags", "owner"]
                )
            except Exception:
                pass

            if existing_table:
                # Update existing table
                logger.info(f"Updating existing table in OpenMetadata: {fqn}")
                
                # Update description
                if metadata.description:
                    existing_table.description = metadata.description

                # Update columns if provided
                if metadata.columns:
                    columns = []
                    for col in metadata.columns:
                        from metadata.generated.schema.entity.data.table import (
                            DataType,
                        )

                        # Map column types
                        col_type = col.get("type", "STRING").upper()
                        try:
                            data_type = DataType[col_type]
                        except KeyError:
                            data_type = DataType.STRING

                        column = Column(
                            name=col["name"],
                            dataType=data_type,
                            description=col.get("description"),
                        )
                        columns.append(column)
                    existing_table.columns = columns

                # Use patch method to update
                self._client.patch(entity=Table, source=existing_table, destination=existing_table)
            else:
                # Create new table
                logger.info(f"Creating new table in OpenMetadata: {fqn}")

                # Build column definitions
                columns = []
                for col in metadata.columns:
                    from metadata.generated.schema.entity.data.table import DataType

                    col_type = col.get("type", "STRING").upper()
                    try:
                        data_type = DataType[col_type]
                    except KeyError:
                        data_type = DataType.STRING

                    column = Column(
                        name=col["name"],
                        dataType=data_type,
                        description=col.get("description"),
                    )
                    columns.append(column)

                # Create table request
                create_table = CreateTableRequest(
                    name=metadata.name,
                    databaseSchema=f"{service_name}.{database_name}.{schema_name}",
                    columns=columns,
                    description=metadata.description,
                )

                self._client.create_or_update(create_table)

            logger.info(f"Table metadata updated in OpenMetadata: {fqn}")

        except Exception as e:
            logger.error(f"Failed to create/update table in OpenMetadata: {e}")
            raise

    def push_lineage(self, lineage: LineageInfo) -> None:
        """Push lineage information to OpenMetadata.

        Args:
            lineage: Lineage information to push
        """
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first.")

        try:
            from metadata.generated.schema.api.lineage.addLineage import AddLineageRequest
            from metadata.generated.schema.type.entityReference import EntityReference
            from metadata.generated.schema.entity.data.table import Table

            # Create lineage edge from source to target
            lineage_request = AddLineageRequest(
                edge={
                    "fromEntity": EntityReference(
                        id=None, type="table", fullyQualifiedName=lineage.source_fqn
                    ),
                    "toEntity": EntityReference(
                        id=None, type="table", fullyQualifiedName=lineage.target_fqn
                    ),
                    "lineageDetails": {
                        "pipeline": {
                            "name": lineage.pipeline_name,
                            "description": lineage.pipeline_description,
                        },
                        "source": "dativo_ingestion",
                    },
                }
            )

            self._client.add_lineage(lineage_request)
            logger.info(
                f"Lineage pushed to OpenMetadata: {lineage.source_fqn} -> {lineage.target_fqn}"
            )

        except Exception as e:
            logger.warning(f"Failed to push lineage to OpenMetadata: {e}")
            # Don't raise - lineage is optional

    def add_tags(self, table_fqn: str, tags: Dict[str, str]) -> None:
        """Add or update tags for a table.

        Args:
            table_fqn: Fully qualified name of the table
            tags: Dictionary of tags to add/update
        """
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first.")

        try:
            from metadata.generated.schema.entity.data.table import Table
            from metadata.generated.schema.type.tagLabel import (
                TagLabel,
                LabelType,
                State,
            )

            # Get existing table
            table = self._client.get_by_name(entity=Table, fqn=table_fqn, fields=["tags"])

            # Build tag labels
            tag_labels = []
            for key, value in tags.items():
                # Format: "tag_name" or "category.tag_name"
                tag_fqn = f"{key}:{value}" if value else key
                tag_label = TagLabel(
                    tagFQN=tag_fqn,
                    labelType=LabelType.Automated,
                    state=State.Suggested,
                    source="dativo_ingestion",
                )
                tag_labels.append(tag_label)

            # Update table tags
            table.tags = tag_labels
            self._client.patch(entity=Table, source=table, destination=table)
            
            logger.info(f"Tags added to table in OpenMetadata: {table_fqn}")

        except Exception as e:
            logger.warning(f"Failed to add tags to OpenMetadata: {e}")
            # Don't raise - tags are optional

    def set_owner(self, table_fqn: str, owner: str) -> None:
        """Set owner for a table.

        Args:
            table_fqn: Fully qualified name of the table
            owner: Owner identifier (email or username)
        """
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first.")

        try:
            from metadata.generated.schema.entity.data.table import Table
            from metadata.generated.schema.type.entityReference import EntityReference
            from metadata.generated.schema.entity.teams.user import User

            # Get existing table
            table = self._client.get_by_name(entity=Table, fqn=table_fqn, fields=["owner"])

            # Try to find user by email or name
            try:
                user = self._client.get_by_name(entity=User, fqn=owner)
                if user:
                    table.owner = EntityReference(
                        id=user.id, type="user", name=owner
                    )
                    self._client.patch(entity=Table, source=table, destination=table)
                    logger.info(f"Owner set for table in OpenMetadata: {table_fqn}")
            except Exception as user_error:
                logger.warning(
                    f"User '{owner}' not found in OpenMetadata, skipping owner assignment: {user_error}"
                )

        except Exception as e:
            logger.warning(f"Failed to set owner in OpenMetadata: {e}")
            # Don't raise - owner is optional
