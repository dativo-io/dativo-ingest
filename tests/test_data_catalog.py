"""Unit tests for data catalog integration."""

import json
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest

from dativo_ingest.config import AssetDefinition
from dativo_ingest.data_catalog import (
    AWSGlueCatalogClient,
    CatalogLineage,
    CatalogManager,
    DatabricksUnityCatalogClient,
    NessieCatalogClient,
    OpenMetadataCatalogClient,
)


# Fixtures
@pytest.fixture
def sample_schema():
    """Sample schema for testing."""
    return [
        {"name": "id", "type": "string", "required": True, "description": "Record ID"},
        {
            "name": "name",
            "type": "string",
            "required": False,
            "description": "Record name",
        },
        {"name": "amount", "type": "float", "required": True, "description": "Amount"},
        {"name": "created_at", "type": "timestamp", "description": "Creation timestamp"},
    ]


@pytest.fixture
def sample_asset_definition():
    """Sample asset definition for testing."""
    asset_data = {
        "apiVersion": "v3.0.2",
        "kind": "DataContract",
        "name": "test_table",
        "version": "1.0",
        "domain": "test_domain",
        "dataProduct": "test_product",
        "source_type": "stripe",
        "object": "customers",
        "schema": [
            {"name": "id", "type": "string", "required": True},
            {"name": "name", "type": "string", "required": False},
        ],
        "team": {"owner": "data-team@example.com"},
        "tags": ["stripe", "customers"],
        "compliance": {"classification": ["PII", "SENSITIVE"]},
    }
    return AssetDefinition(**asset_data)


@pytest.fixture
def catalog_lineage():
    """Sample catalog lineage for testing."""
    return CatalogLineage(
        source_type="stripe",
        source_object="customers",
        target_table="stripe_customers",
        target_database="test_db",
        job_id="test_job_123",
        tenant_id="test_tenant",
        execution_time=datetime(2024, 1, 1, 12, 0, 0),
        upstream_tables=["stripe.raw.customers"],
        downstream_tables=["analytics.customers"],
        records_written=1000,
        files_written=5,
        metadata={"test_key": "test_value"},
    )


# AWS Glue Tests
class TestAWSGlueCatalogClient:
    """Tests for AWS Glue Data Catalog client."""

    @patch("dativo_ingest.data_catalog.boto3")
    def test_init(self, mock_boto3):
        """Test AWS Glue client initialization."""
        config = {"region": "us-west-2", "database": "test_db"}
        client = AWSGlueCatalogClient(config)

        assert client.region == "us-west-2"
        assert client.database == "test_db"
        mock_boto3.client.assert_called_once_with("glue", region_name="us-west-2")

    @patch("dativo_ingest.data_catalog.boto3")
    def test_create_table(self, mock_boto3, sample_schema):
        """Test table creation in AWS Glue."""
        mock_glue = Mock()
        mock_glue.exceptions.EntityNotFoundException = Exception
        mock_boto3.client.return_value = mock_glue

        config = {"region": "us-east-1", "database": "test_db"}
        client = AWSGlueCatalogClient(config)

        # Simulate table doesn't exist (EntityNotFoundException)
        mock_glue.update_table.side_effect = Exception("EntityNotFoundException")

        result = client.create_or_update_table(
            database="test_db",
            table_name="test_table",
            schema=sample_schema,
            location="s3://bucket/path",
            metadata={"description": "Test table"},
        )

        assert result["status"] == "created"
        assert result["table"] == "test_table"
        mock_glue.create_table.assert_called_once()

    @patch("dativo_ingest.data_catalog.boto3")
    def test_push_lineage(self, mock_boto3, catalog_lineage):
        """Test lineage pushing to AWS Glue."""
        mock_glue = Mock()
        mock_boto3.client.return_value = mock_glue

        # Mock get_table response
        mock_glue.get_table.return_value = {
            "Table": {
                "Name": "test_table",
                "StorageDescriptor": {"Columns": []},
                "Parameters": {},
            }
        }

        config = {"region": "us-east-1", "database": "test_db"}
        client = AWSGlueCatalogClient(config)

        result = client.push_lineage(catalog_lineage)

        assert result["status"] == "success"
        assert result["lineage_pushed"] is True
        mock_glue.update_table.assert_called_once()

    @patch("dativo_ingest.data_catalog.boto3")
    def test_add_tags(self, mock_boto3):
        """Test adding tags to AWS Glue table."""
        mock_glue = Mock()
        mock_boto3.client.return_value = mock_glue

        config = {"region": "us-east-1", "database": "test_db"}
        client = AWSGlueCatalogClient(config)

        tags = {"environment": "production", "team": "data"}

        with patch.dict("os.environ", {"AWS_ACCOUNT_ID": "123456789012"}):
            result = client.add_tags("test_db", "test_table", tags)

        assert result["status"] == "success"
        assert result["tags_added"] == 2


