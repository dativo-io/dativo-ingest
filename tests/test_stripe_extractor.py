"""Unit tests for Stripe extractor (Airbyte-based)."""

from unittest.mock import MagicMock, patch

import pytest

from dativo_ingest.config import ConnectorRecipe, SourceConfig
from dativo_ingest.connectors.stripe_extractor import StripeExtractor


@pytest.fixture
def stripe_connector_recipe():
    """Create Stripe connector recipe."""
    return ConnectorRecipe(
        name="stripe",
        type="stripe",
        roles=["source"],
        default_engine={
            "type": "airbyte",
            "options": {
                "airbyte": {
                    "docker_image": "airbyte/source-stripe:2.1.5",
                    "streams_default": ["customers", "charges", "invoices"],
                    "start_date_default": "2024-01-01",
                }
            },
        },
        credentials={"type": "api_key", "from_env": "STRIPE_API_KEY"},
    )


@pytest.fixture
def stripe_source_config():
    """Create Stripe source config."""
    return SourceConfig(
        type="stripe",
        objects=["customers"],
        credentials={},
        incremental={"strategy": "created", "cursor_field": "created"},
    )


@patch("dativo_ingest.connectors.engine_framework.docker")
@patch("dativo_ingest.connectors.engine_framework.DOCKER_AVAILABLE", True)
def test_stripe_extractor_initialization(
    mock_docker, stripe_source_config, stripe_connector_recipe
):
    """Test Stripe extractor initialization."""
    extractor = StripeExtractor(
        stripe_source_config, stripe_connector_recipe, tenant_id="test_tenant"
    )

    assert extractor.docker_image == "airbyte/source-stripe:2.1.5"
    assert extractor.source_config.type == "stripe"


@patch("dativo_ingest.connectors.engine_framework.docker")
@patch("dativo_ingest.connectors.engine_framework.subprocess")
@patch("dativo_ingest.connectors.engine_framework.DOCKER_AVAILABLE", True)
@patch("os.getenv")
def test_stripe_extract(
    mock_getenv,
    mock_subprocess,
    mock_docker,
    stripe_source_config,
    stripe_connector_recipe,
):
    """Test Stripe extraction."""
    mock_getenv.return_value = "sk_test_123"

    mock_client = MagicMock()
    mock_docker.from_env.return_value = mock_client
    mock_client.images.get.return_value = MagicMock()

    import json

    mock_process = MagicMock()
    mock_process.communicate.return_value = (
        json.dumps(
            {
                "type": "RECORD",
                "record": {"id": "cus_123", "email": "customer@example.com"},
            }
        )
        + "\n",
        "",
    )
    mock_process.returncode = 0
    mock_subprocess.Popen.return_value = mock_process

    extractor = StripeExtractor(
        stripe_source_config, stripe_connector_recipe, tenant_id="test_tenant"
    )
    batches = list(extractor.extract())

    assert len(batches) > 0
    assert len(batches[0]) == 1
    assert batches[0][0]["id"] == "cus_123"


@patch("dativo_ingest.connectors.engine_framework.docker")
@patch("dativo_ingest.connectors.engine_framework.DOCKER_AVAILABLE", True)
def test_stripe_extract_metadata(
    mock_docker, stripe_source_config, stripe_connector_recipe
):
    """Test Stripe metadata extraction."""
    extractor = StripeExtractor(
        stripe_source_config, stripe_connector_recipe, tenant_id="test_tenant"
    )
    metadata = extractor.extract_metadata()

    assert "tags" in metadata
    assert metadata["tags"]["connector"] == "stripe"
    assert metadata["tags"]["category"] == "payments"
