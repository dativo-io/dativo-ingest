"""Base catalog client interface for data catalog integrations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class TableMetadata:
    """Metadata for a table/dataset."""

    name: str
    database: Optional[str] = None
    schema: Optional[str] = None
    description: Optional[str] = None
    owner: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)
    columns: List[Dict[str, Any]] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LineageInfo:
    """Lineage information for a data pipeline."""

    source_fqn: str  # Fully qualified name of source
    target_fqn: str  # Fully qualified name of target
    pipeline_name: str
    pipeline_description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: str = "success"  # success, failed, running
    records_read: Optional[int] = None
    records_written: Optional[int] = None
    bytes_read: Optional[int] = None
    bytes_written: Optional[int] = None
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CatalogConfig:
    """Configuration for catalog connection."""

    type: str  # openmetadata, aws_glue, databricks_unity, nessie
    connection: Dict[str, Any]
    enabled: bool = True
    push_lineage: bool = True
    push_metadata: bool = True


class BaseCatalogClient(ABC):
    """Base class for data catalog clients."""

    def __init__(self, config: CatalogConfig):
        """Initialize catalog client.

        Args:
            config: Catalog configuration
        """
        self.config = config
        self._client = None

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the catalog.

        Raises:
            Exception: If connection fails
        """
        pass

    @abstractmethod
    def create_or_update_table(self, metadata: TableMetadata) -> None:
        """Create or update table metadata in the catalog.

        Args:
            metadata: Table metadata to create or update

        Raises:
            Exception: If operation fails
        """
        pass

    @abstractmethod
    def push_lineage(self, lineage: LineageInfo) -> None:
        """Push lineage information to the catalog.

        Args:
            lineage: Lineage information to push

        Raises:
            Exception: If operation fails
        """
        pass

    @abstractmethod
    def add_tags(self, table_fqn: str, tags: Dict[str, str]) -> None:
        """Add or update tags for a table.

        Args:
            table_fqn: Fully qualified name of the table
            tags: Dictionary of tags to add/update

        Raises:
            Exception: If operation fails
        """
        pass

    @abstractmethod
    def set_owner(self, table_fqn: str, owner: str) -> None:
        """Set owner for a table.

        Args:
            table_fqn: Fully qualified name of the table
            owner: Owner identifier (email, username, etc.)

        Raises:
            Exception: If operation fails
        """
        pass

    def close(self) -> None:
        """Close catalog connection.

        Default implementation does nothing. Override if needed.
        """
        pass

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
