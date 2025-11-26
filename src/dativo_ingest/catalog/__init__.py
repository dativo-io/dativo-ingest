"""Data catalog integration for lineage and metadata tracking."""

from .base import BaseCatalogClient, CatalogConfig, LineageInfo, TableMetadata
from .factory import CatalogClientFactory

__all__ = [
    "BaseCatalogClient",
    "CatalogConfig",
    "LineageInfo",
    "TableMetadata",
    "CatalogClientFactory",
]
