"""Tests for catalog integration functionality."""

import os
from unittest.mock import MagicMock, Mock, patch

import pytest

from dativo_ingest.catalog_integration import (
    AWSGlueIntegration,
    CatalogIntegration,
    DatabricksUnityCatalogIntegration,
    NessieIntegration,
    OpenMetadataIntegration,
    create_catalog_integration,
)
from dativo_ingest.config import AssetDefinition, JobConfig, TeamModel


@pytest.fixture
def sample_asset_definition():
    """Create a sample asset definition for testing."""
    return AssetDefinition(
        name="test_table",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[
            {"name": "id", "type": "string", "required": True},
            {"name": "name", "type": "string", "required": False},
        ],
        team=TeamModel(owner="test@example.com"),
        domain="test_domain",
        dataProduct="test_product",
    )


@pytest.fixture
def sample_job_config():
    """Create a sample job config for testing."""
    return JobConfig(
        tenant_id="test_tenant",
        source_connector_path="connectors/csv.yaml",
        target_connector_path="connectors/iceberg.yaml",
        asset_path="assets/test.yaml",
        catalog={"type": "openmetadata", "api_url": "http://localhost:8585/api"},
    )


class TestCatalogIntegration:
    """Test base catalog integration class."""

    def test_base_class_raises_not_implemented(self, sample_asset_definition, sample_job_config):
        """Test that base class methods raise NotImplementedError."""
        integration = CatalogIntegration(
            catalog_config={"type": "test"},
            asset_definition=sample_asset_definition,
            job_config=sample_job_config,
        )

        with pytest.raises(NotImplementedError):
            integration.push_lineage([], {})

        with pytest.raises(NotImplementedError):
            integration.push_metadata({})

    def test_derive_metadata(self, sample_asset_definition, sample_job_config):
        """Test metadata derivation."""
        integration = CatalogIntegration(
            catalog_config={"type": "test"},
            asset_definition=sample_asset_definition,
            job_config=sample_job_config,
        )

        metadata = integration._derive_metadata()

        assert "tags" in metadata
        assert "owners" in metadata
        assert "domain" in metadata
        assert metadata["domain"] == "test_domain"
        assert "test@example.com" in metadata["owners"]