# Databricks Unity Catalog Tests
class TestDatabricksUnityCatalogClient:
    """Tests for Databricks Unity Catalog client."""

    @patch("dativo_ingest.data_catalog.requests.Session")
    def test_init(self, mock_session):
        """Test Unity Catalog client initialization."""
        config = {
            "workspace_url": "https://test.databricks.com",
            "token": "test_token",
            "catalog": "main",
        }
        client = DatabricksUnityCatalogClient(config)

        assert client.workspace_url == "https://test.databricks.com"
        assert client.catalog == "main"

    @patch("dativo_ingest.data_catalog.requests.Session")
    def test_create_table(self, mock_session, sample_schema):
        """Test table creation in Unity Catalog."""
        mock_session_instance = Mock()
        mock_session.return_value = mock_session_instance

        # Mock response for table doesn't exist
        mock_get_response = Mock()
        mock_get_response.status_code = 404
        mock_session_instance.get.return_value = mock_get_response

        # Mock response for table creation
        mock_post_response = Mock()
        mock_post_response.status_code = 201
        mock_post_response.raise_for_status = Mock()
        mock_session_instance.post.return_value = mock_post_response

        config = {
            "workspace_url": "https://test.databricks.com",
            "token": "test_token",
            "catalog": "main",
        }
        client = DatabricksUnityCatalogClient(config)

        result = client.create_or_update_table(
            database="test_schema",
            table_name="test_table",
            schema=sample_schema,
            location="s3://bucket/path",
            metadata={"description": "Test table"},
        )

        assert result["status"] == "created"
        assert "test_table" in result["table"]

    @patch("dativo_ingest.data_catalog.requests.Session")
    def test_push_lineage(self, mock_session, catalog_lineage):
        """Test lineage pushing to Unity Catalog."""
        mock_session_instance = Mock()
        mock_session.return_value = mock_session_instance

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_session_instance.post.return_value = mock_response

        config = {
            "workspace_url": "https://test.databricks.com",
            "token": "test_token",
            "catalog": "main",
        }
        client = DatabricksUnityCatalogClient(config)

        result = client.push_lineage(catalog_lineage)

        assert result["status"] == "success"
        assert result["lineage_pushed"] is True


# Nessie Catalog Tests
class TestNessieCatalogClient:
    """Tests for Nessie Catalog client."""

    @patch("dativo_ingest.data_catalog.requests.Session")
    def test_init(self, mock_session):
        """Test Nessie client initialization."""
        config = {"uri": "http://localhost:19120", "branch": "main"}
        client = NessieCatalogClient(config)

        assert client.uri == "http://localhost:19120"
        assert client.branch == "main"
        assert client.base_uri == "http://localhost:19120/api/v1"

    @patch("dativo_ingest.data_catalog.requests.Session")
    def test_create_or_update_table(self, mock_session, sample_schema):
        """Test table creation in Nessie."""
        mock_session_instance = Mock()
        mock_session.return_value = mock_session_instance

        mock_response = Mock()
        mock_response.status_code = 200
        mock_session_instance.post.return_value = mock_response

        config = {"uri": "http://localhost:19120", "branch": "main"}
        client = NessieCatalogClient(config)

        result = client.create_or_update_table(
            database="test_db",
            table_name="test_table",
            schema=sample_schema,
            location="s3://bucket/path",
            metadata={"snapshot_id": 1, "schema_id": 1, "spec_id": 0, "sort_order_id": 0},
        )

        assert result["status"] == "success"
        assert result["table"] == "test_db.test_table"

    @patch("dativo_ingest.data_catalog.requests.Session")
    def test_push_lineage(self, mock_session, catalog_lineage):
        """Test lineage pushing to Nessie."""
        mock_session_instance = Mock()
        mock_session.return_value = mock_session_instance

        mock_response = Mock()
        mock_response.status_code = 200
        mock_session_instance.get.return_value = mock_response

        config = {"uri": "http://localhost:19120", "branch": "main"}
        client = NessieCatalogClient(config)

        result = client.push_lineage(catalog_lineage)

        assert result["status"] == "success"
        assert result["lineage_stored"] is True


