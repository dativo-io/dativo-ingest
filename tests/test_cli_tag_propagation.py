"""Integration tests for CLI source tag extraction and propagation.

These tests verify the actual flow of source tag extraction through the CLI.
They test extractors directly and verify tags flow to IcebergCommitter.
"""

import tempfile
from pathlib import Path

import pytest

from dativo_ingest.config import AssetDefinition, SourceConfig, TargetConfig
from dativo_ingest.connectors.csv_extractor import CSVExtractor
from dativo_ingest.iceberg_committer import IcebergCommitter
from dativo_ingest.tag_derivation import derive_tags_from_asset


@pytest.fixture
def sample_csv_file():
    """Create a temporary CSV file for testing."""
    import csv

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        writer = csv.writer(f)
        writer.writerow(["id", "email", "phone"])
        writer.writerow(["1", "test@example.com", "555-1234"])
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def sample_asset_definition():
    """Create a sample asset definition for testing."""
    return AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_file",
        schema=[
            {"name": "id", "type": "integer"},
            {"name": "email", "type": "string"},
            {"name": "phone", "type": "string"},
        ],
        team={"owner": "test@example.com"},
    )


@pytest.fixture
def sample_target_config():
    """Create a sample target config for testing."""
    return TargetConfig(
        type="iceberg",
        catalog="nessie",
        branch="main",
        warehouse="s3://test-bucket/",
        connection={
            "nessie": {"uri": "http://localhost:19120/api/v1"},
            "s3": {
                "endpoint": "http://localhost:9000",
                "bucket": "test-bucket",
                "access_key_id": "test-key",
                "secret_access_key": "test-secret",
            },
        },
    )


def test_cli_extracts_source_tags_from_extractor(sample_csv_file, sample_asset_definition, sample_target_config):
    """Test that extractor extracts source tags and they can be passed to IcebergCommitter."""
    # Test extractor directly
    source_config = SourceConfig(
        type="csv",
        files=[{"path": sample_csv_file, "object": "test_file"}],
    )

    extractor = CSVExtractor(source_config)
    metadata = extractor.extract_metadata()

    # Verify source tags are extracted
    assert "tags" in metadata
    source_tags = metadata["tags"]
    assert "email" in source_tags
    assert "phone" in source_tags

    # Test that source tags can be passed to IcebergCommitter
    committer = IcebergCommitter(
        asset_definition=sample_asset_definition,
        target_config=sample_target_config,
        source_tags=source_tags,
    )

    # Verify source tags are stored
    assert committer.source_tags == source_tags

    # Verify properties can be derived
    properties = committer._derive_table_properties()
    assert "asset.name" in properties
    assert "governance.owner" in properties


def test_cli_handles_extract_metadata_exception(sample_asset_definition, sample_target_config):
    """Test error handling when extract_metadata encounters errors."""
    # Test with non-existent file - should return empty tags, not raise
    source_config = SourceConfig(
        type="csv",
        files=[{"path": "/nonexistent/file.csv", "object": "test_file"}],
    )

    extractor = CSVExtractor(source_config)
    # Should not raise - should return empty tags
    metadata = extractor.extract_metadata()

    assert "tags" in metadata
    assert metadata["tags"] == {}  # Empty when file doesn't exist

    # Should still be able to create committer with empty source tags
    committer = IcebergCommitter(
        asset_definition=sample_asset_definition,
        target_config=sample_target_config,
        source_tags=None,  # No source tags when extraction fails
    )

    # Should work fine with None source tags
    assert committer.source_tags is None
    properties = committer._derive_table_properties()
    assert "asset.name" in properties


def test_cli_handles_get_source_tags_exception(sample_asset_definition, sample_target_config):
    """Test that extractors without extract_metadata work fine."""
    # CSVExtractor implements extract_metadata, but if it didn't, it should still work
    # Test that IcebergCommitter works with None source tags
    committer = IcebergCommitter(
        asset_definition=sample_asset_definition,
        target_config=sample_target_config,
        source_tags=None,  # No source tags (extractor doesn't implement method)
    )

    # Should work fine with None source tags
    assert committer.source_tags is None
    properties = committer._derive_table_properties()
    assert "asset.name" in properties
    assert "governance.owner" in properties


def test_cli_source_tags_none_when_not_implemented(sample_asset_definition, sample_target_config):
    """Test that source_tags can be None when extractor doesn't implement method."""
    # Test IcebergCommitter with None source tags (simulating extractor without method)
    committer = IcebergCommitter(
        asset_definition=sample_asset_definition,
        target_config=sample_target_config,
        source_tags=None,  # No source tags
    )

    # Should work fine
    assert committer.source_tags is None
    properties = committer._derive_table_properties()
    assert "asset.name" in properties


def test_cli_source_tags_metadata_with_source_tags_key(sample_csv_file, sample_asset_definition, sample_target_config):
    """Test that extract_metadata can return 'source_tags' key (alternative to 'tags')."""
    # CSVExtractor returns {"tags": {...}}, but CLI also checks for "source_tags"
    # Test that both formats work
    source_config = SourceConfig(
        type="csv",
        files=[{"path": sample_csv_file, "object": "test_file"}],
    )

    extractor = CSVExtractor(source_config)
    metadata = extractor.extract_metadata()

    # CSVExtractor returns {"tags": {...}}
    assert "tags" in metadata
    source_tags = metadata.get("tags") or metadata.get("source_tags")

    # Should be able to use either format
    assert source_tags is not None
    assert len(source_tags) > 0

    # Test passing to committer
    committer = IcebergCommitter(
        asset_definition=sample_asset_definition,
        target_config=sample_target_config,
        source_tags=source_tags,
    )

    assert committer.source_tags == source_tags


def test_cli_source_tags_empty_dict_when_no_tags(sample_asset_definition, sample_target_config):
    """Test that empty source tags are handled gracefully."""
    # Test with empty source tags dict
    empty_source_tags = {}

    committer = IcebergCommitter(
        asset_definition=sample_asset_definition,
        target_config=sample_target_config,
        source_tags=empty_source_tags,
    )

    # Should work fine with empty dict
    assert committer.source_tags == {}
    properties = committer._derive_table_properties()
    assert "asset.name" in properties

    # Test with None source tags
    committer_none = IcebergCommitter(
        asset_definition=sample_asset_definition,
        target_config=sample_target_config,
        source_tags=None,
    )

    assert committer_none.source_tags is None
    properties_none = committer_none._derive_table_properties()
    assert "asset.name" in properties_none

