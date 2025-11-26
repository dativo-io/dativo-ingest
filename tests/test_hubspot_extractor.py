"""Unit tests for HubSpot extractor."""

from unittest.mock import MagicMock, patch

import pytest

from dativo_ingest.config import ConnectorRecipe, SourceConfig
from dativo_ingest.connectors.hubspot_extractor import HubSpotExtractor


@pytest.fixture
def hubspot_connector_recipe():
    """Create HubSpot connector recipe."""
    return ConnectorRecipe(
        name="hubspot",
        type="hubspot",
        roles=["source"],
        default_engine={
            "type": "airbyte",
            "options": {
                "airbyte": {
                    "docker_image": "airbyte/source-hubspot:0.2.0",
                    "streams_default": ["contacts", "deals", "companies"],
                    "start_date_default": "2024-01-01",
                }
            },
        },
        credentials={"type": "api_key", "from_env": "HUBSPOT_API_KEY"},
    )


@pytest.fixture
def hubspot_source_config():
    """Create HubSpot source config."""
    return SourceConfig(
        type="hubspot",
        objects=["contacts"],
        credentials={},
        incremental={"strategy": "updated_after", "cursor_field": "updatedAt"},
    )


@patch("dativo_ingest.connectors.engine_framework.docker")
@patch("dativo_ingest.connectors.engine_framework.DOCKER_AVAILABLE", True)
def test_hubspot_extractor_initialization(
    mock_docker, hubspot_source_config, hubspot_connector_recipe
):
    """Test HubSpot extractor initialization."""
    extractor = HubSpotExtractor(
        hubspot_source_config, hubspot_connector_recipe, tenant_id="test_tenant"
    )

    assert extractor.docker_image == "airbyte/source-hubspot:0.2.0"
    assert extractor.source_config.type == "hubspot"


@patch("dativo_ingest.connectors.engine_framework.docker")
@patch("dativo_ingest.connectors.engine_framework.subprocess")
@patch("dativo_ingest.connectors.engine_framework.DOCKER_AVAILABLE", True)
@patch("os.getenv")
def test_hubspot_extract(
    mock_getenv,
    mock_subprocess,
    mock_docker,
    hubspot_source_config,
    hubspot_connector_recipe,
):
    """Test HubSpot extraction."""
    mock_getenv.return_value = "test-hubspot-key"

    mock_client = MagicMock()
    mock_docker.from_env.return_value = mock_client
    mock_client.images.get.return_value = MagicMock()

    import json

    mock_process = MagicMock()
    mock_process.communicate.return_value = (
        json.dumps(
            {"type": "RECORD", "record": {"id": "123", "email": "test@example.com"}}
        )
        + "\n",
        "",
    )
    mock_process.returncode = 0
    mock_subprocess.Popen.return_value = mock_process

    extractor = HubSpotExtractor(
        hubspot_source_config, hubspot_connector_recipe, tenant_id="test_tenant"
    )
    batches = list(extractor.extract())

    assert len(batches) > 0
    assert len(batches[0]) == 1
    assert batches[0][0]["id"] == "123"


@patch("dativo_ingest.connectors.engine_framework.docker")
@patch("dativo_ingest.connectors.engine_framework.DOCKER_AVAILABLE", True)
def test_hubspot_extract_metadata(
    mock_docker, hubspot_source_config, hubspot_connector_recipe
):
    """Test HubSpot metadata extraction."""
    extractor = HubSpotExtractor(
        hubspot_source_config, hubspot_connector_recipe, tenant_id="test_tenant"
    )
    metadata = extractor.extract_metadata()

    assert "tags" in metadata
    assert metadata["tags"]["connector"] == "hubspot"
    assert metadata["tags"]["category"] == "crm"
