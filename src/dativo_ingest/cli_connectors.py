"""CLI commands for connector lifecycle management."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .connectors.catalog import ConnectorCatalog
from .connectors.resolver import ConnectorResolver
from .config import ConnectorRecipe
from .logging import get_logger, setup_logging
from .validator import ConnectorValidator


def connectors_list_command(args: argparse.Namespace) -> int:
    """List all connectors with resolved metadata.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0=success, 2=failure)
    """
    logger = setup_logging(level="INFO", redact_secrets=True)

    try:
        # Load registry
        registry_path = Path(args.registry_path) if args.registry_path else Path(__file__).parent.parent.parent / "registry" / "connectors.yaml"
        if not registry_path.exists():
            print(f"ERROR: Registry file not found: {registry_path}", file=sys.stderr)
            return 2

        with open(registry_path, "r") as f:
            registry_data = yaml.safe_load(f)

        # Initialize catalog and resolver
        catalog_dir = Path(args.catalog_dir) if args.catalog_dir else registry_path.parent / "catalogs"
        catalog = ConnectorCatalog(catalog_dir)
        catalog.load()
        resolver = ConnectorResolver(catalog_dir)

        connectors = registry_data.get("connectors", {})
        results = []

        for connector_name, connector_info in connectors.items():
            # Get engine type
            engine_type = connector_info.get("default_engine", "native")

            # Try to load connector recipe if path is known
            connector_recipe = None
            # Note: In a real implementation, we'd need to know the recipe path
            # For now, we'll just use the registry info

            # Get resolved info
            resolved_info = resolver.get_resolved_info(
                connector_name=connector_name,
                engine_type=engine_type,
                connector_recipe=connector_recipe,
            )

            # Merge registry info with resolved info
            result = {
                "name": connector_name,
                "category": connector_info.get("category"),
                "engine": engine_type,
                "engines_supported": connector_info.get("engines_supported", []),
                "docker_image": resolved_info.get("docker_image"),
                "version": resolved_info.get("version"),
                "external_id": resolved_info.get("external_id") or connector_info.get("external_id"),
                "source_of_truth": connector_info.get("source_of_truth"),
                "capabilities": resolved_info.get("capabilities", []),
                "supports_incremental": connector_info.get("supports_incremental", False),
                "allowed_in_cloud": connector_info.get("allowed_in_cloud", True),
            }

            # Add catalog metadata if available
            catalog_entry = resolved_info.get("catalog_entry")
            if catalog_entry:
                result["catalog_metadata"] = {
                    "external_id": catalog_entry.external_id,
                    "docker_image": catalog_entry.docker_image_default,
                    "version": catalog_entry.version_default,
                }

            results.append(result)

        # Output results
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            # Table format
            print(f"\n{'Name':<20} {'Engine':<12} {'Docker Image':<40} {'Version':<15} {'Source':<10}")
            print("-" * 100)
            for result in sorted(results, key=lambda x: x["name"]):
                docker_image = result.get("docker_image") or "-"
                version = result.get("version") or "-"
                source = result.get("source_of_truth") or "native"
                print(
                    f"{result['name']:<20} {result['engine']:<12} {docker_image:<40} {version:<15} {source:<10}"
                )

        logger.info(
            f"Listed {len(results)} connectors",
            extra={"event_type": "connectors_listed", "count": len(results)},
        )

        return 0

    except Exception as e:
        logger.error(
            f"Failed to list connectors: {e}",
            extra={"event_type": "connectors_list_error"},
            exc_info=True,
        )
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


def connectors_sync_command(args: argparse.Namespace) -> int:
    """Sync external connector catalogs.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0=success, 2=failure)
    """
    logger = setup_logging(level="INFO", redact_secrets=True)

    try:
        # Determine catalog directory
        if args.catalog_dir:
            catalog_dir = Path(args.catalog_dir)
        else:
            registry_path = Path(__file__).parent.parent.parent / "registry" / "connectors.yaml"
            catalog_dir = registry_path.parent / "catalogs"

        catalog = ConnectorCatalog(catalog_dir)

        # Sync from Airbyte
        if args.source == "airbyte" or args.source == "all":
            catalog_url = args.catalog_url or None
            output_file = catalog_dir / "airbyte.json" if not args.output else Path(args.output)
            catalog.sync_from_airbyte(catalog_url=catalog_url, output_file=output_file)
            print(f"✓ Synced Airbyte catalog to {output_file}")

        # Add other sources here (singer, meltano, etc.)
        if args.source == "singer":
            print("ERROR: Singer catalog sync not yet implemented", file=sys.stderr)
            return 2

        if args.source == "meltano":
            print("ERROR: Meltano catalog sync not yet implemented", file=sys.stderr)
            return 2

        logger.info(
            f"Synced connector catalog from {args.source}",
            extra={"event_type": "catalog_synced", "source": args.source},
        )

        return 0

    except Exception as e:
        logger.error(
            f"Failed to sync catalog: {e}",
            extra={"event_type": "catalog_sync_error"},
            exc_info=True,
        )
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


def connectors_inspect_command(args: argparse.Namespace) -> int:
    """Inspect a specific connector and show resolved metadata.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0=success, 2=failure)
    """
    logger = setup_logging(level="INFO", redact_secrets=True)

    try:
        connector_name = args.name

        # Load registry
        registry_path = Path(args.registry_path) if args.registry_path else Path(__file__).parent.parent.parent / "registry" / "connectors.yaml"
        if not registry_path.exists():
            print(f"ERROR: Registry file not found: {registry_path}", file=sys.stderr)
            return 2

        with open(registry_path, "r") as f:
            registry_data = yaml.safe_load(f)

        connectors = registry_data.get("connectors", {})
        if connector_name not in connectors:
            print(f"ERROR: Connector '{connector_name}' not found in registry", file=sys.stderr)
            return 2

        connector_info = connectors[connector_name]

        # Initialize catalog and resolver
        catalog_dir = Path(args.catalog_dir) if args.catalog_dir else registry_path.parent / "catalogs"
        catalog = ConnectorCatalog(catalog_dir)
        catalog.load()
        resolver = ConnectorResolver(catalog_dir)

        # Get engine type
        engine_type = connector_info.get("default_engine", "native")

        # Try to load connector recipe if we can find it
        connector_recipe = None
        # In a real implementation, we'd search for the recipe file
        # For now, we'll work with registry info

        # Get resolved info
        resolved_info = resolver.get_resolved_info(
            connector_name=connector_name,
            engine_type=engine_type,
            connector_recipe=connector_recipe,
        )

        # Build inspection result
        result = {
            "name": connector_name,
            "registry": {
                "category": connector_info.get("category"),
                "default_engine": engine_type,
                "engines_supported": connector_info.get("engines_supported", []),
                "external_id": connector_info.get("external_id"),
                "docker_image_default": connector_info.get("docker_image_default"),
                "version_default": connector_info.get("version_default"),
                "source_of_truth": connector_info.get("source_of_truth"),
                "supports_incremental": connector_info.get("supports_incremental", False),
                "allowed_in_cloud": connector_info.get("allowed_in_cloud", True),
                "objects_supported": connector_info.get("objects_supported", []),
            },
            "resolved": {
                "engine": resolved_info.get("engine_type"),
                "docker_image": resolved_info.get("docker_image"),
                "version": resolved_info.get("version"),
                "external_id": resolved_info.get("external_id"),
                "capabilities": resolved_info.get("capabilities", []),
            },
        }

        # Add catalog entry if available
        catalog_entry = resolved_info.get("catalog_entry")
        if catalog_entry:
            result["catalog"] = {
                "external_id": catalog_entry.external_id,
                "docker_image_default": catalog_entry.docker_image_default,
                "version_default": catalog_entry.version_default,
                "capabilities": catalog_entry.capabilities,
                "metadata": catalog_entry.metadata,
            }

        # Output result
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"\nConnector: {connector_name}")
            print("=" * 80)
            print(f"\nRegistry Information:")
            print(f"  Category: {result['registry'].get('category', 'N/A')}")
            print(f"  Default Engine: {result['registry'].get('default_engine', 'N/A')}")
            print(f"  Engines Supported: {', '.join(result['registry'].get('engines_supported', []))}")
            print(f"  Source of Truth: {result['registry'].get('source_of_truth', 'native')}")
            print(f"  Supports Incremental: {result['registry'].get('supports_incremental', False)}")
            print(f"  Allowed in Cloud: {result['registry'].get('allowed_in_cloud', True)}")

            print(f"\nResolved Configuration:")
            print(f"  Engine: {result['resolved'].get('engine', 'N/A')}")
            print(f"  Docker Image: {result['resolved'].get('docker_image', 'N/A')}")
            print(f"  Version: {result['resolved'].get('version', 'N/A')}")
            print(f"  External ID: {result['resolved'].get('external_id', 'N/A')}")
            print(f"  Capabilities: {', '.join(result['resolved'].get('capabilities', [])) or 'None'}")

            if "catalog" in result:
                print(f"\nCatalog Entry:")
                print(f"  External ID: {result['catalog'].get('external_id', 'N/A')}")
                print(f"  Docker Image: {result['catalog'].get('docker_image_default', 'N/A')}")
                print(f"  Version: {result['catalog'].get('version_default', 'N/A')}")

        logger.info(
            f"Inspected connector: {connector_name}",
            extra={"event_type": "connector_inspected", "connector": connector_name},
        )

        return 0

    except Exception as e:
        logger.error(
            f"Failed to inspect connector: {e}",
            extra={"event_type": "connector_inspect_error"},
            exc_info=True,
        )
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
