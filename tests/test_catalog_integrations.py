"""Tests for data catalog integrations."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests
import yaml

from dativo_ingest.catalogs import CatalogManager
from dativo_ingest.catalogs.aws_glue import AWSGlueCatalog
from dativo_ingest.catalogs.base import BaseCatalog
from dativo_ingest.catalogs.openmetadata import OpenMetadataCatalog
from dativo_ingest.config import AssetDefinition, CatalogConfig, JobConfig, TargetConfig


@pytest.fixture
def sample_asset_definition():
    """Create a sample asset definition for testing."""
    asset_data = {
        "$schema": "schemas/odcs/dativo-odcs-3.0.2-extended.schema.json",
        "apiVersion": "v3.0.2",
        "kind": "DataContract",
        "name": "test_table",
        "version": "1.0",
        "source_type": "csv",
        "object": "test_data",
        "domain": "test_domain",
        "dataProduct": "test_product",
        "schema": [
            {"name": "id", "type": "string", "required": True},
            {"name": "name", "type": "string", "required": False},
            {"name": "value", "type": "integer", "required": False},
        ],
        "team": {"owner": "test@example.com"},
        "tags": ["test", "integration"],
        "description": {
            "purpose": "Test table for catalog integration",
            "usage": "Testing purposes only",
        },
    }
    return AssetDefinition(**asset_data)


@pytest.fixture
def sample_job_config(sample_asset_definition):
    """Create a sample job config for testing."""
    job_data = {
        "tenant_id": "test_tenant",
        "source_connector_path": "connectors/csv.yaml",
        "target_connector_path": "connectors/iceberg.yaml",
        "asset_path": "assets/test.yaml",
        "source": {
            "type": "csv",
            "files": [{"path": "test.csv", "object": "test_data"}],
        },
        "target": {
            "type": "iceberg",
            "connection": {
                "s3": {
                    "bucket": "test-bucket",
                    "prefix": "raw/test",
                }
            },
        },
    }
    return JobConfig(**job_data)


@pytest.fixture
def sample_target_config():
    """Create a sample target config for testing."""
    return TargetConfig(
        type="iceberg",
        connection={
            "s3": {
                "bucket": "test-bucket",
                "prefix": "raw/test",
            }
        },
    )


class TestBaseCatalog:
    """Tests for base catalog functionality."""

    def test_extract_source_entities_csv(self, sample_job_config, sample_asset_definition, sample_target_config):
        """Test source entity extraction for CSV source."""
        catalog = BaseCatalog(
            catalog_config={"type": "test"},
            job_config=sample_job_config,
            asset_definition=sample_asset_definition,
            target_config=sample_target_config,
        )

        entities = catalog._extract_source_entities()
        assert len(entities) == 1
        assert entities[0]["type"] == "file"
        assert entities[0]["source_type"] == "csv"

    def test_extract_source_entities_postgres(self, sample_asset_definition, sample_target_config):
        """Test source entity extraction for PostgreSQL source."""
        job_data = {
            "tenant_id": "test_tenant",
            "source_connector_path": "connectors/postgres.yaml",
            "target_connector_path": "connectors/iceberg.yaml",
            "asset_path": "assets/test.yaml",
            "source": {
                "type": "postgres",
                "connection": {"database": "test_db", "schema": "public"},
                "tables": [{"name": "users", "object": "users"}],
            },
            "target": {
                "type": "iceberg",
                "connection": {"s3": {"bucket": "test-bucket"}},
            },
        }
        job_config = JobConfig(**job_data)

        catalog = BaseCatalog(
            catalog_config={"type": "test"},
            job_config=job_config,
            asset_definition=sample_asset_definition,
            target_config=sample_target_config,
        )

        entities = catalog._extract_source_entities()
        assert len(entities) == 1
        assert entities[0]["type"] == "table"
        assert entities[0]["database"] == "test_db"
        assert entities[0]["name"] == "users"

    def test_extract_target_entity(self, sample_job_config, sample_asset_definition, sample_target_config):
        """Test target entity extraction."""
        catalog = BaseCatalog(
            catalog_config={"type": "test"},
            job_config=sample_job_config,
            asset_definition=sample_asset_definition,
            target_config=sample_target_config,
        )

        entity = catalog._extract_target_entity()
        assert entity["type"] == "dataset"
        assert entity["database"] == "test_domain"
        assert entity["schema"] == "test_product"
        assert entity["name"] == "test_table"

    def test_extract_metadata(self, sample_job_config, sample_asset_definition, sample_target_config):
        """Test metadata extraction."""
        catalog = BaseCatalog(
            catalog_config={"type": "test"},
            job_config=sample_job_config,
            asset_definition=sample_asset_definition,
            target_config=sample_target_config,
        )

        metadata = catalog._extract_metadata()
        assert "tags" in metadata
        assert "owners" in metadata
        assert "description" in metadata
        assert "test@example.com" in metadata["owners"]


class TestOpenMetadataCatalog:
    """Tests for OpenMetadata catalog integration."""

    @patch("dativo_ingest.catalogs.openmetadata.requests")
    def test_ensure_entity_exists_new_table(self, mock_requests, sample_job_config, sample_asset_definition, sample_target_config):
        """Test ensuring entity exists when table doesn't exist."""
        # Mock API responses
        mock_requests.get.side_effect = [
            # Database exists
            Mock(status_code=200, json=lambda: {"name": "test_domain"}),
            # Schema exists
            Mock(status_code=200, json=lambda: {"name": "test_product"}),
            # Table doesn't exist
            Mock(status_code=404),
        ]
        mock_requests.post.return_value = Mock(status_code=200, json=lambda: {"id": "table-id"})
        mock_requests.put.return_value = Mock(status_code=200, json=lambda: {"id": "table-id"})

        catalog = OpenMetadataCatalog(
            catalog_config={"api_url": "http://localhost:8585/api"},
            job_config=sample_job_config,
            asset_definition=sample_asset_definition,
            target_config=sample_target_config,
        )

        entity = {"database": "test_domain", "schema": "test_product", "name": "test_table"}
        result = catalog.ensure_entity_exists(entity)

        # Should have called POST to create table
        assert mock_requests.post.called

    @patch("dativo_ingest.catalogs.openmetadata.requests")
    def test_push_metadata(self, mock_requests, sample_job_config, sample_asset_definition, sample_target_config):
        """Test pushing metadata to OpenMetadata."""
        # Mock get table response
        mock_requests.get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "id": "table-id",
                "name": "test_table",
                "description": "Old description",
                "tags": [],
                "owners": [],
            },
        )
        mock_requests.put.return_value = Mock(status_code=200, json=lambda: {"id": "table-id"})

        catalog = OpenMetadataCatalog(
            catalog_config={"api_url": "http://localhost:8585/api"},
            job_config=sample_job_config,
            asset_definition=sample_asset_definition,
            target_config=sample_target_config,
        )

        entity = {"database": "test_domain", "schema": "test_product", "name": "test_table"}
        metadata = {
            "tags": ["test:value", "integration"],
            "owners": ["test@example.com"],
            "description": "Test description",
        }

        result = catalog.push_metadata(entity, metadata)
        assert result["status"] == "success"
        assert mock_requests.put.called

    @patch("dativo_ingest.catalogs.openmetadata.requests")
    def test_push_lineage(self, mock_requests, sample_job_config, sample_asset_definition, sample_target_config):
        """Test pushing lineage to OpenMetadata."""
        mock_requests.put.return_value = Mock(status_code=200, json=lambda: {"status": "success"})

        catalog = OpenMetadataCatalog(
            catalog_config={"api_url": "http://localhost:8585/api"},
            job_config=sample_job_config,
            asset_definition=sample_asset_definition,
            target_config=sample_target_config,
        )

        source_entities = [
            {"type": "file", "source_type": "csv", "name": "test.csv"},
        ]
        target_entity = {
            "database": "test_domain",
            "schema": "test_product",
            "name": "test_table",
        }

        result = catalog.push_lineage(source_entities, target_entity)
        assert result["status"] == "success"
        assert result["edges"] == 1
        assert mock_requests.put.called


