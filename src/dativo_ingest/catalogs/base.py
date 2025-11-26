"""Base classes and interfaces for data catalog integration."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CatalogConfig(BaseModel):
    """Configuration for data catalog connection."""

    type: str = Field(..., description="Catalog type: glue, unity, nessie, openmetadata")
    enabled: bool = Field(default=True, description="Enable catalog integration")
    
    # Common connection parameters
    uri: Optional[str] = Field(None, description="Catalog URI/endpoint")
    
    # Authentication
    auth_type: Optional[str] = Field(None, description="Authentication type: token, aws, oauth, etc.")
    token: Optional[str] = Field(None, description="API token or access token")
    
    # AWS-specific
    aws_region: Optional[str] = Field(None, description="AWS region for Glue")
    aws_account_id: Optional[str] = Field(None, description="AWS account ID")
    
    # Databricks-specific
    workspace_url: Optional[str] = Field(None, description="Databricks workspace URL")
    catalog_name: Optional[str] = Field(None, description="Unity Catalog name")
    
    # Nessie-specific
    branch: Optional[str] = Field(None, description="Nessie branch name")
    
    # OpenMetadata-specific
    server_config: Optional[Dict[str, Any]] = Field(None, description="OpenMetadata server configuration")
    
    # Additional configuration
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")
    
    # Lineage configuration
    push_lineage: bool = Field(default=True, description="Push lineage information")
    push_schema: bool = Field(default=True, description="Push schema information")
    push_metadata: bool = Field(default=True, description="Push tags, owners, and other metadata")


class LineageInfo(BaseModel):
    """Lineage information for data pipeline execution."""
    
    # Source information
    source_type: str = Field(..., description="Source system type (e.g., postgres, stripe, csv)")
    source_name: Optional[str] = Field(None, description="Source database/service name")
    source_dataset: Optional[str] = Field(None, description="Source table/object/file name")
    source_columns: Optional[List[str]] = Field(default_factory=list, description="Source columns")
    
    # Target information
    target_type: str = Field(..., description="Target system type (e.g., iceberg, s3)")
    target_name: Optional[str] = Field(None, description="Target database/warehouse name")
    target_dataset: str = Field(..., description="Target table/dataset name")
    target_columns: Optional[List[str]] = Field(default_factory=list, description="Target columns")
    
    # Pipeline execution information
    pipeline_name: str = Field(..., description="Pipeline/job name")
    tenant_id: str = Field(..., description="Tenant ID")
    execution_id: Optional[str] = Field(None, description="Unique execution ID")
    execution_time: datetime = Field(default_factory=datetime.utcnow, description="Execution timestamp")
    
    # Statistics
    records_processed: Optional[int] = Field(None, description="Number of records processed")
    bytes_processed: Optional[int] = Field(None, description="Number of bytes processed")
    
    # Transformation information
    transformation_type: Optional[str] = Field(None, description="Type of transformation applied")
    transformation_description: Optional[str] = Field(None, description="Description of transformation")
    
    # Additional metadata
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional lineage metadata")


class BaseCatalogClient(ABC):
    """Abstract base class for data catalog clients."""
    
    def __init__(self, config: CatalogConfig):
        """Initialize catalog client.
        
        Args:
            config: Catalog configuration
        """
        self.config = config
        self._validate_config()
    
    @abstractmethod
    def _validate_config(self) -> None:
        """Validate catalog-specific configuration.
        
        Raises:
            ValueError: If configuration is invalid
        """
        pass
    
    @abstractmethod
    def register_dataset(
        self,
        dataset_name: str,
        schema: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Register or update a dataset in the catalog.
        
        Args:
            dataset_name: Fully qualified dataset name (e.g., "database.schema.table")
            schema: List of field definitions with name, type, description, etc.
            metadata: Additional metadata (tags, owner, description, etc.)
        
        Returns:
            Dictionary with registration result including dataset_id, url, etc.
        """
        pass
    
    @abstractmethod
    def publish_lineage(
        self,
        lineage_info: LineageInfo,
    ) -> Dict[str, Any]:
        """Publish lineage information to the catalog.
        
        Args:
            lineage_info: Lineage information for the pipeline execution
        
        Returns:
            Dictionary with lineage publication result
        """
        pass
    
    @abstractmethod
    def update_metadata(
        self,
        dataset_name: str,
        tags: Optional[List[str]] = None,
        owner: Optional[str] = None,
        classification: Optional[List[str]] = None,
        custom_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Update dataset metadata in the catalog.
        
        Args:
            dataset_name: Fully qualified dataset name
            tags: List of tags to apply
            owner: Owner email or username
            classification: Data classification labels
            custom_metadata: Additional custom metadata
        
        Returns:
            Dictionary with metadata update result
        """
        pass
    
    @abstractmethod
    def test_connection(self) -> bool:
        """Test connection to the catalog.
        
        Returns:
            True if connection successful, False otherwise
        """
        pass
    
    def get_dataset_fqn(
        self,
        dataset_name: str,
        domain: Optional[str] = None,
        namespace: Optional[str] = None,
    ) -> str:
        """Get fully qualified name for a dataset.
        
        Args:
            dataset_name: Base dataset name
            domain: Optional domain/database name
            namespace: Optional namespace/schema name
        
        Returns:
            Fully qualified dataset name
        """
        parts = []
        if domain:
            parts.append(domain)
        if namespace:
            parts.append(namespace)
        parts.append(dataset_name)
        return ".".join(parts)
