"""Unit tests for catalog integrations."""

import os
from datetime import datetime
from unittest.mock import MagicMock, patch, Mock

import pytest

from dativo_ingest.catalog_integrations import (
    AWSGlueCatalogClient,
    BaseCatalogClient,
    DatabricksUnityCatalogClient,
    LineageInfo,
    NessieCatalogClient,
    OpenMetadataCatalogClient,
    create_catalog_client,
)
from dativo_ingest.config import AssetDefinition, CatalogConfig


@pytest.fixture
def sample_asset_definition():
    """Create a sample asset definition for testing."""
    return AssetDefinition(
        name="test_table",
        version="1.0",
        source_type="postgres",
        object="users",
        schema=[
            {"name": "id", "type": "integer", "required": True, "description": "User ID"},
            {"name": "name", "type": "string", "required": True, "description": "User name"},
            {"name": "email", "type": "string", "required": False, "description": "User email"},
            {"name": "created_at", "type": "timestamp", "required": True, "description": "Creation timestamp"},
        ],
        team={"owner": "data-team@company.com"},
        domain="analytics",
        tags=["test", "users"],
    )


@pytest.fixture
def sample_lineage_info(sample_asset_definition):
    """Create a sample lineage info for testing."""
    return LineageInfo(
        source_type="postgres",
        source_name="users",
        target_type="iceberg",
        target_name="test_table",
        asset_definition=sample_asset_definition,
        record_count=1000,
        file_count=5,
        total_bytes=1024000,
        file_paths=[
            "s3://bucket/domain/table/file1.parquet",
            "s3://bucket/domain/table/file2.parquet",
        ],
        execution_time=datetime(2024, 1, 1, 12, 0, 0),
    )


class TestLineageInfo:
    """Tests for LineageInfo class."""

    def test_lineage_info_creation(self, sample_asset_definition):
        """Test LineageInfo creation with all parameters."""
        lineage = LineageInfo(
            source_type="postgres",
            source_name="users",
            target_type="iceberg",
            target_name="test_table",
            asset_definition=sample_asset_definition,
            record_count=1000,
            file_count=5,
            total_bytes=1024000,
            file_paths=["s3://bucket/path/file.parquet"],
            execution_time=datetime.utcnow(),
            classification_overrides={"email": "PII"},
            finops={"cost_center": "analytics"},
            governance_overrides={"retention_days": 90},
            source_tags={"source_system": "postgres"},
        )

        assert lineage.source_type == "postgres"
        assert lineage.source_name == "users"
        assert lineage.target_type == "iceberg"
        assert lineage.target_name == "test_table"
        assert lineage.record_count == 1000
        assert lineage.file_count == 5
        assert lineage.total_bytes == 1024000
        assert len(lineage.file_paths) == 1
        assert lineage.classification_overrides == {"email": "PII"}
        assert lineage.finops == {"cost_center": "analytics"}


class TestBaseCatalogClient:
    """Tests for BaseCatalogClient abstract class."""

    def test_derive_table_properties(self, sample_lineage_info):
        """Test deriving table properties from lineage info."""
        # Create a concrete implementation for testing
        class TestCatalogClient(BaseCatalogClient):
            def push_lineage(self, lineage_info):
                return {}

            def create_or_update_table(self, table_name, schema, metadata):
                return {}

        catalog_config = CatalogConfig(
            type="test",
            connection={},
        )
        client = TestCatalogClient(catalog_config)

        properties = client._derive_table_properties(sample_lineage_info)

        # Check that properties include expected fields
        assert "source_type" in properties
        assert properties["source_type"] == "postgres"
        assert "source_name" in properties
        assert properties["source_name"] == "users"
        assert "target_type" in properties
        assert "last_ingestion_time" in properties
        assert "last_record_count" in properties
        assert properties["last_record_count"] == "1000"


class TestAWSGlueCatalogClient:
    """Tests for AWS Glue catalog client."""

    @patch("dativo_ingest.catalog_integrations.boto3")
    def test_client_initialization(self, mock_boto3):
        """Test AWS Glue client initialization."""
        catalog_config = CatalogConfig(
            type="aws_glue",
            connection={
                "region": "us-east-1",
                "database": "test_db",
            },
        )

        client = AWSGlueCatalogClient(catalog_config)
        assert client.catalog_config == catalog_config
        assert client._client is None  # Client not created until first use

    @patch("dativo_ingest.catalog_integrations.boto3")
    def test_push_lineage_creates_table(self, mock_boto3, sample_lineage_info):
        """Test pushing lineage creates a new table in Glue."""
        mock_glue_client = MagicMock()
        mock_boto3.client.return_value = mock_glue_client
        
        # Simulate table doesn't exist
        mock_glue_client.update_table.side_effect = mock_glue_client.exceptions.EntityNotFoundException()

        catalog_config = CatalogConfig(
            type="aws_glue",
            connection={
                "region": "us-east-1",
                "database": "test_db",
                "bucket": "test-bucket",
            },
        )

        client = AWSGlueCatalogClient(catalog_config)
        result = client.push_lineage(sample_lineage_info)

        # Verify create_table was called after update failed
        assert mock_glue_client.create_table.called
        assert result["status"] == "success"
        assert result["catalog"] == "aws_glue"
        assert result["database"] == "test_db"

    @patch("dativo_ingest.catalog_integrations.boto3")
    def test_push_lineage_updates_existing_table(self, mock_boto3, sample_lineage_info):
        """Test pushing lineage updates an existing table in Glue."""
        mock_glue_client = MagicMock()
        mock_boto3.client.return_value = mock_glue_client

        catalog_config = CatalogConfig(
            type="aws_glue",
            connection={
                "region": "us-east-1",
                "database": "test_db",
                "bucket": "test-bucket",
            },
        )

        client = AWSGlueCatalogClient(catalog_config)
        result = client.push_lineage(sample_lineage_info)

        # Verify update_table was called
        assert mock_glue_client.update_table.called
        assert result["status"] == "success"


