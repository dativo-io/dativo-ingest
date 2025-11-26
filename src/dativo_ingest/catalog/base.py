"""Base classes for data catalog integrations."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class CatalogLineage:
    """Represents data lineage information for a catalog."""

    source_entities: List[Dict[str, Any]]  # List of source table/entity references
    target_entity: Dict[str, Any]  # Target table/entity reference
    process_name: str  # Name of the process/job
    process_type: str = "etl"  # Type of process (etl, elt, etc.)


@dataclass
class CatalogMetadata:
    """Represents metadata to be pushed to a catalog."""

    name: str
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    owners: Optional[List[str]] = None
    schema: Optional[List[Dict[str, Any]]] = None
    custom_properties: Optional[Dict[str, Any]] = None
    classification: Optional[List[str]] = None
    cost_center: Optional[str] = None
    business_tags: Optional[List[str]] = None
    project: Optional[str] = None
    environment: Optional[str] = None


class BaseCatalog(ABC):
    """Base class for data catalog integrations."""

    def __init__(self, connection: Dict[str, Any], database: Optional[str] = None):
        """Initialize catalog connection.

        Args:
            connection: Connection configuration dictionary
            database: Optional database/schema name
        """
        self.connection = connection
        self.database = database

    @abstractmethod
    def push_lineage(self, lineage: CatalogLineage) -> None:
        """Push lineage information to the catalog.

        Args:
            lineage: Lineage information to push

        Raises:
            Exception: If lineage push fails
        """
        pass

    @abstractmethod
    def push_metadata(
        self, table_name: str, metadata: CatalogMetadata, location: Optional[str] = None
    ) -> None:
        """Push metadata to the catalog.

        Args:
            table_name: Name of the table/entity
            metadata: Metadata to push
            location: Optional physical location (S3 path, etc.)

        Raises:
            Exception: If metadata push fails
        """
        pass

    @abstractmethod
    def table_exists(self, table_name: str, database: Optional[str] = None) -> bool:
        """Check if a table exists in the catalog.

        Args:
            table_name: Name of the table
            database: Optional database/schema name

        Returns:
            True if table exists, False otherwise
        """
        pass

    @abstractmethod
    def create_table_if_not_exists(
        self,
        table_name: str,
        schema: List[Dict[str, Any]],
        location: Optional[str] = None,
        metadata: Optional[CatalogMetadata] = None,
    ) -> None:
        """Create a table in the catalog if it doesn't exist.

        Args:
            table_name: Name of the table
            schema: Schema definition (list of field definitions)
            location: Optional physical location (S3 path, etc.)
            metadata: Optional metadata to attach

        Raises:
            Exception: If table creation fails
        """
        pass
