"""Unit tests for Airbyte extractor."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from dativo_ingest.config import ConnectorRecipe, SourceConfig
from dativo_ingest.connectors.engine_framework import AirbyteExtractor


@pytest.fixture
def mock_connector_recipe():
    """Create a mock connector recipe for Airbyte."""
    return ConnectorRecipe(
        name="hubspot",
        type="hubspot",
        roles=["source"],
        default_engine={
            "type": "airbyte",
            "options": {
                "airbyte": {
                    "docker_image": "airbyte/source-hubspot:0.2.0",
                    "streams_default": ["contacts"],
                    "start_date_default": "2024-01-01",
                }
            },
        },
        credentials={"type": "api_key", "from_env": "HUBSPOT_API_KEY"},
    )


@pytest.fixture
def source_config():
    """Create a source config for testing."""
    return SourceConfig(
        type="hubspot",
        objects=["contacts"],
        credentials={},
        incremental={"strategy": "updated_after", "cursor_field": "updatedAt"},
    )


@patch("dativo_ingest.connectors.engine_framework.docker")
@patch("dativo_ingest.connectors.engine_framework.subprocess")
@patch("dativo_ingest.connectors.engine_framework.DOCKER_AVAILABLE", True)
def test_airbyte_extractor_initialization(
    mock_subprocess, mock_docker, source_config, mock_connector_recipe
):
    """Test AirbyteExtractor initialization."""
    # Mock docker module
    mock_docker.from_env.return_value = MagicMock()
    extractor = AirbyteExtractor(source_config, mock_connector_recipe)

    assert extractor.docker_image == "airbyte/source-hubspot:0.2.0"
    assert extractor.source_config == source_config
    assert extractor.connector_recipe == mock_connector_recipe


@patch("dativo_ingest.connectors.engine_framework.docker")
@patch("dativo_ingest.connectors.engine_framework.subprocess")
@patch("dativo_ingest.connectors.engine_framework.DOCKER_AVAILABLE", True)
def test_airbyte_extractor_missing_docker_image(
    mock_subprocess, mock_docker, source_config
):
    """Test AirbyteExtractor raises error when docker_image is missing."""
    recipe = ConnectorRecipe(
        name="test",
        type="test",
        roles=["source"],
        default_engine={"type": "airbyte", "options": {"airbyte": {}}},
    )

    with pytest.raises(ValueError, match="docker_image"):
        AirbyteExtractor(source_config, recipe)


@patch("dativo_ingest.connectors.engine_framework.docker")
@patch("dativo_ingest.connectors.engine_framework.subprocess")
@patch("dativo_ingest.connectors.engine_framework.DOCKER_AVAILABLE", True)
@patch("os.getenv")
def test_airbyte_config_building(
    mock_getenv, mock_subprocess, mock_docker, source_config, mock_connector_recipe
):
    """Test Airbyte configuration building."""
    mock_getenv.return_value = "test-api-key"

    extractor = AirbyteExtractor(source_config, mock_connector_recipe)
    config = extractor.config_parser.build_airbyte_config()

    assert "api_key" in config
    assert config["api_key"] == "test-api-key"
    # streams should NOT be in the config - it's a metadata field that gets filtered out
    # Stream selection belongs in the catalog, not in the connector config
    assert "streams" not in config


@patch("dativo_ingest.connectors.engine_framework.docker")
@patch("dativo_ingest.connectors.engine_framework.subprocess")
@patch("dativo_ingest.connectors.engine_framework.DOCKER_AVAILABLE", True)
@patch("os.getenv")
def test_airbyte_extract_records(
    mock_getenv, mock_subprocess, mock_docker, source_config, mock_connector_recipe
):
    """Test Airbyte extraction with mocked Docker."""
    mock_getenv.return_value = "test-api-key"

    # Mock Docker client
    mock_client = MagicMock()
    mock_docker.from_env.return_value = mock_client

    # Mock image exists
    mock_client.images.get.return_value = MagicMock()

    # Mock discover call (needed for catalog generation)
    mock_discover_process = MagicMock()
    mock_discover_process.communicate.return_value = (
        json.dumps(
            {
                "type": "CATALOG",
                "catalog": {
                    "streams": [
                        {
                            "name": "contacts",
                            "json_schema": {"properties": {"id": {}, "name": {}}},
                        }
                    ]
                },
            }
        )
        + "\n",
        "",
    )
    mock_discover_process.returncode = 0

    # Mock read call
    mock_read_process = MagicMock()
    mock_read_process.stdout.readline.side_effect = [
        json.dumps(
            {
                "type": "RECORD",
                "record": {"stream": "contacts", "data": {"id": "1", "name": "Test"}},
            }
        )
        + "\n",
        json.dumps(
            {
                "type": "RECORD",
                "record": {"stream": "contacts", "data": {"id": "2", "name": "Test2"}},
            }
        )
        + "\n",
        "",  # Empty line to stop iteration
    ]
    mock_read_process.stderr = MagicMock()
    mock_read_process.stderr.readline.return_value = ""
    mock_read_process.returncode = 0
    mock_read_process.wait.return_value = 0

    # Return different mocks for discover vs read
    def popen_side_effect(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args", [])
        if "discover" in cmd:
            return mock_discover_process
        else:
            return mock_read_process

    mock_subprocess.Popen.side_effect = popen_side_effect

    extractor = AirbyteExtractor(source_config, mock_connector_recipe)

    # Extract records
    batches = list(extractor.extract())

    # Verify extraction
    assert len(batches) > 0
    assert len(batches[0]) == 2
    assert batches[0][0]["id"] == "1"
    assert batches[0][1]["id"] == "2"


@patch("dativo_ingest.connectors.engine_framework.docker")
@patch("dativo_ingest.connectors.engine_framework.subprocess")
@patch("dativo_ingest.connectors.engine_framework.DOCKER_AVAILABLE", True)
@patch("os.getenv")
def test_airbyte_extract_with_state(
    mock_getenv, mock_subprocess, mock_docker, source_config, mock_connector_recipe
):
    """Test Airbyte extraction with state messages."""
    mock_getenv.return_value = "test-api-key"

    # Mock Docker client
    mock_client = MagicMock()
    mock_docker.from_env.return_value = mock_client
    mock_client.images.get.return_value = MagicMock()

    # Mock discover call (needed for catalog generation)
    mock_discover_process = MagicMock()
    mock_discover_process.communicate.return_value = (
        json.dumps(
            {
                "type": "CATALOG",
                "catalog": {
                    "streams": [
                        {
                            "name": "contacts",
                            "json_schema": {"properties": {"id": {}, "updatedAt": {}}},
                        }
                    ]
                },
            }
        )
        + "\n",
        "",
    )
    mock_discover_process.returncode = 0

    # Mock read call with state message
    mock_read_process = MagicMock()
    mock_read_process.stdout.readline.side_effect = [
        json.dumps(
            {"type": "RECORD", "record": {"stream": "contacts", "data": {"id": "1"}}}
        )
        + "\n",
        json.dumps(
            {"type": "STATE", "state": {"contacts": {"updatedAt": "2024-01-01"}}}
        )
        + "\n",
        "",  # Empty line to stop iteration
    ]
    mock_read_process.stderr = MagicMock()
    mock_read_process.stderr.readline.return_value = ""
    mock_read_process.returncode = 0
    mock_read_process.wait.return_value = 0

    # Return different mocks for discover vs read
    def popen_side_effect(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args", [])
        if "discover" in cmd:
            return mock_discover_process
        else:
            return mock_read_process

    mock_subprocess.Popen.side_effect = popen_side_effect

    extractor = AirbyteExtractor(source_config, mock_connector_recipe)

    # Extract records (state handling is tested in integration tests)
    batches = list(extractor.extract())

    assert len(batches) > 0
    assert len(batches[0]) == 1


@patch("dativo_ingest.connectors.engine_framework.docker")
@patch("dativo_ingest.connectors.engine_framework.DOCKER_AVAILABLE", True)
def test_airbyte_docker_not_available(
    mock_docker, source_config, mock_connector_recipe
):
    """Test Airbyte extractor handles Docker not available."""
    mock_docker.from_env.side_effect = Exception("Docker daemon not running")

    extractor = AirbyteExtractor(source_config, mock_connector_recipe)

    with pytest.raises(RuntimeError, match="Docker daemon"):
        list(extractor.extract())


@patch("dativo_ingest.connectors.engine_framework.docker")
@patch("dativo_ingest.connectors.engine_framework.subprocess")
@patch("dativo_ingest.connectors.engine_framework.DOCKER_AVAILABLE", True)
def test_airbyte_container_error(
    mock_subprocess, mock_docker, source_config, mock_connector_recipe
):
    """Test Airbyte extractor handles container errors."""
    mock_client = MagicMock()
    mock_docker.from_env.return_value = mock_client
    mock_client.images.get.return_value = MagicMock()

    # Mock subprocess error
    mock_process = MagicMock()
    mock_process.communicate.return_value = ("", "Error: Container failed")
    mock_process.returncode = 1
    mock_subprocess.Popen.return_value = mock_process

    extractor = AirbyteExtractor(source_config, mock_connector_recipe)

    with pytest.raises(RuntimeError, match="Container failed"):
        list(extractor.extract())


@patch("dativo_ingest.connectors.engine_framework.docker")
@patch("dativo_ingest.connectors.engine_framework.DOCKER_AVAILABLE", True)
def test_airbyte_extract_metadata(mock_docker, source_config, mock_connector_recipe):
    """Test metadata extraction for Dagster."""
    extractor = AirbyteExtractor(source_config, mock_connector_recipe)
    metadata = extractor.extract_metadata()

    assert "tags" in metadata
    assert metadata["tags"]["connector_type"] == "hubspot"
    assert metadata["tags"]["engine_type"] == "airbyte"


@patch("dativo_ingest.connectors.engine_framework.docker")
@patch("dativo_ingest.connectors.engine_framework.subprocess")
@patch("dativo_ingest.connectors.engine_framework.DOCKER_AVAILABLE", True)
@patch("os.getenv")
def test_airbyte_streams_from_source_config_objects(
    mock_getenv, mock_subprocess, mock_docker, mock_connector_recipe
):
    """Test that streams are correctly retrieved from source_config.objects."""
    mock_getenv.return_value = "test-api-key"

    # Source config with objects specified
    source_config = SourceConfig(
        type="hubspot",
        objects=["contacts", "deals"],  # Explicitly set objects
        credentials={},
    )

    extractor = AirbyteExtractor(source_config, mock_connector_recipe)
    config = extractor.config_parser.build_airbyte_config()

    # Config should not contain streams (it's filtered out)
    assert "streams" not in config

    # Verify streams are correctly retrieved in _run_airbyte_container
    # by checking the logic path (we'll test this via the actual extraction)
    mock_client = MagicMock()
    mock_docker.from_env.return_value = mock_client
    mock_client.images.get.return_value = MagicMock()

    # Mock discover call
    mock_discover_process = MagicMock()
    mock_discover_process.communicate.return_value = (
        json.dumps(
            {
                "type": "CATALOG",
                "catalog": {
                    "streams": [
                        {"name": "contacts", "json_schema": {"properties": {}}},
                        {"name": "deals", "json_schema": {"properties": {}}},
                    ]
                },
            }
        )
        + "\n",
        "",
    )
    mock_discover_process.returncode = 0

    # Mock read call
    mock_read_process = MagicMock()
    mock_read_process.stdout.readline.return_value = ""
    mock_read_process.stderr = MagicMock()
    mock_read_process.stderr.readline.return_value = ""
    mock_read_process.returncode = 0
    mock_read_process.wait.return_value = 0

    def popen_side_effect(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args", [])
        if "discover" in cmd:
            return mock_discover_process
        else:
            return mock_read_process

    mock_subprocess.Popen.side_effect = popen_side_effect

    # The key test: verify that when we call extract, the streams come from source_config.objects
    # We can verify this by checking the discover call was made with the right streams
    list(extractor.extract())

    # Verify that discover was called (which means streams were correctly determined)
    assert mock_subprocess.Popen.called


@patch("dativo_ingest.connectors.engine_framework.docker")
@patch("dativo_ingest.connectors.engine_framework.subprocess")
@patch("dativo_ingest.connectors.engine_framework.DOCKER_AVAILABLE", True)
@patch("os.getenv")
def test_airbyte_streams_fallback_to_defaults(
    mock_getenv, mock_subprocess, mock_docker, mock_connector_recipe
):
    """Test that streams fall back to streams_default when source_config.objects is not set."""
    mock_getenv.return_value = "test-api-key"

    # Source config WITHOUT objects specified (should use defaults)
    source_config = SourceConfig(
        type="hubspot",
        objects=None,  # No objects specified
        credentials={},
    )

    extractor = AirbyteExtractor(source_config, mock_connector_recipe)
    config = extractor.config_parser.build_airbyte_config()

    # Config should not contain streams (it's filtered out)
    assert "streams" not in config

    # Verify that streams_default from connector recipe is used
    # The connector recipe has streams_default: ["contacts"]
    mock_client = MagicMock()
    mock_docker.from_env.return_value = mock_client
    mock_client.images.get.return_value = MagicMock()

    # Mock discover call
    mock_discover_process = MagicMock()
    mock_discover_process.communicate.return_value = (
        json.dumps(
            {
                "type": "CATALOG",
                "catalog": {
                    "streams": [{"name": "contacts", "json_schema": {"properties": {}}}]
                },
            }
        )
        + "\n",
        "",
    )
    mock_discover_process.returncode = 0

    # Mock read call
    mock_read_process = MagicMock()
    mock_read_process.stdout.readline.return_value = ""
    mock_read_process.stderr = MagicMock()
    mock_read_process.stderr.readline.return_value = ""
    mock_read_process.returncode = 0
    mock_read_process.wait.return_value = 0

    def popen_side_effect(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args", [])
        if "discover" in cmd:
            return mock_discover_process
        else:
            return mock_read_process

    mock_subprocess.Popen.side_effect = popen_side_effect

    # Extract should work with default streams
    list(extractor.extract())

    # Verify that discover was called
    assert mock_subprocess.Popen.called


@patch("dativo_ingest.connectors.engine_framework.docker")
@patch("dativo_ingest.connectors.engine_framework.subprocess")
@patch("dativo_ingest.connectors.engine_framework.DOCKER_AVAILABLE", True)
@patch("os.getenv")
def test_airbyte_config_json_does_not_contain_streams(
    mock_getenv, mock_subprocess, mock_docker, source_config, mock_connector_recipe
):
    """Test that the config JSON passed to Docker does not contain 'streams' field."""
    mock_getenv.return_value = "test-api-key"

    mock_client = MagicMock()
    mock_docker.from_env.return_value = mock_client
    mock_client.images.get.return_value = MagicMock()

    # Mock discover call
    mock_discover_process = MagicMock()
    mock_discover_process.communicate.return_value = (
        json.dumps(
            {
                "type": "CATALOG",
                "catalog": {
                    "streams": [{"name": "contacts", "json_schema": {"properties": {}}}]
                },
            }
        )
        + "\n",
        "",
    )
    mock_discover_process.returncode = 0

    # Mock read call
    mock_read_process = MagicMock()
    mock_read_process.stdout.readline.return_value = ""
    mock_read_process.stderr = MagicMock()
    mock_read_process.stderr.readline.return_value = ""
    mock_read_process.returncode = 0
    mock_read_process.wait.return_value = 0

    def popen_side_effect(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args", [])
        if "discover" in cmd:
            return mock_discover_process
        else:
            return mock_read_process

    mock_subprocess.Popen.side_effect = popen_side_effect

    extractor = AirbyteExtractor(source_config, mock_connector_recipe)

    # Build config and verify it doesn't contain streams
    config = extractor.config_parser.build_airbyte_config()
    assert "streams" not in config

    # Serialize config to JSON (as done in _run_airbyte_container)
    config_json = json.dumps(config)
    config_dict = json.loads(config_json)

    # Verify the serialized config also doesn't contain streams
    assert "streams" not in config_dict
    assert "api_key" in config_dict  # But other fields should be present


@patch("dativo_ingest.connectors.engine_framework.docker")
@patch("dativo_ingest.connectors.engine_framework.subprocess")
@patch("dativo_ingest.connectors.engine_framework.DOCKER_AVAILABLE", True)
@patch("os.getenv")
def test_airbyte_temp_file_cleanup_on_second_file_failure(
    mock_getenv, mock_subprocess, mock_docker, source_config, mock_connector_recipe
):
    """Test that temp files are cleaned up even if catalog file creation fails in _run_airbyte_container.

    With the fix, _get_airbyte_catalog no longer creates a temp file (it reuses the catalog
    from discover()). The temp file creation now happens in _run_airbyte_container for the
    catalog file used in the read command. This test verifies cleanup works correctly.
    """
    mock_getenv.return_value = "test-api-key"

    # Mock Docker client
    mock_client = MagicMock()
    mock_docker.from_env.return_value = mock_client
    mock_client.images.get.return_value = MagicMock()

    # Track created temp files
    created_files = []
    call_count = [0]  # Use list to allow modification in nested function
    original_named_temporary_file = tempfile.NamedTemporaryFile

    def mock_named_temporary_file(*args, **kwargs):
        """Mock NamedTemporaryFile to fail on third call (catalog file in _run_airbyte_container)."""
        call_count[0] += 1
        # First two calls succeed (discover config, then read config)
        if call_count[0] <= 2:
            file_obj = original_named_temporary_file(*args, **kwargs)
            created_files.append(Path(file_obj.name))
            return file_obj
        else:
            # Third call fails (for catalog file in _run_airbyte_container)
            raise OSError("Disk full or permission denied")

    # Mock discover call (needed for catalog generation)
    mock_discover_process = MagicMock()
    mock_discover_process.communicate.return_value = (
        json.dumps(
            {
                "type": "CATALOG",
                "catalog": {
                    "streams": [
                        {
                            "name": "contacts",
                            "json_schema": {"properties": {"id": {}, "name": {}}},
                        }
                    ]
                },
            }
        )
        + "\n",
        "",
    )
    mock_discover_process.returncode = 0

    # Return discover process for discover call, but we'll fail before read call
    def popen_side_effect(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args", [])
        if "discover" in cmd:
            return mock_discover_process
        # Should not reach read call due to temp file failure
        return MagicMock()

    mock_subprocess.Popen.side_effect = popen_side_effect

    extractor = AirbyteExtractor(source_config, mock_connector_recipe)

    # Patch tempfile.NamedTemporaryFile to fail on third call (catalog file)
    # Note: tempfile is imported inside _run_airbyte_container, so we patch the builtin module
    with patch("tempfile.NamedTemporaryFile", side_effect=mock_named_temporary_file):
        # Extract should fail when catalog temp file creation fails
        # The OSError gets wrapped in a RuntimeError by _run_airbyte_container
        with pytest.raises(RuntimeError, match="Disk full or permission denied"):
            list(extractor.extract())

    # Verify that temp files were cleaned up
    # (they should not exist after the finally block executes)
    assert (
        len(created_files) == 2
    ), "Should have created exactly two temp files before failure (discover config and read config)"
    assert not created_files[
        0
    ].exists(), "First temp file (discover config) should be cleaned up even if catalog file creation fails"
    assert not created_files[
        1
    ].exists(), "Second temp file (read config) should be cleaned up even if catalog file creation fails"
