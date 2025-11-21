#!/usr/bin/env python3
"""Validate that all asset definitions are ODCS v3.0.2 compliant."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

try:
    import jsonschema
    import yaml
except ImportError:
    print("✗ Missing dependencies. Install with: pip install pyyaml jsonschema")
    sys.exit(1)


def load_schema():
    """Load the extended ODCS schema."""
    schema_path = Path("schemas/odcs/dativo-odcs-3.0.2-extended.schema.json")
    if not schema_path.exists():
        print(f"✗ Schema not found: {schema_path}")
        return None

    with open(schema_path, "r") as f:
        return json.load(f)


def convert_asset_to_odcs_format(asset_data):
    """Convert asset definition to ODCS v3.0.2 format."""
    if "asset" in asset_data:
        # Old format with nested 'asset' key
        odcs_data = asset_data["asset"].copy()
    else:
        # Already in new format
        odcs_data = asset_data.copy()

    # Ensure required ODCS fields
    if "$schema" not in odcs_data:
        odcs_data["$schema"] = "schemas/odcs/dativo-odcs-3.0.2-extended.schema.json"

    if "apiVersion" not in odcs_data:
        odcs_data["apiVersion"] = "v3.0.2"

    if "kind" not in odcs_data:
        odcs_data["kind"] = "DataContract"

    if "status" not in odcs_data:
        odcs_data["status"] = "active"

    if "id" not in odcs_data:
        import uuid

        odcs_data["id"] = str(uuid.uuid4())

    # Migrate governance to team if needed
    if "governance" in odcs_data:
        governance = odcs_data.get("governance", {})
        if "owner" in governance:
            # Convert to ODCS team format (simplified)
            odcs_data["team"] = {"owner": governance["owner"]}

        # Move tags to top level if present
        if "tags" in governance and "tags" not in odcs_data:
            odcs_data["tags"] = governance["tags"]

    return odcs_data


def validate_asset(asset_path, schema):
    """Validate a single asset definition."""
    try:
        with open(asset_path, "r") as f:
            asset_data = yaml.safe_load(f)

        if not asset_data:
            return False, "Empty file"

        # Convert to ODCS format
        odcs_data = convert_asset_to_odcs_format(asset_data)

        # Create resolver for relative $refs
        schema_dir = Path("schemas/odcs")
        resolver = jsonschema.RefResolver(
            base_uri=f"file://{schema_dir.absolute()}/",
            referrer=schema,
        )

        # Validate against schema
        jsonschema.validate(instance=odcs_data, schema=schema, resolver=resolver)

        # Additional checks for Dativo requirements
        errors = []

        # Check required Dativo fields
        if "source_type" not in odcs_data:
            errors.append("Missing required field: source_type")

        if "object" not in odcs_data:
            errors.append("Missing required field: object")

        if "schema" not in odcs_data or not odcs_data["schema"]:
            errors.append("Missing or empty schema field")

        # Check team/owner
        if "team" in odcs_data:
            team = odcs_data["team"]
            if isinstance(team, dict):
                if "owner" not in team:
                    errors.append("team must have 'owner' field")
            elif isinstance(team, list):
                # ODCS format - array of team members
                pass
            else:
                errors.append("team must be object or array")
        else:
            errors.append("Missing required field: team")

        # Check compliance section if present
        if "compliance" in odcs_data:
            compliance = odcs_data["compliance"]
            if "classification" in compliance and not isinstance(
                compliance["classification"], list
            ):
                errors.append("compliance.classification must be an array")
            if "regulations" in compliance and not isinstance(
                compliance["regulations"], list
            ):
                errors.append("compliance.regulations must be an array")

        # Check finops section if present
        if "finops" in odcs_data:
            finops = odcs_data["finops"]
            if "business_tags" in finops and not isinstance(
                finops["business_tags"], list
            ):
                errors.append("finops.business_tags must be an array")
            if "environment" in finops:
                valid_envs = ["production", "staging", "development", "test"]
                if finops["environment"] not in valid_envs:
                    errors.append(f"finops.environment must be one of: {valid_envs}")

        if errors:
            return False, "; ".join(errors)

        return True, "Valid"

    except jsonschema.ValidationError as e:
        return False, f"Schema validation error: {e.message}"
    except yaml.YAMLError as e:
        return False, f"YAML parse error: {e}"
    except Exception as e:
        return False, f"Unexpected error: {e}"


def main():
    """Validate all asset definitions."""
    print("=" * 70)
    print("ODCS v3.0.2 COMPLIANCE VALIDATION")
    print("=" * 70)
    print()

    # Load schema
    print("Loading ODCS v3.0.2 extended schema...")
    schema = load_schema()
    if not schema:
        return 1
    print("✓ Schema loaded\n")

    # Find all asset definition files
    assets_dir = Path("assets").resolve()
    if not assets_dir.exists():
        print(f"✗ Assets directory not found: {assets_dir}")
        return 1

    asset_files = list(assets_dir.rglob("*.yaml"))
    if not asset_files:
        print(f"✗ No asset files found in {assets_dir}")
        return 1

    print(f"Found {len(asset_files)} asset definition(s)\n")
    print("-" * 70)

    # Validate each asset
    results = []
    cwd = Path.cwd().resolve()
    for asset_path in sorted(asset_files):
        # Resolve to absolute path first, then compute relative path
        asset_path_abs = asset_path.resolve()
        try:
            relative_path = str(asset_path_abs.relative_to(cwd))
        except ValueError:
            # If path is not under cwd, use the path as string
            relative_path = str(asset_path)
        print(f"\nValidating: {relative_path}")

        valid, message = validate_asset(asset_path, schema)
        results.append((relative_path, valid, message))

        if valid:
            print(f"  ✓ {message}")
        else:
            print(f"  ✗ {message}")

    # Summary
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)

    valid_count = sum(1 for _, valid, _ in results if valid)
    invalid_count = len(results) - valid_count

    for path, valid, message in results:
        status = "✓ PASS" if valid else "✗ FAIL"
        print(f"{status:10} {path}")
        if not valid:
            print(f"           {message}")

    print(f"\nTotal: {len(results)} asset(s)")
    print(f"Valid: {valid_count}")
    print(f"Invalid: {invalid_count}")

    if invalid_count == 0:
        print("\n✓ All assets are ODCS v3.0.2 compliant!")
        return 0
    else:
        print(f"\n✗ {invalid_count} asset(s) failed validation")
        return 1


if __name__ == "__main__":
    sys.exit(main())
