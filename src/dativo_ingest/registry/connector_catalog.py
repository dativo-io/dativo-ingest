"""External connector catalog synchronization."""

import hashlib
import json
import ssl
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import URLError

import jsonschema

from ..logging import get_logger
from .adapters.airbyte_adapter import AirbyteAdapter
from .adapters.meltano_adapter import MeltanoAdapter
from .adapters.singer_adapter import SingerAdapter


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

    def _validate_schema(self, data: Dict[str, Any]) -> None:
        """Validate normalized catalog against JSON schema.
        
        Raises:
            jsonschema.ValidationError: If validation fails
            FileNotFoundError: If schema file is missing
        """
        # Locate schema file
        # Try relative to this file first
        schema_path = (
            Path(__file__).parent.parent.parent.parent
            / "schemas"
            / "external_catalog.schema.json"
        )
        
        if not schema_path.exists():
            # Try absolute path /app/schemas (Docker)
            schema_path = Path("/app/schemas/external_catalog.schema.json")
            
        if not schema_path.exists():
            # Try relative path from cwd
            schema_path = Path("schemas/external_catalog.schema.json")

        if not schema_path.exists():
            self.logger.warning("External catalog schema not found, skipping validation.")
            return

        with open(schema_path, "r") as f:
            schema = json.load(f)
            
        jsonschema.validate(instance=data, schema=schema)

    def sync_from_url(
        self, 
        url: str, 
        name: str = "airbyte", 
        force: bool = False,
        insecure: bool = False
    ) -> Path:
        """Fetch catalog from URL, normalize, and save to file with idempotency.

        Args:
            url: URL to fetch catalog JSON from
            name: Name of the catalog (used for filename and adapter selection)
            force: Whether to force download ignoring cache
            insecure: Whether to disable SSL certificate verification (INSECURE)

        Returns:
            Path to saved catalog file

        Raises:
            ValueError: If URL is invalid or response is not valid JSON
            URLError: If network request fails
            OSError: If file write fails
            jsonschema.ValidationError: If normalized data is invalid
        """
        self.logger.info(
            f"Syncing catalog '{name}' from {url}...",
            extra={"event_type": "catalog_sync_start", "url": url, "catalog": name},
        )

        output_path = self.catalogs_dir / f"{name}.json"
        
        # Check existing cache for ETag/Last-Modified
        existing_meta = {}
        if not force and output_path.exists():
            try:
                with open(output_path, "r") as f:
                    data = json.load(f)
                    existing_meta = data.get("meta", {})
            except Exception:
                pass

        try:
            # Create SSL context
            if insecure:
                self.logger.warning(
                    "SSL verification disabled. This is insecure and should only be used in development/testing.",
                    extra={"event_type": "ssl_verification_disabled"},
                )
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            else:
                ctx = ssl.create_default_context()

            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Dativo/1.0')
            
            # Add conditional headers
            if existing_meta.get("etag"):
                req.add_header('If-None-Match', existing_meta["etag"])
            if existing_meta.get("last_modified"):
                req.add_header('If-Modified-Since', existing_meta["last_modified"])
            
            try:
                with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
                    # 200 OK - Content updated
                    raw_data_bytes = response.read()
                    
                    # Compute SHA256 of raw content
                    sha256 = hashlib.sha256(raw_data_bytes).hexdigest()
                    
                    # If content hasn't changed (based on hash), we might still want to update metadata
                    if not force and existing_meta.get("sha256") == sha256:
                        self.logger.info(
                            f"Catalog '{name}' content unchanged (SHA256 match).",
                            extra={"event_type": "catalog_sync_skipped", "reason": "content_unchanged"}
                        )
                        return output_path

                    # Extract metadata headers
                    response_headers = response.info()
                    metadata = {
                        "fetched_at": datetime.utcnow().isoformat() + "Z",
                        "source_url": url,
                        "etag": response_headers.get("ETag"),
                        "last_modified": response_headers.get("Last-Modified"),
                        "sha256": sha256
                    }
                    
                    # Parse JSON
                    try:
                        raw_json = json.loads(raw_data_bytes)
                    except json.JSONDecodeError as e:
                        raise ValueError(f"Invalid JSON response: {e}")

                    # Normalize
                    adapter = self._get_adapter(name)
                    normalized_data = adapter.normalize(raw_json, metadata)
                    
                    # Validate against schema
                    try:
                        self._validate_schema(normalized_data)
                    except jsonschema.ValidationError as e:
                        raise ValueError(f"Normalized catalog validation failed: {e.message}") from e
                    
                    # Save to file
                    self._save_atomic(output_path, normalized_data)
                    
                    self.logger.info(
                        f"Successfully synced catalog '{name}' to {output_path}",
                        extra={"event_type": "catalog_sync_success", "path": str(output_path)},
                    )
                    return output_path

            except urllib.error.HTTPError as e:
                if e.code == 304:
                    # 304 Not Modified
                    self.logger.info(
                        f"Catalog '{name}' unchanged (304 Not Modified).",
                        extra={"event_type": "catalog_sync_skipped", "reason": "not_modified"}
                    )
                    return output_path
                else:
                    raise

        except URLError as e:
            self.logger.error(
                f"Failed to fetch catalog from {url}: {e}",
                extra={"event_type": "catalog_sync_error", "error": str(e)},
            )
            raise

    def sync_from_file(self, source_path: Path, name: str = "airbyte") -> Path:
        """Sync from a local file (copy and normalize)."""
        source_path = Path(source_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")
            
        with open(source_path, "rb") as f:
            raw_data_bytes = f.read()
            
        sha256 = hashlib.sha256(raw_data_bytes).hexdigest()
        
        try:
            raw_json = json.loads(raw_data_bytes)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in source file: {e}")
            
        metadata = {
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "source_url": f"file://{source_path.absolute()}",
            "sha256": sha256,
            "etag": None,
            "last_modified": None
        }
        
        adapter = self._get_adapter(name)
        normalized_data = adapter.normalize(raw_json, metadata)
        
        # Validate against schema
        try:
            self._validate_schema(normalized_data)
        except jsonschema.ValidationError as e:
            raise ValueError(f"Normalized catalog validation failed: {e.message}") from e
        
        output_path = self.catalogs_dir / f"{name}.json"
        self._save_atomic(output_path, normalized_data)
        
        return output_path

    def _get_adapter(self, name: str):
        if name == "airbyte":
            return AirbyteAdapter()
        elif name == "singer":
            return SingerAdapter()
        elif name == "meltano":
            return MeltanoAdapter()
        else:
            # Default to Airbyte adapter if unknown, or raise error?
            # For robustness, we can try generic adapter or default to airbyte for now
            return AirbyteAdapter() 

    def _save_atomic(self, path: Path, data: Dict[str, Any]):
        temp_path = path.with_suffix(".tmp")
        with open(temp_path, "w") as f:
            json.dump(data, f, indent=2)
        temp_path.rename(path)

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
