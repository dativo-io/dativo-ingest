"""Factory for creating catalog clients."""

import logging
from typing import Optional

from .base import BaseCatalogClient, CatalogConfig

logger = logging.getLogger(__name__)


def create_catalog_client(config: CatalogConfig) -> Optional[BaseCatalogClient]:
    """Create a catalog client based on configuration.
    
    Args:
        config: Catalog configuration
    
    Returns:
        Catalog client instance or None if disabled
    
    Raises:
        ValueError: If catalog type is unsupported
    """
    if not config.enabled:
        logger.info("Catalog integration is disabled")
        return None
    
    catalog_type = config.type.lower()
    
    if catalog_type == "glue":
        from .aws_glue import GlueCatalogClient
        return GlueCatalogClient(config)
    
    elif catalog_type in ["unity", "unity_catalog", "databricks"]:
        from .unity_catalog import UnityCatalogClient
        return UnityCatalogClient(config)
    
    elif catalog_type == "nessie":
        from .nessie_catalog import NessieCatalogClient
        return NessieCatalogClient(config)
    
    elif catalog_type in ["openmetadata", "open_metadata"]:
        from .openmetadata import OpenMetadataCatalogClient
        return OpenMetadataCatalogClient(config)
    
    else:
        raise ValueError(
            f"Unsupported catalog type: {catalog_type}. "
            f"Supported types: glue, unity, nessie, openmetadata"
        )
