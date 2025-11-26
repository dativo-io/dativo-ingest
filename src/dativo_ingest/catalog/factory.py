"""Factory for creating catalog instances."""

from typing import Dict, Optional

from .base import BaseCatalog
from .aws_glue import AWSGlueCatalog
from .databricks_unity import DatabricksUnityCatalog
from .nessie import NessieCatalog
from .openmetadata import OpenMetadataCatalog


class CatalogFactory:
    """Factory for creating catalog instances."""

    _catalog_classes: Dict[str, type] = {
        "aws_glue": AWSGlueCatalog,
        "databricks_unity": DatabricksUnityCatalog,
        "nessie": NessieCatalog,
        "openmetadata": OpenMetadataCatalog,
    }

    @classmethod
    def create(
        cls,
        catalog_type: str,
        connection: Dict,
        database: Optional[str] = None,
    ) -> BaseCatalog:
        """Create a catalog instance.

        Args:
            catalog_type: Type of catalog (aws_glue, databricks_unity, nessie, openmetadata)
            connection: Connection configuration dictionary
            database: Optional database/schema name

        Returns:
            Catalog instance

        Raises:
            ValueError: If catalog type is not supported
        """
        catalog_class = cls._catalog_classes.get(catalog_type.lower())
        if not catalog_class:
            raise ValueError(
                f"Unsupported catalog type: {catalog_type}. "
                f"Supported types: {', '.join(cls._catalog_classes.keys())}"
            )

        return catalog_class(connection=connection, database=database)
