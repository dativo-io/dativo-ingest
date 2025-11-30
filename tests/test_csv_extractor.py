"""Unit tests for CSV extractor."""

import csv
import tempfile
from pathlib import Path

import pytest

from dativo_ingest.config import SourceConfig
from dativo_ingest.connectors.csv_extractor import CSVExtractor


@pytest.fixture
def sample_csv_file():
    """Create a temporary CSV file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "email"])
        writer.writerow(["1", "Alice", "alice@example.com"])
        writer.writerow(["2", "Bob", "bob@example.com"])
        writer.writerow(["3", "Charlie", "charlie@example.com"])
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def source_config(sample_csv_file):
    """Create a source config for CSV extraction."""
    return SourceConfig(
        type="csv",
        files=[
            {"path": sample_csv_file, "object": "test_object"},
        ],
        engine={
            "type": "native",
            "options": {
                "native": {
                    "chunk_size": 1000,
                    "encoding": "utf-8",
                    "delimiter": ",",
                }
            },
        },
    )


def test_csv_extractor_initialization(source_config):
    """Test CSV extractor initialization."""
    extractor = CSVExtractor(source_config)
    assert extractor.source_config == source_config
    assert extractor.engine_options["chunk_size"] == 1000


def test_extract_records(source_config):
    """Test extracting records from CSV file."""
    extractor = CSVExtractor(source_config)

    all_records = []
    for batch in extractor.extract():
        all_records.extend(batch)

    assert len(all_records) == 3
    assert all_records[0]["id"] == "1"
    assert all_records[0]["name"] == "Alice"
    assert all_records[1]["name"] == "Bob"


def test_extract_with_chunking(source_config):
    """Test extraction with chunking."""
    # Modify config to use small chunk size
    source_config.engine["options"]["native"]["chunk_size"] = 2

    extractor = CSVExtractor(source_config)

    batch_count = 0
    total_records = 0
    for batch in extractor.extract():
        batch_count += 1
        total_records += len(batch)
        assert len(batch) <= 2  # Chunk size

    assert batch_count > 1  # Should have multiple batches
    assert total_records == 3


def test_extract_missing_file():
    """Test extraction fails when file doesn't exist."""
    config = SourceConfig(
        type="csv",
        files=[{"path": "/nonexistent/file.csv", "object": "test"}],
    )

    extractor = CSVExtractor(config)

    with pytest.raises(FileNotFoundError):
        list(extractor.extract())


def test_extract_no_files_config():
    """Test extraction fails when files config is missing."""
    config = SourceConfig(type="csv", files=None)

    extractor = CSVExtractor(config)

    with pytest.raises(ValueError, match="CSV source requires 'files' configuration"):
        list(extractor.extract())


def test_csv_extractor_source_tags(sample_csv_file):
    """Test CSVExtractor extracts column names as naturally available metadata."""
    config = SourceConfig(
        type="csv",
        files=[{"path": sample_csv_file, "object": "test_object"}],
    )

    extractor = CSVExtractor(config)
    result = extractor.extract_metadata()

    assert "tags" in result
    # Column names from CSV header should be extracted
    assert "id" in result["tags"]
    assert "name" in result["tags"]
    assert "email" in result["tags"]
    # All should be marked as "column" to indicate they're from CSV structure
    assert result["tags"]["id"] == "column"
    assert result["tags"]["name"] == "column"
    assert result["tags"]["email"] == "column"


def test_csv_extractor_source_tags_no_metadata(sample_csv_file):
    """Test CSVExtractor extracts column names even from simple CSV."""
    config = SourceConfig(
        type="csv",
        files=[{"path": sample_csv_file, "object": "test_object"}],
    )

    extractor = CSVExtractor(config)
    result = extractor.extract_metadata()

    assert "tags" in result
    # Should have column names from the CSV header
    assert len(result["tags"]) > 0


def test_csv_extractor_source_tags_multiple_files(sample_csv_file):
    """Test CSVExtractor extracts column names from multiple CSV files."""
    # Create second CSV file with different columns
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        writer = csv.writer(f)
        writer.writerow(["id", "phone", "address"])
        writer.writerow(["1", "555-1234", "123 Main St"])
        second_csv = f.name

    try:
        config = SourceConfig(
            type="csv",
            files=[
                {"path": sample_csv_file, "object": "test1"},
                {"path": second_csv, "object": "test2"},
            ],
        )

        extractor = CSVExtractor(config)
        result = extractor.extract_metadata()

        assert "tags" in result
        # Should have columns from both files
        assert "id" in result["tags"]  # Common column
        assert "email" in result["tags"]  # From first file
        assert "phone" in result["tags"]  # From second file
        assert "address" in result["tags"]  # From second file
    finally:
        Path(second_csv).unlink(missing_ok=True)


def test_extract_with_incremental_disabled_by_default(source_config):
    """Test that incremental state is disabled by default - files are always processed."""
    # Source config without incremental should process files
    assert source_config.incremental is None or not source_config.incremental

    extractor = CSVExtractor(source_config)

    # Extract records - should process file even if it was processed before
    all_records = []
    for batch in extractor.extract():
        all_records.extend(batch)

    # Should extract all records
    assert len(all_records) == 3

    # Run again - should still process (incremental disabled)
    all_records2 = []
    for batch in extractor.extract():
        all_records2.extend(batch)

    # Should extract all records again
    assert len(all_records2) == 3
    assert len(all_records) == len(all_records2)


def test_extract_with_incremental_enabled(sample_csv_file):
    """Test that incremental state works when explicitly enabled."""
    import shutil
    import tempfile as tf

    from dativo_ingest.validator import IncrementalStateManager

    # Create state directory
    state_dir = tf.mkdtemp()
    state_path = Path(state_dir) / "test.state.json"

    config = SourceConfig(
        type="csv",
        files=[{"path": sample_csv_file, "object": "test_object"}],
        incremental={
            "strategy": "file_modified_time",
            "lookback_days": 0,
            "state_path": str(state_path),
        },
        engine={
            "type": "native",
            "options": {
                "native": {
                    "chunk_size": 1000,
                    "encoding": "utf-8",
                }
            },
        },
    )

    extractor = CSVExtractor(config)

    # First run - should process file
    all_records = []
    for batch in extractor.extract():
        all_records.extend(batch)

    assert len(all_records) == 3

    # Second run - should skip file (already processed)
    all_records2 = []
    for batch in extractor.extract():
        all_records2.extend(batch)

    # Should be empty (file skipped)
    assert len(all_records2) == 0

    # Cleanup
    shutil.rmtree(state_dir, ignore_errors=True)
