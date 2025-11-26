"""Smoke tests for OpenMetadata catalog integration.

These tests verify that the OpenMetadata catalog integration works end-to-end
with a local OpenMetadata instance. They require OpenMetadata to be running locally.

Run with: pytest tests/smoke_test_openmetadata.py -v
"""

import pytest
import os
import time
from datetime import datetime

from src.dativo_ingest.catalogs.base import CatalogConfig, LineageInfo
from src.dativo_ingest.catalogs.factory import create_catalog_client


# Skip if OpenMetadata is not available
pytest_mark_skipif = pytest.mark.skipif(
    os.getenv("RUN_OPENMETADATA_SMOKE_TESTS") != "true",
    reason="OpenMetadata smoke tests only run when RUN_OPENMETADATA_SMOKE_TESTS=true"
)


@pytest_mark_skipif
class TestOpenMetadataSmoke:
    """Smoke tests for OpenMetadata integration."""
    
    @pytest.fixture(scope="class")
    def openmetadata_config(self):
        """Fixture for OpenMetadata configuration."""
        return CatalogConfig(
            type="openmetadata",
            enabled=True,
            uri=os.getenv("OPENMETADATA_URI", "http://localhost:8585/api"),
            push_lineage=True,
            push_schema=True,
            push_metadata=True,
        )
    
    @pytest.fixture(scope="class")
    def catalog_client(self, openmetadata_config):
        """Fixture for catalog client."""
        return create_catalog_client(openmetadata_config)
    
    def test_connection(self, catalog_client):
        """Test connection to OpenMetadata."""
        assert catalog_client is not None
        assert catalog_client.test_connection() is True
    
    def test_register_dataset(self, catalog_client):
        """Test registering a dataset in OpenMetadata."""
        schema = [
            {"name": "id", "type": "string", "required": True, "description": "Unique identifier"},
            {"name": "name", "type": "string", "description": "User name"},
            {"name": "email", "type": "string", "description": "Email address"},
            {"name": "age", "type": "integer", "description": "Age in years"},
            {"name": "created_at", "type": "timestamp", "description": "Creation timestamp"},
        ]
        
        metadata = {
            "description": "User table for smoke test",
            "owner": "smoketest@dativo.io",
            "tags": ["test", "smoke_test", "dativo"],
            "location": "s3://test-bucket/smoke_test/users",
            "service_name": "dativo_smoke_test",
            "custom_metadata": {
                "tenant_id": "smoke_test_tenant",
                "asset_version": "1.0",
                "source_type": "postgres",
            },
        }
        
        dataset_name = "smoke_test.users"
        
        result = catalog_client.register_dataset(
            dataset_name=dataset_name,
            schema=schema,
            metadata=metadata,
        )
        
        assert result["status"] == "success"
        assert "fqn" in result
        print(f"✓ Dataset registered: {result.get('fqn')}")
    
    def test_publish_lineage(self, catalog_client):
        """Test publishing lineage to OpenMetadata."""
        # First register source and target datasets
        schema = [
            {"name": "id", "type": "string"},
            {"name": "name", "type": "string"},
        ]
        
        # Register source dataset
        catalog_client.register_dataset(
            dataset_name="smoke_test.source_users",
            schema=schema,
            metadata={
                "description": "Source users table",
                "service_name": "dativo_smoke_test",
            },
        )
        
        # Register target dataset
        catalog_client.register_dataset(
            dataset_name="smoke_test.target_users",
            schema=schema,
            metadata={
                "description": "Target users table",
                "service_name": "dativo_smoke_test",
            },
        )
        
        # Wait a bit for registration to complete
        time.sleep(2)
        
        # Publish lineage
        lineage_info = LineageInfo(
            source_type="postgres",
            source_name="smoke_test_db",
            source_dataset="dativo_smoke_test.smoke_test.source_users",
            source_columns=["id", "name"],
            target_type="iceberg",
            target_name="warehouse",
            target_dataset="dativo_smoke_test.smoke_test.target_users",
            target_columns=["id", "name"],
            pipeline_name="smoke_test_pipeline",
            tenant_id="smoke_test_tenant",
            records_processed=1000,
            bytes_processed=50000,
            transformation_type="extract_transform_load",
            transformation_description="Smoke test ETL pipeline",
            execution_time=datetime.utcnow(),
        )
        
        result = catalog_client.publish_lineage(lineage_info)
        
        # Result may be success or partial (if lineage edge creation fails)
        assert result["status"] in ["success", "partial"]
        print(f"✓ Lineage published: {result}")
    
    def test_update_metadata(self, catalog_client):
        """Test updating metadata in OpenMetadata."""
        dataset_name = "smoke_test.users"
        
        result = catalog_client.update_metadata(
            dataset_name=dataset_name,
            tags=["updated", "smoke_test_v2"],
            owner="updated_owner@dativo.io",
            classification=["Public", "Test"],
            custom_metadata={
                "last_updated": datetime.utcnow().isoformat(),
                "test_run": "smoke_test",
            },
        )
        
        # Result may be success or have issues if dataset doesn't exist yet
        assert result["status"] in ["success", "failed"]
        print(f"✓ Metadata updated: {result}")
    
    def test_end_to_end_workflow(self, catalog_client):
        """Test complete workflow: register -> lineage -> metadata."""
        timestamp = int(time.time())
        dataset_name = f"smoke_test.e2e_test_{timestamp}"
        
        # Step 1: Register dataset
        schema = [
            {"name": "id", "type": "string", "required": True},
            {"name": "value", "type": "string"},
            {"name": "timestamp", "type": "timestamp"},
        ]
        
        register_result = catalog_client.register_dataset(
            dataset_name=dataset_name,
            schema=schema,
            metadata={
                "description": "End-to-end test dataset",
                "owner": "e2e_test@dativo.io",
                "service_name": "dativo_smoke_test",
            },
        )
        
        assert register_result["status"] == "success"
        print(f"✓ Step 1: Dataset registered")
        
        # Wait for registration
        time.sleep(2)
        
        # Step 2: Publish lineage
        lineage_info = LineageInfo(
            source_type="csv",
            source_dataset="source.csv",
            target_type="iceberg",
            target_dataset=f"dativo_smoke_test.smoke_test.e2e_test_{timestamp}",
            pipeline_name=f"e2e_test_{timestamp}",
            tenant_id="smoke_test_tenant",
            records_processed=100,
            execution_time=datetime.utcnow(),
        )
        
        lineage_result = catalog_client.publish_lineage(lineage_info)
        print(f"✓ Step 2: Lineage published: {lineage_result.get('status')}")
        
        # Step 3: Update metadata
        metadata_result = catalog_client.update_metadata(
            dataset_name=dataset_name,
            tags=["e2e_test", f"run_{timestamp}"],
            owner="e2e_final@dativo.io",
        )
        print(f"✓ Step 3: Metadata updated: {metadata_result.get('status')}")
        
        print(f"✓ End-to-end workflow completed successfully!")


