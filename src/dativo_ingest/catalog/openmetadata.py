"""OpenMetadata catalog integration for lineage and metadata push."""

import os
from typing import Any, Dict, List, Optional

import requests

from ..config import AssetDefinition, CatalogConfig, JobConfig
from .base import BaseCatalog


class OpenMetadataCatalog(BaseCatalog):
    """OpenMetadata catalog integration."""

    def __init__(
        self,
        catalog_config: CatalogConfig,
        asset_definition: AssetDefinition,
        job_config: JobConfig,
    ):
        """Initialize OpenMetadata catalog client.

        Args:
            catalog_config: Catalog configuration
            asset_definition: Asset definition
            job_config: Job configuration
        """
        super().__init__(catalog_config, asset_definition, job_config)

        connection = catalog_config.connection
        self.api_url = connection.get("api_url") or os.getenv(
            "OPENMETADATA_API_URL", "http://localhost:8585/api"
        )
        self.auth_token = connection.get("auth_token") or os.getenv(
            "OPENMETADATA_AUTH_TOKEN"
        )

        if not self.auth_token:
            raise ValueError(
                "OpenMetadata auth_token is required. "
                "Set it in catalog.connection.auth_token or OPENMETADATA_AUTH_TOKEN env var."
            )

        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.auth_token}",
        }

    def _get_or_create_service(self, service_type: str, service_name: str) -> str:
        """Get or create a service in OpenMetadata.

        Args:
            service_type: Service type (e.g., 'databaseService', 'objectStoreService')
            service_name: Service name

        Returns:
            Service FQN (fully qualified name)
        """
        # Try to get existing service
        try:
            resp = requests.get(
                f"{self.api_url}/v1/services/{service_type}/name/{service_name}",
                headers=self.headers,
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json().get("fullyQualifiedName", service_name)
        except Exception:
            pass

        # Create service if it doesn't exist
        service_config = {
            "name": service_name,
            "serviceType": service_type,
            "connection": {},
        }

        try:
            resp = requests.post(
                f"{self.api_url}/v1/services/{service_type}",
                json=service_config,
                headers=self.headers,
                timeout=10,
            )
            if resp.status_code in [200, 201]:
                return resp.json().get("fullyQualifiedName", service_name)
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to create OpenMetadata service: {e}")

        return service_name

    def ensure_entity_exists(
        self,
        entity: Dict[str, Any],
        schema: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Ensure table exists in OpenMetadata, create if needed.

        Args:
            entity: Entity dictionary
            schema: Optional schema definition

        Returns:
            Entity information dictionary
        """
        database = entity.get("database") or self.catalog_config.database or "default"
        table_name = entity.get("name") or self.asset_definition.name

        # Get or create database service
        service_fqn = self._get_or_create_service("databaseService", "dativo-ingest")

        # Try to get existing table
        fqn = f"{service_fqn}.{database}.{table_name}"
        try:
            resp = requests.get(
                f"{self.api_url}/v1/tables/name/{fqn}",
                headers=self.headers,
                timeout=10,
            )
            if resp.status_code == 200:
                return {
                    "entity_id": resp.json().get("id"),
                    "fqn": fqn,
                    "name": table_name,
                }
        except Exception:
            pass

        # Create table if it doesn't exist
        table_config = {
            "name": table_name,
            "database": {"name": database, "service": {"name": service_fqn}},
            "tableType": "Regular",
        }

        if schema:
            columns = []
            for field in schema:
                columns.append(
                    {
                        "name": field.get("name"),
                        "dataType": self._map_type_to_openmetadata(
                            field.get("type", "string")
                        ),
                        "constraint": (
                            "NOT_NULL" if field.get("required", False) else "NULL"
                        ),
                    }
                )
            table_config["columns"] = columns

        try:
            resp = requests.post(
                f"{self.api_url}/v1/tables",
                json=table_config,
                headers=self.headers,
                timeout=10,
            )
            if resp.status_code in [200, 201]:
                return {
                    "entity_id": resp.json().get("id"),
                    "fqn": fqn,
                    "name": table_name,
                }
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to create OpenMetadata table: {e}")

        return {"fqn": fqn, "name": table_name}

    def _map_type_to_openmetadata(self, field_type: str) -> str:
        """Map field type to OpenMetadata data type.

        Args:
            field_type: Field type string

        Returns:
            OpenMetadata data type
        """
        type_mapping = {
            "string": "STRING",
            "integer": "INT",
            "float": "FLOAT",
            "double": "DOUBLE",
            "boolean": "BOOLEAN",
            "timestamp": "TIMESTAMP",
            "datetime": "TIMESTAMP",
            "date": "DATE",
        }
        return type_mapping.get(field_type.lower(), "STRING")

    def push_metadata(
        self,
        entity: Dict[str, Any],
        tags: Optional[List[str]] = None,
        owners: Optional[List[str]] = None,
        description: Optional[str] = None,
        custom_properties: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Push metadata to OpenMetadata.

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
        service_fqn = self._get_or_create_service("databaseService", "dativo-ingest")
        fqn = f"{service_fqn}.{database}.{table_name}"

        # Get existing table
        try:
            resp = requests.get(
                f"{self.api_url}/v1/tables/name/{fqn}",
                headers=self.headers,
                timeout=10,
            )
            if resp.status_code != 200:
                return {"status": "error", "message": f"Table not found: {fqn}"}

            table_data = resp.json()
        except Exception as e:
            return {"status": "error", "message": f"Failed to get table: {e}"}

        # Update tags
        if tags:
            tag_labels = [{"tagFQN": tag, "source": "Classification"} for tag in tags]
            table_data.setdefault("tags", []).extend(tag_labels)

        # Update owners
        if owners:
            owner_list = []
            for owner in owners:
                # Try to find user by email
                try:
                    user_resp = requests.get(
                        f"{self.api_url}/v1/users/name/{owner}",
                        headers=self.headers,
                        timeout=5,
                    )
                    if user_resp.status_code == 200:
                        owner_list.append(
                            {"id": user_resp.json().get("id"), "type": "user"}
                        )
                except Exception:
                    # If user not found, create a simple owner reference
                    owner_list.append({"name": owner, "type": "user"})
            if owner_list:
                table_data["owners"] = owner_list

        # Update description
        if description:
            table_data["description"] = description

        # Update custom properties
        if custom_properties:
            table_data.setdefault("extension", {}).update(custom_properties)

        # Patch table
        try:
            resp = requests.patch(
                f"{self.api_url}/v1/tables/{table_data.get('id')}",
                json=table_data,
                headers=self.headers,
                timeout=10,
            )
            if resp.status_code in [200, 201]:
                return {
                    "status": "success",
                    "entity_id": table_data.get("id"),
                    "fqn": fqn,
                }
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to update OpenMetadata table metadata: {e}")

        return {"status": "partial", "fqn": fqn}

    def push_lineage(
        self,
        source_entities: List[Dict[str, Any]],
        target_entity: Dict[str, Any],
        operation: str = "ingest",
    ) -> Dict[str, Any]:
        """Push lineage to OpenMetadata.

        Args:
            source_entities: List of source entities
            target_entity: Target entity
            operation: Operation type

        Returns:
            Lineage push result
        """
        database = (
            target_entity.get("database") or self.catalog_config.database or "default"
        )
        table_name = target_entity.get("name") or self.asset_definition.name
        service_fqn = self._get_or_create_service("databaseService", "dativo-ingest")
        target_fqn = f"{service_fqn}.{database}.{table_name}"

        # Build edges for lineage
        edges = []
        for source_entity in source_entities:
            source_fqn = source_entity.get("fqn") or source_entity.get("name")
            if source_fqn:
                edges.append(
                    {
                        "fromEntity": source_fqn,
                        "toEntity": target_fqn,
                        "description": f"{operation} operation",
                    }
                )

        if not edges:
            return {"status": "skipped", "message": "No source entities to link"}

        # Push lineage
        lineage_config = {
            "description": f"Lineage from {operation}",
            "edges": edges,
        }

        try:
            resp = requests.put(
                f"{self.api_url}/v1/lineage/table/name/{target_fqn}",
                json=lineage_config,
                headers=self.headers,
                timeout=10,
            )
            if resp.status_code in [200, 201]:
                return {"status": "success", "edges_count": len(edges)}
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to push OpenMetadata lineage: {e}")

        return {"status": "partial", "edges_count": len(edges)}
