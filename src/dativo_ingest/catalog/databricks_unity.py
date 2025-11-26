"""Databricks Unity Catalog integration for lineage and metadata push."""

import os
from typing import Any, Dict, List, Optional

import requests

from ..config import AssetDefinition, CatalogConfig, JobConfig
from .base import BaseCatalog


class DatabricksUnityCatalog(BaseCatalog):
    """Databricks Unity Catalog integration."""

    def __init__(
        self,
        catalog_config: CatalogConfig,
        asset_definition: AssetDefinition,
        job_config: JobConfig,
    ):
        """Initialize Databricks Unity Catalog client.

        Args:
            catalog_config: Catalog configuration
            asset_definition: Asset definition
            job_config: Job configuration
        """
        super().__init__(catalog_config, asset_definition, job_config)

        connection = catalog_config.connection
        self.workspace_url = connection.get("workspace_url") or os.getenv(
            "DATABRICKS_WORKSPACE_URL"
        )
        self.access_token = connection.get("access_token") or os.getenv(
            "DATABRICKS_ACCESS_TOKEN"
        )

        if not self.workspace_url or not self.access_token:
            raise ValueError(
                "Databricks workspace_url and access_token are required. "
                "Set them in catalog.connection or environment variables."
            )

        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def ensure_entity_exists(
        self,
        entity: Dict[str, Any],
        schema: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Ensure table exists in Unity Catalog, create if needed.

        Args:
            entity: Entity dictionary
            schema: Optional schema definition

        Returns:
            Entity information dictionary
        """
        catalog_name = self.catalog_config.connection.get("catalog", "main")
        database = entity.get("database") or self.catalog_config.database or "default"
        table_name = entity.get("name") or self.asset_definition.name
        location = entity.get("location", "")

        full_name = f"{catalog_name}.{database}.{table_name}"

        # Check if table exists
        try:
            resp = requests.get(
                f"{self.workspace_url}/api/2.1/unity-catalog/tables/{full_name}",
                headers=self.headers,
                timeout=10,
            )
            if resp.status_code == 200:
                return {"entity_id": resp.json().get("name"), "full_name": full_name}
        except Exception:
            pass

        # Create table using SQL API
        # Build CREATE TABLE statement
        columns_sql = []
        if schema:
            for field in schema:
                col_type = self._map_type_to_databricks(field.get("type", "string"))
                nullable = "" if field.get("required", False) else ""
                columns_sql.append(f"{field.get('name')} {col_type}{nullable}")

        columns_str = ", ".join(columns_sql) if columns_sql else "id string"

        create_sql = f"""
        CREATE TABLE IF NOT EXISTS {full_name}
        ({columns_str})
        USING DELTA
        LOCATION '{location}'
        """

        # Execute SQL
        try:
            resp = requests.post(
                f"{self.workspace_url}/api/2.0/sql/statements",
                json={"statement": create_sql, "warehouse_id": self.catalog_config.connection.get("warehouse_id")},
                headers=self.headers,
                timeout=30,
            )
            if resp.status_code in [200, 201]:
                return {"full_name": full_name, "name": table_name}
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to create Unity Catalog table: {e}")

        return {"full_name": full_name, "name": table_name}

    def _map_type_to_databricks(self, field_type: str) -> str:
        """Map field type to Databricks data type.

        Args:
            field_type: Field type string

        Returns:
            Databricks data type
        """
        type_mapping = {
            "string": "STRING",
            "integer": "BIGINT",
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
        """Push metadata to Unity Catalog.

        Args:
            entity: Entity dictionary
            tags: List of tags
            owners: List of owners
            description: Description
            custom_properties: Custom properties

        Returns:
            Push result dictionary
        """
        catalog_name = self.catalog_config.connection.get("catalog", "main")
        database = entity.get("database") or self.catalog_config.database or "default"
        table_name = entity.get("name") or self.asset_definition.name
        full_name = f"{catalog_name}.{database}.{table_name}"

        # Update table properties
        updates = {}
        if description:
            updates["comment"] = description
        if tags:
            updates["properties"] = {"tags": ",".join(tags)}
        if owners:
            # Set table owner
            try:
                resp = requests.patch(
                    f"{self.workspace_url}/api/2.1/unity-catalog/tables/{full_name}",
                    json={"owner": owners[0]},
                    headers=self.headers,
                    timeout=10,
                )
            except Exception:
                pass

        # Update using ALTER TABLE
        if updates:
            alter_sql = f"ALTER TABLE {full_name}"
            if "comment" in updates:
                alter_sql += f" SET TBLPROPERTIES ('comment' = '{updates['comment']}')"
            if "properties" in updates:
                for key, value in updates["properties"].items():
                    alter_sql += f" SET TBLPROPERTIES ('{key}' = '{value}')"

            try:
                resp = requests.post(
                    f"{self.workspace_url}/api/2.0/sql/statements",
                    json={"statement": alter_sql},
                    headers=self.headers,
                    timeout=10,
                )
                if resp.status_code in [200, 201]:
                    return {"status": "success", "full_name": full_name}
            except Exception as e:
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to update Unity Catalog metadata: {e}")

        return {"status": "partial", "full_name": full_name}

    def push_lineage(
        self,
        source_entities: List[Dict[str, Any]],
        target_entity: Dict[str, Any],
        operation: str = "ingest",
    ) -> Dict[str, Any]:
        """Push lineage to Unity Catalog (via table properties).

        Note: Unity Catalog lineage is typically managed through Databricks workflows.
        We store lineage information in table properties.

        Args:
            source_entities: List of source entities
            target_entity: Target entity
            operation: Operation type

        Returns:
            Lineage push result
        """
        catalog_name = self.catalog_config.connection.get("catalog", "main")
        database = target_entity.get("database") or self.catalog_config.database or "default"
        table_name = target_entity.get("name") or self.asset_definition.name
        full_name = f"{catalog_name}.{database}.{table_name}"

        source_names = [e.get("name") or e.get("location", "") for e in source_entities]
        lineage_prop = ",".join(source_names)

        alter_sql = f"""
        ALTER TABLE {full_name}
        SET TBLPROPERTIES (
            'lineage_sources' = '{lineage_prop}',
            'lineage_operation' = '{operation}'
        )
        """

        try:
            resp = requests.post(
                f"{self.workspace_url}/api/2.0/sql/statements",
                json={"statement": alter_sql},
                headers=self.headers,
                timeout=10,
            )
            if resp.status_code in [200, 201]:
                return {"status": "success", "sources_count": len(source_entities)}
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to push Unity Catalog lineage: {e}")

        return {"status": "partial", "sources_count": len(source_entities)}
