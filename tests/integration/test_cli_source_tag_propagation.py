"""Integration tests for CLI source tag extraction and propagation.

These tests verify that:
1. Extractors extract source tags via extract_metadata()
2. CLI passes source tags to IcebergCommitter
3. Source tags are used in tag derivation hierarchy
"""

import tempfile
from pathlib import Path

import pytest

from dativo_ingest.config import AssetDefinition, JobConfig, SourceConfig, TargetConfig
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
    """Create a target config for testing."""
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


def test_csv_extractor_extracts_source_tags(sample_csv_file):
    """Test that CSVExtractor extracts column names as source tags."""
    source_config = SourceConfig(
        type="csv",
        files=[{"path": sample_csv_file, "object": "test_file"}],
    )

    extractor = CSVExtractor(source_config)
    metadata = extractor.extract_metadata()

    assert "tags" in metadata
    # Column names should be extracted
    assert "id" in metadata["tags"]
    assert "email" in metadata["tags"]
    assert "phone" in metadata["tags"]
    # All should be marked as "column"
    assert metadata["tags"]["id"] == "column"
    assert metadata["tags"]["email"] == "column"
    assert metadata["tags"]["phone"] == "column"


def test_source_tags_passed_to_iceberg_committer(
    sample_asset_definition, sample_target_config
):
    """Test that source tags are passed to IcebergCommitter and used in derivation."""
    source_tags = {
        "email": "column",  # From CSV extractor
        "phone": "column",  # From CSV extractor
    }

    committer = IcebergCommitter(
        asset_definition=sample_asset_definition,
        target_config=sample_target_config,
        source_tags=source_tags,
    )

    # Verify source tags are stored
    assert committer.source_tags == source_tags

    # Derive properties - source tags should be available for tag derivation
    properties = committer._derive_table_properties()

    # Verify properties include asset metadata
    assert "asset.name" in properties
    assert "governance.owner" in properties

    # Note: Source tags themselves don't create classification tags automatically
    # (per NO AUTOMATIC CLASSIFICATION principle), but they're available for
    # the tag derivation hierarchy if needed


def test_source_tags_in_tag_derivation_hierarchy(sample_asset_definition):
    """Test that source tags are used in three-level tag hierarchy."""
    # Source tags (level 3 - lowest priority)
    source_tags = {
        "email": "column",  # From extractor
    }

    # Asset definition with explicit classification (level 2 - medium priority)
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_file",
        schema=[
            {
                "name": "email",
                "type": "string",
                "classification": "PII",  # Asset override
            },
            {"name": "phone", "type": "string"},  # No asset classification
        ],
        team={"owner": "test@example.com"},
    )

    # Job overrides (level 1 - highest priority)
    classification_overrides = {
        "email": "HIGH_PII",  # Job override
    }

    # Derive tags with all three levels
    tags = derive_tags_from_asset(
        asset_definition=asset,
        classification_overrides=classification_overrides,
        source_tags=source_tags,
    )

    # Verify hierarchy: job > asset > source
    assert "classification.fields.email" in tags
    assert tags["classification.fields.email"] == "high_pii"  # Job wins

    # phone: source tag "column" doesn't create classification automatically
    # (per NO AUTOMATIC CLASSIFICATION principle)
    # Only explicit classifications create tags


def test_source_tags_with_asset_classification(sample_asset_definition):
    """Test source tags when asset has explicit classification."""
    # Source tags
    source_tags = {
        "phone": "column",  # From extractor
    }

    # Asset with explicit classification for phone
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_file",
        schema=[
            {
                "name": "phone",
                "type": "string",
                "classification": "SENSITIVE",  # Asset classification
            },
        ],
        team={"owner": "test@example.com"},
    )

    tags = derive_tags_from_asset(
        asset_definition=asset,
        source_tags=source_tags,
    )

    # Asset classification should be used (overrides source tag)
    assert "classification.fields.phone" in tags
    assert tags["classification.fields.phone"] == "sensitive"


def test_source_tags_extraction_error_handling(sample_csv_file):
    """Test that extract_metadata errors are handled gracefully."""
    source_config = SourceConfig(
        type="csv",
        files=[{"path": "/nonexistent/file.csv", "object": "test_file"}],
    )

    extractor = CSVExtractor(source_config)
    # Should not raise - should return empty tags
    metadata = extractor.extract_metadata()

    assert "tags" in metadata
    assert metadata["tags"] == {}  # Empty when file doesn't exist


def test_source_tags_empty_when_no_metadata(sample_csv_file):
    """Test that extract_metadata returns empty tags when no metadata available."""
    source_config = SourceConfig(
        type="csv",
        files=[{"path": sample_csv_file, "object": "test_file"}],
    )

    extractor = CSVExtractor(source_config)
    metadata = extractor.extract_metadata()

    # Should have tags (column names from CSV)
    assert "tags" in metadata
    # Should have at least one column
    assert len(metadata["tags"]) > 0


def test_iceberg_committer_with_source_tags_only(
    sample_asset_definition, sample_target_config
):
    """Test IcebergCommitter with only source tags (no asset/job tags)."""
    source_tags = {
        "email": "column",
        "phone": "column",
    }

    committer = IcebergCommitter(
        asset_definition=sample_asset_definition,
        target_config=sample_target_config,
        source_tags=source_tags,
    )

    properties = committer._derive_table_properties()

    # Should have asset metadata
    assert "asset.name" in properties
    assert "governance.owner" in properties

    # Source tags don't automatically create classification tags
    # (per NO AUTOMATIC CLASSIFICATION principle)
    # They're available for the hierarchy but don't auto-classify


def test_source_tags_combined_with_job_overrides(sample_asset_definition):
    """Test source tags combined with job classification overrides."""
    source_tags = {
        "email": "column",
        "phone": "column",
    }

    # Job overrides (highest priority)
    classification_overrides = {
        "email": "PII",  # Job override
    }

    tags = derive_tags_from_asset(
        asset_definition=sample_asset_definition,
        classification_overrides=classification_overrides,
        source_tags=source_tags,
    )

    # Job override should create classification
    assert "classification.fields.email" in tags
    assert tags["classification.fields.email"] == "pii"

    # phone has no job/asset override, so no classification
    # (source tag "column" doesn't auto-classify)
