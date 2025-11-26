"""Unit tests for lineage tracker."""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime

from dativo_ingest.catalog.base import CatalogConfig, TableMetadata, LineageInfo
from dativo_ingest.catalog.lineage_tracker import LineageTracker
from dativo_ingest.config import AssetDefinition


@pytest.fixture
def mock_catalog_client():
    """Create a mock catalog client."""
    client = Mock()
    client.config = CatalogConfig(
        type="openmetadata",
        connection={"host_port": "http://localhost:8585/api"},
        push_lineage=True,
        push_metadata=True,
    )
    return client


@pytest.fixture
def sample_asset_definition():
    """Create a sample asset definition."""
    return AssetDefinition(
        name="test_table",
        version="1.0",
        domain="test_domain",
        dataProduct="test_product",
        source_type="postgres",
        object="customers",
        schema=[
            {"name": "id", "type": "integer", "required": True},
            {"name": "name", "type": "string", "description": "Customer name"},
            {"name": "email", "type": "string"},
        ],
        team={"owner": "data-team@example.com"},
        tags=["pii", "customer"],
        compliance={
            "classification": ["confidential"],
            "regulations": ["gdpr"],
        },
    )


@pytest.fixture
def sample_target_config():
    """Create a sample target config."""
    config = Mock()
    config.connection = {
        "s3": {
            "bucket": "test-bucket",
        }
    }
    return config


class TestLineageTracker:
    """Test cases for LineageTracker."""

    def test_start_and_end_tracking(self, mock_catalog_client):
        """Test start and end tracking."""
        tracker = LineageTracker(mock_catalog_client)
        
        tracker.start_tracking()
        assert tracker._start_time is not None
        
        tracker.end_tracking()
        assert tracker._end_time is not None
        assert tracker._end_time >= tracker._start_time

    def test_build_table_metadata(
        self, mock_catalog_client, sample_asset_definition, sample_target_config
    ):
        """Test building table metadata from asset definition."""
        tracker = LineageTracker(mock_catalog_client)
        
        metadata = tracker.build_table_metadata(
            asset_definition=sample_asset_definition,
            target_config=sample_target_config,
        )
        
        assert isinstance(metadata, TableMetadata)
        assert metadata.name == "test_table"
        assert metadata.database == "test_domain"
        assert metadata.schema == "test_product"
        assert metadata.owner == "data-team@example.com"
        assert len(metadata.columns) == 3
        assert metadata.columns[0]["name"] == "id"
        assert metadata.columns[0]["type"] == "integer"
        assert "domain" in metadata.tags
        assert "data_product" in metadata.tags

    def test_build_lineage_info(self, mock_catalog_client):
        """Test building lineage information."""
        tracker = LineageTracker(mock_catalog_client)
        tracker.start_tracking()
        tracker.end_tracking()
        
        lineage = tracker.build_lineage_info(
            source_fqn="postgres.mydb.customers",
            target_fqn="test_domain.test_table",
            pipeline_name="test_pipeline",
            records_read=1000,
            records_written=950,
            status="success",
        )
        
        assert isinstance(lineage, LineageInfo)
        assert lineage.source_fqn == "postgres.mydb.customers"
        assert lineage.target_fqn == "test_domain.test_table"
        assert lineage.pipeline_name == "test_pipeline"
        assert lineage.records_read == 1000
        assert lineage.records_written == 950
        assert lineage.status == "success"

    def test_push_table_metadata(self, mock_catalog_client, sample_asset_definition, sample_target_config):
        """Test pushing table metadata to catalog."""
        tracker = LineageTracker(mock_catalog_client)
        
        metadata = tracker.build_table_metadata(
            asset_definition=sample_asset_definition,
            target_config=sample_target_config,
        )
        
        tracker.push_table_metadata(metadata)
        mock_catalog_client.create_or_update_table.assert_called_once_with(metadata)

    def test_push_table_metadata_disabled(self, mock_catalog_client, sample_asset_definition, sample_target_config):
        """Test that metadata is not pushed when disabled."""
        mock_catalog_client.config.push_metadata = False
        tracker = LineageTracker(mock_catalog_client)
        
        metadata = tracker.build_table_metadata(
            asset_definition=sample_asset_definition,
            target_config=sample_target_config,
        )
        
        tracker.push_table_metadata(metadata)
        mock_catalog_client.create_or_update_table.assert_not_called()

    def test_push_lineage(self, mock_catalog_client):
        """Test pushing lineage to catalog."""
        tracker = LineageTracker(mock_catalog_client)
        
        lineage = LineageInfo(
            source_fqn="source.table",
            target_fqn="target.table",
            pipeline_name="test_pipeline",
            status="success",
        )
        
        tracker.push_lineage(lineage)
        mock_catalog_client.push_lineage.assert_called_once_with(lineage)

    def test_push_lineage_disabled(self, mock_catalog_client):
        """Test that lineage is not pushed when disabled."""
        mock_catalog_client.config.push_lineage = False
        tracker = LineageTracker(mock_catalog_client)
        
        lineage = LineageInfo(
            source_fqn="source.table",
            target_fqn="target.table",
            pipeline_name="test_pipeline",
            status="success",
        )
        
        tracker.push_lineage(lineage)
        mock_catalog_client.push_lineage.assert_not_called()

    def test_build_target_fqn_openmetadata(self, mock_catalog_client, sample_asset_definition):
        """Test building target FQN for OpenMetadata."""
        tracker = LineageTracker(mock_catalog_client)
        
        fqn = tracker.build_target_fqn(
            catalog_type="openmetadata",
            asset_definition=sample_asset_definition,
        )
        
        assert fqn == "dativo_iceberg_service.test_domain.test_product.test_table"

    def test_build_target_fqn_glue(self, mock_catalog_client, sample_asset_definition):
        """Test building target FQN for AWS Glue."""
        tracker = LineageTracker(mock_catalog_client)
        
        fqn = tracker.build_target_fqn(
            catalog_type="aws_glue",
            asset_definition=sample_asset_definition,
        )
        
        assert fqn == "test_domain.test_table"

    def test_build_target_fqn_unity(self, mock_catalog_client, sample_asset_definition):
        """Test building target FQN for Unity Catalog."""
        tracker = LineageTracker(mock_catalog_client)
        
        fqn = tracker.build_target_fqn(
            catalog_type="databricks_unity",
            asset_definition=sample_asset_definition,
            catalog_config={"catalog": "main"},
        )
        
        assert fqn == "main.test_product.test_table"

    def test_build_source_fqn_postgres(self, mock_catalog_client):
        """Test building source FQN for PostgreSQL."""
        tracker = LineageTracker(mock_catalog_client)
        
        fqn = tracker.build_source_fqn(
            source_type="postgres",
            source_object="customers",
            source_connection={"database": "mydb"},
        )
        
        assert fqn == "postgres.mydb.customers"

    def test_build_source_fqn_saas(self, mock_catalog_client):
        """Test building source FQN for SaaS APIs."""
        tracker = LineageTracker(mock_catalog_client)
        
        fqn = tracker.build_source_fqn(
            source_type="stripe",
            source_object="customers",
        )
        
        assert fqn == "stripe.customers"