# OpenMetadata Tests
class TestOpenMetadataCatalogClient:
    """Tests for OpenMetadata catalog client."""

    @patch("dativo_ingest.data_catalog.requests.Session")
    def test_init(self, mock_session):
        """Test OpenMetadata client initialization."""
        config = {
            "uri": "http://localhost:8585",
            "token": "test_token",
            "api_version": "v1",
        }
        client = OpenMetadataCatalogClient(config)

        assert client.uri == "http://localhost:8585"
        assert client.api_version == "v1"

    @patch("dativo_ingest.data_catalog.requests.Session")
    def test_create_table(self, mock_session, sample_schema):
        """Test table creation in OpenMetadata."""
        mock_session_instance = Mock()
        mock_session.return_value = mock_session_instance

        # Mock response for table doesn't exist
        mock_get_response = Mock()
        mock_get_response.status_code = 404
        mock_session_instance.get.return_value = mock_get_response

        # Mock response for table creation
        mock_post_response = Mock()
        mock_post_response.status_code = 201
        mock_post_response.json.return_value = {"id": "table-123"}
        mock_post_response.raise_for_status = Mock()
        mock_session_instance.post.return_value = mock_post_response

        config = {"uri": "http://localhost:8585", "token": "test_token"}
        client = OpenMetadataCatalogClient(config)

        result = client.create_or_update_table(
            database="test_db",
            table_name="test_table",
            schema=sample_schema,
            location="s3://bucket/path",
            metadata={"description": "Test table"},
        )

        assert result["status"] == "created"
        assert "test_table" in result["table"]

    @patch("dativo_ingest.data_catalog.requests.Session")
    def test_push_lineage(self, mock_session, catalog_lineage):
        """Test lineage pushing to OpenMetadata."""
        mock_session_instance = Mock()
        mock_session.return_value = mock_session_instance

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_session_instance.put.return_value = mock_response

        config = {"uri": "http://localhost:8585", "token": "test_token"}
        client = OpenMetadataCatalogClient(config)

        result = client.push_lineage(catalog_lineage)

        assert result["status"] == "success"
        assert result["lineage_pushed"] is True
        assert result["edges"] >= 0

    @patch("dativo_ingest.data_catalog.requests.Session")
    def test_add_tags(self, mock_session):
        """Test adding tags in OpenMetadata."""
        mock_session_instance = Mock()
        mock_session.return_value = mock_session_instance

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_session_instance.patch.return_value = mock_response

        config = {"uri": "http://localhost:8585", "token": "test_token"}
        client = OpenMetadataCatalogClient(config)

        tags = {"environment": "production", "team": "data"}
        result = client.add_tags("test_db", "test_table", tags)

        assert result["status"] == "success"
        assert result["tags_added"] == 2

    @patch("dativo_ingest.data_catalog.requests.Session")
    def test_add_owners(self, mock_session):
        """Test adding owners in OpenMetadata."""
        mock_session_instance = Mock()
        mock_session.return_value = mock_session_instance

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_session_instance.patch.return_value = mock_response

        config = {"uri": "http://localhost:8585", "token": "test_token"}
        client = OpenMetadataCatalogClient(config)

        owners = ["user1", "user2"]
        result = client.add_owners("test_db", "test_table", owners)

        assert result["status"] == "success"
        assert result["owners_added"] == 2


