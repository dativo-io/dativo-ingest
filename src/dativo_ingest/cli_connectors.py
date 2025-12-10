"""Helper functions backing `dativo connectors` CLI commands."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests

from .registry import ConnectorRegistryService, get_connector_registry
from .registry.catalog_sync import ConnectorCatalogSync


def list_connectors(
    registry_path: Optional[str] = None,
    catalog_dir: Optional[str] = None,
    output_json: bool = False,
) -> int:
    """List connectors with resolved metadata."""
    service = _build_registry_service(registry_path, catalog_dir)
    connector_names = sorted(service.list_connectors().keys())
    rows: List[Dict[str, Any]] = []
    for name in connector_names:
        metadata = service.get_connector_metadata(name) or {"name": name}
        rows.append(metadata)

    if output_json:
        print(json.dumps(rows, indent=2))
    else:
        if not rows:
            print("No connectors registered.")
        else:
            _print_table(
                rows,
                columns=[
                    "name",
                    "default_engine",
                    "source_of_truth",
                    "docker_image",
                    "version",
                    "catalog_source",
                ],
            )
    return 0


def inspect_connector(
    name: str,
    registry_path: Optional[str] = None,
    catalog_dir: Optional[str] = None,
    output_json: bool = False,
) -> int:
    """Show detailed metadata for a single connector."""
    service = _build_registry_service(registry_path, catalog_dir)
    metadata = service.get_connector_metadata(name)
    if metadata is None:
        print(f"Connector '{name}' not found in registry.", file=sys.stderr)
        return 2

    if output_json:
        print(json.dumps(metadata, indent=2))
    else:
        print(f"Connector: {metadata['name']}")
        print(f"Category: {metadata.get('category') or 'n/a'}")
        print(f"Roles: {', '.join(metadata.get('roles') or []) or 'n/a'}")
        print(f"Default engine: {metadata.get('default_engine')}")
        print(f"Source of truth: {metadata.get('source_of_truth')}")
        print(f"External ID: {metadata.get('external_id') or 'n/a'}")
        print(f"Docker repository: {metadata.get('docker_repository') or 'n/a'}")
        print(f"Docker image: {metadata.get('docker_image') or 'n/a'}")
        print(f"Version: {metadata.get('version') or 'n/a'}")
        print(f"Catalog source: {metadata.get('catalog_source')}")
        print(f"Allowed in cloud: {metadata.get('allows_cloud')}")
        print(f"Supports incremental: {metadata.get('supports_incremental')}")
        capabilities = metadata.get("capabilities") or []
        print(f"Capabilities: {', '.join(capabilities) if capabilities else 'n/a'}")
    return 0


def sync_catalogs(
    catalog_dir: Optional[str] = None,
    airbyte_url: Optional[str] = None,
) -> int:
    """Sync external catalogs to registry/catalogs."""
    syncer = ConnectorCatalogSync(catalog_dir=Path(catalog_dir) if catalog_dir else None)
    try:
        results = syncer.sync_all(url=airbyte_url)
    except requests.RequestException as exc:  # type: ignore[name-defined]
        # Avoid importing requests at module import time for CLIs that don't need it
        print(f"Failed to sync catalogs: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # pylint: disable=broad-except
        print(f"Unexpected error syncing catalogs: {exc}", file=sys.stderr)
        return 2

    for catalog_name, path in results.items():
        print(f"Synchronized {catalog_name} catalog -> {path}")
    return 0


def _build_registry_service(
    registry_path: Optional[str],
    catalog_dir: Optional[str],
) -> ConnectorRegistryService:
    if registry_path or catalog_dir:
        return get_connector_registry(
            registry_path=Path(registry_path) if registry_path else None,
            catalog_dir=Path(catalog_dir) if catalog_dir else None,
        )
    return get_connector_registry()


def _print_table(rows: Iterable[Dict[str, Any]], columns: List[str]) -> None:
    """Render a simple monospaced table."""
    row_list = list(rows)
    col_widths = {
        column: max(
            len(column),
            max(len(str(row.get(column, "") or "")) for row in row_list),
        )
        for column in columns
    }
    header = "  ".join(column.upper().ljust(col_widths[column]) for column in columns)
    print(header)
    print("-" * len(header))
    for row in row_list:
        line = "  ".join(
            str(row.get(column, "") or "").ljust(col_widths[column]) for column in columns
        )
        print(line)
