"""Tests for data catalog integrations."""

import json
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests

from dativo_ingest.catalog.aws_glue import AWSGlueCatalog
from dativo_ingest.catalog.base import CatalogLineage, CatalogMetadata
from dativo_ingest.catalog.databricks_unity import DatabricksUnityCatalog
from dativo_ingest.catalog.factory import CatalogFactory
from dativo_ingest.catalog.nessie import NessieCatalog
from dativo_ingest.catalog.openmetadata import OpenMetadataCatalog


class TestCatalogFactory:
    """Tests for CatalogFactory."""

    def test_create_aws_glue(self):
        """Test creating AWS Glue catalog."""
        connection = {"region": "us-east-1"}
        catalog = CatalogFactory.create("aws_glue", connection)
        assert isinstance(catalog, AWSGlueCatalog)

    def test_create_databricks_unity(self):
        """Test creating Databricks Unity Catalog."""
        connection = {
            "workspace_url": "https://workspace.cloud.databricks.com",
            "access_token": "token",
        }
        catalog = CatalogFactory.create("databricks_unity", connection)
        assert isinstance(catalog, DatabricksUnityCatalog)

    def test_create_nessie(self):
        """Test creating Nessie catalog."""
        connection = {"uri": "http://localhost:19120/api/v1"}
        catalog = CatalogFactory.create("nessie", connection)
        assert isinstance(catalog, NessieCatalog)

    def test_create_openmetadata(self):
        """Test creating OpenMetadata catalog."""
        connection = {
            "api_endpoint": "http://localhost:8585/api",
            "auth_provider": "basic",
            "username": "admin",
            "password": "admin",
        }
        catalog = CatalogFactory.create("openmetadata", connection)
        assert isinstance(catalog, OpenMetadataCatalog)

    def test_create_unsupported_type(self):
        """Test creating unsupported catalog type raises error."""
        with pytest.raises(ValueError, match="Unsupported catalog type"):
            CatalogFactory.create("unsupported", {})


class TestAWSGlueCatalog:
    """Tests for AWS Glue catalog integration."""

    @patch("dativo_ingest.catalog.aws_glue.boto3.client")
    def test_table_exists_true(self, mock_boto_client):
        """Test checking if table exists returns True."""
        mock_client = Mock()
        mock_client.get_table.return_value = {"Table": {"Name": "test_table"}}
        mock_boto_client.return_value = mock_client

        catalog = AWSGlueCatalog({"region": "us-east-1"})
        catalog.glue_client = mock_client

        assert catalog.table_exists("test_table") is True

    @patch("dativo_ingest.catalog.aws_glue.boto3.client")
    def test_table_exists_false(self, mock_boto_client):
        """Test checking if table exists returns False."""
        from botocore.exceptions import ClientError

        mock_client = Mock()
        error = ClientError(
            {"Error": {"Code": "EntityNotFoundException"}}, "get_table"
        )
        mock_client.get_table.side_effect = error
        mock_boto_client.return_value = mock_client

        catalog = AWSGlueCatalog({"region": "us-east-1"})
        catalog.glue_client = mock_client

        assert catalog.table_exists("test_table") is False

    @patch("dativo_ingest.catalog.aws_glue.boto3.client")
    def test_push_metadata(self, mock_boto_client):
        """Test pushing metadata to AWS Glue."""
        mock_client = Mock()
        mock_client.get_table.return_value = {
            "Table": {
                "Name": "test_table",
                "Description": "old description",
                "Parameters": {},
            }
        }
        mock_boto_client.return_value = mock_client

        catalog = AWSGlueCatalog({"region": "us-east-1"}, database="test_db")
        catalog.glue_client = mock_client

        metadata = CatalogMetadata(
            name="test_table",
            description="test description",
            tags=["tag1", "tag2"],
            custom_properties={"key": "value"},
        )

        catalog.push_metadata("test_table", metadata)

        mock_client.update_table.assert_called_once()
        call_args = mock_client.update_table.call_args
        assert call_args[1]["DatabaseName"] == "test_db"
        assert call_args[1]["TableInput"]["Description"] == "test description"

    @patch("dativo_ingest.catalog.aws_glue.boto3.client")
    def test_push_lineage(self, mock_boto_client):
        """Test pushing lineage to AWS Glue."""
        mock_client = Mock()
        mock_client.get_table.return_value = {
            "Table": {"Name": "test_table", "Parameters": {}}
        }
        mock_boto_client.return_value = mock_client

        catalog = AWSGlueCatalog({"region": "us-east-1"}, database="test_db")
        catalog.glue_client = mock_client

        lineage = CatalogLineage(
            source_entities=[{"database": "source_db", "table": "source_table"}],
            target_entity={"database": "test_db", "table": "test_table"},
            process_name="test_process",
        )

        catalog.push_lineage(lineage)

        mock_client.update_table.assert_called_once()
        call_args = mock_client.update_table.call_args
        params = call_args[1]["TableInput"]["Parameters"]
        assert "lineage" in params
        lineage_data = json.loads(params["lineage"])
        assert lineage_data["process_name"] == "test_process"