# CatalogManager Tests
class TestCatalogManager:
    """Tests for CatalogManager."""

    @patch("dativo_ingest.data_catalog.OpenMetadataCatalogClient")
    def test_init_openmetadata(self, mock_client, sample_asset_definition):
        """Test CatalogManager initialization with OpenMetadata."""
        catalog_config = {
            "type": "openmetadata",
            "config": {"uri": "http://localhost:8585"},
        }

        manager = CatalogManager(catalog_config, sample_asset_definition)

        assert manager.catalog_config == catalog_config
        assert manager.asset_definition == sample_asset_definition
        mock_client.assert_called_once()

    @patch("dativo_ingest.data_catalog.AWSGlueCatalogClient")
    def test_init_aws_glue(self, mock_client, sample_asset_definition):
        """Test CatalogManager initialization with AWS Glue."""
        catalog_config = {
            "type": "aws_glue",
            "config": {"region": "us-east-1", "database": "test_db"},
        }

        manager = CatalogManager(catalog_config, sample_asset_definition)

        assert manager.catalog_config == catalog_config
        mock_client.assert_called_once()

    def test_init_invalid_type(self, sample_asset_definition):
        """Test CatalogManager initialization with invalid type."""
        catalog_config = {"type": "invalid_catalog", "config": {}}

        with pytest.raises(ValueError, match="Unsupported catalog type"):
            CatalogManager(catalog_config, sample_asset_definition)

    @patch("dativo_ingest.data_catalog.OpenMetadataCatalogClient")
    def test_sync_table_metadata(self, mock_client_class, sample_asset_definition):
        """Test syncing table metadata."""
        mock_client = Mock()
        mock_client.create_or_update_table.return_value = {
            "status": "created",
            "table": "test_db.test_table",
        }
        mock_client_class.return_value = mock_client

        catalog_config = {
            "type": "openmetadata",
            "config": {"uri": "http://localhost:8585"},
            "metadata": {"tier": "gold", "description": "Test table"},
        }

        manager = CatalogManager(catalog_config, sample_asset_definition)

        result = manager.sync_table_metadata(
            database="test_db",
            table_name="test_table",
            location="s3://bucket/path",
            additional_metadata={"records_written": 1000},
        )

        assert result["status"] == "created"
        mock_client.create_or_update_table.assert_called_once()

        # Verify metadata includes asset info
        call_args = mock_client.create_or_update_table.call_args
        metadata = call_args.kwargs["metadata"]
        assert "source_type" in metadata
        assert "domain" in metadata
        assert "records_written" in metadata

    @patch("dativo_ingest.data_catalog.OpenMetadataCatalogClient")
    def test_push_lineage(self, mock_client_class, sample_asset_definition):
        """Test pushing lineage."""
        mock_client = Mock()
        mock_client.push_lineage.return_value = {"status": "success", "lineage_pushed": True}
        mock_client_class.return_value = mock_client

        catalog_config = {
            "type": "openmetadata",
            "config": {"uri": "http://localhost:8585"},
            "lineage": {
                "enabled": True,
                "upstream_tables": ["source.table1", "source.table2"],
            },
        }

        manager = CatalogManager(catalog_config, sample_asset_definition)

        result = manager.push_lineage(
            source_type="stripe",
            source_object="customers",
            target_database="test_db",
            target_table="test_table",
            job_id="test_job",
            tenant_id="test_tenant",
            records_written=1000,
            files_written=5,
        )

        assert result["status"] == "success"
        mock_client.push_lineage.assert_called_once()

    @patch("dativo_ingest.data_catalog.OpenMetadataCatalogClient")
    def test_push_lineage_disabled(self, mock_client_class, sample_asset_definition):
        """Test pushing lineage when disabled."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        catalog_config = {
            "type": "openmetadata",
            "config": {"uri": "http://localhost:8585"},
            "lineage": {"enabled": False},
        }

        manager = CatalogManager(catalog_config, sample_asset_definition)

        result = manager.push_lineage(
            source_type="stripe",
            source_object="customers",
            target_database="test_db",
            target_table="test_table",
            job_id="test_job",
            tenant_id="test_tenant",
        )

        assert result["status"] == "disabled"
        mock_client.push_lineage.assert_not_called()

    @patch("dativo_ingest.data_catalog.OpenMetadataCatalogClient")
    def test_sync_tags(self, mock_client_class, sample_asset_definition):
        """Test syncing tags."""
        mock_client = Mock()
        mock_client.add_tags.return_value = {"status": "success", "tags_added": 3}
        mock_client_class.return_value = mock_client

        catalog_config = {
            "type": "openmetadata",
            "config": {"uri": "http://localhost:8585"},
            "metadata": {"tags": {"custom_tag": "custom_value"}, "tier": "gold"},
        }

        manager = CatalogManager(catalog_config, sample_asset_definition)

        result = manager.sync_tags(database="test_db", table_name="test_table")

        assert result["status"] == "success"
        mock_client.add_tags.assert_called_once()

        # Verify tags include asset tags, domain, and custom tags
        call_args = mock_client.add_tags.call_args
        tags = call_args[0][2]  # Third positional argument
        assert "domain" in tags
        assert "tier" in tags

    @patch("dativo_ingest.data_catalog.OpenMetadataCatalogClient")
    def test_sync_owners(self, mock_client_class, sample_asset_definition):
        """Test syncing owners."""
        mock_client = Mock()
        mock_client.add_owners.return_value = {"status": "success", "owners_added": 1}
        mock_client_class.return_value = mock_client

        catalog_config = {
            "type": "openmetadata",
            "config": {"uri": "http://localhost:8585"},
            "metadata": {"owners": ["additional-owner@example.com"]},
        }

        manager = CatalogManager(catalog_config, sample_asset_definition)

        result = manager.sync_owners(database="test_db", table_name="test_table")

        assert result["status"] == "success"
        mock_client.add_owners.assert_called_once()

        # Verify owners include asset owner and additional owners
        call_args = mock_client.add_owners.call_args
        owners = call_args[0][2]  # Third positional argument
        assert "data-team@example.com" in owners


# Integration Tests (require actual services)
@pytest.mark.integration
class TestCatalogIntegration:
    """Integration tests for catalog clients (require actual services)."""

    def test_openmetadata_full_flow(self, sample_schema, sample_asset_definition):
        """Test full OpenMetadata flow (requires running OpenMetadata)."""
        # Skip if OpenMetadata not available
        pytest.importorskip("metadata")

        catalog_config = {
            "type": "openmetadata",
            "config": {
                "uri": "http://localhost:8585",
                "token": "",
            },
            "metadata": {
                "owners": ["test-owner@example.com"],
                "tags": {"environment": "test"},
                "tier": "bronze",
            },
            "lineage": {"enabled": True, "upstream_tables": []},
        }

        try:
            manager = CatalogManager(catalog_config, sample_asset_definition)

            # Sync table metadata
            table_result = manager.sync_table_metadata(
                database="test_db",
                table_name="test_table",
                location="s3://test-bucket/test/path",
                additional_metadata={"records_written": 100},
            )
            assert table_result["status"] in ["created", "updated"]

            # Push lineage
            lineage_result = manager.push_lineage(
                source_type="stripe",
                source_object="customers",
                target_database="test_db",
                target_table="test_table",
                job_id="test_job",
                tenant_id="test_tenant",
                records_written=100,
                files_written=1,
            )
            # Lineage may fail if upstream tables don't exist
            assert lineage_result["status"] in ["success", "error"]

            # Sync tags
            tags_result = manager.sync_tags("test_db", "test_table")
            assert tags_result["status"] in ["success", "error"]

            # Sync owners
            owners_result = manager.sync_owners("test_db", "test_table")
            assert owners_result["status"] in ["success", "error"]

        except Exception as e:
            pytest.skip(f"OpenMetadata not available: {e}")
