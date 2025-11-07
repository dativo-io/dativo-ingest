"""Unit tests for Parquet writer."""

import tempfile
from pathlib import Path

import pytest

from dativo_ingest.config import AssetDefinition, TargetConfig
from dativo_ingest.parquet_writer import ParquetWriter


@pytest.fixture
def sample_asset_definition():
    """Create a sample asset definition for testing."""
    return AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[
            {"name": "id", "type": "integer", "required": True},
            {"name": "name", "type": "string", "required": True},
            {"name": "created_at", "type": "timestamp", "required": True},
        ],
        team={"owner": "test@example.com"},
    )


@pytest.fixture
def target_config():
    """Create a target config for testing."""
    return TargetConfig(
        type="iceberg",
        warehouse="s3://test-bucket/",
        file_format="parquet",
        partitioning=["ingest_date"],
        parquet_target_size_mb=150,
    )


@pytest.fixture
def output_dir():
    """Create a temporary output directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def test_parquet_writer_initialization(sample_asset_definition, target_config, output_dir):
    """Test Parquet writer initialization."""
    writer = ParquetWriter(sample_asset_definition, target_config, output_dir)
    
    assert writer.asset_definition == sample_asset_definition
    assert writer.target_config == target_config
    assert writer.target_size_mb == 150
    assert writer.partitioning == ["ingest_date"]


def test_write_batch(sample_asset_definition, target_config, output_dir):
    """Test writing a batch of records to Parquet."""
    writer = ParquetWriter(sample_asset_definition, target_config, output_dir)
    
    records = [
        {
            "id": 1,
            "name": "Alice",
            "created_at": "2024-01-01T00:00:00",
        },
        {
            "id": 2,
            "name": "Bob",
            "created_at": "2024-01-01T00:00:00",
        },
    ]
    
    file_metadata = writer.write_batch(records, file_counter=0)
    
    assert len(file_metadata) > 0
    assert file_metadata[0]["record_count"] == 2
    assert "path" in file_metadata[0]
    assert "local_path" in file_metadata[0]
    
    # Verify file was created
    local_path = Path(file_metadata[0]["local_path"])
    assert local_path.exists()


def test_write_empty_batch(sample_asset_definition, target_config, output_dir):
    """Test writing an empty batch."""
    writer = ParquetWriter(sample_asset_definition, target_config, output_dir)
    
    file_metadata = writer.write_batch([], file_counter=0)
    
    assert len(file_metadata) == 0


def test_partitioning(sample_asset_definition, target_config, output_dir):
    """Test partitioning functionality."""
    writer = ParquetWriter(sample_asset_definition, target_config, output_dir)
    
    records = [
        {
            "id": 1,
            "name": "Alice",
            "created_at": "2024-01-01T00:00:00",
        },
    ]
    
    file_metadata = writer.write_batch(records, file_counter=0)
    
    # Check that partition path is included
    assert file_metadata[0]["partition"] is not None
    assert "ingest_date=" in file_metadata[0]["partition"]


def test_create_pyarrow_schema(sample_asset_definition, target_config, output_dir):
    """Test PyArrow schema creation."""
    writer = ParquetWriter(sample_asset_definition, target_config, output_dir)
    
    schema = writer._create_pyarrow_schema()
    
    assert schema is not None
    # Verify schema has correct fields
    field_names = [field.name for field in schema]
    assert "id" in field_names
    assert "name" in field_names
    assert "created_at" in field_names

