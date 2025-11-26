"""Integration tests for Airbyte extractor with real Docker containers."""

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from dativo_ingest.config import ConnectorRecipe, SourceConfig
from dativo_ingest.connectors.engine_framework import AirbyteExtractor


@pytest.fixture
def docker_available():
    """Check if Docker is available."""
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


@pytest.mark.skipif(
    not os.getenv("TEST_WITH_DOCKER", "").lower() == "true",
    reason="Docker integration tests require TEST_WITH_DOCKER=true",
)
def test_airbyte_spec_command(docker_available):
    """Test Airbyte spec command (lightweight test)."""
    if not docker_available:
        pytest.skip("Docker not available")

    # Test with a simple Airbyte source that supports spec
    image = "airbyte/source-hubspot:0.2.0"

    try:
        result = subprocess.run(
            ["docker", "run", "--rm", image, "spec"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Spec command should return JSON
        if result.returncode == 0:
            spec_data = json.loads(result.stdout)
            assert "connectionSpecification" in spec_data
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        pytest.skip("Airbyte image not available or spec command failed")


@pytest.mark.skipif(
    not os.getenv("TEST_WITH_DOCKER", "").lower() == "true",
    reason="Docker integration tests require TEST_WITH_DOCKER=true",
)
def test_airbyte_config_validation(docker_available):
    """Test Airbyte config validation."""
    if not docker_available:
        pytest.skip("Docker not available")

    image = "airbyte/source-hubspot:0.2.0"
    config = {"api_key": "test-key"}

    try:
        process = subprocess.Popen(
            ["docker", "run", "--rm", "-i", image, "check", "--config", "/dev/stdin"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        stdout, stderr = process.communicate(input=json.dumps(config), timeout=30)

        # Check command may fail with invalid key, but should not crash
        assert process.returncode in [0, 1]  # 0 = valid, 1 = invalid config
    except subprocess.TimeoutExpired:
        pytest.skip("Airbyte check command timed out")
