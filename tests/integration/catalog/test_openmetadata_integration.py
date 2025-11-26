"""Integration tests for OpenMetadata catalog client.

These tests require a running OpenMetadata instance.
They can be run against a local OpenMetadata docker container or skipped if not available.
"""

import os
import pytest
import requests

from dativo_ingest.catalog.base import CatalogConfig, TableMetadata, LineageInfo
from dativo_ingest.catalog.openmetadata_client import OpenMetadataClient


# Skip tests if OpenMetadata is not available
def is_openmetadata_available():
    """Check if OpenMetadata is available."""
    try:
        host_port = os.getenv("OPENMETADATA_HOST_PORT", "http://localhost:8585/api")
        response = requests.get(f"{host_port}/v1/system/version", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not is_openmetadata_available(),
    reason="OpenMetadata not available. Start with: docker-compose up -d openmetadata"
)


@pytest.fixture
def openmetadata_config():
    """OpenMetadata configuration for testing."""
    return CatalogConfig(
        type="openmetadata",
        connection={
            "host_port": os.getenv("OPENMETADATA_HOST_PORT", "http://localhost:8585/api"),
            "service_name": "dativo_test_service",
        },
        push_lineage=True,
        push_metadata=True,
    )


@pytest.fixture
def openmetadata_client(openmetadata_config):
    """Create and connect OpenMetadata client."""
    client = OpenMetadataClient(openmetadata_config)
    client.connect()
    yield client
    client.close()


@pytest.fixture
def sample_table_metadata():
    """Sample table metadata for testing."""
    return TableMetadata(
        name="test_customers",
        database="test_domain",
        schema="test_product",
        description="Test customer table",
        owner="data-team@example.com",
        tags={
            "domain": "test_domain",
            "data_product": "test_product",
            "classification": "confidential",
        },
        columns=[
            {"name": "id", "type": "INTEGER", "description": "Customer ID", "required": True},
            {"name": "name", "type": "STRING", "description": "Customer name"},
            {"name": "email", "type": "STRING", "description": "Customer email"},
        ],
        properties={
            "source_type": "postgres",
            "object": "customers",
            "version": "1.0",
        },
    )


class TestOpenMetadataIntegration:
    """Integration tests for OpenMetadata client."""

    def test_connect(self, openmetadata_client):
        """Test connecting to OpenMetadata."""
        assert openmetadata_client._client is not None

    def test_create_table(self, openmetadata_client, sample_table_metadata):
        """Test creating a table in OpenMetadata."""
        # This should create or update without error
        openmetadata_client.create_or_update_table(sample_table_metadata)

    def test_update_table(self, openmetadata_client, sample_table_metadata):
        """Test updating an existing table."""
        # Create first
        openmetadata_client.create_or_update_table(sample_table_metadata)
        
        # Update with new description
        sample_table_metadata.description = "Updated customer table"
        openmetadata_client.create_or_update_table(sample_table_metadata)

    def test_push_lineage(self, openmetadata_client, sample_table_metadata):
        """Test pushing lineage information."""
        # Create table first
        openmetadata_client.create_or_update_table(sample_table_metadata)
        
        # Build FQN
        service_name = openmetadata_client.config.connection.get("service_name", "dativo_test_service")
        target_fqn = f"{service_name}.{sample_table_metadata.database}.{sample_table_metadata.schema}.{sample_table_metadata.name}"
        
        # Push lineage
        lineage = LineageInfo(
            source_fqn="postgres.mydb.customers",
            target_fqn=target_fqn,
            pipeline_name="test_pipeline",
            pipeline_description="Test ingestion pipeline",
            records_read=1000,
            records_written=950,
            status="success",
        )
        
        # This should not raise an exception
        openmetadata_client.push_lineage(lineage)

    def test_add_tags(self, openmetadata_client, sample_table_metadata):
        """Test adding tags to a table."""
        # Create table first
        openmetadata_client.create_or_update_table(sample_table_metadata)
        
        # Build FQN
        service_name = openmetadata_client.config.connection.get("service_name", "dativo_test_service")
        table_fqn = f"{service_name}.{sample_table_metadata.database}.{sample_table_metadata.schema}.{sample_table_metadata.name}"
        
        # Add tags
        tags = {
            "environment": "test",
            "team": "data-engineering",
        }
        
        # This should not raise an exception
        openmetadata_client.add_tags(table_fqn, tags)

    def test_set_owner(self, openmetadata_client, sample_table_metadata):
        """Test setting owner for a table."""
        # Create table first
        openmetadata_client.create_or_update_table(sample_table_metadata)
        
        # Build FQN
        service_name = openmetadata_client.config.connection.get("service_name", "dativo_test_service")
        table_fqn = f"{service_name}.{sample_table_metadata.database}.{sample_table_metadata.schema}.{sample_table_metadata.name}"
        
        # Set owner
        # Note: This will only work if the user exists in OpenMetadata
        openmetadata_client.set_owner(table_fqn, "admin")
