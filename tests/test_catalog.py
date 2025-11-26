"""Tests for catalog integration."""

import os
from unittest.mock import MagicMock, Mock, patch

import pytest

from dativo_ingest.catalog import CatalogFactory
from dativo_ingest.config import AssetDefinition, CatalogConfig, JobConfig, TargetConfig


@pytest.fixture
def sample_asset_definition():
    """Create a sample asset definition for testing."""
    return AssetDefinition(
        name="test_table",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[{"name": "id", "type": "string", "required": True}],
        team={"owner": "test@example.com"},
        domain="test_domain",
        dataProduct="test_product",
        tags=["test_tag"],
    )


@pytest.fixture
def sample_job_config(sample_asset_definition):
    """Create a sample job config for testing."""
    return JobConfig(
        tenant_id="test_tenant",
        source_connector_path="connectors/csv.yaml",
        target_connector_path="connectors/iceberg.yaml",
        asset_path="assets/test.yaml",
        source={"type": "csv", "files": [{"path": "test.csv", "object": "test"}]},
        target={
            "type": "iceberg",
            "connection": {
                "s3": {
                    "bucket": "test-bucket",
                    "endpoint": "http://localhost:9000",
                }
            },
        },
    )


class TestCatalogConfig:
    """Test CatalogConfig model."""

    def test_catalog_config_creation(self):
        """Test creating a catalog config."""
        config = CatalogConfig(
            type="openmetadata",
            connection={"api_url": "http://localhost:8585/api", "auth_token": "test-token"},
            database="test_db",
        )
        assert config.type == "openmetadata"
        assert config.database == "test_db"
        assert config.push_lineage is True
        assert config.push_metadata is True

    def test_catalog_config_defaults(self):
        """Test catalog config defaults."""
        config = CatalogConfig(
            type="aws_glue",
            connection={"region": "us-east-1"},
        )
        assert config.push_lineage is True
        assert config.push_metadata is True
        assert config.database is None


class TestCatalogFactory:
    """Test CatalogFactory."""

    def test_create_openmetadata_catalog(self, sample_asset_definition, sample_job_config):
        """Test creating OpenMetadata catalog."""
        catalog_config = CatalogConfig(
            type="openmetadata",
            connection={"api_url": "http://localhost:8585/api", "auth_token": "test-token"},
        )
        catalog = CatalogFactory.create(catalog_config, sample_asset_definition, sample_job_config)
        assert catalog.__class__.__name__ == "OpenMetadataCatalog"

    def test_create_aws_glue_catalog(self, sample_asset_definition, sample_job_config):
        """Test creating AWS Glue catalog."""
        catalog_config = CatalogConfig(
            type="aws_glue",
            connection={"region": "us-east-1"},
        )
        with patch("dativo_ingest.catalog.aws_glue.boto3"):
            catalog = CatalogFactory.create(
                catalog_config, sample_asset_definition, sample_job_config
            )
            assert catalog.__class__.__name__ == "AWSGlueCatalog"

    def test_create_databricks_unity_catalog(self, sample_asset_definition, sample_job_config):
        """Test creating Databricks Unity Catalog."""
        catalog_config = CatalogConfig(
            type="databricks_unity",
            connection={"workspace_url": "https://test.databricks.com", "access_token": "token"},
        )
        catalog = CatalogFactory.create(catalog_config, sample_asset_definition, sample_job_config)
        assert catalog.__class__.__name__ == "DatabricksUnityCatalog"

    def test_create_nessie_catalog(self, sample_asset_definition, sample_job_config):
        """Test creating Nessie catalog."""
        catalog_config = CatalogConfig(
            type="nessie",
            connection={"uri": "http://localhost:19120"},
        )
        catalog = CatalogFactory.create(catalog_config, sample_asset_definition, sample_job_config)
        assert catalog.__class__.__name__ == "NessieCatalog"

    def test_create_unsupported_catalog(self, sample_asset_definition, sample_job_config):
        """Test creating unsupported catalog type."""
        catalog_config = CatalogConfig(
            type="unsupported",
            connection={},
        )
        with pytest.raises(ValueError, match="Unsupported catalog type"):
            CatalogFactory.create(catalog_config, sample_asset_definition, sample_job_config)


