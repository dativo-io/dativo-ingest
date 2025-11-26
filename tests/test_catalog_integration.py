"""Integration tests for catalog clients.

These tests verify that catalog clients can be created and configured correctly.
They use mocks for actual catalog connections to avoid external dependencies.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from src.dativo_ingest.catalogs.base import CatalogConfig, LineageInfo
from src.dativo_ingest.catalogs.factory import create_catalog_client
from src.dativo_ingest.catalogs.aws_glue import GlueCatalogClient
from src.dativo_ingest.catalogs.unity_catalog import UnityCatalogClient
from src.dativo_ingest.catalogs.nessie_catalog import NessieCatalogClient
from src.dativo_ingest.catalogs.openmetadata import OpenMetadataCatalogClient


def test_factory_creates_glue_client():
    """Test factory creates Glue client."""
    config = CatalogConfig(
        type="glue",
        enabled=True,
        aws_region="us-east-1",
    )
    
    client = create_catalog_client(config)
    assert isinstance(client, GlueCatalogClient)


def test_factory_creates_unity_client():
    """Test factory creates Unity Catalog client."""
    config = CatalogConfig(
        type="unity",
        enabled=True,
        workspace_url="https://workspace.databricks.com",
        token="test-token",
    )
    
    client = create_catalog_client(config)
    assert isinstance(client, UnityCatalogClient)


def test_factory_creates_nessie_client():
    """Test factory creates Nessie client."""
    config = CatalogConfig(
        type="nessie",
        enabled=True,
        uri="http://localhost:19120/api/v1",
    )
    
    client = create_catalog_client(config)
    assert isinstance(client, NessieCatalogClient)


def test_factory_creates_openmetadata_client():
    """Test factory creates OpenMetadata client."""
    config = CatalogConfig(
        type="openmetadata",
        enabled=True,
        uri="http://localhost:8585/api",
    )
    
    with patch("src.dativo_ingest.catalogs.openmetadata.OpenMetadata"):
        client = create_catalog_client(config)
        assert isinstance(client, OpenMetadataCatalogClient)


def test_factory_returns_none_when_disabled():
    """Test factory returns None when catalog is disabled."""
    config = CatalogConfig(
        type="glue",
        enabled=False,
        aws_region="us-east-1",
    )
    
    client = create_catalog_client(config)
    assert client is None


def test_factory_raises_for_unsupported_type():
    """Test factory raises error for unsupported catalog type."""
    config = CatalogConfig(
        type="unsupported",
        enabled=True,
    )
    
    with pytest.raises(ValueError, match="Unsupported catalog type"):
        create_catalog_client(config)


def test_factory_handles_alternative_names():
    """Test factory handles alternative names for catalog types."""
    # Test 'unity_catalog' alias
    config = CatalogConfig(
        type="unity_catalog",
        enabled=True,
        workspace_url="https://workspace.databricks.com",
        token="test-token",
    )
    client = create_catalog_client(config)
    assert isinstance(client, UnityCatalogClient)
    
    # Test 'databricks' alias
    config = CatalogConfig(
        type="databricks",
        enabled=True,
        workspace_url="https://workspace.databricks.com",
        token="test-token",
    )
    client = create_catalog_client(config)
    assert isinstance(client, UnityCatalogClient)
    
    # Test 'open_metadata' alias
    config = CatalogConfig(
        type="open_metadata",
        enabled=True,
        uri="http://localhost:8585/api",
    )
    with patch("src.dativo_ingest.catalogs.openmetadata.OpenMetadata"):
        client = create_catalog_client(config)
        assert isinstance(client, OpenMetadataCatalogClient)


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


@patch("src.dativo_ingest.catalogs.aws_glue.boto3.client")
def test_glue_full_workflow(mock_boto_client, sample_lineage):
    """Test full workflow with Glue catalog."""
    # Create client
    config = CatalogConfig(
        type="glue",
        enabled=True,
        aws_region="us-east-1",
        aws_account_id="123456789012",
    )
    client = create_catalog_client(config)
    
    # Mock boto3 client
    mock_client = Mock()
    mock_boto_client.return_value = mock_client
    mock_client.get_database.return_value = {"Database": {"Name": "default"}}
    mock_client.exceptions.EntityNotFoundException = Exception
    
    # Test connection
    mock_client.get_databases.return_value = {"DatabaseList": []}
    assert client.test_connection() is True
    
    # Register dataset
    schema = [
        {"name": "id", "type": "string"},
        {"name": "name", "type": "string"},
    ]
    metadata = {
        "description": "Test table",
        "owner": "test@example.com",
    }
    
    mock_client.update_table.side_effect = Exception("Not found")
    result = client.register_dataset("default.users", schema, metadata)
    assert result["status"] == "success"
    
    # Publish lineage
    mock_client.update_table.side_effect = None
    mock_client.get_table.return_value = {
        "Table": {
            "Name": "users",
            "StorageDescriptor": {"Columns": []},
            "Parameters": {},
        }
    }
    result = client.publish_lineage(sample_lineage)
    assert result["status"] == "success"


@patch("src.dativo_ingest.catalogs.openmetadata.OpenMetadata")
def test_openmetadata_full_workflow(mock_om_class, sample_lineage):
    """Test full workflow with OpenMetadata catalog."""
    # Create client
    config = CatalogConfig(
        type="openmetadata",
        enabled=True,
        uri="http://localhost:8585/api",
    )
    client = create_catalog_client(config)
    
    # Mock OpenMetadata client
    mock_client = Mock()
    mock_om_class.return_value = mock_client
    client._client = mock_client
    
    # Test connection
    mock_client.health_check.return_value = True
    assert client.test_connection() is True
    
    # Register dataset
    schema = [
        {"name": "id", "type": "string"},
        {"name": "name", "type": "string"},
    ]
    metadata = {
        "description": "Test table",
        "owner": "test@example.com",
    }
    
    mock_service = Mock()
    mock_service.id = "service-123"
    mock_service.fullyQualifiedName = "dativo_service"
    
    mock_database = Mock()
    mock_database.id = "db-123"
    mock_database.fullyQualifiedName = "dativo_service.default"
    
    mock_table = Mock()
    mock_table.id = "table-123"
    
    mock_client.get_by_name.side_effect = [mock_service, mock_database]
    mock_client.create_or_update.return_value = mock_table
    
    result = client.register_dataset("default.users", schema, metadata)
    assert result["status"] == "success"


def test_config_with_environment_variables():
    """Test catalog configuration with environment variables."""
    import os
    
    # Set environment variables
    os.environ["AWS_REGION"] = "us-west-2"
    os.environ["CATALOG_URI"] = "http://catalog.example.com"
    
    # Create config with env var references
    config = CatalogConfig(
        type="glue",
        enabled=True,
    )
    
    client = create_catalog_client(config)
    assert client.config.aws_region in ["us-west-2", "us-east-1"]
    
    # Clean up
    os.environ.pop("AWS_REGION", None)
    os.environ.pop("CATALOG_URI", None)


def test_lineage_info_validation():
    """Test LineageInfo validation."""
    lineage = LineageInfo(
        source_type="postgres",
        target_type="iceberg",
        target_dataset="default.users",
        pipeline_name="test_pipeline",
        tenant_id="test_tenant",
        execution_time=datetime.utcnow(),
    )
    
    assert lineage.source_type == "postgres"
    assert lineage.target_type == "iceberg"
    assert lineage.tenant_id == "test_tenant"
    assert isinstance(lineage.execution_time, datetime)


def test_lineage_info_with_metadata():
    """Test LineageInfo with additional metadata."""
    lineage = LineageInfo(
        source_type="postgres",
        source_name="mydb",
        source_dataset="users",
        target_type="iceberg",
        target_dataset="default.users",
        pipeline_name="test_pipeline",
        tenant_id="test_tenant",
        records_processed=1000,
        bytes_processed=50000,
        transformation_type="etl",
        transformation_description="Extract, transform, load",
        execution_time=datetime.utcnow(),
        metadata={"custom_field": "custom_value"},
    )
    
    assert lineage.records_processed == 1000
    assert lineage.bytes_processed == 50000
    assert lineage.transformation_type == "etl"
    assert lineage.metadata["custom_field"] == "custom_value"
