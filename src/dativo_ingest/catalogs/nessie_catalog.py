"""Nessie catalog integration."""

import logging
from typing import Any, Dict, List, Optional

from .base import BaseCatalogClient, CatalogConfig, LineageInfo

logger = logging.getLogger(__name__)


class NessieCatalogClient(BaseCatalogClient):
    """Nessie catalog client for Apache Iceberg tables."""
    
    def __init__(self, config: CatalogConfig):
        """Initialize Nessie catalog client.
        
        Args:
            config: Catalog configuration
        """
        super().__init__(config)
        self._api_client = None
    
    def _validate_config(self) -> None:
        """Validate Nessie-specific configuration."""
        if not self.config.uri:
            raise ValueError("uri is required for Nessie catalog")
        
        if not self.config.branch:
            # Use default branch
            self.config.branch = "main"
    
    def _get_api_url(self, endpoint: str = "") -> str:
        """Get full API URL for Nessie.
        
        Args:
            endpoint: Optional endpoint path
        
        Returns:
            Full URL
        """
        base_url = self.config.uri.rstrip("/")
        
        # Ensure /api/v1 or /api/v2 is present
        if not ("/api/v1" in base_url or "/api/v2" in base_url):
            base_url = f"{base_url}/api/v1"
        
        if endpoint:
            endpoint = endpoint.lstrip("/")
            return f"{base_url}/{endpoint}"
        return base_url
    
    def _get_session(self):
        """Get HTTP session with authentication."""
        try:
            import requests
        except ImportError:
            raise ImportError(
                "requests is required for Nessie integration. "
                "Install with: pip install requests"
            )
        
        session = requests.Session()
        
        # Add authentication if token provided
        if self.config.token:
            session.headers["Authorization"] = f"Bearer {self.config.token}"
        
        session.headers["Content-Type"] = "application/json"
        
        return session
    
    def register_dataset(
        self,
        dataset_name: str,
        schema: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Register or update a table in Nessie catalog.
        
        Note: Nessie stores Iceberg table metadata. The actual table creation
        is typically done via PyIceberg or Spark. This method updates the
        table's metadata in Nessie.
        
        Args:
            dataset_name: Table name (format: "namespace.table")
            schema: List of field definitions
            metadata: Additional metadata
        
        Returns:
            Dictionary with registration result
        """
        session = self._get_session()
        metadata = metadata or {}
        
        # Parse dataset name
        parts = dataset_name.split(".")
        if len(parts) >= 2:
            namespace = ".".join(parts[:-1])
            table_name = parts[-1]
        else:
            namespace = "default"
            table_name = dataset_name
        
        # Build table key
        table_key = {
            "elements": namespace.split(".") + [table_name],
        }
        
        try:
            # Get current branch reference
            branch_url = self._get_api_url(f"trees/tree/{self.config.branch}")
            response = session.get(branch_url)
            response.raise_for_status()
            branch_data = response.json()
            current_hash = branch_data.get("hash")
            
            # Check if table exists
            content_url = self._get_api_url(
                f"trees/tree/{self.config.branch}/content/{namespace}.{table_name}"
            )
            response = session.get(content_url)
            
            if response.status_code == 200:
                # Table exists - we would update metadata here
                # For now, just log that it exists
                logger.info(f"Table already registered in Nessie: {namespace}.{table_name}")
                action = "exists"
            else:
                # Table doesn't exist in Nessie
                # In practice, table creation happens via Iceberg commits
                logger.info(f"Table will be registered on first Iceberg commit: {namespace}.{table_name}")
                action = "pending_commit"
            
            return {
                "status": "success",
                "action": action,
                "namespace": namespace,
                "table": table_name,
                "branch": self.config.branch,
                "branch_hash": current_hash,
            }
        except Exception as e:
            logger.error(f"Failed to register table in Nessie: {e}")
            return {
                "status": "failed",
                "error": str(e),
            }
    
    def publish_lineage(
        self,
        lineage_info: LineageInfo,
    ) -> Dict[str, Any]:
        """Publish lineage information to Nessie.
        
        Note: Nessie doesn't have a dedicated lineage API. This stores lineage
        as commit metadata when changes are made.
        
        Args:
            lineage_info: Lineage information
        
        Returns:
            Dictionary with lineage publication result
        """
        if not self.config.push_lineage:
            return {"status": "skipped", "reason": "lineage push disabled"}
        
        # Lineage is stored as part of Iceberg commits via table properties
        # This is handled by the IcebergCommitter, not directly via Nessie API
        
        lineage_metadata = {
            "lineage.source_type": lineage_info.source_type,
            "lineage.pipeline_name": lineage_info.pipeline_name,
            "lineage.execution_time": lineage_info.execution_time.isoformat(),
            "lineage.tenant_id": lineage_info.tenant_id,
        }
        
        if lineage_info.source_name:
            lineage_metadata["lineage.source_name"] = lineage_info.source_name
        if lineage_info.source_dataset:
            lineage_metadata["lineage.source_dataset"] = lineage_info.source_dataset
        if lineage_info.records_processed:
            lineage_metadata["lineage.records_processed"] = str(lineage_info.records_processed)
        
        logger.info(
            f"Lineage metadata prepared for Nessie commit: {lineage_info.target_dataset}"
        )
        
        return {
            "status": "success",
            "method": "iceberg_properties",
            "lineage_metadata": lineage_metadata,
            "note": "Lineage will be committed via Iceberg table properties",
        }
    
    def update_metadata(
        self,
        dataset_name: str,
        tags: Optional[List[str]] = None,
        owner: Optional[str] = None,
        classification: Optional[List[str]] = None,
        custom_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Update dataset metadata in Nessie.
        
        Note: Metadata updates are done via Iceberg table properties.
        
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
        
        # Build metadata that will be stored as Iceberg table properties
        table_properties = {}
        
        if owner:
            table_properties["owner"] = owner
        if tags:
            for i, tag in enumerate(tags):
                table_properties[f"tag.{i}"] = tag
        if classification:
            table_properties["classification"] = ",".join(classification) if isinstance(classification, list) else classification
        if custom_metadata:
            table_properties.update(custom_metadata)
        
        logger.info(
            f"Metadata prepared for Nessie/Iceberg table: {dataset_name}"
        )
        
        return {
            "status": "success",
            "method": "iceberg_properties",
            "table_properties": table_properties,
            "note": "Metadata will be committed via Iceberg table properties",
        }
    
    def test_connection(self) -> bool:
        """Test connection to Nessie catalog.
        
        Returns:
            True if connection successful
        """
        try:
            session = self._get_session()
            
            # Try to get default branch
            url = self._get_api_url("trees/tree/main")
            response = session.get(url)
            response.raise_for_status()
            
            logger.info("Successfully connected to Nessie catalog")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Nessie catalog: {e}")
            return False
    
    def get_branch_info(self) -> Dict[str, Any]:
        """Get information about the current branch.
        
        Returns:
            Dictionary with branch information
        """
        try:
            session = self._get_session()
            url = self._get_api_url(f"trees/tree/{self.config.branch}")
            response = session.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get branch info from Nessie: {e}")
            return {}
    
    def create_branch(self, branch_name: str, from_branch: str = "main") -> bool:
        """Create a new branch in Nessie.
        
        Args:
            branch_name: Name of the new branch
            from_branch: Source branch to branch from
        
        Returns:
            True if successful
        """
        try:
            session = self._get_session()
            
            # Get source branch hash
            source_url = self._get_api_url(f"trees/tree/{from_branch}")
            response = session.get(source_url)
            response.raise_for_status()
            source_data = response.json()
            source_hash = source_data.get("hash")
            
            # Create new branch
            create_url = self._get_api_url(f"trees/branch/{branch_name}")
            response = session.post(
                create_url,
                json={
                    "sourceRefName": from_branch,
                    "hash": source_hash,
                },
            )
            
            if response.status_code in [200, 201]:
                logger.info(f"Created Nessie branch: {branch_name} from {from_branch}")
                return True
            else:
                logger.warning(f"Failed to create Nessie branch: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Failed to create Nessie branch: {e}")
            return False
