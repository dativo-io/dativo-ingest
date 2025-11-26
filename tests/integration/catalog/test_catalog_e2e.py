"""End-to-end tests for catalog integration with full pipeline.

These tests verify the catalog integration in a full ingestion pipeline.
"""

import os
import pytest
import tempfile
import yaml
from pathlib import Path

# Skip if OpenMetadata not available
def is_openmetadata_available():
    """Check if OpenMetadata is available."""
    try:
        import requests
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
def test_job_with_catalog(tmp_path):
    """Create a test job configuration with catalog enabled."""
    # Create job config
    job_config = {
        "tenant_id": "test_tenant",
        "source_connector_path": "connectors/csv.yaml",
        "target_connector_path": "connectors/iceberg.yaml",
        "asset_path": "assets/test_asset.yaml",
        "source": {
            "files": [
                {"path": str(tmp_path / "test_data.csv"), "object": "test_customers"}
            ]
        },
        "target": {
            "connection": {
                "s3": {
                    "bucket": "test-bucket",
                }
            }
        },
        "catalog": {
            "type": "openmetadata",
            "connection": {
                "host_port": os.getenv("OPENMETADATA_HOST_PORT", "http://localhost:8585/api"),
                "service_name": "dativo_e2e_test",
            },
            "enabled": True,
            "push_lineage": True,
            "push_metadata": True,
        },
    }
    
    # Create test CSV data
    csv_data = """id,name,email
1,John Doe,john@example.com
2,Jane Smith,jane@example.com
"""
    csv_path = tmp_path / "test_data.csv"
    csv_path.write_text(csv_data)
    
    # Create asset definition
    asset_definition = {
        "name": "test_customers",
        "version": "1.0",
        "apiVersion": "v3.0.2",
        "kind": "DataContract",
        "domain": "test",
        "dataProduct": "customers",
        "source_type": "csv",
        "object": "test_customers",
        "schema": [
            {"name": "id", "type": "integer", "required": True},
            {"name": "name", "type": "string"},
            {"name": "email", "type": "string"},
        ],
        "team": {"owner": "data-team@example.com"},
        "tags": ["test", "e2e"],
    }
    
    return {
        "job_config": job_config,
        "asset_definition": asset_definition,
        "tmp_path": tmp_path,
    }


class TestCatalogE2E:
    """End-to-end tests for catalog integration."""

    def test_catalog_factory_from_job_config(self, test_job_with_catalog):
        """Test creating catalog client from job configuration."""
        from dativo_ingest.catalog.factory import CatalogClientFactory
        
        client = CatalogClientFactory.create_from_job_config(
            test_job_with_catalog["job_config"]
        )
        
        assert client is not None
        assert client.config.type == "openmetadata"
        assert client.config.push_lineage is True
        assert client.config.push_metadata is True

    def test_lineage_tracker_workflow(self, test_job_with_catalog):
        """Test complete lineage tracking workflow."""
        from dativo_ingest.catalog.factory import CatalogClientFactory
        from dativo_ingest.catalog.lineage_tracker import LineageTracker
        from dativo_ingest.config import AssetDefinition
        from unittest.mock import Mock
        
        # Create catalog client
        client = CatalogClientFactory.create_from_job_config(
            test_job_with_catalog["job_config"]
        )
        client.connect()
        
        # Create lineage tracker
        tracker = LineageTracker(client)
        tracker.start_tracking()
        
        # Create asset definition
        asset_dict = test_job_with_catalog["asset_definition"]
        asset = AssetDefinition(**asset_dict)
        
        # Create mock target config
        target_config = Mock()
        target_config.connection = {"s3": {"bucket": "test-bucket"}}
        
        # Build and push table metadata
        table_metadata = tracker.build_table_metadata(
            asset_definition=asset,
            target_config=target_config,
        )
        tracker.push_table_metadata(table_metadata)
        
        # Build target FQN
        target_fqn = tracker.build_target_fqn(
            catalog_type="openmetadata",
            asset_definition=asset,
            catalog_config=test_job_with_catalog["job_config"]["catalog"]["connection"],
        )
        
        # Build source FQN
        source_fqn = tracker.build_source_fqn(
            source_type="csv",
            source_object="test_customers",
        )
        
        # End tracking and push lineage
        tracker.end_tracking()
        lineage = tracker.build_lineage_info(
            source_fqn=source_fqn,
            target_fqn=target_fqn,
            pipeline_name="test_e2e_pipeline",
            records_read=2,
            records_written=2,
            status="success",
        )
        tracker.push_lineage(lineage)
        
        # Push tags
        tracker.push_tags(target_fqn, table_metadata.tags)
        
        # Set owner
        if table_metadata.owner:
            tracker.set_owner(target_fqn, table_metadata.owner)
        
        # Close client
        client.close()

    def test_catalog_disabled(self, test_job_with_catalog):
        """Test that catalog operations are skipped when disabled."""
        from dativo_ingest.catalog.factory import CatalogClientFactory
        
        # Disable catalog
        job_config = test_job_with_catalog["job_config"].copy()
        job_config["catalog"]["enabled"] = False
        
        client = CatalogClientFactory.create_from_job_config(job_config)
        assert client is None
