"""External connector catalog loader and resolver.

This module handles loading external connector catalogs (e.g., Airbyte's catalog)
into a normalized internal format for connector resolution.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..logging import get_logger


class ConnectorCatalogEntry:
    """Normalized connector catalog entry."""

    def __init__(
        self,
        name: str,
        external_id: str,
        docker_image_default: Optional[str] = None,
        version_default: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Initialize catalog entry.

        Args:
            name: Connector name (e.g., "stripe", "hubspot")
            external_id: External catalog identifier (e.g., "airbyte/source-stripe")
            docker_image_default: Default Docker image for the connector
            version_default: Default version tag
            capabilities: List of connector capabilities
            metadata: Additional metadata from the catalog
        """
        self.name = name
        self.external_id = external_id
        self.docker_image_default = docker_image_default
        self.version_default = version_default
        self.capabilities = capabilities or []
        self.metadata = metadata or {}


class ConnectorCatalog:
    """External connector catalog loader and resolver."""

    def __init__(self, catalog_dir: Optional[Path] = None):
        """Initialize catalog loader.

        Args:
            catalog_dir: Directory containing catalog JSON files.
                        Defaults to /workspace/registry/catalogs
        """
        if catalog_dir is None:
            # Default to workspace registry/catalogs directory
            workspace_root = Path(__file__).parent.parent.parent.parent
            catalog_dir = workspace_root / "registry" / "catalogs"

        self.catalog_dir = Path(catalog_dir)
        self._entries: Dict[str, ConnectorCatalogEntry] = {}
        self._loaded = False
        self.logger = get_logger()

    def load(self) -> None:
        """Load all catalog files from the catalog directory.

        Catalog files are expected to be JSON files in the catalog directory.
        Each file should contain a list of connector definitions or a single
        connector definition.

        This method is safe to call multiple times - it will reload catalogs
        if called again.
        """
        if not self.catalog_dir.exists():
            self.logger.debug(
                f"Catalog directory does not exist: {self.catalog_dir}. "
                "Catalog loading will be skipped."
            )
            self._entries = {}
            self._loaded = True
            return

        self._entries = {}
        catalog_files = list(self.catalog_dir.glob("*.json"))

        if not catalog_files:
            self.logger.debug(
                f"No catalog files found in {self.catalog_dir}. "
                "Catalog loading will be skipped."
            )
            self._loaded = True
            return

        for catalog_file in catalog_files:
            try:
                self._load_catalog_file(catalog_file)
            except Exception as e:
                self.logger.warning(
                    f"Failed to load catalog file {catalog_file}: {e}",
                    extra={"event_type": "catalog_load_warning", "file": str(catalog_file)},
                )

        self._loaded = True
        self.logger.info(
            f"Loaded {len(self._entries)} connector entries from {len(catalog_files)} catalog file(s)",
            extra={
                "event_type": "catalog_loaded",
                "entry_count": len(self._entries),
                "file_count": len(catalog_files),
            },
        )

    def _load_catalog_file(self, catalog_file: Path) -> None:
        """Load a single catalog JSON file.

        Args:
            catalog_file: Path to the catalog JSON file
        """
        with open(catalog_file, "r") as f:
            data = json.load(f)

        # Handle different catalog formats
        connectors = []
        if isinstance(data, list):
            connectors = data
        elif isinstance(data, dict):
            # Airbyte format: {"sources": [...]} or {"connectors": [...]}
            connectors = data.get("sources", data.get("connectors", []))
            if not connectors and "data" in data:
                # Some catalogs wrap in a "data" key
                connectors = data["data"]

        for connector_data in connectors:
            entry = self._parse_connector_entry(connector_data, catalog_file.name)
            if entry:
                # Use name as key, but allow multiple entries with same name
                # (last one wins, or we could merge)
                self._entries[entry.name] = entry

    def _parse_connector_entry(
        self, connector_data: Dict[str, Any], source_file: str
    ) -> Optional[ConnectorCatalogEntry]:
        """Parse a connector entry from catalog data.

        Supports multiple catalog formats:
        - Airbyte format: {"dockerImage": "...", "dockerRepository": "...", ...}
        - Generic format: {"name": "...", "docker_image": "...", ...}

        Args:
            connector_data: Raw connector data from catalog
            source_file: Name of the source catalog file (for logging)

        Returns:
            Parsed ConnectorCatalogEntry or None if parsing fails
        """
        try:
            # Extract name - try multiple fields
            name = (
                connector_data.get("name")
                or connector_data.get("connectorName")
                or connector_data.get("sourceDefinitionId")
            )

            if not name:
                self.logger.warning(
                    f"Connector entry missing name field in {source_file}",
                    extra={"event_type": "catalog_parse_warning"},
                )
                return None

            # Normalize name (remove prefixes like "source-", "destination-")
            name = name.replace("source-", "").replace("destination-", "").lower()

            # Extract external_id
            external_id = (
                connector_data.get("external_id")
                or connector_data.get("sourceDefinitionId")
                or connector_data.get("definitionId")
                or name
            )

            # Extract docker image - try multiple formats
            docker_image = (
                connector_data.get("docker_image_default")
                or connector_data.get("dockerImage")
                or connector_data.get("dockerRepository")
            )

            # If docker_image is a full image string, use it; otherwise construct it
            if docker_image and ":" not in docker_image:
                # Might be just the repository name, try to construct full image
                version = connector_data.get("version_default") or connector_data.get(
                    "dockerImageTag"
                )
                if version:
                    docker_image = f"{docker_image}:{version}"

            # Extract version
            version = (
                connector_data.get("version_default")
                or connector_data.get("dockerImageTag")
                or connector_data.get("version")
            )

            # Extract capabilities
            capabilities = connector_data.get("capabilities", [])
            if not capabilities:
                # Try to infer from other fields
                if connector_data.get("supportsIncremental"):
                    capabilities.append("incremental")
                if connector_data.get("supportsNormalization"):
                    capabilities.append("normalization")

            # Store all metadata for potential future use
            metadata = {k: v for k, v in connector_data.items() if k not in ["name", "external_id"]}

            return ConnectorCatalogEntry(
                name=name,
                external_id=external_id,
                docker_image_default=docker_image,
                version_default=version,
                capabilities=capabilities,
                metadata=metadata,
            )

        except Exception as e:
            self.logger.warning(
                f"Failed to parse connector entry in {source_file}: {e}",
                extra={"event_type": "catalog_parse_warning"},
            )
            return None

    def get_entry(self, connector_name: str) -> Optional[ConnectorCatalogEntry]:
        """Get catalog entry for a connector by name.

        Args:
            connector_name: Connector name (e.g., "stripe", "hubspot")

        Returns:
            ConnectorCatalogEntry if found, None otherwise
        """
        if not self._loaded:
            self.load()

        return self._entries.get(connector_name.lower())

    def get_all_entries(self) -> Dict[str, ConnectorCatalogEntry]:
        """Get all catalog entries.

        Returns:
            Dictionary mapping connector names to entries
        """
        if not self._loaded:
            self.load()

        return self._entries.copy()

    def sync_from_airbyte(
        self, catalog_url: Optional[str] = None, output_file: Optional[Path] = None
    ) -> None:
        """Sync catalog from Airbyte's public catalog.

        Args:
            catalog_url: URL to Airbyte catalog JSON. If None, uses default Airbyte catalog URL.
            output_file: Path to write the catalog. If None, writes to catalog_dir/airbyte.json
        """
        import requests

        if catalog_url is None:
            # Default Airbyte catalog URL (example - adjust as needed)
            catalog_url = "https://connectors.airbyte.com/files/generated_reports/connector_registry_report.json"

        try:
            self.logger.info(
                f"Fetching Airbyte catalog from {catalog_url}",
                extra={"event_type": "catalog_sync_start"},
            )
            response = requests.get(catalog_url, timeout=30)
            response.raise_for_status()
            data = response.json()

            # Ensure catalog directory exists
            self.catalog_dir.mkdir(parents=True, exist_ok=True)

            # Write to output file
            if output_file is None:
                output_file = self.catalog_dir / "airbyte.json"

            with open(output_file, "w") as f:
                json.dump(data, f, indent=2)

            self.logger.info(
                f"Successfully synced Airbyte catalog to {output_file}",
                extra={"event_type": "catalog_sync_complete", "file": str(output_file)},
            )

            # Reload catalogs
            self.load()

        except Exception as e:
            self.logger.error(
                f"Failed to sync Airbyte catalog: {e}",
                extra={"event_type": "catalog_sync_error"},
                exc_info=True,
            )
            raise