class TestDatabricksUnityCatalogClient:
    """Tests for Databricks Unity Catalog client."""

    def test_client_initialization(self):
        """Test Databricks Unity Catalog client initialization."""
        catalog_config = CatalogConfig(
            type="databricks_unity",
            connection={
                "workspace_url": "https://workspace.databricks.com",
                "token": "test-token",
                "catalog": "main",
                "schema": "default",
            },
        )

        client = DatabricksUnityCatalogClient(catalog_config)
        assert client.catalog_config == catalog_config
        assert client._session is None

    @patch("dativo_ingest.catalog_integrations.requests.Session")
    def test_push_lineage_creates_table(self, mock_session_class, sample_lineage_info):
        """Test pushing lineage creates a new table in Unity Catalog."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        
        # Mock successful table creation
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_session.post.return_value = mock_response

        catalog_config = CatalogConfig(
            type="databricks_unity",
            connection={
                "workspace_url": "https://workspace.databricks.com",
                "token": "test-token",
                "catalog": "main",
                "schema": "default",
                "bucket": "test-bucket",
            },
        )

        client = DatabricksUnityCatalogClient(catalog_config)
        result = client.push_lineage(sample_lineage_info)

        assert result["status"] == "success"
        assert result["catalog"] == "databricks_unity"
        assert "main.default.test_table" in result["full_name"]

    @patch("dativo_ingest.catalog_integrations.requests.Session")
    def test_push_lineage_updates_existing_table(self, mock_session_class, sample_lineage_info):
        """Test pushing lineage updates an existing table in Unity Catalog."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        
        # Mock table already exists (409 conflict)
        mock_post_response = MagicMock()
        mock_post_response.status_code = 409
        mock_session.post.return_value = mock_post_response
        
        # Mock successful update
        mock_patch_response = MagicMock()
        mock_patch_response.status_code = 200
        mock_session.patch.return_value = mock_patch_response

        catalog_config = CatalogConfig(
            type="databricks_unity",
            connection={
                "workspace_url": "https://workspace.databricks.com",
                "token": "test-token",
                "catalog": "main",
                "schema": "default",
                "bucket": "test-bucket",
            },
        )

        client = DatabricksUnityCatalogClient(catalog_config)
        result = client.push_lineage(sample_lineage_info)

        # Verify patch was called after post returned 409
        assert mock_session.patch.called
        assert result["status"] == "success"


class TestNessieCatalogClient:
    """Tests for Nessie catalog client."""

    @patch("dativo_ingest.catalog_integrations.init")
    def test_client_initialization(self, mock_init):
        """Test Nessie catalog client initialization."""
        catalog_config = CatalogConfig(
            type="nessie",
            connection={
                "uri": "http://localhost:19120/api/v1",
                "branch": "main",
            },
        )

        client = NessieCatalogClient(catalog_config)
        assert client.catalog_config == catalog_config
        assert client._client is None

    @patch("dativo_ingest.catalog_integrations.init")
    def test_push_lineage(self, mock_init, sample_lineage_info):
        """Test pushing lineage to Nessie."""
        mock_nessie_client = MagicMock()
        mock_init.return_value = mock_nessie_client
        
        # Mock get_reference
        mock_ref = MagicMock()
        mock_nessie_client.get_reference.return_value = mock_ref

        catalog_config = CatalogConfig(
            type="nessie",
            connection={
                "uri": "http://localhost:19120/api/v1",
                "branch": "main",
                "bucket": "test-bucket",
            },
        )

        client = NessieCatalogClient(catalog_config)
        result = client.push_lineage(sample_lineage_info)

        assert result["status"] == "success"
        assert result["catalog"] == "nessie"
        assert result["branch"] == "main"
        assert result["namespace"] == "analytics"
        assert result["table"] == "test_table"


