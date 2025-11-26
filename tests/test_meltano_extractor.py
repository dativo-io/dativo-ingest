"""Unit tests for Meltano extractor."""

from unittest.mock import MagicMock, patch

import pytest

from dativo_ingest.config import ConnectorRecipe, SourceConfig
from dativo_ingest.connectors.engine_framework import MeltanoExtractor


@pytest.fixture
def mock_connector_recipe():
    """Create a mock connector recipe for Meltano."""
    return ConnectorRecipe(
        name="postgres",
        type="postgres",
        roles=["source"],
        default_engine={
            "type": "meltano",
            "options": {
                "meltano": {
                    "tap_name": "tap-postgres",
                }
            },
        },
        credentials={"type": "database", "from_env": "POSTGRES_CONNECTION_STRING"},
    )


@pytest.fixture
def source_config():
    """Create a source config for testing."""
    return SourceConfig(
        type="postgres",
        objects=["employees"],
        credentials={},
        incremental={"strategy": "updated_at", "cursor_field": "modifieddate"},
    )


def test_meltano_extractor_initialization(source_config, mock_connector_recipe):
    """Test MeltanoExtractor initialization without tenant_id."""
    extractor = MeltanoExtractor(source_config, mock_connector_recipe)

    assert extractor.source_config == source_config
    assert extractor.connector_recipe == mock_connector_recipe
    assert extractor.tenant_id is None


def test_meltano_extractor_initialization_with_tenant_id(
    source_config, mock_connector_recipe
):
    """Test MeltanoExtractor initialization with tenant_id parameter."""
    tenant_id = "test_tenant"
    extractor = MeltanoExtractor(source_config, mock_connector_recipe, tenant_id=tenant_id)

    assert extractor.source_config == source_config
    assert extractor.connector_recipe == mock_connector_recipe
    assert extractor.tenant_id == tenant_id


def test_meltano_extractor_tenant_id_passed_to_parent(
    source_config, mock_connector_recipe
):
    """Test that tenant_id is properly passed to BaseEngineExtractor."""
    tenant_id = "test_tenant"
    extractor = MeltanoExtractor(source_config, mock_connector_recipe, tenant_id=tenant_id)

    # Verify tenant_id is stored in the extractor
    assert extractor.tenant_id == tenant_id
    # Verify config_parser received tenant_id (it's created in parent __init__)
    assert extractor.config_parser.tenant_id == tenant_id


def test_meltano_extractor_extract_not_implemented(
    source_config, mock_connector_recipe
):
    """Test that MeltanoExtractor.extract() raises NotImplementedError."""
    extractor = MeltanoExtractor(source_config, mock_connector_recipe)

    with pytest.raises(NotImplementedError, match="Meltano extractor not yet implemented"):
        list(extractor.extract())


def test_meltano_extractor_extract_metadata(source_config, mock_connector_recipe):
    """Test metadata extraction for Dagster."""
    extractor = MeltanoExtractor(source_config, mock_connector_recipe)
    metadata = extractor.extract_metadata()

    assert "tags" in metadata
    assert metadata["tags"]["connector_type"] == "postgres"
    assert metadata["tags"]["engine_type"] == "meltano"

