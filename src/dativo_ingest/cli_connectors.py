"""CLI commands for connector registry management."""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .logging import get_logger
from .registry import (
    CatalogLoader,
    ConnectorRegistry,
    RegistryLoadError,
    RegistryNotFoundError,
)


def format_connector_list(
    connectors: List[str],
    registry: ConnectorRegistry,
    json_output: bool = False,
    verbose: bool = False,
) -> None:
    """Format and print connector list.

    Args:
        connectors: List of connector names
        registry: ConnectorRegistry instance
        json_output: Whether to output JSON
        verbose: Whether to include verbose details
    """
    if json_output:
        output = []
        for name in sorted(connectors):
            resolved = registry.resolve_connector(name)
            if resolved:
                output.append(resolved.to_dict())
        print(json.dumps({"connectors": output, "count": len(output)}, indent=2))
    else:
        print(f"\nRegistered Connectors ({len(connectors)}):")
        print("=" * 80)

        for name in sorted(connectors):
            resolved = registry.resolve_connector(name)
            if not resolved:
                continue

            # Basic info
            print(f"\n{name}")
            print(f"  Roles: {', '.join(resolved.roles)}")
            print(f"  Default Engine: {resolved.default_engine}")
            print(f"  Engines Supported: {', '.join(resolved.engines_supported)}")

            if verbose:
                # Verbose details
                if resolved.category:
                    print(f"  Category: {resolved.category}")
                if resolved.docker_image:
                    print(f"  Docker Image: {resolved.docker_image}")
                if resolved.version:
                    print(f"  Version: {resolved.version}")
                if resolved.external_id:
                    print(f"  External ID: {resolved.external_id}")
                print(f"  Source of Truth: {resolved.source_of_truth}")
                print(f"  Cloud Mode: {'✓' if resolved.allowed_in_cloud else '✗'}")
                print(f"  Incremental: {'✓' if resolved.supports_incremental else '✗'}")
                if resolved.capabilities:
                    print(f"  Capabilities: {', '.join(resolved.capabilities)}")

        print()


def format_connector_inspect(
    name: str,
    resolved: Optional[Any],
    json_output: bool = False,
) -> None:
    """Format and print connector inspection details.

    Args:
        name: Connector name
        resolved: ResolvedConnector instance
        json_output: Whether to output JSON
    """
    if not resolved:
        if json_output:
            print(json.dumps({"error": f"Connector '{name}' not found"}, indent=2))
        else:
            print(f"ERROR: Connector '{name}' not found in registry", file=sys.stderr)
        sys.exit(2)

    if json_output:
        print(json.dumps(resolved.to_dict(), indent=2))
    else:
        print(f"\nConnector: {name}")
        print("=" * 80)
        print(f"Type: {resolved.connector_type}")
        print(f"Roles: {', '.join(resolved.roles)}")
        print(f"Category: {resolved.category or 'N/A'}")
        print()

        print("Engine Configuration:")
        print(f"  Default Engine: {resolved.default_engine}")
        print(f"  Supported Engines: {', '.join(resolved.engines_supported)}")
        print()

        print("Runtime Configuration:")
        if resolved.docker_image:
            print(f"  Docker Image: {resolved.docker_image}")
        if resolved.version:
            print(f"  Version: {resolved.version}")
        if resolved.external_id:
            print(f"  External ID: {resolved.external_id}")
        print(f"  Source of Truth: {resolved.source_of_truth}")
        print()

        print("Capabilities:")
        print(f"  Allowed in Cloud: {'✓' if resolved.allowed_in_cloud else '✗'}")
        print(
            f"  Supports Incremental: {'✓' if resolved.supports_incremental else '✗'}"
        )
        if resolved.incremental_strategy_default:
            print(f"  Incremental Strategy: {resolved.incremental_strategy_default}")
        if resolved.capabilities:
            print(f"  Additional: {', '.join(resolved.capabilities)}")
        print()

        # Catalog info
        if resolved.catalog_entry:
            print("External Catalog Entry:")
            print(f"  Catalog: {resolved.catalog_entry.source_of_truth}")
            print(f"  External ID: {resolved.catalog_entry.external_id}")
            if resolved.catalog_entry.docker_image_default:
                print(f"  Docker Image: {resolved.catalog_entry.docker_image_default}")
            if resolved.catalog_entry.version_default:
                print(f"  Version: {resolved.catalog_entry.version_default}")
            if resolved.catalog_entry.metadata:
                print(f"  Metadata: {resolved.catalog_entry.metadata}")
        else:
            print("External Catalog Entry: None")
        print()


