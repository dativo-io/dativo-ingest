"""Unit tests for Stripe extractor (Airbyte-based)."""

from unittest.mock import MagicMock, patch

import pytest

from dativo_ingest.config import ConnectorRecipe, SourceConfig
from dativo_ingest.connectors.stripe_extractor import (
    StripeConfigParser,
    StripeExtractor,
)


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

    # Mock discover call (needed for catalog generation)
    mock_discover_process = MagicMock()
    mock_discover_process.communicate.return_value = (
        json.dumps({"type": "CATALOG", "catalog": {"streams": [{"name": "customers", "json_schema": {"properties": {}}}]}})
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
                "record": {"stream": "customers", "data": {"id": "cus_123", "email": "customer@example.com"}},
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


@patch("os.getenv")
def test_stripe_config_parser_credentials_mapping(mock_getenv, stripe_connector_recipe):
    """Test StripeConfigParser maps API key to client_secret."""
    mock_getenv.return_value = "sk_test_12345"

    source_config = SourceConfig(
        type="stripe",
        objects=["customers"],
        credentials={},
    )

    parser = StripeConfigParser(
        source_config, stripe_connector_recipe, tenant_id="test"
    )
    credentials = parser._get_credentials()

    # Should map api_key to client_secret (Airbyte Stripe requirement)
    assert "client_secret" in credentials
    assert credentials["client_secret"] == "sk_test_12345"
    assert "api_key" not in credentials


@patch("os.getenv")
def test_stripe_config_parser_account_id_from_env(mock_getenv, stripe_connector_recipe):
    """Test StripeConfigParser gets account_id from environment."""

    def getenv_side_effect(key):
        if key == "STRIPE_API_KEY":
            return "sk_test_12345"
        elif key in ("STRIPE_ACCOUNT_ID", "STRIPE_ACCOUNT"):
            return "acct_test_123"
        return None

    mock_getenv.side_effect = getenv_side_effect

    source_config = SourceConfig(
        type="stripe",
        objects=["customers"],
        credentials={},
    )

    parser = StripeConfigParser(
        source_config, stripe_connector_recipe, tenant_id="test"
    )
    credentials = parser._get_credentials()

    assert "client_secret" in credentials
    assert "account_id" in credentials
    assert credentials["account_id"] == "acct_test_123"


@patch("os.getenv")
@patch("requests.get")
def test_stripe_config_parser_account_id_auto_fetch(
    mock_requests, mock_getenv, stripe_connector_recipe
):
    """Test StripeConfigParser auto-fetches account_id from Stripe API."""
    def getenv_side_effect(key):
        if key == "STRIPE_API_KEY":
            return "sk_test_12345"
        # Return None for account_id env vars to trigger auto-fetch
        return None

    mock_getenv.side_effect = getenv_side_effect

    # Mock Stripe API response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "acct_auto_fetched"}
    mock_requests.return_value = mock_response

    source_config = SourceConfig(
        type="stripe",
        objects=["customers"],
        credentials={},
    )

    parser = StripeConfigParser(
        source_config, stripe_connector_recipe, tenant_id="test"
    )
    config = parser.build_airbyte_config()

    # Should have auto-fetched account_id
    assert "account_id" in config
    assert config["account_id"] == "acct_auto_fetched"
    assert "client_secret" in config
    mock_requests.assert_called_once()


@patch("os.getenv")
def test_stripe_config_parser_date_format_conversion(
    mock_getenv, stripe_connector_recipe
):
    """Test StripeConfigParser converts date format to ISO 8601."""
    mock_getenv.return_value = "sk_test_12345"

    source_config = SourceConfig(
        type="stripe",
        objects=["customers"],
        credentials={},
    )

    parser = StripeConfigParser(
        source_config, stripe_connector_recipe, tenant_id="test"
    )
    config = parser.build_airbyte_config()

    # Should convert YYYY-MM-DD to YYYY-MM-DDTHH:MM:SSZ
    if "start_date" in config:
        assert config["start_date"] == "2024-01-01T00:00:00Z"