class TestOpenMetadataCatalog:
    """Test OpenMetadata catalog integration."""

    @pytest.fixture
    def openmetadata_catalog(self, sample_asset_definition, sample_job_config):
        """Create OpenMetadata catalog instance."""
        catalog_config = CatalogConfig(
            type="openmetadata",
            connection={"api_url": "http://localhost:8585/api", "auth_token": "test-token"},
            database="test_db",
        )
        return CatalogFactory.create(catalog_config, sample_asset_definition, sample_job_config)

    def test_extract_source_entities(self, openmetadata_catalog):
        """Test extracting source entities."""
        entities = openmetadata_catalog._extract_source_entities()
        assert len(entities) > 0
        assert entities[0]["type"] == "file"

    def test_extract_target_entity(self, openmetadata_catalog):
        """Test extracting target entity."""
        entity = openmetadata_catalog._extract_target_entity()
        assert entity["name"] == "test_table"
        assert entity["type"] == "table"
        assert "s3://" in entity["location"]

    def test_extract_tags(self, openmetadata_catalog):
        """Test extracting tags."""
        tags = openmetadata_catalog._extract_tags()
        assert "test_tag" in tags
        assert "domain:test_domain" in tags
        assert "source-type:csv" in tags

    def test_extract_owners(self, openmetadata_catalog):
        """Test extracting owners."""
        owners = openmetadata_catalog._extract_owners()
        assert "test@example.com" in owners

    def test_extract_description(self, openmetadata_catalog, sample_asset_definition):
        """Test extracting description."""
        sample_asset_definition.description = {
            "purpose": "Test purpose",
            "usage": "Test usage",
        }
        description = openmetadata_catalog._extract_description()
        assert "Test purpose" in description
        assert "Test usage" in description

    @patch("dativo_ingest.catalog.openmetadata.requests")
    def test_ensure_entity_exists(self, mock_requests, openmetadata_catalog):
        """Test ensuring entity exists."""
        # Mock service creation
        mock_requests.get.return_value.status_code = 200
        mock_requests.get.return_value.json.return_value = {"fullyQualifiedName": "test-service"}

        # Mock table creation
        mock_requests.post.return_value.status_code = 201
        mock_requests.post.return_value.json.return_value = {"id": "test-id", "fqn": "test.fqn"}

        entity = {"name": "test_table", "database": "test_db", "location": "s3://bucket/table"}
        result = openmetadata_catalog.ensure_entity_exists(entity)
        assert "fqn" in result or "name" in result

    @patch("dativo_ingest.catalog.openmetadata.requests")
    def test_push_metadata(self, mock_requests, openmetadata_catalog):
        """Test pushing metadata."""
        # Mock table get
        mock_requests.get.return_value.status_code = 200
        mock_requests.get.return_value.json.return_value = {"id": "test-id"}

        # Mock patch
        mock_requests.patch.return_value.status_code = 200

        entity = {"name": "test_table", "database": "test_db"}
        result = openmetadata_catalog.push_metadata(
            entity, tags=["tag1"], owners=["owner@example.com"], description="Test description"
        )
        assert result["status"] in ["success", "partial"]

    @patch("dativo_ingest.catalog.openmetadata.requests")
    def test_push_lineage(self, mock_requests, openmetadata_catalog):
        """Test pushing lineage."""
        # Mock service creation
        mock_requests.get.return_value.status_code = 200
        mock_requests.get.return_value.json.return_value = {"fullyQualifiedName": "test-service"}

        # Mock lineage push
        mock_requests.put.return_value.status_code = 200

        source_entities = [{"name": "source1", "type": "file"}]
        target_entity = {"name": "test_table", "database": "test_db"}
        result = openmetadata_catalog.push_lineage(source_entities, target_entity)
        assert result["status"] in ["success", "partial"]


class TestAWSGlueCatalog:
    """Test AWS Glue catalog integration."""

    @pytest.fixture
    def aws_glue_catalog(self, sample_asset_definition, sample_job_config):
        """Create AWS Glue catalog instance."""
        catalog_config = CatalogConfig(
            type="aws_glue",
            connection={"region": "us-east-1"},
            database="test_db",
        )
        with patch("dativo_ingest.catalog.aws_glue.boto3"):
            return CatalogFactory.create(catalog_config, sample_asset_definition, sample_job_config)

    @patch("dativo_ingest.catalog.aws_glue.boto3")
    def test_ensure_entity_exists(self, mock_boto3, sample_asset_definition, sample_job_config):
        """Test ensuring entity exists in Glue."""
        catalog_config = CatalogConfig(
            type="aws_glue",
            connection={"region": "us-east-1"},
            database="test_db",
        )
        catalog = CatalogFactory.create(catalog_config, sample_asset_definition, sample_job_config)

        # Mock Glue client
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.get_database.side_effect = Exception("NotFound")
        mock_client.get_table.side_effect = Exception("NotFound")
        mock_client.create_database.return_value = {}
        mock_client.create_table.return_value = {}

        entity = {"name": "test_table", "database": "test_db", "location": "s3://bucket/table"}
        result = catalog.ensure_entity_exists(entity)
        assert "table" in result


class TestNessieCatalog:
    """Test Nessie catalog integration."""

    @pytest.fixture
    def nessie_catalog(self, sample_asset_definition, sample_job_config):
        """Create Nessie catalog instance."""
        catalog_config = CatalogConfig(
            type="nessie",
            connection={"uri": "http://localhost:19120"},
            database="test_db",
        )
        return CatalogFactory.create(catalog_config, sample_asset_definition, sample_job_config)

    def test_push_lineage(self, nessie_catalog):
        """Test pushing lineage to Nessie."""
        source_entities = [{"name": "source1", "location": "s3://bucket/source"}]
        target_entity = {"name": "test_table", "location": "s3://bucket/target"}
        result = nessie_catalog.push_lineage(source_entities, target_entity)
        assert result["status"] == "success"
        assert "lineage_info" in result


class TestCatalogIntegration:
    """Integration tests for catalog functionality."""

    @pytest.mark.integration
    def test_catalog_in_job_config(self, tmp_path, sample_asset_definition):
        """Test catalog configuration in job config."""
        job_yaml = """
tenant_id: test_tenant
source_connector_path: connectors/csv.yaml
target_connector_path: connectors/iceberg.yaml
asset_path: assets/test.yaml
source:
  type: csv
  files:
    - path: test.csv
target:
  type: iceberg
  connection:
    s3:
      bucket: test-bucket
catalog:
  type: openmetadata
  connection:
    api_url: http://localhost:8585/api
    auth_token: test-token
  database: test_db
  push_lineage: true
  push_metadata: true
"""
        job_file = tmp_path / "test_job.yaml"
        job_file.write_text(job_yaml)

        job_config = JobConfig.from_yaml(job_file, validate_schema=False)
        assert job_config.catalog is not None
        assert job_config.catalog.type == "openmetadata"
        assert job_config.catalog.database == "test_db"
        assert job_config.catalog.push_lineage is True
        assert job_config.catalog.push_metadata is True
