"""Connector catalog sync helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Optional

import requests

from .connector_registry import get_connector_registry

DEFAULT_AIRBYTE_REGISTRY_URL = (
    "https://connectors.airbyte.com/files/registries/v0/oss_registry.json"
)


class ConnectorCatalogSync:
    """Download and persist external connector catalogs."""

    def __init__(self, catalog_dir: Optional[Path] = None):
        if catalog_dir:
            self.catalog_dir = Path(catalog_dir)
        else:
            self.catalog_dir = get_connector_registry().catalog_dir
        self.catalog_dir.mkdir(parents=True, exist_ok=True)

    def sync_airbyte(self, url: Optional[str] = None) -> Path:
        """Download Airbyte OSS registry."""
        registry_url = url or os.getenv("DATIVO_AIRBYTE_REGISTRY_URL", DEFAULT_AIRBYTE_REGISTRY_URL)
        response = requests.get(registry_url, timeout=60)
        response.raise_for_status()

        data = response.json()
        target_path = self.catalog_dir / "airbyte.json"
        with open(target_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        return target_path

    def sync_all(self, url: Optional[str] = None) -> Dict[str, Path]:
        """Sync all known external catalogs (currently Airbyte)."""
        results: Dict[str, Path] = {}
        results["airbyte"] = self.sync_airbyte(url=url)
        return results
