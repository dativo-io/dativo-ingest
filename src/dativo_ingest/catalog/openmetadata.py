"""OpenMetadata catalog integration."""

import json
from typing import Any, Dict, List, Optional

import requests
from requests.auth import HTTPBasicAuth

from .base import BaseCatalog, CatalogLineage, CatalogMetadata


class OpenMetadataCatalog(BaseCatalog):
    """OpenMetadata catalog integration."""

    def __init__(self, connection: Dict[str, Any], database: Optional[str] = None):
        """Initialize OpenMetadata catalog connection.

        Args:
            connection: Connection configuration with:
                - api_endpoint: OpenMetadata API endpoint (e.g., http://localhost:8585/api)
                - auth_provider: Authentication provider (basic, jwt, etc.)
                - username: Username for basic auth (optional)
                - password: Password for basic auth (optional)
                - jwt_token: JWT token for JWT auth (optional)
            database: Optional database/schema name
        """
        super().__init__(connection, database)
        self.api_endpoint = connection.get("api_endpoint", "http://localhost:8585/api")
        self.auth_provider = connection.get("auth_provider", "basic")
        self.username = connection.get("username", "admin")
        self.password = connection.get("password", "admin")
        self.jwt_token = connection.get("jwt_token")
        self.database_service = connection.get("database_service", "default")
        self._session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create authenticated requests session."""
        session = requests.Session()
        if self.auth_provider == "basic":
            session.auth = HTTPBasicAuth(self.username, self.password)
        elif self.auth_provider == "jwt" and self.jwt_token:
            session.headers.update({"Authorization": f"Bearer {self.jwt_token}"})
        return session

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers."""
        headers = {"Content-Type": "application/json"}
        if self.auth_provider == "jwt" and self.jwt_token:
            headers["Authorization"] = f"Bearer {self.jwt_token}"
        return headers

    def table_exists(self, table_name: str, database: Optional[str] = None) -> bool:
        """Check if a table exists in OpenMetadata."""
        db_name = database or self.database or "default"
        fqn = f"{self.database_service}.{db_name}.{table_name}"

        try:
            response = self._session.get(
                f"{self.api_endpoint}/v1/tables/name/{fqn}",
                headers=self._get_headers(),
                timeout=10,
            )
            return response.status_code == 200
        except Exception:
            return False

    def create_table_if_not_exists(
        self,
        table_name: str,
        schema: List[Dict[str, Any]],
        location: Optional[str] = None,
        metadata: Optional[CatalogMetadata] = None,
    ) -> None:
        """Create a table in OpenMetadata if it doesn't exist."""
        db_name = self.database or "default"
        fqn = f"{self.database_service}.{db_name}.{table_name}"

        if self.table_exists(table_name, db_name):
            # Update existing table metadata
            self.push_metadata(table_name, metadata or CatalogMetadata(name=table_name), location)
            return

        # Convert schema to OpenMetadata format
        columns = []
        for field in schema:
            column = {
                "name": field.get("name", ""),
                "dataType": self._map_data_type(field.get("type", "string")),
                "description": field.get("description"),
            }
            if field.get("nullable", True):
                column["constraint"] = "NULL"
            columns.append(column)

        # Create table entity
        table_entity = {
            "name": table_name,
            "databaseSchema": fqn.rsplit(".", 1)[0],
            "columns": columns,
            "tableType": "Regular",
        }

        if location:
            table_entity["location"] = location

        if metadata:
            if metadata.description:
                table_entity["description"] = metadata.description
            if metadata.tags:
                table_entity["tags"] = [
                    {"tagFQN": tag} for tag in metadata.tags
                ]
            if metadata.owners:
                table_entity["owners"] = [
                    {"id": owner, "type": "user"} for owner in metadata.owners
                ]

        try:
            response = self._session.post(
                f"{self.api_endpoint}/v1/tables",
                json=table_entity,
                headers=self._get_headers(),
                timeout=30,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to create table in OpenMetadata: {e}") from e

    def push_metadata(
        self, table_name: str, metadata: CatalogMetadata, location: Optional[str] = None
    ) -> None:
        """Push metadata to OpenMetadata."""
        db_name = self.database or "default"
        fqn = f"{self.database_service}.{db_name}.{table_name}"

        # Get existing table
        try:
            response = self._session.get(
                f"{self.api_endpoint}/v1/tables/name/{fqn}",
                headers=self._get_headers(),
                timeout=10,
            )
            if response.status_code != 200:
                # Table doesn't exist, create it
                self.create_table_if_not_exists(
                    table_name, metadata.schema or [], location, metadata
                )
                return

            table_data = response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to get table from OpenMetadata: {e}") from e

        # Update metadata
        updates = {}
        if metadata.description:
            updates["description"] = metadata.description
        if metadata.tags:
            updates["tags"] = [{"tagFQN": tag} for tag in metadata.tags]
        if metadata.owners:
            updates["owners"] = [{"id": owner, "type": "user"} for owner in metadata.owners]

        # Add custom properties
        if metadata.custom_properties:
            updates["customProperties"] = metadata.custom_properties

        if metadata.classification:
            updates["classification"] = metadata.classification

        if updates:
            try:
                # Patch table
                response = self._session.patch(
                    f"{self.api_endpoint}/v1/tables/{table_data.get('id')}",
                    json=updates,
                    headers=self._get_headers(),
                    timeout=30,
                )
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                raise Exception(f"Failed to update table metadata in OpenMetadata: {e}") from e

    def push_lineage(self, lineage: CatalogLineage) -> None:
        """Push lineage information to OpenMetadata."""
        # OpenMetadata uses pipeline entities for lineage
        pipeline_name = lineage.process_name

        # Create or update pipeline
        pipeline_entity = {
            "name": pipeline_name,
            "service": self.database_service,
            "pipelineType": lineage.process_type,
        }

        try:
            # Check if pipeline exists
            response = self._session.get(
                f"{self.api_endpoint}/v1/pipelines/name/{self.database_service}.{pipeline_name}",
                headers=self._get_headers(),
                timeout=10,
            )

            if response.status_code != 200:
                # Create pipeline
                response = self._session.post(
                    f"{self.api_endpoint}/v1/pipelines",
                    json=pipeline_entity,
                    headers=self._get_headers(),
                    timeout=30,
                )
                response.raise_for_status()
                pipeline_data = response.json()
            else:
                pipeline_data = response.json()

            # Create lineage edges
            edges = []
            for source in lineage.source_entities:
                source_fqn = source.get("fqn") or f"{source.get('database', 'default')}.{source.get('table', '')}"
                target_fqn = lineage.target_entity.get("fqn") or f"{lineage.target_entity.get('database', 'default')}.{lineage.target_entity.get('table', '')}"

                edge = {
                    "fromEntity": f"table:{source_fqn}",
                    "toEntity": f"table:{target_fqn}",
                    "description": f"ETL process: {pipeline_name}",
                }
                edges.append(edge)

            # Add lineage
            if edges:
                lineage_payload = {
                    "edges": edges,
                    "pipeline": {"id": pipeline_data.get("id")},
                }

                response = self._session.put(
                    f"{self.api_endpoint}/v1/lineage",
                    json=lineage_payload,
                    headers=self._get_headers(),
                    timeout=30,
                )
                response.raise_for_status()

        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to push lineage to OpenMetadata: {e}") from e

    def _map_data_type(self, data_type: str) -> str:
        """Map common data types to OpenMetadata types."""
        type_mapping = {
            "string": "STRING",
            "varchar": "STRING",
            "text": "STRING",
            "int": "INT",
            "integer": "INT",
            "bigint": "BIGINT",
            "float": "FLOAT",
            "double": "DOUBLE",
            "decimal": "DECIMAL",
            "boolean": "BOOLEAN",
            "date": "DATE",
            "timestamp": "TIMESTAMP",
            "array": "ARRAY",
            "struct": "STRUCT",
            "map": "MAP",
        }
        return type_mapping.get(data_type.lower(), "STRING")