def connectors_list_command(
    role: Optional[str] = None,
    json_output: bool = False,
    verbose: bool = False,
) -> int:
    """List all registered connectors.

    Args:
        role: Optional role filter ('source' or 'target')
        json_output: Whether to output JSON
        verbose: Whether to include verbose details

    Returns:
        Exit code (0=success, 2=failure)
    """
    try:
        registry = ConnectorRegistry.from_default_paths()
        connectors = registry.list_connectors(role=role)

        if not connectors:
            if json_output:
                print(json.dumps({"connectors": [], "count": 0}, indent=2))
            else:
                print("No connectors found in registry")
            return 0

        format_connector_list(connectors, registry, json_output, verbose)
        return 0

    except (RegistryNotFoundError, RegistryLoadError) as e:
        if json_output:
            print(json.dumps({"error": str(e)}, indent=2))
        else:
            print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        if json_output:
            print(json.dumps({"error": str(e)}, indent=2))
        else:
            print(f"ERROR: Failed to list connectors: {e}", file=sys.stderr)
        return 2


def connectors_inspect_command(
    name: str,
    engine: Optional[str] = None,
    json_output: bool = False,
) -> int:
    """Inspect a specific connector.

    Args:
        name: Connector name to inspect
        engine: Optional engine override
        json_output: Whether to output JSON

    Returns:
        Exit code (0=success, 2=failure)
    """
    try:
        registry = ConnectorRegistry.from_default_paths()
        resolved = registry.resolve_connector(name, engine=engine)

        format_connector_inspect(name, resolved, json_output)
        return 0

    except (RegistryNotFoundError, RegistryLoadError) as e:
        if json_output:
            print(json.dumps({"error": str(e)}, indent=2))
        else:
            print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        if json_output:
            print(json.dumps({"error": str(e)}, indent=2))
        else:
            print(f"ERROR: Failed to inspect connector: {e}", file=sys.stderr)
        return 2