class TestOpenMetadataCatalog:
    """Tests for OpenMetadata catalog integration."""

    @patch("dativo_ingest.catalog.openmetadata.requests.Session")
    def test_table_exists_true(self, mock_session_class):
        """Test checking if table exists returns True."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        catalog = OpenMetadataCatalog(
            {
                "api_endpoint": "http://localhost:8585/api",
                "auth_provider": "basic",
            }
        )
        catalog._session = mock_session

        assert catalog.table_exists("test_table") is True

    @patch("dativo_ingest.catalog.openmetadata.requests.Session")
    def test_table_exists_false(self, mock_session_class):
        """Test checking if table exists returns False."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 404
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        catalog = OpenMetadataCatalog(
            {
                "api_endpoint": "http://localhost:8585/api",
                "auth_provider": "basic",
            }
        )
        catalog._session = mock_session

        assert catalog.table_exists("test_table") is False

    @patch("dativo_ingest.catalog.openmetadata.requests.Session")
    def test_push_metadata(self, mock_session_class):
        """Test pushing metadata to OpenMetadata."""
        mock_session = Mock()
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {"id": "table-id"}
        mock_patch_response = Mock()
        mock_patch_response.status_code = 200
        mock_session.get.return_value = mock_get_response
        mock_session.patch.return_value = mock_patch_response
        mock_session_class.return_value = mock_session

        catalog = OpenMetadataCatalog(
            {
                "api_endpoint": "http://localhost:8585/api",
                "auth_provider": "basic",
            }
        )
        catalog._session = mock_session

        metadata = CatalogMetadata(
            name="test_table",
            description="test description",
            tags=["tag1"],
            owners=["owner1"],
        )

        catalog.push_metadata("test_table", metadata)

        mock_session.patch.assert_called_once()
        call_args = mock_session.patch.call_args
        assert "description" in call_args[1]["json"]

    @patch("dativo_ingest.catalog.openmetadata.requests.Session")
    def test_push_lineage(self, mock_session_class):
        """Test pushing lineage to OpenMetadata."""
        mock_session = Mock()
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {"id": "pipeline-id"}
        mock_post_response = Mock()
        mock_post_response.status_code = 200
        mock_put_response = Mock()
        mock_put_response.status_code = 200
        mock_session.get.return_value = mock_get_response
        mock_session.post.return_value = mock_post_response
        mock_session.put.return_value = mock_put_response
        mock_session_class.return_value = mock_session

        catalog = OpenMetadataCatalog(
            {
                "api_endpoint": "http://localhost:8585/api",
                "auth_provider": "basic",
            }
        )
        catalog._session = mock_session

        lineage = CatalogLineage(
            source_entities=[{"database": "source_db", "table": "source_table"}],
            target_entity={"database": "target_db", "table": "target_table"},
            process_name="test_process",
        )

        catalog.push_lineage(lineage)

        # Check that lineage was pushed
        assert mock_session.put.called


class TestDatabricksUnityCatalog:
    """Tests for Databricks Unity Catalog integration."""

    @patch("dativo_ingest.catalog.databricks_unity.requests.get")
    def test_table_exists_true(self, mock_get):
        """Test checking if table exists returns True."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        catalog = DatabricksUnityCatalog(
            {
                "workspace_url": "https://workspace.cloud.databricks.com",
                "access_token": "token",
            }
        )

        assert catalog.table_exists("test_table") is True

    @patch("dativo_ingest.catalog.databricks_unity.requests.get")
    def test_table_exists_false(self, mock_get):
        """Test checking if table exists returns False."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        catalog = DatabricksUnityCatalog(
            {
                "workspace_url": "https://workspace.cloud.databricks.com",
                "access_token": "token",
            }
        )

        assert catalog.table_exists("test_table") is False

    @patch("dativo_ingest.catalog.databricks_unity.requests.get")
    @patch("dativo_ingest.catalog.databricks_unity.requests.patch")
    def test_push_metadata(self, mock_patch, mock_get):
        """Test pushing metadata to Databricks Unity Catalog."""
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {"properties": {}}
        mock_get.return_value = mock_get_response

        mock_patch_response = Mock()
        mock_patch_response.status_code = 200
        mock_patch.return_value = mock_patch_response

        catalog = DatabricksUnityCatalog(
            {
                "workspace_url": "https://workspace.cloud.databricks.com",
                "access_token": "token",
            }
        )

        metadata = CatalogMetadata(
            name="test_table",
            description="test description",
            tags=["tag1"],
        )

        catalog.push_metadata("test_table", metadata)

        mock_patch.assert_called_once()


