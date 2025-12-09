"""Tests for Mimesis connector factory registration."""

import logging
from unittest.mock import Mock

import pytest

from dativo_ingest.config import AssetDefinition, SourceConfig
from dativo_ingest.connectors.factory import ExtractorFactory


class LogCaptureHandler(logging.Handler):
    """Handler that captures log records for testing."""

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


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


def test_factory_synthetic_connector_deprecated():
    """Test that synthetic connector type is deprecated but still works (maps to mimesis)."""
    source_config = SourceConfig(type="synthetic")
    job_config = Mock()
    asset_definition = create_minimal_asset_definition()

    # Synthetic type is deprecated but should still work (maps to mimesis)
    extractor, source_tags = ExtractorFactory.create(
        source_config=source_config,
        job_config=job_config,
        asset_definition=asset_definition,
    )

    assert extractor is not None
    from dativo_ingest.connectors.mimesis_extractor import MimesisExtractor

    assert isinstance(extractor, MimesisExtractor)


def test_factory_synthetic_connector_logs_deprecation_warning():
    """Test that synthetic connector type logs deprecation warning with correct event_type."""
    source_config = SourceConfig(type="synthetic")
    job_config = Mock()
    asset_definition = create_minimal_asset_definition()

    # Capture log records using a custom handler
    logger = logging.getLogger("dativo_ingest")
    handler = LogCaptureHandler()
    handler.setLevel(logging.WARNING)
    logger.addHandler(handler)
    original_level = logger.level
    logger.setLevel(logging.WARNING)

    try:
        ExtractorFactory.create(
            source_config=source_config,
            job_config=job_config,
            asset_definition=asset_definition,
        )

        # Check that a deprecation warning was logged
        # Python's logging module flattens the 'extra' dict onto LogRecord as direct attributes
        # So we use getattr() instead of record.extra.get()
        assert any(
            getattr(record, "event_type", None) == "deprecated_connector_type"
            for record in handler.records
        ), "Expected deprecation warning with event_type='deprecated_connector_type'"
    finally:
        logger.removeHandler(handler)
        logger.setLevel(original_level)


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