class TestOpenMetadataCatalogClient:
    """Tests for OpenMetadata catalog client."""

    def test_client_initialization(self):
        """Test OpenMetadata catalog client initialization."""
        catalog_config = CatalogConfig(
            type="openmetadata",
            connection={
                "host_port": "http://localhost:8585/api",
                "service_name": "dativo_ingestion",
            },
        )

        client = OpenMetadataCatalogClient(catalog_config)
        assert client.catalog_config == catalog_config
        assert client._client is None

    @patch("dativo_ingest.catalog_integrations.OpenMetadata")
    def test_push_lineage_creates_entities(self, mock_om_class, sample_lineage_info):
        """Test pushing lineage creates all necessary entities in OpenMetadata."""
        mock_om_client = MagicMock()
        mock_om_class.return_value = mock_om_client
        
        # Mock service, database, schema don't exist
        mock_om_client.get_by_name.side_effect = Exception("Not found")
        
        # Mock successful creation
        mock_service = MagicMock()
        mock_service.id = "service-123"
        mock_database = MagicMock()
        mock_database.id = "db-123"
        mock_schema = MagicMock()
        mock_schema.id = "schema-123"
        mock_table = MagicMock()
        mock_table.id = MagicMock()
        mock_table.id.__root__ = "table-123"
        
        mock_om_client.create_or_update.side_effect = [
            mock_service,
            mock_database,
            mock_schema,
            mock_table,
        ]

        catalog_config = CatalogConfig(
            type="openmetadata",
            connection={
                "host_port": "http://localhost:8585/api",
                "service_name": "dativo_ingestion",
                "database": "test_db",
                "schema": "default",
            },
        )

        client = OpenMetadataCatalogClient(catalog_config)
        result = client.push_lineage(sample_lineage_info)

        assert result["status"] == "success"
        assert result["catalog"] == "openmetadata"
        assert "table_fqn" in result
        assert "table_id" in result


class TestCatalogClientFactory:
    """Tests for catalog client factory function."""

    def test_create_aws_glue_client(self):
        """Test creating AWS Glue client via factory."""
        catalog_config = CatalogConfig(
            type="aws_glue",
            connection={"region": "us-east-1"},
        )

        client = create_catalog_client(catalog_config)
        assert isinstance(client, AWSGlueCatalogClient)

    def test_create_databricks_unity_client(self):
        """Test creating Databricks Unity Catalog client via factory."""
        catalog_config = CatalogConfig(
            type="databricks_unity",
            connection={
                "workspace_url": "https://workspace.databricks.com",
                "token": "test-token",
            },
        )

        client = create_catalog_client(catalog_config)
        assert isinstance(client, DatabricksUnityCatalogClient)

    def test_create_nessie_client(self):
        """Test creating Nessie client via factory."""
        catalog_config = CatalogConfig(
            type="nessie",
            connection={"uri": "http://localhost:19120/api/v1"},
        )

        client = create_catalog_client(catalog_config)
        assert isinstance(client, NessieCatalogClient)

    def test_create_openmetadata_client(self):
        """Test creating OpenMetadata client via factory."""
        catalog_config = CatalogConfig(
            type="openmetadata",
            connection={"host_port": "http://localhost:8585/api"},
        )

        client = create_catalog_client(catalog_config)
        assert isinstance(client, OpenMetadataCatalogClient)

    def test_create_unsupported_client(self):
        """Test that creating unsupported client type raises ValueError."""
        catalog_config = CatalogConfig(
            type="unsupported_catalog",
            connection={},
        )

        with pytest.raises(ValueError, match="Unsupported catalog type"):
            create_catalog_client(catalog_config)


class TestCatalogConfigInJobConfig:
    """Tests for catalog configuration in job config."""

    def test_job_config_with_catalog(self):
        """Test job config with catalog configuration."""
        from dativo_ingest.config import JobConfig

        job_data = {
            "tenant_id": "test_tenant",
            "source_connector_path": "connectors/test.yaml",
            "target_connector_path": "connectors/test.yaml",
            "asset_path": "assets/test.yaml",
            "catalog": {
                "type": "openmetadata",
                "enabled": True,
                "connection": {
                    "host_port": "http://localhost:8585/api",
                    "service_name": "dativo_ingestion",
                },
                "options": {
                    "database": "test_db",
                    "schema": "default",
                },
            },
        }

        job = JobConfig(**job_data)
        assert job.catalog is not None
        assert job.catalog.type == "openmetadata"
        assert job.catalog.enabled is True
        assert job.catalog.connection["host_port"] == "http://localhost:8585/api"

    def test_job_config_without_catalog(self):
        """Test job config without catalog configuration."""
        from dativo_ingest.config import JobConfig

        job_data = {
            "tenant_id": "test_tenant",
            "source_connector_path": "connectors/test.yaml",
            "target_connector_path": "connectors/test.yaml",
            "asset_path": "assets/test.yaml",
        }

        job = JobConfig(**job_data)
        assert job.catalog is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