class TestOpenMetadataIntegration:
    """Test OpenMetadata integration."""

    def test_init(self, sample_asset_definition, sample_job_config):
        """Test OpenMetadata integration initialization."""
        config = {"type": "openmetadata", "api_url": "http://localhost:8585/api"}
        integration = OpenMetadataIntegration(
            catalog_config=config,
            asset_definition=sample_asset_definition,
            job_config=sample_job_config,
        )

        assert integration.api_url == "http://localhost:8585/api"
        assert integration.auth_token is None

    def test_init_with_env_var(self, sample_asset_definition, sample_job_config):
        """Test initialization with environment variable."""
        with patch.dict(os.environ, {"OPENMETADATA_AUTH_TOKEN": "test-token"}):
            config = {"type": "openmetadata"}
            integration = OpenMetadataIntegration(
                catalog_config=config,
                asset_definition=sample_asset_definition,
                job_config=sample_job_config,
            )

            assert integration.auth_token == "test-token"

    @patch("dativo_ingest.catalog_integration.requests.put")
    def test_push_lineage_success(self, mock_put, sample_asset_definition, sample_job_config):
        """Test successful lineage push."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_response.content = b'{"status": "ok"}'
        mock_put.return_value = mock_response

        config = {"type": "openmetadata", "api_url": "http://localhost:8585/api"}
        integration = OpenMetadataIntegration(
            catalog_config=config,
            asset_definition=sample_asset_definition,
            job_config=sample_job_config,
        )

        source_entities = [{"fqn": "source.table1", "type": "table"}]
        target_entity = {"fqn": "target.table1", "type": "table"}

        result = integration.push_lineage(source_entities, target_entity)

        assert result["status"] == "success"
        assert result["edges_pushed"] == 1
        mock_put.assert_called_once()

    @patch("dativo_ingest.catalog_integration.requests.put")
    def test_push_lineage_error(self, mock_put, sample_asset_definition, sample_job_config):
        """Test lineage push with error."""
        mock_put.side_effect = Exception("Connection error")

        config = {"type": "openmetadata", "api_url": "http://localhost:8585/api"}
        integration = OpenMetadataIntegration(
            catalog_config=config,
            asset_definition=sample_asset_definition,
            job_config=sample_job_config,
        )

        result = integration.push_lineage([{"fqn": "source.table1"}], {"fqn": "target.table1"})

        assert result["status"] == "error"
        assert "error" in result

    @patch("dativo_ingest.catalog_integration.requests.get")
    @patch("dativo_ingest.catalog_integration.requests.put")
    def test_push_metadata_update(self, mock_put, mock_get, sample_asset_definition, sample_job_config):
        """Test metadata push with update."""
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {"id": "entity-123", "tags": []}
        mock_get.return_value = mock_get_response

        mock_put_response = Mock()
        mock_put_response.status_code = 200
        mock_put.return_value = mock_put_response

        config = {"type": "openmetadata", "api_url": "http://localhost:8585/api"}
        integration = OpenMetadataIntegration(
            catalog_config=config,
            asset_definition=sample_asset_definition,
            job_config=sample_job_config,
        )

        entity = {"fqn": "test_domain.test_product.test_table", "type": "table"}
        result = integration.push_metadata(entity)

        assert result["status"] == "success"
        assert result["action"] == "updated"
        mock_get.assert_called_once()
        mock_put.assert_called_once()

    @patch("dativo_ingest.catalog_integration.requests.get")
    @patch("dativo_ingest.catalog_integration.requests.post")
    def test_push_metadata_create(self, mock_post, mock_get, sample_asset_definition, sample_job_config):
        """Test metadata push with create."""
        mock_get_response = Mock()
        mock_get_response.status_code = 404
        mock_get.return_value = mock_get_response

        mock_post_response = Mock()
        mock_post_response.status_code = 201
        mock_post_response.json.return_value = {"id": "entity-456"}
        mock_post.return_value = mock_post_response

        config = {"type": "openmetadata", "api_url": "http://localhost:8585/api"}
        integration = OpenMetadataIntegration(
            catalog_config=config,
            asset_definition=sample_asset_definition,
            job_config=sample_job_config,
        )

        entity = {"fqn": "test_domain.test_product.test_table", "type": "table"}
        result = integration.push_metadata(entity)

        assert result["status"] == "success"
        assert result["action"] == "created"
        mock_get.assert_called_once()
        mock_post.assert_called_once()


class TestAWSGlueIntegration:
    """Test AWS Glue integration."""

    @patch("dativo_ingest.catalog_integration.boto3.client")
    def test_push_lineage_success(self, mock_boto_client, sample_asset_definition, sample_job_config):
        """Test successful lineage push to AWS Glue."""
        mock_glue = Mock()
        mock_glue.get_table.return_value = {
            "Table": {
                "StorageDescriptor": {},
                "Parameters": {},
            }
        }
        mock_boto_client.return_value = mock_glue

        config = {"type": "aws_glue", "region": "us-east-1"}
        integration = AWSGlueIntegration(
            catalog_config=config,
            asset_definition=sample_asset_definition,
            job_config=sample_job_config,
        )

        source_entities = [{"fqn": "source.table1", "table": "table1"}]
        target_entity = {"database": "default", "table": "test_table"}

        result = integration.push_lineage(source_entities, target_entity)

        assert result["status"] == "success"
        mock_glue.get_table.assert_called_once()
        mock_glue.update_table.assert_called_once()

    @patch("dativo_ingest.catalog_integration.boto3.client")
    def test_push_metadata_success(self, mock_boto_client, sample_asset_definition, sample_job_config):
        """Test successful metadata push to AWS Glue."""
        mock_glue = Mock()
        mock_glue.get_table.return_value = {
            "Table": {
                "StorageDescriptor": {},
                "Parameters": {},
            }
        }
        mock_boto_client.return_value = mock_glue

        config = {"type": "aws_glue", "region": "us-east-1"}
        integration = AWSGlueIntegration(
            catalog_config=config,
            asset_definition=sample_asset_definition,
            job_config=sample_job_config,
        )

        entity = {"database": "default", "table": "test_table"}
        result = integration.push_metadata(entity)

        assert result["status"] == "success"
        mock_glue.get_table.assert_called_once()
        mock_glue.update_table.assert_called_once()


class TestDatabricksUnityCatalogIntegration:
    """Test Databricks Unity Catalog integration."""

    def test_init(self, sample_asset_definition, sample_job_config):
        """Test Databricks integration initialization."""
        config = {
            "type": "databricks",
            "workspace_url": "https://test.cloud.databricks.com",
            "token": "test-token",
        }
        integration = DatabricksUnityCatalogIntegration(
            catalog_config=config,
            asset_definition=sample_asset_definition,
            job_config=sample_job_config,
        )

        assert integration.workspace_url == "https://test.cloud.databricks.com"
        assert integration.token == "test-token"

    @patch("dativo_ingest.catalog_integration.requests.post")
    def test_push_lineage_success(self, mock_post, sample_asset_definition, sample_job_config):
        """Test successful lineage push to Databricks."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        config = {
            "type": "databricks",
            "workspace_url": "https://test.cloud.databricks.com",
            "token": "test-token",
        }
        integration = DatabricksUnityCatalogIntegration(
            catalog_config=config,
            asset_definition=sample_asset_definition,
            job_config=sample_job_config,
        )

        source_entities = [{"catalog": "main", "schema": "default", "table": "source1"}]
        target_entity = {"catalog": "main", "schema": "default", "table": "target1"}

        result = integration.push_lineage(source_entities, target_entity)

        assert result["status"] == "success"
        mock_post.assert_called_once()

    @patch("dativo_ingest.catalog_integration.requests.patch")
    def test_push_metadata_success(self, mock_patch, sample_asset_definition, sample_job_config):
        """Test successful metadata push to Databricks."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_patch.return_value = mock_response

        config = {
            "type": "databricks",
            "workspace_url": "https://test.cloud.databricks.com",
            "token": "test-token",
        }
        integration = DatabricksUnityCatalogIntegration(
            catalog_config=config,
            asset_definition=sample_asset_definition,
            job_config=sample_job_config,
        )

        entity = {"catalog": "main", "schema": "default", "table": "test_table"}
        result = integration.push_metadata(entity)

        assert result["status"] == "success"
        mock_patch.assert_called_once()


class TestNessieIntegration:
    """Test Nessie integration."""

    def test_push_lineage(self, sample_asset_definition, sample_job_config):
        """Test Nessie lineage push (handled via table properties)."""
        config = {"type": "nessie"}
        integration = NessieIntegration(
            catalog_config=config,
            asset_definition=sample_asset_definition,
            job_config=sample_job_config,
        )

        result = integration.push_lineage([], {})

        assert result["status"] == "success"
        assert "note" in result

    def test_push_metadata(self, sample_asset_definition, sample_job_config):
        """Test Nessie metadata push (handled via table properties)."""
        config = {"type": "nessie"}
        integration = NessieIntegration(
            catalog_config=config,
            asset_definition=sample_asset_definition,
            job_config=sample_job_config,
        )

        result = integration.push_metadata({})

        assert result["status"] == "success"
        assert "note" in result


class TestCreateCatalogIntegration:
    """Test catalog integration factory function."""

    def test_create_openmetadata(self, sample_asset_definition, sample_job_config):
        """Test creating OpenMetadata integration."""
        config = {"type": "openmetadata"}
        integration = create_catalog_integration(
            catalog_config=config,
            asset_definition=sample_asset_definition,
            job_config=sample_job_config,
        )

        assert isinstance(integration, OpenMetadataIntegration)

    def test_create_aws_glue(self, sample_asset_definition, sample_job_config):
        """Test creating AWS Glue integration."""
        config = {"type": "aws_glue"}
        integration = create_catalog_integration(
            catalog_config=config,
            asset_definition=sample_asset_definition,
            job_config=sample_job_config,
        )

        assert isinstance(integration, AWSGlueIntegration)

    def test_create_databricks(self, sample_asset_definition, sample_job_config):
        """Test creating Databricks integration."""
        config = {"type": "databricks"}
        integration = create_catalog_integration(
            catalog_config=config,
            asset_definition=sample_asset_definition,
            job_config=sample_job_config,
        )

        assert isinstance(integration, DatabricksUnityCatalogIntegration)

    def test_create_nessie(self, sample_asset_definition, sample_job_config):
        """Test creating Nessie integration."""
        config = {"type": "nessie"}
        integration = create_catalog_integration(
            catalog_config=config,
            asset_definition=sample_asset_definition,
            job_config=sample_job_config,
        )

        assert isinstance(integration, NessieIntegration)

    def test_create_unsupported(self, sample_asset_definition, sample_job_config):
        """Test creating unsupported catalog type."""
        config = {"type": "unsupported"}
        integration = create_catalog_integration(
            catalog_config=config,
            asset_definition=sample_asset_definition,
            job_config=sample_job_config,
        )

        assert integration is None