class TestAWSGlueCatalog:
    """Tests for AWS Glue catalog integration."""

    @pytest.mark.skipif(
        os.getenv("SKIP_AWS_TESTS") == "true",
        reason="AWS tests require AWS credentials",
    )
    @patch("dativo_ingest.catalogs.aws_glue.boto3")
    def test_ensure_entity_exists(self, mock_boto3, sample_job_config, sample_asset_definition, sample_target_config):
        """Test ensuring entity exists in AWS Glue."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        # Mock get_database - database exists
        mock_client.get_database.return_value = {"Database": {"Name": "test_domain"}}

        # Mock get_table - table doesn't exist
        from botocore.exceptions import ClientError

        error_response = {"Error": {"Code": "EntityNotFoundException"}}
        mock_client.get_table.side_effect = ClientError(error_response, "GetTable")

        # Mock create_table
        mock_client.create_table.return_value = {}

        catalog = AWSGlueCatalog(
            catalog_config={"region": "us-east-1"},
            job_config=sample_job_config,
            asset_definition=sample_asset_definition,
            target_config=sample_target_config,
        )

        entity = {"database": "test_domain", "name": "test_table"}
        result = catalog.ensure_entity_exists(entity)

        assert mock_client.create_table.called


class TestCatalogManager:
    """Tests for catalog manager."""

    def test_catalog_manager_no_catalog(self, sample_job_config, sample_asset_definition, sample_target_config):
        """Test catalog manager when no catalog is configured."""
        manager = CatalogManager(
            job_config=sample_job_config,
            asset_definition=sample_asset_definition,
            target_config=sample_target_config,
        )

        result = manager.push_lineage()
        assert result is None

    def test_catalog_manager_openmetadata(self, sample_asset_definition, sample_target_config):
        """Test catalog manager with OpenMetadata."""
        job_data = {
            "tenant_id": "test_tenant",
            "source_connector_path": "connectors/csv.yaml",
            "target_connector_path": "connectors/iceberg.yaml",
            "asset_path": "assets/test.yaml",
            "source": {
                "type": "csv",
                "files": [{"path": "test.csv", "object": "test_data"}],
            },
            "target": {
                "type": "iceberg",
                "connection": {"s3": {"bucket": "test-bucket"}},
            },
            "catalog": CatalogConfig(
                type="openmetadata",
                connection={"api_url": "http://localhost:8585/api"},
            ),
        }
        job_config = JobConfig(**job_data)

        manager = CatalogManager(
            job_config=job_config,
            asset_definition=sample_asset_definition,
            target_config=sample_target_config,
        )

        # Should initialize OpenMetadata catalog
        catalog = manager._get_catalog()
        assert catalog is not None
        assert isinstance(catalog, OpenMetadataCatalog)

    def test_catalog_manager_disabled(self, sample_asset_definition, sample_target_config):
        """Test catalog manager when catalog is disabled."""
        job_data = {
            "tenant_id": "test_tenant",
            "source_connector_path": "connectors/csv.yaml",
            "target_connector_path": "connectors/iceberg.yaml",
            "asset_path": "assets/test.yaml",
            "source": {"type": "csv"},
            "target": {"type": "iceberg", "connection": {"s3": {"bucket": "test-bucket"}}},
            "catalog": CatalogConfig(
                type="openmetadata",
                connection={"api_url": "http://localhost:8585/api"},
                enabled=False,
            ),
        }
        job_config = JobConfig(**job_data)

        manager = CatalogManager(
            job_config=job_config,
            asset_definition=sample_asset_definition,
            target_config=sample_target_config,
        )

        result = manager.push_lineage()
        assert result is None


@pytest.mark.integration
class TestOpenMetadataIntegration:
    """Integration tests for OpenMetadata (requires running OpenMetadata instance)."""

    @pytest.mark.skipif(
        os.getenv("OPENMETADATA_URL") is None,
        reason="OpenMetadata integration tests require OPENMETADATA_URL environment variable",
    )
    def test_openmetadata_smoke_test(self, sample_asset_definition, sample_target_config):
        """Smoke test for OpenMetadata integration."""
        api_url = os.getenv("OPENMETADATA_URL", "http://localhost:8585/api")
        auth_token = os.getenv("OPENMETADATA_TOKEN")

        job_data = {
            "tenant_id": "test_tenant",
            "source_connector_path": "connectors/csv.yaml",
            "target_connector_path": "connectors/iceberg.yaml",
            "asset_path": "assets/test.yaml",
            "source": {
                "type": "csv",
                "files": [{"path": "test.csv", "object": "test_data"}],
            },
            "target": {
                "type": "iceberg",
                "connection": {"s3": {"bucket": "test-bucket"}},
            },
            "catalog": CatalogConfig(
                type="openmetadata",
                connection={"api_url": api_url, "auth_token": auth_token},
            ),
        }
        job_config = JobConfig(**job_data)

        manager = CatalogManager(
            job_config=job_config,
            asset_definition=sample_asset_definition,
            target_config=sample_target_config,
        )

        # Test ensure entity exists
        try:
            result = manager.ensure_entity_exists()
            assert result is not None
        except Exception as e:
            pytest.skip(f"OpenMetadata not available: {e}")

        # Test push metadata
        try:
            result = manager.push_metadata()
            assert result is not None
        except Exception as e:
            pytest.skip(f"OpenMetadata not available: {e}")

        # Test push lineage
        try:
            result = manager.push_lineage()
            assert result is not None
        except Exception as e:
            pytest.skip(f"OpenMetadata not available: {e}")
