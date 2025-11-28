"""Pytest configuration and shared fixtures."""

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