class TestNessieCatalog:
    """Tests for Nessie catalog integration."""

    @patch("dativo_ingest.catalog.nessie.NessieClient")
    def test_table_exists_true(self, mock_client_class):
        """Test checking if table exists returns True."""
        mock_client = Mock()
        mock_client.get_content.return_value = Mock()
        mock_client_class.return_value = mock_client

        catalog = NessieCatalog({"uri": "http://localhost:19120/api/v1"})
        catalog.client = mock_client

        assert catalog.table_exists("test_table") is True

    @patch("dativo_ingest.catalog.nessie.NessieClient")
    def test_table_exists_false(self, mock_client_class):
        """Test checking if table exists returns False."""
        mock_client = Mock()
        mock_client.get_content.side_effect = Exception("Not found")
        mock_client_class.return_value = mock_client

        catalog = NessieCatalog({"uri": "http://localhost:19120/api/v1"})
        catalog.client = mock_client

        assert catalog.table_exists("test_table") is False


class TestCatalogIntegration:
    """Integration tests for catalog functionality."""

    @patch("dativo_ingest.catalog.integration.CatalogFactory")
    def test_push_to_catalog_with_metadata(self, mock_factory):
        """Test pushing metadata to catalog."""
        from dativo_ingest.catalog.integration import push_to_catalog
        from dativo_ingest.config import AssetDefinition, JobConfig, SourceConfig, TargetConfig

        # Mock catalog
        mock_catalog = Mock()
        mock_factory.create.return_value = mock_catalog

        # Create job config with catalog
        job_config = Mock(spec=JobConfig)
        job_config.catalog = Mock()
        job_config.catalog.type = "openmetadata"
        job_config.catalog.connection = {"api_endpoint": "http://localhost:8585/api"}
        job_config.catalog.database = "test_db"
        job_config.catalog.table_name = None
        job_config.tenant_id = "test_tenant"
        job_config.environment = "test"

        # Create asset definition
        asset_definition = Mock(spec=AssetDefinition)
        asset_definition.name = "test_asset"
        asset_definition.description = Mock()
        asset_definition.description.purpose = "test purpose"
        asset_definition.tags = ["tag1", "tag2"]
        asset_definition.team = Mock()
        asset_definition.team.owner = "owner1"
        asset_definition.schema = [{"name": "col1", "type": "string"}]
        asset_definition.compliance = None
        asset_definition.finops = None
        asset_definition.domain = "test_domain"
        asset_definition.dataProduct = "test_product"
        asset_definition.source_type = "postgres"

        source_config = Mock(spec=SourceConfig)
        target_config = Mock(spec=TargetConfig)

        push_to_catalog(
            job_config=job_config,
            asset_definition=asset_definition,
            source_config=source_config,
            target_config=target_config,
            output_location="s3://bucket/path",
        )

        # Verify catalog.push_metadata was called
        assert mock_catalog.push_metadata.called
        call_args = mock_catalog.push_metadata.call_args
        assert call_args[0][0] == "test_asset"  # table_name
        assert call_args[0][2] == "s3://bucket/path"  # location

    @patch("dativo_ingest.catalog.integration.CatalogFactory")
    def test_push_to_catalog_with_lineage(self, mock_factory):
        """Test pushing lineage to catalog."""
        from dativo_ingest.catalog.integration import push_to_catalog
        from dativo_ingest.config import AssetDefinition, JobConfig, SourceConfig, TargetConfig

        # Mock catalog
        mock_catalog = Mock()
        mock_factory.create.return_value = mock_catalog

        # Create job config with catalog
        job_config = Mock(spec=JobConfig)
        job_config.catalog = Mock()
        job_config.catalog.type = "openmetadata"
        job_config.catalog.connection = {"api_endpoint": "http://localhost:8585/api"}
        job_config.catalog.database = "test_db"
        job_config.catalog.table_name = None
        job_config.tenant_id = "test_tenant"
        job_config.environment = "test"

        # Create asset definition
        asset_definition = Mock(spec=AssetDefinition)
        asset_definition.name = "test_asset"
        asset_definition.description = None
        asset_definition.tags = []
        asset_definition.team = None
        asset_definition.schema = []
        asset_definition.compliance = None
        asset_definition.finops = None
        asset_definition.domain = None
        asset_definition.dataProduct = None
        asset_definition.source_type = "postgres"

        source_config = Mock(spec=SourceConfig)
        target_config = Mock(spec=TargetConfig)

        source_entities = [
            {"database": "source_db", "table": "source_table"}
        ]

        push_to_catalog(
            job_config=job_config,
            asset_definition=asset_definition,
            source_config=source_config,
            target_config=target_config,
            output_location="s3://bucket/path",
            source_entities=source_entities,
        )

        # Verify catalog.push_lineage was called
        assert mock_catalog.push_lineage.called
