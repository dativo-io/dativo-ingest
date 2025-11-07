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

