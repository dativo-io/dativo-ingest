"""Integration tests for catalog functionality with OpenMetadata."""

import os
import subprocess
import time
from pathlib import Path

import pytest
import requests

from dativo_ingest.catalog import CatalogFactory
from dativo_ingest.config import AssetDefinition, CatalogConfig, JobConfig


@pytest.fixture(scope="module")
def openmetadata_server():
    """Start OpenMetadata server for testing (if available)."""
    # Check if OpenMetadata is already running
    try:
        resp = requests.get("http://localhost:8585/health", timeout=2)
        if resp.status_code == 200:
            yield "http://localhost:8585"
            return
    except Exception:
        pass

    # Try to start OpenMetadata via Docker if available
    try:
        # Check if docker is available
        subprocess.run(["docker", "--version"], check=True, capture_output=True)

        # Try to start OpenMetadata
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                "openmetadata-test",
                "-p",
                "8585:8585",
                "openmetadata/openmetadata-server:latest",
            ],
            check=False,
            capture_output=True,
        )

        # Wait for server to start
        for _ in range(30):
            try:
                resp = requests.get("http://localhost:8585/health", timeout=2)
                if resp.status_code == 200:
                    yield "http://localhost:8585"
                    return
            except Exception:
                time.sleep(2)

        pytest.skip("OpenMetadata server not available")
    except Exception:
        pytest.skip("Docker not available or OpenMetadata server not running")


@pytest.fixture
def openmetadata_auth_token(openmetadata_server):
    """Get or create OpenMetadata auth token."""
    # For testing, we'll use a default token or create one
    # In real scenarios, this would be configured
    token = os.getenv("OPENMETADATA_AUTH_TOKEN")
    if not token:
        # Try to create a token via API (if admin credentials available)
        # For now, skip if no token
        pytest.skip("OPENMETADATA_AUTH_TOKEN not set")
    return token


@pytest.mark.integration
class TestOpenMetadataIntegration:
    """Integration tests for OpenMetadata catalog."""

    @pytest.fixture
    def sample_asset(self):
        """Create sample asset definition."""
        return AssetDefinition(
            name="test_integration_table",
            version="1.0",
            source_type="csv",
            object="test_object",
            schema=[
                {"name": "id", "type": "string", "required": True},
                {"name": "name", "type": "string", "required": False},
            ],
            team={"owner": "test@example.com"},
            domain="test_domain",
            dataProduct="test_product",
            tags=["integration_test"],
            description={"purpose": "Integration test table"},
        )

    @pytest.fixture
    def sample_job_config(self):
        """Create sample job config."""
        return JobConfig(
            tenant_id="test_tenant",
            source_connector_path="connectors/csv.yaml",
            target_connector_path="connectors/iceberg.yaml",
            asset_path="assets/test.yaml",
            source={
                "type": "csv",
                "files": [{"path": "tests/fixtures/seeds/test.csv", "object": "test"}],
            },
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

    def test_catalog_creation(
        self,
        openmetadata_server,
        openmetadata_auth_token,
        sample_asset,
        sample_job_config,
    ):
        """Test creating catalog instance."""
        catalog_config = CatalogConfig(
            type="openmetadata",
            connection={
                "api_url": f"{openmetadata_server}/api",
                "auth_token": openmetadata_auth_token,
            },
            database="test_db",
        )

        catalog = CatalogFactory.create(catalog_config, sample_asset, sample_job_config)
        assert catalog is not None
        assert catalog.__class__.__name__ == "OpenMetadataCatalog"

    def test_ensure_entity_exists(
        self,
        openmetadata_server,
        openmetadata_auth_token,
        sample_asset,
        sample_job_config,
    ):
        """Test ensuring entity exists in OpenMetadata."""
        catalog_config = CatalogConfig(
            type="openmetadata",
            connection={
                "api_url": f"{openmetadata_server}/api",
                "auth_token": openmetadata_auth_token,
            },
            database="test_db",
        )

        catalog = CatalogFactory.create(catalog_config, sample_asset, sample_job_config)

        entity = {
            "name": "test_integration_table",
            "database": "test_db",
            "location": "s3://test-bucket/test_table",
        }

        result = catalog.ensure_entity_exists(entity, schema=sample_asset.schema)
        assert result is not None
        assert "fqn" in result or "name" in result

    def test_push_metadata(
        self,
        openmetadata_server,
        openmetadata_auth_token,
        sample_asset,
        sample_job_config,
    ):
        """Test pushing metadata to OpenMetadata."""
        catalog_config = CatalogConfig(
            type="openmetadata",
            connection={
                "api_url": f"{openmetadata_server}/api",
                "auth_token": openmetadata_auth_token,
            },
            database="test_db",
        )

        catalog = CatalogFactory.create(catalog_config, sample_asset, sample_job_config)

        # Ensure entity exists first
        entity = catalog._extract_target_entity()
        catalog.ensure_entity_exists(entity, schema=sample_asset.schema)

        # Push metadata
        tags = catalog._extract_tags()
        owners = catalog._extract_owners()
        description = catalog._extract_description()

        result = catalog.push_metadata(
            entity, tags=tags, owners=owners, description=description
        )

        assert result["status"] in ["success", "partial"]

    def test_push_lineage(
        self,
        openmetadata_server,
        openmetadata_auth_token,
        sample_asset,
        sample_job_config,
    ):
        """Test pushing lineage to OpenMetadata."""
        catalog_config = CatalogConfig(
            type="openmetadata",
            connection={
                "api_url": f"{openmetadata_server}/api",
                "auth_token": openmetadata_auth_token,
            },
            database="test_db",
        )

        catalog = CatalogFactory.create(catalog_config, sample_asset, sample_job_config)

        # Extract entities
        source_entities = catalog._extract_source_entities()
        target_entity = catalog._extract_target_entity()

        # Ensure target exists
        catalog.ensure_entity_exists(target_entity, schema=sample_asset.schema)

        # Push lineage
        result = catalog.push_lineage(
            source_entities, target_entity, operation="ingest"
        )

        assert result["status"] in ["success", "partial", "skipped"]


@pytest.mark.integration
def test_job_with_catalog_config(tmp_path):
    """Test running a job with catalog configuration."""
    # Create a test job config with catalog
    job_yaml = """
tenant_id: test_tenant
source_connector_path: connectors/csv.yaml
target_connector_path: connectors/iceberg.yaml
asset_path: tests/fixtures/assets/csv/v1.0/employee.yaml
source:
  type: csv
  files:
    - path: tests/fixtures/seeds/AdventureWorks-oltp-install-script/Employee.csv
      object: Employee
target:
  type: iceberg
  connection:
    s3:
      endpoint: "${S3_ENDPOINT}"
      bucket: test-bucket
catalog:
  type: openmetadata
  connection:
    api_url: "${OPENMETADATA_API_URL:-http://localhost:8585/api}"
    auth_token: "${OPENMETADATA_AUTH_TOKEN}"
  database: test_db
  push_lineage: true
  push_metadata: true
schema_validation_mode: warn
"""
    job_file = tmp_path / "test_catalog_job.yaml"
    job_file.write_text(job_yaml)

    # Load and validate job config
    job_config = JobConfig.from_yaml(job_file, validate_schema=False)
    assert job_config.catalog is not None
    assert job_config.catalog.type == "openmetadata"

    # Note: Actual job execution would require OpenMetadata server and proper setup
    # This test validates the configuration structure
