"""Data catalog integrations for lineage and metadata tracking."""

from .base import BaseCatalog
from .manager import CatalogManager

__all__ = ["BaseCatalog", "CatalogManager"]
