"""Connector registry and catalog management."""

from .catalog_loader import CatalogLoader, ExternalConnector
from .connector_registry import (
    ConnectorRegistry,
    RegistryLoadError,
    RegistryNotFoundError,
    ResolvedConnector,
    resolve_image_and_version,
)

# Public API - recommended usage
__all__ = [
    "ConnectorRegistry",
    "ResolvedConnector",
    "RegistryNotFoundError",
    "RegistryLoadError",
    # Internal APIs (exposed for CLI/testing, but not recommended for general use)
    "CatalogLoader",
    "ExternalConnector",
    "resolve_image_and_version",
]
