"""CLI commands for validation."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .config import AssetDefinition, JobConfig
from .logging import get_logger, setup_logging
from .metrics import record_validate_metric
from .validator import ConnectorValidator


def validate_config_command(args: argparse.Namespace) -> int:
    """Validate job configuration.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0=success, 2=failure)
    """
    path = Path(args.path)
    if not path.exists():
        print(f"ERROR: Config file not found: {path}", file=sys.stderr)
        return 2

    # Set up basic logging
    setup_logging(level="INFO" if args.verbose else "WARNING")
    logger = get_logger()

    results = {
        "valid": False,
        "file": str(path),
        "checks": [],
        "errors": [],
    }

    try:
        # 1. YAML Syntax & JSON Schema
        try:
            job_config = JobConfig.from_yaml(path, validate_schema=True)
            results["checks"].append({"name": "yaml_syntax_and_schema", "status": "passed"})
        except Exception as e:
            results["checks"].append({"name": "yaml_syntax_and_schema", "status": "failed", "error": str(e)})
            raise

        # 2. Asset Definition Existence & Schema Presence
        try:
            job_config.validate_schema_presence()
            results["checks"].append({"name": "asset_definition_presence", "status": "passed"})
        except SystemExit:
            # validate_schema_presence calls sys.exit(2) on failure
            # We catch it to provide structured output
            results["checks"].append({
                "name": "asset_definition_presence",
                "status": "failed",
                "error": "Asset definition missing or invalid"
            })
            raise ValueError("Asset definition validation failed")
        except Exception as e:
             results["checks"].append({
                "name": "asset_definition_presence",
                "status": "failed",
                "error": str(e)
            })
             raise

        # 3. Connector References & Mode Restrictions
        try:
            validator = ConnectorValidator()
            validator.validate_job(job_config, mode=args.mode)
            results["checks"].append({"name": "connector_validation", "status": "passed"})
        except SystemExit:
            results["checks"].append({
                "name": "connector_validation",
                "status": "failed",
                "error": "Connector validation failed (see stderr for details)"
            })
            raise ValueError("Connector validation failed")
        except Exception as e:
            results["checks"].append({"name": "connector_validation", "status": "failed", "error": str(e)})
            raise

        results["valid"] = True

    except Exception as e:
        if not any(e_msg == str(e) for e_msg in results["errors"]):
             results["errors"].append(str(e))

    # Output
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        if results["valid"]:
            print(f"\n✓ CONFIG VALIDATION: VALID")
            print(f"  File: {path}")
            print("\n  No issues found.")
        else:
            print(f"\n✗ CONFIG VALIDATION: INVALID")
            print(f"  File: {path}")
            print("\n  Errors:")
            for error in results["errors"]:
                print(f"  - {error}")
            
            if args.verbose:
                print("\n  Check Details:")
                for check in results["checks"]:
                    status_symbol = "✓" if check["status"] == "passed" else "✗"
                    print(f"  [{status_symbol}] {check['name']}")
                    if check.get("error"):
                        print(f"      Error: {check['error']}")

    record_validate_metric("config", "success" if results["valid"] else "failure")
    return 0 if results["valid"] else 2


def validate_asset_command(args: argparse.Namespace) -> int:
    """Validate asset definition.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0=success, 2=failure)
    """
    path = Path(args.path)
    if not path.exists():
        print(f"ERROR: Asset file not found: {path}", file=sys.stderr)
        return 2

    setup_logging(level="INFO" if args.verbose else "WARNING")

    results = {
        "valid": False,
        "file": str(path),
        "checks": [],
        "errors": [],
    }

    try:
        # 1. YAML Syntax, JSON Schema, ODCS fields, Governance
        # AssetDefinition.from_yaml handles all of these
        try:
            asset = AssetDefinition.from_yaml(path, validate_schema=not args.skip_schema)
            
            # Explicit governance validation (already called in model_validator but good to be explicit in checks)
            # Actually model_validator is called automatically by Pydantic on instantiation
            
            results["checks"].append({"name": "yaml_syntax", "status": "passed"})
            if not args.skip_schema:
                 results["checks"].append({"name": "json_schema_validation", "status": "passed"})
            results["checks"].append({"name": "odcs_requirements", "status": "passed"})
            results["checks"].append({"name": "governance_requirements", "status": "passed"})
            
        except Exception as e:
            # Try to determine which check failed
            error_msg = str(e)
            failed_check = "validation"
            if "YAML" in error_msg:
                failed_check = "yaml_syntax"
            elif "Schema validation failed" in error_msg:
                failed_check = "json_schema_validation"
            elif "team.owner is required" in error_msg or "oncall_rotation is required" in error_msg:
                failed_check = "governance_requirements"
            
            results["checks"].append({"name": failed_check, "status": "failed", "error": error_msg})
            raise

        results["valid"] = True

    except Exception as e:
         if not any(e_msg == str(e) for e_msg in results["errors"]):
            results["errors"].append(str(e))

    # Output
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        if results["valid"]:
            print(f"\n✓ ASSET VALIDATION: VALID")
            print(f"  File: {path}")
            if args.verbose:
                print(f"  Name: {asset.name}")
                print(f"  Version: {asset.version}")
            print("\n  No issues found.")
        else:
            print(f"\n✗ ASSET VALIDATION: INVALID")
            print(f"  File: {path}")
            print("\n  Errors:")
            for error in results["errors"]:
                print(f"  - {error}")
            
            if args.verbose:
                print("\n  Check Details:")
                for check in results["checks"]:
                    status_symbol = "✓" if check["status"] == "passed" else "✗"
                    print(f"  [{status_symbol}] {check['name']}")
                    if check.get("error"):
                        print(f"      Error: {check['error']}")

    record_validate_metric("asset", "success" if results["valid"] else "failure")
    return 0 if results["valid"] else 2
