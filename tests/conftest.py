"""Pytest configuration and shared fixtures."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_docker(request):
    """Automatically mock Docker for unit tests only.

    This fixture ensures that docker is always available as a Mock for unit tests,
    even if the docker package is not installed in the test environment.

    Integration and smoke tests that need real Docker will skip this mock
    if they have the 'integration', 'smoke', or 'requires_docker' markers.

    Tests that need to customize the mock can still patch docker explicitly.
    """
    # Check if this test should use real Docker (integration/smoke tests)
    markers = [marker.name for marker in request.node.iter_markers()]
    use_real_docker = any(
        marker in markers for marker in ["integration", "smoke", "requires_docker"]
    )

    # Also check if test file is in integration directory or has integration/smoke in name
    test_path = str(request.node.fspath)
    is_integration_test = (
        "/integration/" in test_path
        or "_integration.py" in test_path
        or "_smoke" in test_path
    )

    # Skip mocking if this is an integration/smoke test
    if use_real_docker or is_integration_test:
        yield None
        return

    # For unit tests, provide the mock
    with patch("dativo_ingest.sandbox.docker") as mock_docker_module:
        # Set up a default mock client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client
        yield mock_docker_module


@pytest.fixture(autouse=True)
def cleanup_wal_files(request):
    """Automatically clean up WAL temp files after each test.

    This fixture ensures that:
    1. WAL temp files (*.wal.json.tmp) are cleaned up from all locations
    2. WAL files in tests/fixtures/wal created during tests are cleaned up

    The cleanup runs after each test, even if the test fails.
    Note: Tests using tmp_path fixture will have their WAL files automatically
    cleaned up by pytest, so this focuses on files outside tmp_path.
    """
    # Yield control to the test
    yield

    # Cleanup after test completes
    try:
        import json

        # Clean up temp files (*.wal.json.tmp) in common locations
        cleanup_paths = [
            Path("tests/fixtures/wal"),
            Path("/app/wal"),  # Default WAL location
            Path("/tmp/wal"),
        ]

        # Try to get tmp_path if the test uses it
        try:
            if "tmp_path" in request.fixturenames:
                tmp_path = request.getfixturevalue("tmp_path")
                if tmp_path:
                    cleanup_paths.append(Path(tmp_path))
        except Exception:
            pass

        for base_path in cleanup_paths:
            if not base_path.exists():
                continue

            # Clean up temp files (*.wal.json.tmp)
            for temp_file in base_path.rglob("*.wal.json.tmp"):
                try:
                    if temp_file.exists():
                        temp_file.unlink()
                except Exception:
                    pass  # Ignore cleanup errors

            # For tests/fixtures/wal, clean up WAL files created during tests
            # (preserve any intentional fixture files)
            if base_path == Path("tests/fixtures/wal"):
                for wal_file in base_path.rglob("*.wal.json"):
                    try:
                        if not wal_file.exists():
                            continue

                        # Check if it's a test-generated file by checking the run_id pattern
                        # Test-generated files typically have timestamp run_ids like 20240101_120000
                        try:
                            with open(wal_file, "r") as f:
                                wal_data = json.load(f)
                                run_id = wal_data.get("run_id", "")
                                # If run_id matches timestamp pattern (YYYYMMDD_HHMMSS), clean it
                                # This pattern indicates a test-generated file, not a fixture
                                if (
                                    len(run_id) == 15
                                    and run_id[8] == "_"
                                    and run_id.replace("_", "").isdigit()
                                ):
                                    wal_file.unlink()
                        except (json.JSONDecodeError, IOError):
                            # If we can't read it, it might be corrupted, clean it up
                            wal_file.unlink()
                    except Exception:
                        pass  # Ignore cleanup errors

    except Exception:
        pass  # Don't fail tests if cleanup fails
