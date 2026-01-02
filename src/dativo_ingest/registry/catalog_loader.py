"""External connector catalog loader for Airbyte, Singer, Meltano, etc."""

import json
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from .adapters.airbyte_adapter import AirbyteAdapter
from .adapters.meltano_adapter import MeltanoAdapter
from .adapters.singer_adapter import SingerAdapter


class ExternalConnector(BaseModel):
    """Normalized representation of an external connector from a catalog."""

    name: str
    external_id: str
    docker_image_default: Optional[str] = None
    version_default: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)
    source_of_truth: str = "external"  # airbyte, singer, meltano, native
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CatalogLoader:
    """Loads and manages external connector catalogs (e.g., Airbyte's catalog)."""

    def __init__(self, catalogs_dir: Optional[Path] = None):
        """Initialize catalog loader.

        Args:
            catalogs_dir: Directory containing catalog JSON files.
                         Defaults to /registry/catalogs/ or relative path.
        """
        if catalogs_dir is None:
            # Try multiple possible paths
            possible_paths = [
                Path("/app/registry/catalogs"),
                Path("registry/catalogs"),
                Path(__file__).parent.parent.parent.parent / "registry" / "catalogs",
            ]
            for path in possible_paths:
                if path.exists():
                    catalogs_dir = path
                    break

            # If still None, default to relative path
            if catalogs_dir is None:
                catalogs_dir = Path("registry/catalogs")

        self.catalogs_dir = catalogs_dir
        self.catalogs: Dict[str, List[ExternalConnector]] = {}
        if self.catalogs_dir and self.catalogs_dir.exists():
            self._load_catalogs()

    def _load_catalogs(self) -> None:
        """Load all catalog JSON files from the catalogs directory."""
        if not self.catalogs_dir or not self.catalogs_dir.exists():
            return

        for catalog_file in self.catalogs_dir.glob("*.json"):
            try:
                catalog_name = catalog_file.stem
                with open(catalog_file, "r") as f:
                    catalog_data = json.load(f)

                connectors = self._parse_catalog(catalog_data, catalog_name)
                self.catalogs[catalog_name] = connectors
            except Exception as e:
                # Log error but don't fail - catalogs are optional
                warnings.warn(
                    f"Failed to load catalog {catalog_file}: {e}", stacklevel=2
                )

    def _parse_catalog(
        self, catalog_data: Dict[str, Any], source_of_truth: str
    ) -> List[ExternalConnector]:
        """Parse catalog data into normalized ExternalConnector objects.

        Supports normalized catalog format (schema_version=1).
        Also supports raw catalog formats (e.g., Airbyte "sources" format) by
        automatically normalizing them using adapters.

        Args:
            catalog_data: Raw catalog JSON data
            source_of_truth: Name of the catalog (e.g., 'airbyte', 'singer')

        Returns:
            List of ExternalConnector objects
        """
        connectors = []

        # Normalized format with "connectors" list
        if "connectors" in catalog_data and isinstance(
            catalog_data["connectors"], list
        ):
            for item in catalog_data["connectors"]:
                connector = self._parse_connector_item(item, source_of_truth)
                if connector:
                    connectors.append(connector)

        # Fallback: Detect raw catalog formats and normalize them
        elif "sources" in catalog_data and isinstance(catalog_data["sources"], list):
            # Raw Airbyte format detected - normalize using adapter
            warnings.warn(
                f"Catalog '{source_of_truth}' appears to be in raw Airbyte format. "
                f"Normalizing automatically. For better performance, consider using "
                f"'dativo connectors sync {source_of_truth}' to pre-normalize the catalog.",
                UserWarning,
                stacklevel=3,
            )

            try:
                adapter = AirbyteAdapter()
                metadata = {
                    "fetched_at": datetime.utcnow().isoformat() + "Z",
                    "source_url": None,
                    "sha256": "",
                    "etag": None,
                    "last_modified": None,
                }
                normalized_data = adapter.normalize(catalog_data, metadata)

                # Parse normalized connectors
                if "connectors" in normalized_data and isinstance(
                    normalized_data["connectors"], list
                ):
                    for item in normalized_data["connectors"]:
                        connector = self._parse_connector_item(item, source_of_truth)
                        if connector:
                            connectors.append(connector)
            except Exception as e:
                warnings.warn(
                    f"Failed to normalize raw Airbyte catalog '{source_of_truth}': {e}. "
                    f"No connectors will be loaded from this catalog.",
                    UserWarning,
                    stacklevel=3,
                )

        return connectors

    def _parse_connector_item(
        self, item: Dict[str, Any], source_of_truth: str
    ) -> Optional[ExternalConnector]:
        """Parse a normalized connector item."""
        try:
            raw_name = item.get("name", "")
            # Normalize name: lowercase and replace spaces/dashes with underscores
            name = raw_name.lower().replace(" ", "_").replace("-", "_")

            external_id = item.get("external_id", "")
            docker_image = item.get("docker_image")
            version = item.get("version")

            # Map capabilities object to list of strings
            capabilities_list = []
            caps = item.get("capabilities", {})
            if isinstance(caps, dict):
                if caps.get("supports_incremental"):
                    capabilities_list.append("incremental")
                if caps.get("supports_state"):
                    capabilities_list.append("state")
                if caps.get("supports_discover"):
                    capabilities_list.append("discover")
                if caps.get("requires_tables"):
                    capabilities_list.append("requires_tables")
                if caps.get("supports_queries"):
                    capabilities_list.append("queries")
            elif isinstance(caps, list):
                # Legacy support if capabilities is already a list
                capabilities_list = caps

            return ExternalConnector(
                name=name,
                external_id=external_id,
                docker_image_default=docker_image,
                version_default=version,
                capabilities=capabilities_list,
                source_of_truth=source_of_truth,
                metadata=item.get("metadata", {}),
            )
        except Exception:
            return None

    def get_connector(
        self, name: str, catalog_name: Optional[str] = None
    ) -> Optional[ExternalConnector]:
        """Get connector by name from catalogs.

        Args:
            name: Connector name to search for
            catalog_name: Optional catalog name to search in (e.g., 'airbyte').
                         If None, searches all catalogs.

        Returns:
            ExternalConnector if found, None otherwise
        """
        if catalog_name:
            # Search specific catalog
            connectors = self.catalogs.get(catalog_name, [])
            for connector in connectors:
                if connector.name == name:
                    return connector
        else:
            # Search all catalogs
            for connectors in self.catalogs.values():
                for connector in connectors:
                    if connector.name == name:
                        return connector

        return None

    def list_connectors(
        self, catalog_name: Optional[str] = None
    ) -> List[ExternalConnector]:
        """List all connectors from catalogs.

        Args:
            catalog_name: Optional catalog name to filter by

        Returns:
            List of ExternalConnector objects
        """
        if catalog_name:
            return self.catalogs.get(catalog_name, [])

        # Return all connectors from all catalogs
        all_connectors = []
        for connectors in self.catalogs.values():
            all_connectors.extend(connectors)
        return all_connectors

    def has_catalogs(self) -> bool:
        """Check if any catalogs are loaded.

        Returns:
            True if at least one catalog is loaded
        """
        return len(self.catalogs) > 0

    def get_catalog_names(self) -> List[str]:
        """Get list of loaded catalog names.

        Returns:
            List of catalog names (e.g., ['airbyte', 'singer'])
        """
        return list(self.catalogs.keys())
