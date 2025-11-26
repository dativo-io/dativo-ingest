"""Unit tests for AWS Glue Data Catalog client."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.dativo_ingest.catalogs.base import CatalogConfig, LineageInfo
from src.dativo_ingest.catalogs.aws_glue import GlueCatalogClient


@pytest.fixture
def glue_config():
    """Fixture for Glue catalog configuration."""
    return CatalogConfig(
        type="glue",
        enabled=True,
        aws_region="us-east-1",
        aws_account_id="123456789012",
    )


@pytest.fixture
def glue_client(glue_config):
    """Fixture for Glue catalog client."""
    return GlueCatalogClient(glue_config)


@pytest.fixture
def sample_schema():
    """Fixture for sample schema."""
    return [
        {"name": "id", "type": "string", "required": True, "description": "Unique identifier"},
        {"name": "name", "type": "string", "description": "Name field"},
        {"name": "age", "type": "integer"},
        {"name": "created_at", "type": "timestamp"},
    ]


@pytest.fixture
def sample_lineage():
    """Fixture for sample lineage info."""
    return LineageInfo(
        source_type="postgres",
        source_name="mydb",
        source_dataset="users",
        target_type="iceberg",
        target_name="warehouse",
        target_dataset="default.users",
        pipeline_name="postgres_to_iceberg",
        tenant_id="test_tenant",
        records_processed=1000,
        bytes_processed=50000,
        execution_time=datetime.utcnow(),
    )


def test_glue_config_validation(glue_config):
    """Test Glue configuration validation."""
    client = GlueCatalogClient(glue_config)
    assert client.config.aws_region == "us-east-1"
    assert client.config.type == "glue"


def test_glue_config_defaults():
    """Test Glue configuration with defaults."""
    config = CatalogConfig(
        type="glue",
        enabled=True,
    )
    client = GlueCatalogClient(config)
    # Should have default region from environment or 'us-east-1'
    assert client.config.aws_region in ["us-east-1"] or client.config.aws_region is not None


@patch("src.dativo_ingest.catalogs.aws_glue.boto3.client")
def test_register_dataset(mock_boto_client, glue_client, sample_schema):
    """Test registering a dataset in Glue."""
    # Mock Glue client
    mock_client = Mock()
    mock_boto_client.return_value = mock_client
    
    # Mock database exists
    mock_client.get_database.return_value = {"Database": {"Name": "default"}}
    
    # Mock table doesn't exist (will create)
    mock_client.exceptions.EntityNotFoundException = Exception
    mock_client.update_table.side_effect = Exception("EntityNotFound")
    
    # Register dataset
    metadata = {
        "description": "Test table",
        "owner": "test@example.com",
        "tags": ["tag1=value1", "tag2=value2"],
        "location": "s3://bucket/path",
    }
    
    result = glue_client.register_dataset(
        dataset_name="default.test_table",
        schema=sample_schema,
        metadata=metadata,
    )
    
    # Verify result
    assert result["status"] == "success"
    assert result["action"] == "created"
    assert result["database"] == "default"
    assert result["table"] == "test_table"
    
    # Verify create_table was called
    mock_client.create_table.assert_called_once()
    call_args = mock_client.create_table.call_args
    assert call_args[1]["DatabaseName"] == "default"
    assert call_args[1]["TableInput"]["Name"] == "test_table"


@patch("src.dativo_ingest.catalogs.aws_glue.boto3.client")
def test_publish_lineage(mock_boto_client, glue_client, sample_lineage):
    """Test publishing lineage to Glue."""
    # Mock Glue client
    mock_client = Mock()
    mock_boto_client.return_value = mock_client
    
    # Mock get_table
    mock_client.get_table.return_value = {
        "Table": {
            "Name": "users",
            "StorageDescriptor": {"Columns": []},
            "Parameters": {}
        }
    }
    
    # Publish lineage
    result = glue_client.publish_lineage(sample_lineage)
    
    # Verify result
    assert result["status"] == "success"
    assert result["database"] == "default"
    assert result["table"] == "users"
    assert "lineage_params" in result
    
    # Verify update_table was called with lineage parameters
    mock_client.update_table.assert_called_once()


@patch("src.dativo_ingest.catalogs.aws_glue.boto3.client")
def test_update_metadata(mock_boto_client, glue_client):
    """Test updating metadata in Glue."""
    # Mock Glue client
    mock_client = Mock()
    mock_boto_client.return_value = mock_client
    
    # Mock get_table
    mock_client.get_table.return_value = {
        "Table": {
            "Name": "test_table",
            "StorageDescriptor": {"Columns": []},
            "Parameters": {}
        }
    }
    
    # Update metadata
    result = glue_client.update_metadata(
        dataset_name="default.test_table",
        tags=["env=prod", "team=data"],
        owner="owner@example.com",
        classification=["PII", "Sensitive"],
    )
    
    # Verify result
    assert result["status"] == "success"
    assert result["database"] == "default"
    assert result["table"] == "test_table"
    
    # Verify update_table was called
    mock_client.update_table.assert_called_once()


@patch("src.dativo_ingest.catalogs.aws_glue.boto3.client")
def test_test_connection(mock_boto_client, glue_client):
    """Test connection test."""
    # Mock Glue client
    mock_client = Mock()
    mock_boto_client.return_value = mock_client
    
    # Mock get_databases
    mock_client.get_databases.return_value = {"DatabaseList": []}
    
    # Test connection
    assert glue_client.test_connection() is True
    
    # Verify get_databases was called
    mock_client.get_databases.assert_called_once()


@patch("src.dativo_ingest.catalogs.aws_glue.boto3.client")
def test_test_connection_failure(mock_boto_client, glue_client):
    """Test connection failure."""
    # Mock Glue client
    mock_client = Mock()
    mock_boto_client.return_value = mock_client
    
    # Mock get_databases to raise exception
    mock_client.get_databases.side_effect = Exception("Connection failed")
    
    # Test connection should return False
    assert glue_client.test_connection() is False


def test_type_mapping(glue_client):
    """Test type mapping from asset schema to Glue types."""
    assert glue_client._map_type_to_glue("string") == "string"
    assert glue_client._map_type_to_glue("integer") == "bigint"
    assert glue_client._map_type_to_glue("float") == "double"
    assert glue_client._map_type_to_glue("boolean") == "boolean"
    assert glue_client._map_type_to_glue("timestamp") == "timestamp"
    assert glue_client._map_type_to_glue("unknown_type") == "string"


@patch("src.dativo_ingest.catalogs.aws_glue.boto3.client")
def test_ensure_database_exists(mock_boto_client, glue_client):
    """Test ensuring database exists."""
    # Mock Glue client
    mock_client = Mock()
    mock_boto_client.return_value = mock_client
    
    # Mock database doesn't exist
    mock_client.exceptions.EntityNotFoundException = Exception
    mock_client.get_database.side_effect = Exception("EntityNotFound")
    
    # Ensure database exists
    glue_client._ensure_database_exists("test_db")
    
    # Verify create_database was called
    mock_client.create_database.assert_called_once()
    call_args = mock_client.create_database.call_args
    assert call_args[1]["DatabaseInput"]["Name"] == "test_db"
