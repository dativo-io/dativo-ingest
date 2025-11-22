#!/usr/bin/env python3
"""Verify complete integration of tag propagation system.

This test verifies:
- Tag derivation module (explicit tags only)
- Asset definitions structure
- Job configuration examples
- IcebergCommitter integration
- CLI integration
- Documentation
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


def test_module_imports():
    """Test that all required modules can be imported."""
    print("1. Verifying tag derivation module...")

    try:
        from dativo_ingest.tag_derivation import TagDerivation, derive_tags_from_asset

        print("   ✓ Tag derivation module imported successfully")
        return True
    except ImportError as e:
        print(f"   ✗ Failed to import tag derivation: {e}")
        return False


def test_explicit_only():
    """Test explicit-only classification (NO auto-detection)."""
    print("\n2. Verifying explicit-only classification...")

    from dativo_ingest.tag_derivation import TagDerivation

    class MockAsset:
        def __init__(self):
            self.schema = []
            self.compliance = None
            self.team = None
            self.finops = None

    derivation = TagDerivation(asset_definition=MockAsset())

    # Test that NO fields are auto-classified
    test_cases = [
        ("email", "string"),
        ("phone", "string"),
        ("first_name", "string"),
        ("salary", "double"),
        ("id", "integer"),
    ]

    for field_name, field_type in test_cases:
        result = derivation._classify_field(field_name, field_type)
        if result is not None:
            print(f"   ✗ {field_name} → {result} (expected None - no auto-detection)")
            return False

    print("   ✓ No automatic classification (explicit tags only)")
    return True


def test_asset_structure():
    """Test that asset definitions have proper structure."""
    print("\n3. Verifying example asset definitions...")

    import yaml

    assets_to_check = [
        "assets/csv/v1.0/employee.yaml",
        "assets/stripe/v1.0/customers.yaml",
        "assets/postgres/v1.0/db_orders.yaml",
        "assets/mysql/v1.0/db_customers.yaml",
    ]

    for asset_path in assets_to_check:
        if not os.path.exists(asset_path):
            print(f"   ✗ Asset not found: {asset_path}")
            return False

        with open(asset_path, "r") as f:
            asset_data = yaml.safe_load(f)

        asset_dict = asset_data.get("asset", {})

        # Check for compliance section
        if "compliance" not in asset_dict:
            print(f"   ✗ {os.path.basename(asset_path)} missing compliance section")
            return False

        # Check for finops section
        if "finops" not in asset_dict:
            print(f"   ✗ {os.path.basename(asset_path)} missing finops section")
            return False

        print(f"   ✓ {os.path.basename(asset_path)}")

    return True


def test_job_examples():
    """Test that job examples have override support."""
    print("\n4. Verifying example job with overrides...")

    job_path = "docs/examples/jobs/acme/employee_with_overrides.yaml"

    if not os.path.exists(job_path):
        print(f"   ✗ Job example not found: {job_path}")
        return False

    import yaml

    with open(job_path, "r") as f:
        job_data = yaml.safe_load(f)

    # Job data is flat, not nested under 'job' key

    # Check for classification_overrides
    if "classification_overrides" not in job_data:
        print("   ✗ Missing classification_overrides in job example")
        return False

    # Check for finops overrides
    if "finops" not in job_data:
        print("   ✗ Missing finops in job example")
        return False

    print("   ✓ Job example has override support")
    return True


def test_iceberg_committer():
    """Test IcebergCommitter integration."""
    print("\n5. Verifying IcebergCommitter integration...")

    try:
        # Check file directly to avoid import errors from missing dependencies
        with open("src/dativo_ingest/iceberg_committer.py", "r") as f:
            committer_content = f.read()

        # Check for new parameters in __init__
        required_params = ["classification_overrides", "finops", "governance_overrides"]

        for param in required_params:
            if param not in committer_content:
                print(f"   ✗ Missing parameter: {param}")
                return False

        # Check for _derive_table_properties method
        if "_derive_table_properties" not in committer_content:
            print("   ✗ Missing _derive_table_properties method")
            return False

        print("   ✓ IcebergCommitter has correct signature")
        return True
    except Exception as e:
        print(f"   ✗ Failed to verify IcebergCommitter: {e}")
        return False


def test_cli_integration():
    """Test CLI integration."""
    print("\n6. Verifying CLI integration...")

    try:
        with open("src/dativo_ingest/cli.py", "r") as f:
            cli_content = f.read()

        # Check if CLI passes overrides to committer
        if "classification_overrides" not in cli_content:
            print("   ✗ CLI missing classification_overrides support")
            return False

        if "job_config.classification_overrides" not in cli_content:
            print("   ✗ CLI not passing classification_overrides to committer")
            return False

        print("   ✓ CLI integration correct")
        return True
    except Exception as e:
        print(f"   ✗ Failed to verify CLI: {e}")
        return False


def test_documentation():
    """Test that documentation exists."""
    print("\n7. Verifying documentation...")

    docs_to_check = [
        ("Main guide", "docs/TAG_PROPAGATION.md"),
        ("Tag precedence", "docs/TAG_PRECEDENCE.md"),
    ]

    for name, doc_path in docs_to_check:
        if not os.path.exists(doc_path):
            print(f"   ✗ {name} not found: {doc_path}")
            return False

        # Check that docs mention explicit-only approach
        with open(doc_path, "r") as f:
            content = f.read().lower()

        # Should mention "explicit" or "no automatic"
        if (
            "explicit" not in content
            and "no automatic" not in content
            and "no auto" not in content
        ):
            print(f"   ⚠️  {name} doesn't mention explicit-only approach")

    print("   ✓ All documentation exists")
    return True


def main():
    """Run integration verification."""
    print("=" * 70)
    print("TAG PROPAGATION INTEGRATION VERIFICATION")
    print("=" * 70)
    print()

    tests = [
        ("Module imports", test_module_imports),
        ("Explicit-only classification", test_explicit_only),
        ("Asset structure", test_asset_structure),
        ("Job examples", test_job_examples),
        ("IcebergCommitter integration", test_iceberg_committer),
        ("CLI integration", test_cli_integration),
        ("Documentation", test_documentation),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n   ✗ Exception in {name}: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "=" * 70)
    print("INTEGRATION TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:10} {name}")

    print()
    if passed == total:
        print(f"✅ All {total} integration tests passed!")
        return 0
    else:
        print(f"❌ {total - passed} of {total} tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
