"""Catalog syncer for fetching and caching external connector catalogs."""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

try:
    import requests
    
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


class CatalogSyncError(Exception):
    """Raised when catalog sync fails."""

    pass


class CatalogSyncer:
    """Syncs external connector catalogs from remote URLs."""

    # Known catalog URLs
    KNOWN_CATALOGS = {
        "airbyte": "https://connectors.airbyte.com/files/generated_reports/connector_registry_report.json",
        "airbyte_oss": "https://connectors.airbyte.com/files/registries/v0/oss_registry.json",
    }

    def __init__(self, catalogs_dir: Optional[Path] = None):
        """Initialize catalog syncer.

        Args:
            catalogs_dir: Directory to store catalog files.
                         Defaults to registry/catalogs/
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

            # If none exist, use first writable location
            if catalogs_dir is None:
                for path in possible_paths:
                    try:
                        path.mkdir(parents=True, exist_ok=True)
                        catalogs_dir = path
                        break
                    except Exception:
                        continue

        if catalogs_dir is None:
            raise CatalogSyncError("Failed to find or create catalogs directory")

        self.catalogs_dir = catalogs_dir

    def sync_from_url(
        self,
        url: str,
        catalog_name: Optional[str] = None,
        force: bool = False,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """Fetch catalog from remote URL and cache locally.

        Args:
            url: URL to fetch catalog from
            catalog_name: Optional catalog name (defaults to filename or URL hash)
            force: Force re-download even if cached
            timeout: Request timeout in seconds

        Returns:
            Dictionary with sync results

        Raises:
            CatalogSyncError: If sync fails
        """
        if not REQUESTS_AVAILABLE:
            raise CatalogSyncError(
                "requests library not available. Install with: pip install requests"
            )

        # Determine catalog name
        if catalog_name is None:
            # Try to extract from URL
            parsed = urlparse(url)
            filename = Path(parsed.path).stem
            if filename and filename != "":
                catalog_name = filename
            else:
                # Use URL hash
                url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
                catalog_name = f"catalog_{url_hash}"

        # Remove .json extension if present
        if catalog_name.endswith(".json"):
            catalog_name = catalog_name[:-5]

        dest_path = self.catalogs_dir / f"{catalog_name}.json"

        # Check if already cached
        if dest_path.exists() and not force:
            # Read existing file
            with open(dest_path, "r") as f:
                cached_data = json.load(f)

            return {
                "status": "cached",
                "catalog_name": catalog_name,
                "path": str(dest_path),
                "url": url,
                "cached": True,
                "connectors_count": self._count_connectors(cached_data),
            }

        # Fetch from URL
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as e:
            raise CatalogSyncError(f"Failed to fetch catalog from {url}: {e}") from e

        # Parse JSON
        try:
            catalog_data = response.json()
        except json.JSONDecodeError as e:
            raise CatalogSyncError(f"Invalid JSON response from {url}: {e}") from e

        # Add metadata
        if isinstance(catalog_data, dict):
            catalog_data["_sync_metadata"] = {
                "synced_at": datetime.utcnow().isoformat(),
                "source_url": url,
                "catalog_name": catalog_name,
            }

        # Write to file
        try:
            with open(dest_path, "w") as f:
                json.dump(catalog_data, f, indent=2)
        except OSError as e:
            raise CatalogSyncError(
                f"Failed to write catalog to {dest_path}: {e}"
            ) from e

        return {
            "status": "synced",
            "catalog_name": catalog_name,
            "path": str(dest_path),
            "url": url,
            "cached": False,
            "connectors_count": self._count_connectors(catalog_data),
        }

    def sync_known_catalog(
        self, catalog_name: str, force: bool = False, timeout: int = 30
    ) -> Dict[str, Any]:
        """Sync a known catalog by name.

        Args:
            catalog_name: Name of known catalog (e.g., 'airbyte', 'airbyte_oss')
            force: Force re-download even if cached
            timeout: Request timeout in seconds

        Returns:
            Dictionary with sync results

        Raises:
            CatalogSyncError: If sync fails or catalog name unknown
        """
        if catalog_name not in self.KNOWN_CATALOGS:
            available = ", ".join(self.KNOWN_CATALOGS.keys())
            raise CatalogSyncError(
                f"Unknown catalog: {catalog_name}. Available: {available}"
            )

        url = self.KNOWN_CATALOGS[catalog_name]
        return self.sync_from_url(url, catalog_name, force, timeout)

    def sync_from_file(self, source_path: Path, catalog_name: Optional[str] = None) -> Dict[str, Any]:
        """Copy catalog from local file.

        Args:
            source_path: Path to source catalog file
            catalog_name: Optional catalog name (defaults to source filename)

        Returns:
            Dictionary with sync results

        Raises:
            CatalogSyncError: If sync fails
        """
        if not source_path.exists():
            raise CatalogSyncError(f"Catalog file not found: {source_path}")

        if not source_path.is_file():
            raise CatalogSyncError(f"Not a file: {source_path}")

        # Determine catalog name
        if catalog_name is None:
            catalog_name = source_path.stem

        dest_path = self.catalogs_dir / f"{catalog_name}.json"

        # Validate JSON
        try:
            with open(source_path, "r") as f:
                catalog_data = json.load(f)
        except json.JSONDecodeError as e:
            raise CatalogSyncError(
                f"Invalid JSON in catalog file {source_path}: {e}"
            ) from e
        except OSError as e:
            raise CatalogSyncError(f"Failed to read catalog file {source_path}: {e}") from e

        # Add metadata
        if isinstance(catalog_data, dict):
            catalog_data["_sync_metadata"] = {
                "synced_at": datetime.utcnow().isoformat(),
                "source_file": str(source_path),
                "catalog_name": catalog_name,
            }

        # Write to destination
        try:
            with open(dest_path, "w") as f:
                json.dump(catalog_data, f, indent=2)
        except OSError as e:
            raise CatalogSyncError(
                f"Failed to write catalog to {dest_path}: {e}"
            ) from e

        return {
            "status": "synced",
            "catalog_name": catalog_name,
            "path": str(dest_path),
            "source_file": str(source_path),
            "connectors_count": self._count_connectors(catalog_data),
        }

    def list_synced_catalogs(self) -> Dict[str, Any]:
        """List all synced catalogs.

        Returns:
            Dictionary with catalog information
        """
        catalogs = []

        if not self.catalogs_dir.exists():
            return {"catalogs": [], "count": 0}

        for catalog_file in self.catalogs_dir.glob("*.json"):
            try:
                with open(catalog_file, "r") as f:
                    catalog_data = json.load(f)

                info = {
                    "name": catalog_file.stem,
                    "path": str(catalog_file),
                    "connectors_count": self._count_connectors(catalog_data),
                }

                # Add sync metadata if available
                if isinstance(catalog_data, dict) and "_sync_metadata" in catalog_data:
                    metadata = catalog_data["_sync_metadata"]
                    info["synced_at"] = metadata.get("synced_at")
                    info["source_url"] = metadata.get("source_url")
                    info["source_file"] = metadata.get("source_file")

                catalogs.append(info)
            except Exception:
                # Skip invalid files
                continue

        return {"catalogs": catalogs, "count": len(catalogs)}

    def _count_connectors(self, catalog_data: Any) -> int:
        """Count connectors in catalog data.

        Args:
            catalog_data: Catalog JSON data

        Returns:
            Number of connectors
        """
        if not isinstance(catalog_data, dict):
            return 0

        # Try different formats
        if "connectors" in catalog_data and isinstance(catalog_data["connectors"], list):
            return len(catalog_data["connectors"])
        elif "sources" in catalog_data and isinstance(catalog_data["sources"], list):
            return len(catalog_data["sources"])
        elif "destinations" in catalog_data and isinstance(catalog_data["destinations"], list):
            return len(catalog_data["destinations"])

        return 0

    @classmethod
    def get_known_catalog_names(cls) -> list[str]:
        """Get list of known catalog names.

        Returns:
            List of catalog names
        """
        return list(cls.KNOWN_CATALOGS.keys())
