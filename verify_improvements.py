#!/usr/bin/env python3
"""Verification script for platform improvements.

This script verifies that all implemented features are working correctly.
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_imports():
    """Test that all new imports work correctly."""
    print("Testing imports...")
    
    try:
        # Test plugin imports
        from dativo_ingest import (
            BaseReader,
            BaseWriter,
            ConnectionTestResult,
            DiscoveryResult,
            PluginLoader,
        )
        print("  ✓ Plugin classes imported successfully")
        
        # Test error imports
        from dativo_ingest import (
            DativoError,
            ConnectionError,
            NetworkError,
            TimeoutError,
            AuthenticationError,
            InvalidCredentialsError,
            ConfigurationError,
            is_retryable_error,
            get_error_code,
        )
        print("  ✓ Error classes imported successfully")
        
        # Test that version is available
        from dativo_ingest import __version__
        print(f"  ✓ Platform version: {__version__}")
        
        return True
    except ImportError as e:
        print(f"  ✗ Import failed: {e}")
        return False


def test_connection_result():
    """Test ConnectionTestResult class."""
    print("\nTesting ConnectionTestResult...")
    
    try:
        from dativo_ingest import ConnectionTestResult
        
        # Test success result
        result = ConnectionTestResult(
            success=True,
            message="Connected",
            details={"host": "localhost"}
        )
        assert result.success == True
        assert result.message == "Connected"
        assert result.details["host"] == "localhost"
        
        result_dict = result.to_dict()
        assert result_dict["success"] == True
        assert result_dict["message"] == "Connected"
        
        print("  ✓ Success result works")
        
        # Test failure result
        result = ConnectionTestResult(
            success=False,
            message="Auth failed",
            error_code="AUTH_FAILED"
        )
        assert result.success == False
        assert result.error_code == "AUTH_FAILED"
        
        result_dict = result.to_dict()
        assert result_dict["success"] == False
        assert result_dict["error_code"] == "AUTH_FAILED"
        
        print("  ✓ Failure result works")
        return True
    except Exception as e:
        print(f"  ✗ Test failed: {e}")
        return False


def test_discovery_result():
    """Test DiscoveryResult class."""
    print("\nTesting DiscoveryResult...")
    
    try:
        from dativo_ingest import DiscoveryResult
        
        objects = [
            {"name": "users", "type": "table"},
            {"name": "orders", "type": "table"}
        ]
        metadata = {"database": "test"}
        
        result = DiscoveryResult(objects=objects, metadata=metadata)
        assert len(result.objects) == 2
        assert result.metadata["database"] == "test"
        
        result_dict = result.to_dict()
        assert len(result_dict["objects"]) == 2
        assert result_dict["metadata"]["database"] == "test"
        
        print("  ✓ DiscoveryResult works")
        return True
    except Exception as e:
        print(f"  ✗ Test failed: {e}")
        return False


def test_error_hierarchy():
    """Test error hierarchy and helper functions."""
    print("\nTesting error hierarchy...")
    
    try:
        from dativo_ingest import (
            NetworkError,
            InvalidCredentialsError,
            is_retryable_error,
            get_error_code,
        )
        
        # Test retryable error
        network_error = NetworkError("Connection failed")
        assert is_retryable_error(network_error) == True
        assert get_error_code(network_error) == "NETWORK_ERROR"
        print("  ✓ NetworkError is retryable")
        
        # Test non-retryable error
        auth_error = InvalidCredentialsError("Bad password")
        assert is_retryable_error(auth_error) == False
        assert get_error_code(auth_error) == "INVALID_CREDENTIALS"
        print("  ✓ InvalidCredentialsError is not retryable")
        
        # Test error dict
        error_dict = network_error.to_dict()
        assert error_dict["error_code"] == "NETWORK_ERROR"
        assert error_dict["retryable"] == True
        print("  ✓ Error to_dict works")
        
        return True
    except Exception as e:
        print(f"  ✗ Test failed: {e}")
        return False


def test_base_reader():
    """Test BaseReader interface."""
    print("\nTesting BaseReader interface...")
    
    try:
        from dativo_ingest import BaseReader, ConnectionTestResult, DiscoveryResult
        
        # Create a test reader
        class TestReader(BaseReader):
            __version__ = "1.0.0"
            
            def extract(self, state_manager=None):
                yield []
        
        # Check that version is set
        reader = TestReader(None)
        assert reader.__version__ == "1.0.0"
        print("  ✓ Version attribute works")
        
        # Check default check_connection
        result = reader.check_connection()
        assert isinstance(result, ConnectionTestResult)
        assert result.success == True
        print("  ✓ Default check_connection works")
        
        # Check default discover
        result = reader.discover()
        assert isinstance(result, DiscoveryResult)
        assert len(result.objects) == 0
        print("  ✓ Default discover works")
        
        return True
    except Exception as e:
        print(f"  ✗ Test failed: {e}")
        return False


def test_base_writer():
    """Test BaseWriter interface."""
    print("\nTesting BaseWriter interface...")
    
    try:
        from dativo_ingest import BaseWriter, ConnectionTestResult
        
        # Create a test writer
        class TestWriter(BaseWriter):
            __version__ = "1.0.0"
            
            def write_batch(self, records, file_counter):
                return []
        
        # Check that version is set
        writer = TestWriter(None, None, "")
        assert writer.__version__ == "1.0.0"
        print("  ✓ Version attribute works")
        
        # Check default check_connection
        result = writer.check_connection()
        assert isinstance(result, ConnectionTestResult)
        assert result.success == True
        print("  ✓ Default check_connection works")
        
        return True
    except Exception as e:
        print(f"  ✗ Test failed: {e}")
        return False


def test_documentation():
    """Test that all documentation files exist."""
    print("\nTesting documentation...")
    
    docs = [
        "docs/CONNECTOR_VS_PLUGIN_DECISION_TREE.md",
        "docs/PLUGIN_SANDBOXING.md",
        "docs/IMPROVEMENTS_SUMMARY.md",
        "IMPLEMENTATION_REPORT.md",
    ]
    
    all_exist = True
    for doc in docs:
        path = Path(doc)
        if path.exists():
            print(f"  ✓ {doc} exists")
        else:
            print(f"  ✗ {doc} missing")
            all_exist = False
    
    return all_exist


def main():
    """Run all verification tests."""
    print("=" * 60)
    print("Platform Improvements Verification")
    print("=" * 60)
    
    tests = [
        ("Imports", test_imports),
        ("ConnectionTestResult", test_connection_result),
        ("DiscoveryResult", test_discovery_result),
        ("Error Hierarchy", test_error_hierarchy),
        ("BaseReader Interface", test_base_reader),
        ("BaseWriter Interface", test_base_writer),
        ("Documentation", test_documentation),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ {name} failed with exception: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All verification tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
