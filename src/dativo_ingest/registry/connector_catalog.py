"""External connector catalog synchronization."""

import json
import ssl
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import URLError

from ..logging import get_logger


class CatalogSyncer:
    """Syncs external connector catalogs from remote sources."""

    def __init__(self, catalogs_dir: Optional[Path] = None):
        """Initialize catalog syncer.

        Args:
            catalogs_dir: Directory to store catalog JSON files.
                         Defaults to /registry/catalogs/ or relative path.
        """
        self.logger = get_logger()

        if catalogs_dir is None:
            # Try multiple possible paths - consistent with CatalogLoader
            possible_paths = [
                Path("/app/registry/catalogs"),
                Path("registry/catalogs"),
                Path(__file__).parent.parent.parent.parent / "registry" / "catalogs",
            ]
            for path in possible_paths:
                # If path exists or its parent exists (so we can create it)
                if path.exists() or path.parent.exists():
                    catalogs_dir = path
                    break
            
            # If still None, default to relative path
            if catalogs_dir is None:
                catalogs_dir = Path("registry/catalogs")

        self.catalogs_dir = catalogs_dir
        
        # Ensure directory exists
        if not self.catalogs_dir.exists():
            try:
                self.catalogs_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                self.logger.warning(
                    f"Failed to create catalogs directory {self.catalogs_dir}: {e}"
                )

    def sync_from_url(self, url: str, name: str = "airbyte") -> Path:
        """Fetch catalog from URL and save to file.

        Args:
            url: URL to fetch catalog JSON from
            name: Name of the catalog (used for filename)

        Returns:
            Path to saved catalog file

        Raises:
            ValueError: If URL is invalid or response is not valid JSON
            URLError: If network request fails
            OSError: If file write fails
        """
        self.logger.info(
            f"Syncing catalog '{name}' from {url}...",
            extra={"event_type": "catalog_sync_start", "url": url, "catalog": name},
        )

        try:
            # Create SSL context that ignores self-signed certs (useful for internal registries)
            # For public internet, this might be too permissive, but practical for many enterprise envs
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            req = urllib.request.Request(url)
            # Add User-Agent to avoid 403s from some servers
            req.add_header('User-Agent', 'Dativo/1.0')
            
            with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
                if response.status != 200:
                    raise ValueError(f"HTTP {response.status}: {response.reason}")
                
                data = response.read()
                
            # Verify it's valid JSON
            try:
                json_data = json.loads(data)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON response: {e}")

            # Basic validation
            if not isinstance(json_data, (dict, list)):
                raise ValueError("Catalog must be a JSON object or list")

            # Save to file
            output_path = self.catalogs_dir / f"{name}.json"
            
            # Write atomically (write to temp file then rename)
            temp_path = output_path.with_suffix(".tmp")
            with open(temp_path, "wb") as f:
                f.write(data)
            
            temp_path.rename(output_path)
            
            self.logger.info(
                f"Successfully synced catalog '{name}' to {output_path}",
                extra={"event_type": "catalog_sync_success", "path": str(output_path)},
            )
            
            return output_path

        except URLError as e:
            self.logger.error(
                f"Failed to fetch catalog from {url}: {e}",
                extra={"event_type": "catalog_sync_error", "error": str(e)},
            )
            raise

    def get_default_url(self, name: str) -> Optional[str]:
        """Get default URL for known catalogs.
        
        Args:
            name: Catalog name
            
        Returns:
            Default URL or None
        """
        defaults = {
            "airbyte": "https://connectors.airbyte.com/files/registries/v0/oss_registry.json",
            "meltano": "https://hub.meltano.com/index.json",  # Example
        }
        return defaults.get(name.lower())
