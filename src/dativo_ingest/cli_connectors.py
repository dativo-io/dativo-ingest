"""CLI commands for connector registry management."""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .logging import get_logger
from .registry import CatalogLoader, ConnectorRegistry


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
                print(
                    f"  Incremental: {'✓' if resolved.supports_incremental else '✗'}"
                )
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
        registry = ConnectorRegistry()
        connectors = registry.list_connectors(role=role)

        if not connectors:
            if json_output:
                print(json.dumps({"connectors": [], "count": 0}, indent=2))
            else:
                print("No connectors found in registry")
            return 0

        format_connector_list(connectors, registry, json_output, verbose)
        return 0

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
        registry = ConnectorRegistry()
        resolved = registry.resolve_connector(name, engine=engine)

        format_connector_inspect(name, resolved, json_output)
        return 0

    except Exception as e:
        if json_output:
            print(json.dumps({"error": str(e)}, indent=2))
        else:
            print(f"ERROR: Failed to inspect connector: {e}", file=sys.stderr)
        return 2


def connectors_sync_command(
    catalog_url: Optional[str] = None,
    catalog_file: Optional[str] = None,
    json_output: bool = False,
    verbose: bool = False,
) -> int:
    """Sync external connector catalogs.

    Args:
        catalog_url: Optional URL to fetch catalog from
        catalog_file: Optional local catalog file to copy
        json_output: Whether to output JSON
        verbose: Whether to include verbose details

    Returns:
        Exit code (0=success, 2=failure)
    """
    logger = get_logger()

    try:
        # Determine catalogs directory
        catalogs_dir = None
        possible_paths = [
            Path("/app/registry/catalogs"),
            Path("registry/catalogs"),
            Path(__file__).parent.parent.parent / "registry" / "catalogs",
        ]
        for path in possible_paths:
            if path.exists():
                catalogs_dir = path
                break

        if not catalogs_dir:
            # Create the directory
            for path in possible_paths:
                try:
                    path.mkdir(parents=True, exist_ok=True)
                    catalogs_dir = path
                    break
                except Exception:
                    continue

        if not catalogs_dir:
            if json_output:
                print(
                    json.dumps(
                        {"error": "Failed to create catalogs directory"}, indent=2
                    )
                )
            else:
                print("ERROR: Failed to create catalogs directory", file=sys.stderr)
            return 2

        synced = False

        # Handle URL sync
        if catalog_url:
            if json_output:
                print(
                    json.dumps(
                        {
                            "error": "URL sync not implemented yet. Please download the catalog manually."
                        },
                        indent=2,
                    )
                )
            else:
                print("ERROR: URL sync not implemented yet", file=sys.stderr)
                print(
                    "Please download the catalog manually and use --catalog-file",
                    file=sys.stderr,
                )
            return 2

        # Handle file copy
        if catalog_file:
            import shutil

            source_path = Path(catalog_file)
            if not source_path.exists():
                if json_output:
                    print(json.dumps({"error": f"File not found: {catalog_file}"}, indent=2))
                else:
                    print(f"ERROR: File not found: {catalog_file}", file=sys.stderr)
                return 2

            dest_path = catalogs_dir / source_path.name
            shutil.copy2(source_path, dest_path)

            logger.info(
                f"Copied catalog: {source_path.name}",
                extra={"event_type": "catalog_synced"},
            )
            synced = True

            if not json_output:
                print(f"✓ Synced catalog: {source_path.name} -> {dest_path}")

        # If no specific sync action, just reload existing catalogs
        if not synced:
            loader = CatalogLoader(catalogs_dir)
            catalog_names = loader.get_catalog_names()

            if json_output:
                print(
                    json.dumps(
                        {
                            "catalogs": catalog_names,
                            "count": len(catalog_names),
                            "status": "loaded",
                        },
                        indent=2,
                    )
                )
            else:
                if catalog_names:
                    print(f"\nLoaded Catalogs ({len(catalog_names)}):")
                    for catalog_name in catalog_names:
                        connectors = loader.list_connectors(catalog_name)
                        print(f"  - {catalog_name}: {len(connectors)} connectors")
                else:
                    print("No catalogs found. Catalogs are optional.")
                    print(
                        f"To add a catalog, place a JSON file in: {catalogs_dir}"
                    )

            return 0

        # Show sync results
        if json_output:
            loader = CatalogLoader(catalogs_dir)
            catalog_names = loader.get_catalog_names()
            print(
                json.dumps(
                    {
                        "catalogs": catalog_names,
                        "count": len(catalog_names),
                        "status": "synced",
                    },
                    indent=2,
                )
            )
        else:
            print("\n✓ Catalog sync complete")
            loader = CatalogLoader(catalogs_dir)
            catalog_names = loader.get_catalog_names()
            if verbose and catalog_names:
                print(f"\nAvailable Catalogs ({len(catalog_names)}):")
                for catalog_name in catalog_names:
                    connectors = loader.list_connectors(catalog_name)
                    print(f"  - {catalog_name}: {len(connectors)} connectors")

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
