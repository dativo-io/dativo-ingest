"""Unit tests for Airbyte extractor."""

import json
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
    assert "streams" in config
    assert config["streams"] == ["contacts"]


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

    # Mock subprocess for container execution
    mock_process = MagicMock()
    mock_process.communicate.return_value = (
        json.dumps({"type": "RECORD", "record": {"id": "1", "name": "Test"}})
        + "\n"
        + json.dumps({"type": "RECORD", "record": {"id": "2", "name": "Test2"}})
        + "\n",
        "",
    )
    mock_process.returncode = 0
    mock_subprocess.Popen.return_value = mock_process

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

    # Mock subprocess with state message
    mock_process = MagicMock()
    mock_process.communicate.return_value = (
        json.dumps({"type": "RECORD", "record": {"id": "1"}})
        + "\n"
        + json.dumps(
            {"type": "STATE", "state": {"contacts": {"updatedAt": "2024-01-01"}}}
        )
        + "\n",
        "",
    )
    mock_process.returncode = 0
    mock_subprocess.Popen.return_value = mock_process

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
