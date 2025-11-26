"""Databricks Unity Catalog integration."""

import logging
from typing import Any, Dict, List, Optional

from .base import BaseCatalogClient, CatalogConfig, LineageInfo

logger = logging.getLogger(__name__)


class UnityCatalogClient(BaseCatalogClient):
    """Databricks Unity Catalog client."""
    
    def __init__(self, config: CatalogConfig):
        """Initialize Unity Catalog client.
        
        Args:
            config: Catalog configuration
        """
        super().__init__(config)
        self._session = None
    
    def _validate_config(self) -> None:
        """Validate Unity Catalog-specific configuration."""
        if not self.config.workspace_url:
            raise ValueError("workspace_url is required for Unity Catalog")
        
        if not self.config.token:
            raise ValueError("token (Databricks access token) is required for Unity Catalog")
        
        if not self.config.catalog_name:
            # Use default catalog name
            self.config.catalog_name = "main"
    
    def _get_session(self):
        """Get or create HTTP session with authentication."""
        if self._session is None:
            try:
                import requests
            except ImportError:
                raise ImportError(
                    "requests is required for Unity Catalog integration. "
                    "Install with: pip install requests"
                )
            
            self._session = requests.Session()
            self._session.headers.update({
                "Authorization": f"Bearer {self.config.token}",
                "Content-Type": "application/json",
            })
        return self._session
    
    def _get_api_url(self, endpoint: str) -> str:
        """Get full API URL for an endpoint.
        
        Args:
            endpoint: API endpoint path
        
        Returns:
            Full URL
        """
        base_url = self.config.workspace_url.rstrip("/")
        endpoint = endpoint.lstrip("/")
        return f"{base_url}/api/2.1/unity-catalog/{endpoint}"
    
    def register_dataset(
        self,
        dataset_name: str,
        schema: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Register or update a table in Unity Catalog.
        
        Args:
            dataset_name: Table name (format: "catalog.schema.table")
            schema: List of field definitions
            metadata: Additional metadata
        
        Returns:
            Dictionary with registration result
        """
        session = self._get_session()
        metadata = metadata or {}
        
        # Parse dataset name
        parts = dataset_name.split(".")
        if len(parts) >= 3:
            catalog_name = parts[0]
            schema_name = parts[1]
            table_name = ".".join(parts[2:])
        elif len(parts) == 2:
            catalog_name = self.config.catalog_name
            schema_name = parts[0]
            table_name = parts[1]
        else:
            catalog_name = self.config.catalog_name
            schema_name = "default"
            table_name = dataset_name
        
        # Convert schema to Unity Catalog format
        uc_columns = []
        for field in schema:
            column = {
                "name": field.get("name", ""),
                "type_text": self._map_type_to_unity(field.get("type", "string")),
                "type_name": self._get_type_name(field.get("type", "string")),
                "position": field.get("position", len(uc_columns)),
                "nullable": not field.get("required", False),
            }
            if field.get("description"):
                column["comment"] = field["description"]
            uc_columns.append(column)
        
        # Ensure catalog and schema exist
        self._ensure_catalog_exists(catalog_name)
        self._ensure_schema_exists(catalog_name, schema_name)
        
        # Build table request
        table_request = {
            "name": table_name,
            "catalog_name": catalog_name,
            "schema_name": schema_name,
            "table_type": metadata.get("table_type", "EXTERNAL"),
            "data_source_format": metadata.get("data_source_format", "PARQUET"),
            "columns": uc_columns,
            "storage_location": metadata.get("location", ""),
        }
        
        if metadata.get("description"):
            table_request["comment"] = metadata["description"]
        
        # Add properties
        properties = {}
        if metadata.get("owner"):
            properties["owner"] = metadata["owner"]
        if metadata.get("classification"):
            properties["classification"] = ",".join(metadata["classification"]) if isinstance(metadata["classification"], list) else metadata["classification"]
        if metadata.get("custom_metadata"):
            properties.update(metadata["custom_metadata"])
        
        if properties:
            table_request["properties"] = properties
        
        # Try to create or update table
        full_table_name = f"{catalog_name}.{schema_name}.{table_name}"
        
        try:
            # Check if table exists
            get_url = self._get_api_url(f"tables/{full_table_name}")
            response = session.get(get_url)
            
            if response.status_code == 200:
                # Table exists, update it
                update_url = self._get_api_url(f"tables/{full_table_name}")
                response = session.patch(update_url, json=table_request)
                response.raise_for_status()
                action = "updated"
            else:
                # Table doesn't exist, create it
                create_url = self._get_api_url("tables")
                response = session.post(create_url, json=table_request)
                response.raise_for_status()
                action = "created"
            
            result_data = response.json()
            
            # Add tags if provided
            if metadata.get("tags") and self.config.push_metadata:
                self._add_tags(full_table_name, metadata["tags"])
            
            logger.info(f"Successfully {action} Unity Catalog table: {full_table_name}")
            
            return {
                "status": "success",
                "action": action,
                "catalog": catalog_name,
                "schema": schema_name,
                "table": table_name,
                "full_name": full_table_name,
                "table_id": result_data.get("table_id"),
            }
        except Exception as e:
            logger.error(f"Failed to register table in Unity Catalog: {e}")
            return {
                "status": "failed",
                "error": str(e),
            }
    
    def publish_lineage(
        self,
        lineage_info: LineageInfo,
    ) -> Dict[str, Any]:
        """Publish lineage information to Unity Catalog.
        
        Args:
            lineage_info: Lineage information
        
        Returns:
            Dictionary with lineage publication result
        """
        if not self.config.push_lineage:
            return {"status": "skipped", "reason": "lineage push disabled"}
        
        session = self._get_session()
        
        # Parse target dataset name
        parts = lineage_info.target_dataset.split(".")
        if len(parts) >= 3:
            full_table_name = lineage_info.target_dataset
        else:
            full_table_name = f"{self.config.catalog_name}.default.{lineage_info.target_dataset}"
        
        # Build lineage request
        lineage_request = {
            "table_name": full_table_name,
            "notebook_id": lineage_info.execution_id or lineage_info.pipeline_name,
            "upstream_tables": [],
        }
        
        # Add source as upstream table if available
        if lineage_info.source_dataset:
            lineage_request["upstream_tables"].append({
                "table_full_name": lineage_info.source_dataset,
                "table_type": lineage_info.source_type,
            })
        
        try:
            # Unity Catalog lineage API (beta)
            url = self._get_api_url("lineage-tracking/table-lineage")
            response = session.post(url, json=lineage_request)
            
            if response.status_code in [200, 201]:
                logger.info(f"Published lineage to Unity Catalog for: {full_table_name}")
                return {
                    "status": "success",
                    "table": full_table_name,
                }
            else:
                # Lineage API might not be available, store as table properties instead
                return self._store_lineage_as_properties(lineage_info, full_table_name)
        except Exception as e:
            logger.warning(f"Failed to publish lineage via API, storing as properties: {e}")
            return self._store_lineage_as_properties(lineage_info, full_table_name)
    
    def _store_lineage_as_properties(
        self,
        lineage_info: LineageInfo,
        full_table_name: str,
    ) -> Dict[str, Any]:
        """Store lineage information as table properties.
        
        Args:
            lineage_info: Lineage information
            full_table_name: Full table name
        
        Returns:
            Dictionary with result
        """
        session = self._get_session()
        
        lineage_props = {
            "lineage.source_type": lineage_info.source_type,
            "lineage.pipeline_name": lineage_info.pipeline_name,
            "lineage.execution_time": lineage_info.execution_time.isoformat(),
        }
        
        if lineage_info.source_name:
            lineage_props["lineage.source_name"] = lineage_info.source_name
        if lineage_info.source_dataset:
            lineage_props["lineage.source_dataset"] = lineage_info.source_dataset
        if lineage_info.records_processed:
            lineage_props["lineage.records_processed"] = str(lineage_info.records_processed)
        
        try:
            url = self._get_api_url(f"tables/{full_table_name}")
            response = session.patch(url, json={"properties": lineage_props})
            response.raise_for_status()
            
            logger.info(f"Stored lineage as properties for: {full_table_name}")
            return {
                "status": "success",
                "table": full_table_name,
                "method": "properties",
            }
        except Exception as e:
            logger.error(f"Failed to store lineage as properties: {e}")
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
        """Update dataset metadata in Unity Catalog.
        
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
        
        session = self._get_session()
        
        # Parse dataset name
        parts = dataset_name.split(".")
        if len(parts) >= 3:
            full_table_name = dataset_name
        else:
            full_table_name = f"{self.config.catalog_name}.default.{dataset_name}"
        
        # Build update request
        properties = {}
        
        if owner:
            properties["owner"] = owner
        if classification:
            properties["classification"] = ",".join(classification) if isinstance(classification, list) else classification
        if custom_metadata:
            properties.update(custom_metadata)
        
        try:
            if properties:
                url = self._get_api_url(f"tables/{full_table_name}")
                response = session.patch(url, json={"properties": properties})
                response.raise_for_status()
            
            # Add tags
            if tags:
                self._add_tags(full_table_name, tags)
            
            logger.info(f"Updated metadata for Unity Catalog table: {full_table_name}")
            
            return {
                "status": "success",
                "table": full_table_name,
            }
        except Exception as e:
            logger.error(f"Failed to update metadata in Unity Catalog: {e}")
            return {
                "status": "failed",
                "error": str(e),
            }
    
    def test_connection(self) -> bool:
        """Test connection to Unity Catalog.
        
        Returns:
            True if connection successful
        """
        try:
            session = self._get_session()
            url = self._get_api_url("catalogs")
            response = session.get(url)
            response.raise_for_status()
            logger.info("Successfully connected to Unity Catalog")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Unity Catalog: {e}")
            return False
    
    def _ensure_catalog_exists(self, catalog_name: str) -> None:
        """Ensure Unity Catalog exists.
        
        Args:
            catalog_name: Catalog name
        """
        session = self._get_session()
        
        try:
            url = self._get_api_url(f"catalogs/{catalog_name}")
            response = session.get(url)
            
            if response.status_code == 404:
                # Create catalog
                create_url = self._get_api_url("catalogs")
                response = session.post(create_url, json={"name": catalog_name})
                response.raise_for_status()
                logger.info(f"Created Unity Catalog: {catalog_name}")
        except Exception as e:
            logger.warning(f"Could not ensure catalog exists: {e}")
    
    def _ensure_schema_exists(self, catalog_name: str, schema_name: str) -> None:
        """Ensure schema exists in catalog.
        
        Args:
            catalog_name: Catalog name
            schema_name: Schema name
        """
        session = self._get_session()
        
        try:
            full_schema_name = f"{catalog_name}.{schema_name}"
            url = self._get_api_url(f"schemas/{full_schema_name}")
            response = session.get(url)
            
            if response.status_code == 404:
                # Create schema
                create_url = self._get_api_url("schemas")
                response = session.post(create_url, json={
                    "name": schema_name,
                    "catalog_name": catalog_name,
                })
                response.raise_for_status()
                logger.info(f"Created Unity Catalog schema: {full_schema_name}")
        except Exception as e:
            logger.warning(f"Could not ensure schema exists: {e}")
    
    def _add_tags(self, full_table_name: str, tags: List[str]) -> None:
        """Add tags to Unity Catalog table.
        
        Args:
            full_table_name: Full table name
            tags: List of tags
        """
        # Unity Catalog uses table properties for tags
        tag_props = {}
        for i, tag in enumerate(tags[:20]):  # Limit to 20 tags
            tag_props[f"tag.{i}"] = tag
        
        if tag_props:
            session = self._get_session()
            url = self._get_api_url(f"tables/{full_table_name}")
            try:
                response = session.patch(url, json={"properties": tag_props})
                response.raise_for_status()
            except Exception as e:
                logger.warning(f"Failed to add tags to Unity Catalog table: {e}")
    
    def _map_type_to_unity(self, field_type: str) -> str:
        """Map field type to Unity Catalog type.
        
        Args:
            field_type: Field type from asset definition
        
        Returns:
            Unity Catalog type string
        """
        type_mapping = {
            "string": "STRING",
            "integer": "BIGINT",
            "long": "BIGINT",
            "float": "DOUBLE",
            "double": "DOUBLE",
            "boolean": "BOOLEAN",
            "date": "DATE",
            "timestamp": "TIMESTAMP",
            "datetime": "TIMESTAMP",
            "array": "ARRAY<STRING>",
            "object": "STRUCT",
        }
        return type_mapping.get(field_type.lower(), "STRING")
    
    def _get_type_name(self, field_type: str) -> str:
        """Get type name for Unity Catalog.
        
        Args:
            field_type: Field type from asset definition
        
        Returns:
            Type name enum value
        """
        type_name_mapping = {
            "string": "STRING",
            "integer": "LONG",
            "long": "LONG",
            "float": "DOUBLE",
            "double": "DOUBLE",
            "boolean": "BOOLEAN",
            "date": "DATE",
            "timestamp": "TIMESTAMP",
            "datetime": "TIMESTAMP",
        }
        return type_name_mapping.get(field_type.lower(), "STRING")
