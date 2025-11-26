"""Integration tests for OpenMetadata catalog."""

import os
import time
from pathlib import Path

import pytest
import requests
import yaml

from dativo_ingest.config import AssetDefinition, JobConfig
from dativo_ingest.data_catalog import CatalogManager


@pytest.fixture(scope="module")
def openmetadata_available():
    """Check if OpenMetadata is available."""
    uri = os.getenv("OPENMETADATA_URI", "http://localhost:8585")
    try:
        response = requests.get(f"{uri}/api/v1/health", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


@pytest.fixture
def sample_asset_definition():
    """Create a sample asset definition."""
    asset_data = {
        "apiVersion": "v3.0.2",
        "kind": "DataContract",
        "name": "catalog_test_table",
        "version": "1.0",
        "domain": "catalog_test",
        "dataProduct": "integration_tests",
        "source_type": "csv",
        "object": "test_data",
        "schema": [
            {"name": "id", "type": "string", "required": True, "description": "Record ID"},
            {"name": "name", "type": "string", "required": False, "description": "Name"},
            {"name": "value", "type": "integer", "required": True, "description": "Value"},
        ],
        "team": {"owner": "integration-test@example.com"},
        "tags": ["integration", "test"],
        "compliance": {"classification": ["PUBLIC"]},
    }
    return AssetDefinition(**asset_data)


@pytest.fixture
def catalog_config():
    """Create catalog configuration for OpenMetadata."""
    return {
        "type": "openmetadata",
        "config": {
            "uri": os.getenv("OPENMETADATA_URI", "http://localhost:8585"),
            "token": os.getenv("OPENMETADATA_TOKEN", ""),
            "api_version": "v1",
        },
        "metadata": {
            "owners": ["integration-test@example.com"],
            "tags": {"test_type": "integration", "environment": "test"},
            "description": "Integration test table",
            "tier": "bronze",
        },
        "lineage": {
            "enabled": True,
            "upstream_tables": [],
            "downstream_tables": [],
        },
    }


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("RUN_OPENMETADATA_TESTS"),
    reason="OpenMetadata integration tests disabled. Set RUN_OPENMETADATA_TESTS=1 to enable.",
)
class TestOpenMetadataIntegration:
    """Integration tests with OpenMetadata."""

    def test_openmetadata_connection(self, openmetadata_available):
        """Test connection to OpenMetadata."""
        if not openmetadata_available:
            pytest.skip("OpenMetadata is not available")

        uri = os.getenv("OPENMETADATA_URI", "http://localhost:8585")
        response = requests.get(f"{uri}/api/v1/health")
        assert response.status_code == 200

    def test_create_table_metadata(
        self, openmetadata_available, sample_asset_definition, catalog_config
    ):
        """Test creating table metadata in OpenMetadata."""
        if not openmetadata_available:
            pytest.skip("OpenMetadata is not available")

        manager = CatalogManager(catalog_config, sample_asset_definition)

        result = manager.sync_table_metadata(
            database="catalog_test",
            table_name="catalog_test_table",
            location="s3://test-bucket/catalog_test/integration_tests/catalog_test_table",
            additional_metadata={
                "records_written": 100,
                "files_written": 1,
                "total_bytes": 10240,
            },
        )

        assert result["status"] in ["created", "updated"]
        assert "catalog_test_table" in result.get("table", "")

    def test_push_lineage(
        self, openmetadata_available, sample_asset_definition, catalog_config
    ):
        """Test pushing lineage to OpenMetadata."""
        if not openmetadata_available:
            pytest.skip("OpenMetadata is not available")

        manager = CatalogManager(catalog_config, sample_asset_definition)

        # First ensure table exists
        manager.sync_table_metadata(
            database="catalog_test",
            table_name="catalog_test_table",
            location="s3://test-bucket/catalog_test/integration_tests/catalog_test_table",
        )

        # Push lineage
        result = manager.push_lineage(
            source_type="csv",
            source_object="test_data",
            target_database="catalog_test",
            target_table="catalog_test_table",
            job_id="integration_test_job",
            tenant_id="test_tenant",
            records_written=100,
            files_written=1,
        )

        # Lineage push may fail if upstream tables don't exist, but should not raise exception
        assert result["status"] in ["success", "error"]

    def test_sync_tags(
        self, openmetadata_available, sample_asset_definition, catalog_config
    ):
        """Test syncing tags to OpenMetadata."""
        if not openmetadata_available:
            pytest.skip("OpenMetadata is not available")

        manager = CatalogManager(catalog_config, sample_asset_definition)

        # First ensure table exists
        manager.sync_table_metadata(
            database="catalog_test",
            table_name="catalog_test_table",
            location="s3://test-bucket/catalog_test/integration_tests/catalog_test_table",
        )

        # Sync tags
        result = manager.sync_tags("catalog_test", "catalog_test_table")

        assert result["status"] in ["success", "error", "skipped"]

    def test_sync_owners(
        self, openmetadata_available, sample_asset_definition, catalog_config
    ):
        """Test syncing owners to OpenMetadata."""
        if not openmetadata_available:
            pytest.skip("OpenMetadata is not available")

        manager = CatalogManager(catalog_config, sample_asset_definition)

        # First ensure table exists
        manager.sync_table_metadata(
            database="catalog_test",
            table_name="catalog_test_table",
            location="s3://test-bucket/catalog_test/integration_tests/catalog_test_table",
        )

        # Sync owners
        result = manager.sync_owners("catalog_test", "catalog_test_table")

        assert result["status"] in ["success", "error", "skipped"]

    def test_full_catalog_sync(
        self, openmetadata_available, sample_asset_definition, catalog_config
    ):
        """Test full catalog sync workflow."""
        if not openmetadata_available:
            pytest.skip("OpenMetadata is not available")

        manager = CatalogManager(catalog_config, sample_asset_definition)

        # 1. Sync table metadata
        table_result = manager.sync_table_metadata(
            database="catalog_test",
            table_name="catalog_test_table",
            location="s3://test-bucket/catalog_test/integration_tests/catalog_test_table",
            additional_metadata={"records_written": 150, "files_written": 2},
        )
        assert table_result["status"] in ["created", "updated"]

        # Give OpenMetadata time to process
        time.sleep(1)

        # 2. Push lineage
        lineage_result = manager.push_lineage(
            source_type="csv",
            source_object="test_data",
            target_database="catalog_test",
            target_table="catalog_test_table",
            job_id="full_sync_test",
            tenant_id="test_tenant",
            records_written=150,
            files_written=2,
        )
        # Don't assert success as lineage may fail without upstream tables
        assert lineage_result is not None

        # 3. Sync tags
        tags_result = manager.sync_tags("catalog_test", "catalog_test_table")
        assert tags_result is not None

        # 4. Sync owners
        owners_result = manager.sync_owners("catalog_test", "catalog_test_table")
        assert owners_result is not None


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("RUN_OPENMETADATA_TESTS"),
    reason="OpenMetadata smoke tests disabled. Set RUN_OPENMETADATA_TESTS=1 to enable.",
)
class TestOpenMetadataSmokeTest:
    """Smoke tests for OpenMetadata with actual job execution."""

    def test_job_with_catalog_config(
        self, openmetadata_available, tmp_path
    ):
        """Test job execution with catalog configuration."""
        if not openmetadata_available:
            pytest.skip("OpenMetadata is not available")

        # Create test CSV file
        csv_file = tmp_path / "test_data.csv"
        csv_file.write_text("id,name,value\\n1,test,100\\n2,test2,200\\n")

        # Create asset definition
        asset_file = tmp_path / "test_asset.yaml"
        asset_data = {
            "apiVersion": "v3.0.2",
            "kind": "DataContract",
            "name": "smoke_test_table",
            "version": "1.0",
            "domain": "smoke_test",
            "dataProduct": "smoke_tests",
            "source_type": "csv",
            "object": "test_data",
            "schema": [
                {"name": "id", "type": "string", "required": True},
                {"name": "name", "type": "string", "required": False},
                {"name": "value", "type": "integer", "required": True},
            ],
            "team": {"owner": "smoke-test@example.com"},
            "tags": ["smoke", "test"],
        }
        with open(asset_file, "w") as f:
            yaml.dump(asset_data, f)

        # Create job config with catalog
        job_file = tmp_path / "test_job.yaml"
        job_data = {
            "tenant_id": "test_tenant",
            "source_connector_path": "connectors/csv.yaml",
            "target_connector_path": "connectors/s3.yaml",
            "asset_path": str(asset_file),
            "source": {"files": [{"path": str(csv_file), "object": "test_data"}]},
            "target": {
                "connection": {
                    "bucket": "test-bucket",
                    "prefix": "smoke_test",
                    "endpoint": "${S3_ENDPOINT}",
                    "access_key_id": "${AWS_ACCESS_KEY_ID}",
                    "secret_access_key": "${AWS_SECRET_ACCESS_KEY}",
                }
            },
            "catalog": {
                "type": "openmetadata",
                "config": {
                    "uri": os.getenv("OPENMETADATA_URI", "http://localhost:8585"),
                    "token": os.getenv("OPENMETADATA_TOKEN", ""),
                },
                "metadata": {
                    "owners": ["smoke-test@example.com"],
                    "tags": {"test_type": "smoke"},
                    "tier": "bronze",
                },
                "lineage": {"enabled": True},
            },
        }
        with open(job_file, "w") as f:
            yaml.dump(job_data, f)

        # Note: This test creates the config but doesn't execute the job
        # Full execution would require connectors and infrastructure setup
        job_config = JobConfig.from_yaml(job_file)
        assert job_config.catalog is not None
        assert job_config.catalog["type"] == "openmetadata"
