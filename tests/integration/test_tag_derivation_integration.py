#!/usr/bin/env python3
"""Simple validation script for tag derivation implementation."""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))


def test_module_structure():
    """Test that the tag_derivation module has the expected structure."""
    from dativo_ingest import tag_derivation

    # Check for main class
    assert hasattr(tag_derivation, "TagDerivation"), "TagDerivation class not found"

    # Check for convenience function
    assert hasattr(
        tag_derivation, "derive_tags_from_asset"
    ), "derive_tags_from_asset function not found"

    # Check TagDerivation methods
    cls = tag_derivation.TagDerivation
    expected_methods = [
        "derive_field_classifications",
        "derive_default_classification",
        "derive_governance_tags",
        "derive_finops_tags",
        "derive_all_tags",
    ]

    for method in expected_methods:
        assert hasattr(cls, method), f"Method {method} not found in TagDerivation"

    print("✓ Tag derivation module structure is correct")
    return True


def test_explicit_classification_only():
    """Test that NO automatic classification is performed."""
    from dativo_ingest.tag_derivation import TagDerivation

    # Mock asset definition with minimal structure
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
        ("first_name", "string"),
        ("phone", "string"),
        ("salary", "double"),
        ("amount", "double"),
        ("id", "integer"),
        ("status", "string"),
    ]

    for field_name, field_type in test_cases:
        result = derivation._classify_field(field_name, field_type)
        if result is not None:
            print(
                f"✗ Unexpected auto-classification: {field_name} -> {result} (should be None)"
            )
            return False

    print("✓ No automatic classification (explicit tags only)")
    return True


def test_iceberg_committer_signature():
    """Test that IcebergCommitter has the expected signature."""
    import ast
    import inspect

    # Read the source file directly to avoid import issues
    with open("src/dativo_ingest/iceberg_committer.py", "r") as f:
        source = f.read()

    # Check for required imports
    if "from .tag_derivation import derive_tags_from_asset" not in source:
        print("✗ IcebergCommitter missing tag_derivation import")
        return False

    # Parse the AST to check __init__ signature
    tree = ast.parse(source)

    found_init = False
    found_derive_props = False
    found_update_props = False

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if node.name == "__init__":
                found_init = True
                # Check for new parameters
                param_names = [arg.arg for arg in node.args.args]
                required_params = [
                    "classification_overrides",
                    "finops",
                    "governance_overrides",
                ]
                for param in required_params:
                    if param not in param_names:
                        print(f"✗ IcebergCommitter.__init__ missing parameter: {param}")
                        return False
            elif node.name == "_derive_table_properties":
                found_derive_props = True
            elif node.name == "_update_table_properties":
                found_update_props = True

    if not found_init:
        print("✗ IcebergCommitter.__init__ not found")
        return False
    if not found_derive_props:
        print("✗ IcebergCommitter._derive_table_properties not found")
        return False
    if not found_update_props:
        print("✗ IcebergCommitter._update_table_properties not found")
        return False

    print("✓ IcebergCommitter signature is correct")
    return True


def test_config_extensions():
    """Test that config has the expected extensions."""
    import ast

    # Read the config file directly
    with open("src/dativo_ingest/config.py", "r") as f:
        source = f.read()

    # Check for FinOpsModel class
    if "class FinOpsModel" not in source:
        print("✗ FinOpsModel class not found in config")
        return False

    # Check for finops field in AssetDefinition
    if "finops: Optional[FinOpsModel]" not in source:
        print("✗ finops field not found in AssetDefinition")
        return False

    # Check for tag override fields in JobConfig
    required_fields = [
        "classification_overrides: Optional[Dict[str, str]]",
        "finops: Optional[Dict[str, Any]]",
        "governance_overrides: Optional[Dict[str, Any]]",
    ]

    for field in required_fields:
        if field not in source:
            print(f"✗ JobConfig missing field: {field}")
            return False

    print("✓ Config extensions are correct")
    return True


def main():
    """Run all validation tests."""
    print("Validating tag derivation implementation...\n")

    tests = [
        ("Module structure", test_module_structure),
        ("Explicit classification only", test_explicit_classification_only),
        ("IcebergCommitter signature", test_iceberg_committer_signature),
        ("Config extensions", test_config_extensions),
    ]

    results = []
    for name, test_func in tests:
        print(f"\nTesting {name}...")
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"✗ {name} failed with exception: {e}")
            results.append((name, False))

    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:10} {name}")

    all_passed = all(result for _, result in results)

    if all_passed:
        print("\n✓ All validation tests passed!")
        return 0
    else:
        print("\n✗ Some validation tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
