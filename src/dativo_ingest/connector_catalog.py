"""External connector catalog syncing and normalization.

This module provides a unified way to consume external connector ecosystems
(Airbyte/Singer/Meltano) in a headless, config-driven way.

Primary responsibility:
- Sync remote catalog indexes (e.g., Airbyte registry index JSON)
- Normalize into Dativo's generic catalog JSON format
- Cache under registry/catalogs/<catalog>.json (default: airbyte.json)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class CatalogSyncResult:
    """Result of a catalog sync operation."""

    catalog_name: str
    destination: Path
    connector_count: int
    normalized: bool


class CatalogSyncError(RuntimeError):
    """Raised when catalog sync fails."""


_SLUGIFY_RE = re.compile(r"[^a-z0-9]+")


def slugify_connector_name(name: str) -> str:
    """Normalize a human-readable connector name into a registry key."""
    raw = (name or "").strip().lower()
    raw = _SLUGIFY_RE.sub("_", raw)
    raw = raw.strip("_")
    return raw


def normalize_airbyte_catalog_index(catalog_data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize an Airbyte catalog index into Dativo's generic format.

    Accepts Airbyte's "sources" list format (as used by this repo's existing
    `CatalogLoader`) and emits a generic catalog:

    {
      "catalog_name": "airbyte",
      "catalog_version": "...",
      "last_updated": "...",
      "connectors": [
        {
          "name": "stripe",
          "id": "<sourceDefinitionId>",
          "docker_image_default": "airbyte/source-stripe:4.0.0",
          "version_default": "4.0.0",
          "capabilities": [...],
          "metadata": {...}
        }
      ]
    }
    """
    sources = catalog_data.get("sources")
    if not isinstance(sources, list):
        raise CatalogSyncError(
            "Unsupported Airbyte catalog format: expected top-level 'sources' list"
        )

    connectors: List[Dict[str, Any]] = []
    for item in sources:
        if not isinstance(item, dict):
            continue

        airbyte_id = item.get("sourceDefinitionId") or item.get("definitionId")
        name_raw = item.get("name") or ""
        docker_repo = item.get("dockerRepository") or ""
        docker_tag = item.get("dockerImageTag") or ""

        connector_name = slugify_connector_name(str(name_raw))

        docker_image_default: Optional[str] = None
        version_default: Optional[str] = None
        if docker_repo and docker_tag:
            docker_image_default = f"{docker_repo}:{docker_tag}"
            version_default = str(docker_tag)

        capabilities: List[str] = []
        support_level = item.get("supportLevel")
        if support_level:
            capabilities.append(f"support:{support_level}")

        connectors.append(
            {
                "name": connector_name,
                "id": str(airbyte_id) if airbyte_id else "",
                "docker_image_default": docker_image_default,
                "version_default": version_default,
                "capabilities": capabilities,
                "metadata": {
                    "documentation_url": item.get("documentationUrl"),
                    "support_level": support_level,
                    "docker_repository": docker_repo,
                    "docker_image_tag": docker_tag,
                },
            }
        )

    now = datetime.now(timezone.utc).isoformat()
    return {
        "catalog_name": "airbyte",
        "catalog_version": "1.0.0",
        "last_updated": now,
        "connectors": connectors,
    }


def _download_json(url: str, timeout_seconds: int = 30) -> Dict[str, Any]:
    try:
        req = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "dativo-ingest/connector-catalog",
            },
        )
        with urlopen(req, timeout=timeout_seconds) as resp:
            payload = resp.read()
        return json.loads(payload.decode("utf-8"))
    except Exception as e:
        raise CatalogSyncError(f"Failed to download or parse catalog JSON: {e}") from e


def sync_catalog_url_to_cache(
    *,
    catalog_url: str,
    destination_dir: Path,
    destination_filename: Optional[str] = None,
    timeout_seconds: int = 30,
) -> CatalogSyncResult:
    """Sync a remote catalog URL to a local cache file.

    - If the downloaded JSON looks like an Airbyte catalog (has 'sources'),
      it is normalized into the generic format before caching.
    - Otherwise, the JSON is written as-is.
    """
    destination_dir.mkdir(parents=True, exist_ok=True)

    parsed = urlparse(catalog_url)
    filename_from_url = Path(parsed.path).name if parsed.path else ""
    filename = destination_filename or filename_from_url or "airbyte.json"
    dest_path = destination_dir / filename

    data = _download_json(catalog_url, timeout_seconds=timeout_seconds)

    normalized = False
    catalog_name = Path(filename).stem or "airbyte"
    if isinstance(data, dict) and "sources" in data:
        data = normalize_airbyte_catalog_index(data)
        normalized = True
        catalog_name = "airbyte"

    # Write atomically
    tmp_path = dest_path.with_suffix(dest_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n")
    tmp_path.replace(dest_path)

    connector_count = 0
    if isinstance(data, dict):
        if isinstance(data.get("connectors"), list):
            connector_count = len(data["connectors"])
        elif isinstance(data.get("sources"), list):
            connector_count = len(data["sources"])

    return CatalogSyncResult(
        catalog_name=catalog_name,
        destination=dest_path,
        connector_count=connector_count,
        normalized=normalized,
    )

