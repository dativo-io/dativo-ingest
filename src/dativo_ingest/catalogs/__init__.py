"""Data catalog integration module for Dativo.

Supports multiple data catalog systems:
- AWS Glue
- Databricks Unity Catalog  
- Nessie (via REST API)
- OpenMetadata

Each catalog client implements the BaseCatalogClient interface for:
- Registering datasets/tables
- Publishing lineage information
- Propagating metadata (tags, owners, classifications)
"""

from .base import BaseCatalogClient, CatalogConfig, LineageInfo
from .factory import create_catalog_client

__all__ = [
    "BaseCatalogClient",
    "CatalogConfig",
    "LineageInfo",
    "create_catalog_client",
]