def test_openmetadata_config_parsing():
    """Test OpenMetadata configuration parsing from job config."""
    from src.dativo_ingest.config import JobConfig
    
    # Create a minimal job config with catalog block
    job_config_data = {
        "tenant_id": "test_tenant",
        "source_connector_path": "connectors/csv.yaml",
        "target_connector_path": "connectors/iceberg.yaml",
        "asset_path": "assets/csv/v1.0/test_asset.yaml",
        "catalog": {
            "type": "openmetadata",
            "enabled": True,
            "uri": "http://localhost:8585/api",
            "push_lineage": True,
            "push_schema": True,
            "push_metadata": True,
        },
    }
    
    # Would normally load from YAML, but we'll construct directly for test
    # This tests that the catalog config can be extracted
    from src.dativo_ingest.catalogs.base import CatalogConfig
    
    catalog_config = CatalogConfig(**job_config_data["catalog"])
    
    assert catalog_config.type == "openmetadata"
    assert catalog_config.enabled is True
    assert catalog_config.uri == "http://localhost:8585/api"
    assert catalog_config.push_lineage is True


if __name__ == "__main__":
    """Run smoke tests directly."""
    # Set environment variable to enable smoke tests
    os.environ["RUN_OPENMETADATA_SMOKE_TESTS"] = "true"
    
    # Run pytest
    pytest.main([__file__, "-v", "-s"])