def connectors_sync_command(
    catalog_url: Optional[str] = None,
    catalog_file: Optional[str] = None,
    catalog_name: Optional[str] = None,
    force: bool = False,
    json_output: bool = False,
    verbose: bool = False,
) -> int:
    """Sync external connector catalogs.

    Args:
        catalog_url: Optional URL to fetch catalog from
        catalog_file: Optional local catalog file to copy
        catalog_name: Optional catalog name (for known catalogs or custom naming)
        force: Force re-download even if cached
        json_output: Whether to output JSON
        verbose: Whether to include verbose details

    Returns:
        Exit code (0=success, 2=failure)
    """
    from .registry import CatalogSyncError, CatalogSyncer

    logger = get_logger()

    try:
        syncer = CatalogSyncer()
        synced = False
        result = None

        # Handle URL sync
        if catalog_url:
            try:
                result = syncer.sync_from_url(
                    catalog_url, catalog_name=catalog_name, force=force
                )
                synced = True

                logger.info(
                    f"Synced catalog from URL: {catalog_url}",
                    extra={"event_type": "catalog_synced", "catalog_name": result["catalog_name"]},
                )

                if not json_output:
                    status = "✓ Downloaded" if not result.get("cached") else "✓ Cached"
                    print(
                        f"{status}: {result['catalog_name']} "
                        f"({result['connectors_count']} connectors)"
                    )
            except CatalogSyncError as e:
                if json_output:
                    print(json.dumps({"error": str(e)}, indent=2))
                else:
                    print(f"ERROR: {e}", file=sys.stderr)
                return 2

        # Handle known catalog sync
        elif catalog_name and not catalog_file:
            try:
                result = syncer.sync_known_catalog(catalog_name, force=force)
                synced = True

                logger.info(
                    f"Synced known catalog: {catalog_name}",
                    extra={"event_type": "catalog_synced", "catalog_name": catalog_name},
                )

                if not json_output:
                    status = "✓ Downloaded" if not result.get("cached") else "✓ Cached"
                    print(
                        f"{status}: {result['catalog_name']} "
                        f"({result['connectors_count']} connectors)"
                    )
            except CatalogSyncError as e:
                if json_output:
                    print(json.dumps({"error": str(e)}, indent=2))
                else:
                    print(f"ERROR: {e}", file=sys.stderr)
                    # Show available catalogs
                    available = CatalogSyncer.get_known_catalog_names()
                    print(f"Available known catalogs: {', '.join(available)}", file=sys.stderr)
                return 2

        # Handle file copy
        elif catalog_file:
            try:
                source_path = Path(catalog_file)
                result = syncer.sync_from_file(source_path, catalog_name=catalog_name)
                synced = True

                logger.info(
                    f"Synced catalog from file: {catalog_file}",
                    extra={"event_type": "catalog_synced", "catalog_name": result["catalog_name"]},
                )

                if not json_output:
                    print(
                        f"✓ Synced: {result['catalog_name']} "
                        f"({result['connectors_count']} connectors)"
                    )
            except CatalogSyncError as e:
                if json_output:
                    print(json.dumps({"error": str(e)}, indent=2))
                else:
                    print(f"ERROR: {e}", file=sys.stderr)
                return 2

        # If no specific sync action, show existing catalogs
        if not synced:
            result = syncer.list_synced_catalogs()

            if json_output:
                print(json.dumps(result, indent=2))
            else:
                if result["count"] > 0:
                    print(f"\nSynced Catalogs ({result['count']}):")
                    print("=" * 80)
                    for catalog in result["catalogs"]:
                        print(f"\n{catalog['name']}")
                        print(f"  Connectors: {catalog['connectors_count']}")
                        if verbose:
                            if catalog.get("synced_at"):
                                print(f"  Synced At: {catalog['synced_at']}")
                            if catalog.get("source_url"):
                                print(f"  Source URL: {catalog['source_url']}")
                            if catalog.get("source_file"):
                                print(f"  Source File: {catalog['source_file']}")
                            print(f"  Path: {catalog['path']}")
                    print()
                else:
                    print("\nNo catalogs synced. Catalogs are optional.")
                    print("\nTo sync a known catalog:")
                    available = CatalogSyncer.get_known_catalog_names()
                    for name in available:
                        print(f"  dativo connectors sync --catalog-name {name}")
                    print("\nOr sync from URL:")
                    print("  dativo connectors sync --catalog-url <url>")
                    print("\nOr copy from local file:")
                    print("  dativo connectors sync --catalog-file <path>")
                    print()

            return 0

        # Show sync results
        if json_output and result:
            print(json.dumps(result, indent=2))
        elif result and verbose:
            loader = CatalogLoader(syncer.catalogs_dir)
            catalog_names = loader.get_catalog_names()
            if catalog_names:
                print(f"\nAll Synced Catalogs ({len(catalog_names)}):")
                for name in catalog_names:
                    connectors = loader.list_connectors(name)
                    print(f"  - {name}: {len(connectors)} connectors")

        return 0

    except Exception as e:
        logger.error(
            f"Catalog sync failed: {e}",
            extra={"event_type": "catalog_sync_error"},
            exc_info=True,
        )
        if json_output:
            print(json.dumps({"error": str(e)}, indent=2))
        else:
            print(f"ERROR: Catalog sync failed: {e}", file=sys.stderr)
        return 2
