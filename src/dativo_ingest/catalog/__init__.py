"""Data catalog integration for lineage and metadata push."""

from .base import BaseCatalog
from .factory import CatalogFactory

__all__ = ["BaseCatalog", "CatalogFactory"]
