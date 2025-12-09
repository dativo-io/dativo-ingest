"""Tests for Mimesis connector factory registration."""

from unittest.mock import Mock

import pytest

from dativo_ingest.config import AssetDefinition, SourceConfig
from dativo_ingest.connectors.factory import ExtractorFactory


def create_minimal_asset_definition() -> AssetDefinition:
    """Create a minimal asset definition for testing."""
    return AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="mimesis",
        object="test_object",
        schema=[{"name": "id", "type": "integer", "required": True}],
        team={"owner": "test@example.com"},
    )


def test_factory_mimesis_connector():
    """Test that factory creates MimesisExtractor for mimesis type."""
    source_config = SourceConfig(type="mimesis")
    job_config = Mock()
    asset_definition = create_minimal_asset_definition()

    extractor, source_tags = ExtractorFactory.create(
        source_config=source_config,
        job_config=job_config,
        asset_definition=asset_definition,
    )

    assert extractor is not None
    from dativo_ingest.connectors.mimesis_extractor import MimesisExtractor

    assert isinstance(extractor, MimesisExtractor)


def test_factory_mimesis_requires_asset_definition():
    """Test that mimesis connector raises error without asset_definition."""
    source_config = SourceConfig(type="mimesis")
    job_config = Mock()

    with pytest.raises(ValueError, match="requires asset_definition"):
        ExtractorFactory.create(
            source_config=source_config,
            job_config=job_config,
            asset_definition=None,
        )


def test_factory_mimesis_validates_asset_definition_type():
    """Test that mimesis connector validates asset_definition type."""
    source_config = SourceConfig(type="mimesis")
    job_config = Mock()

    with pytest.raises(ValueError, match="must be AssetDefinition instance"):
        ExtractorFactory.create(
            source_config=source_config,
            job_config=job_config,
            asset_definition="not_an_asset_definition",
        )
