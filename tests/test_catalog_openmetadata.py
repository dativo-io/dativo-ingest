"""Unit tests for OpenMetadata catalog client."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.dativo_ingest.catalogs.base import CatalogConfig, LineageInfo
from src.dativo_ingest.catalogs.openmetadata import OpenMetadataCatalogClient


@pytest.fixture
def openmetadata_config():
    """Fixture for OpenMetadata catalog configuration."""
    return CatalogConfig(
        type="openmetadata",
        enabled=True,
        uri="http://localhost:8585/api",
    )


@pytest.fixture
def openmetadata_client(openmetadata_config):
    """Fixture for OpenMetadata catalog client."""
    with patch("src.dativo_ingest.catalogs.openmetadata.OpenMetadata"):
        client = OpenMetadataCatalogClient(openmetadata_config)
        return client


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


def test_openmetadata_config_validation(openmetadata_config):
    """Test OpenMetadata configuration validation."""
    with patch("src.dativo_ingest.catalogs.openmetadata.OpenMetadata"):
        client = OpenMetadataCatalogClient(openmetadata_config)
        assert client.config.uri == "http://localhost:8585/api"
        assert client.config.type == "openmetadata"


def test_openmetadata_config_defaults():
    """Test OpenMetadata configuration with defaults."""
    config = CatalogConfig(
        type="openmetadata",
        enabled=True,
    )
    with patch("src.dativo_ingest.catalogs.openmetadata.OpenMetadata"):
        client = OpenMetadataCatalogClient(config)
        # Should have default URI
        assert client.config.uri == "http://localhost:8585/api"


@patch("src.dativo_ingest.catalogs.openmetadata.OpenMetadata")
def test_register_dataset(mock_om_class, openmetadata_client, sample_schema):
    """Test registering a dataset in OpenMetadata."""
    # Mock OpenMetadata client
    mock_client = Mock()
    mock_om_class.return_value = mock_client
    openmetadata_client._client = mock_client
    
    # Mock service and database
    mock_service = Mock()
    mock_service.id = "service-123"
    mock_service.fullyQualifiedName = "dativo_service"
    
    mock_database = Mock()
    mock_database.id = "db-123"
    mock_database.fullyQualifiedName = "dativo_service.default"
    
    mock_client.get_by_name.side_effect = [mock_service, mock_database]
    
    # Mock created table
    mock_table = Mock()
    mock_table.id = "table-123"
    mock_client.create_or_update.return_value = mock_table
    
    # Register dataset
    metadata = {
        "description": "Test table",
        "owner": "test@example.com",
        "tags": ["tag1", "tag2"],
        "location": "s3://bucket/path",
    }
    
    result = openmetadata_client.register_dataset(
        dataset_name="default.test_table",
        schema=sample_schema,
        metadata=metadata,
    )
    
    # Verify result
    assert result["status"] == "success"
    assert result["action"] == "created_or_updated"
    assert "fqn" in result


@patch("src.dativo_ingest.catalogs.openmetadata.OpenMetadata")
def test_publish_lineage(mock_om_class, openmetadata_client, sample_lineage):
    """Test publishing lineage to OpenMetadata."""
    # Mock OpenMetadata client
    mock_client = Mock()
    mock_om_class.return_value = mock_client
    openmetadata_client._client = mock_client
    
    # Mock tables
    mock_source_table = Mock()
    mock_source_table.id = "source-123"
    
    mock_target_table = Mock()
    mock_target_table.id = "target-123"
    
    mock_client.get_by_name.side_effect = [mock_target_table, mock_source_table]
    
    # Publish lineage
    result = openmetadata_client.publish_lineage(sample_lineage)
    
    # Verify result
    assert result["status"] == "success"
    
    # Verify add_lineage was called
    mock_client.add_lineage.assert_called_once()


@patch("src.dativo_ingest.catalogs.openmetadata.OpenMetadata")
def test_update_metadata(mock_om_class, openmetadata_client):
    """Test updating metadata in OpenMetadata."""
    # Mock OpenMetadata client
    mock_client = Mock()
    mock_om_class.return_value = mock_client
    openmetadata_client._client = mock_client
    
    # Mock table
    mock_table = Mock()
    mock_table.id = "table-123"
    mock_client.get_by_name.return_value = mock_table
    
    # Update metadata
    result = openmetadata_client.update_metadata(
        dataset_name="default.test_table",
        tags=["env=prod", "team=data"],
        owner="owner@example.com",
        classification=["PII", "Sensitive"],
    )
    
    # Verify result
    assert result["status"] == "success"


@patch("src.dativo_ingest.catalogs.openmetadata.OpenMetadata")
def test_test_connection(mock_om_class, openmetadata_client):
    """Test connection test."""
    # Mock OpenMetadata client
    mock_client = Mock()
    mock_om_class.return_value = mock_client
    openmetadata_client._client = mock_client
    
    # Mock health_check
    mock_client.health_check.return_value = True
    
    # Test connection
    assert openmetadata_client.test_connection() is True


@patch("src.dativo_ingest.catalogs.openmetadata.OpenMetadata")
def test_test_connection_failure(mock_om_class, openmetadata_client):
    """Test connection failure."""
    # Mock OpenMetadata client
    mock_client = Mock()
    mock_om_class.return_value = mock_client
    openmetadata_client._client = mock_client
    
    # Mock health_check to raise exception
    mock_client.health_check.side_effect = Exception("Connection failed")
    
    # Test connection should return False
    assert openmetadata_client.test_connection() is False


def test_type_mapping(openmetadata_client):
    """Test type mapping from asset schema to OpenMetadata types."""
    from metadata.generated.schema.entity.data.table import DataType
    
    assert openmetadata_client._map_type_to_openmetadata("string") == DataType.STRING
    assert openmetadata_client._map_type_to_openmetadata("integer") == DataType.BIGINT
    assert openmetadata_client._map_type_to_openmetadata("float") == DataType.DOUBLE
    assert openmetadata_client._map_type_to_openmetadata("boolean") == DataType.BOOLEAN
    assert openmetadata_client._map_type_to_openmetadata("timestamp") == DataType.TIMESTAMP
    assert openmetadata_client._map_type_to_openmetadata("unknown_type") == DataType.STRING


def test_build_fqn(openmetadata_client):
    """Test building fully qualified names."""
    # Simple name
    fqn = openmetadata_client._build_fqn("users", "postgres")
    assert fqn == "postgres_service.default.users"
    
    # Already has service prefix
    fqn = openmetadata_client._build_fqn("myservice.mydb.users", "postgres")
    assert fqn == "myservice.mydb.users"
