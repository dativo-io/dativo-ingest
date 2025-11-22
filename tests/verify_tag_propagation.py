#!/usr/bin/env python3
"""Verify tag propagation in Iceberg tables.

This script connects to a Nessie catalog and verifies that tags
have been properly propagated to Iceberg table properties.
"""

import os
import sys
from typing import Dict, List, Optional

try:
    from pyiceberg.catalog import load_catalog
except ImportError:
    print("⚠️  PyIceberg not installed - skipping tag verification")
    sys.exit(0)


def verify_table_properties(
    catalog_uri: str,
    warehouse: str,
    namespace: str,
    table_name: str,
    expected_tags: Dict[str, str],
) -> bool:
    """Verify that expected tags exist in table properties.

    Args:
        catalog_uri: Nessie catalog URI
        warehouse: Warehouse path
        namespace: Table namespace
        table_name: Table name
        expected_tags: Expected tag key-value pairs

    Returns:
        True if all expected tags match, False otherwise
    """
    print(f"\n🔍 Verifying tags for {namespace}.{table_name}...")

    try:
        # Load catalog
        catalog = load_catalog(
            "nessie",
            **{
                "uri": catalog_uri,
                "warehouse": warehouse,
            },
        )

        # Load table
        table = catalog.load_table(f"{namespace}.{table_name}")

        # Get properties
        properties = table.properties

        # Check expected tags
        all_match = True
        for key, expected_value in expected_tags.items():
            actual_value = properties.get(key)

            if actual_value is None:
                print(f"  ✗ Missing tag: {key}")
                all_match = False
            elif actual_value.lower() != expected_value.lower():
                print(f"  ✗ Tag mismatch: {key}")
                print(f"    Expected: {expected_value}")
                print(f"    Actual:   {actual_value}")
                all_match = False
            else:
                print(f"  ✓ {key}={actual_value}")

        # Show all classification tags
        classification_tags = {
            k: v for k, v in properties.items() if k.startswith("classification.")
        }
        if classification_tags:
            print(f"\n  📋 All classification tags:")
            for k, v in sorted(classification_tags.items()):
                print(f"     {k}={v}")

        # Show all governance tags
        governance_tags = {
            k: v for k, v in properties.items() if k.startswith("governance.")
        }
        if governance_tags:
            print(f"\n  📋 All governance tags:")
            for k, v in sorted(governance_tags.items()):
                print(f"     {k}={v}")

        # Show all finops tags
        finops_tags = {k: v for k, v in properties.items() if k.startswith("finops.")}
        if finops_tags:
            print(f"\n  📋 All finops tags:")
            for k, v in sorted(finops_tags.items()):
                print(f"     {k}={v}")

        return all_match

    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def main():
    """Run tag verification tests."""
    print("=" * 70)
    print("TAG PROPAGATION VERIFICATION")
    print("=" * 70)

    # Get configuration from environment
    nessie_uri = os.getenv("NESSIE_URI", "http://localhost:19120/api/v1")
    warehouse = os.getenv("WAREHOUSE", "s3://test-bucket/warehouse")

    print(f"\nNessie URI: {nessie_uri}")
    print(f"Warehouse: {warehouse}")

    # Test cases - tables that should exist after smoke tests
    test_cases = [
        {
            "namespace": "test_tenant",
            "table_name": "csv_employee",
            "expected_tags": {
                "classification.default": "pii",
                "governance.retention_days": "90",
                "finops.cost_center": "HR-001",
                "asset.name": "csv_employee",
                "asset.source_type": "csv",
            },
        },
        {
            "namespace": "test_tenant",
            "table_name": "stripe_customers",
            "expected_tags": {
                "classification.default": "pii",
                "governance.retention_days": "365",
                "finops.cost_center": "SALES-001",
                "asset.name": "stripe_customers",
                "asset.source_type": "stripe",
            },
        },
    ]

    results = []
    for test_case in test_cases:
        result = verify_table_properties(
            catalog_uri=nessie_uri,
            warehouse=warehouse,
            namespace=test_case["namespace"],
            table_name=test_case["table_name"],
            expected_tags=test_case["expected_tags"],
        )
        results.append((test_case["table_name"], result))

    # Summary
    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for table_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:10} {table_name}")

    print()
    if passed == total:
        print(f"✅ All {total} tag verification tests passed!")
        return 0
    else:
        print(f"❌ {total - passed} of {total} tests failed")
        print("\n⚠️  Note: This may be expected if:")
        print("  - Nessie catalog is not configured")
        print("  - Tables haven't been created yet")
        print("  - Running in non-catalog mode")
        return 1


if __name__ == "__main__":
    sys.exit(main())
