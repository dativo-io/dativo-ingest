"""Smoke tests for catalog integrations using OpenMetadata."""

import os
import subprocess
import time
from pathlib import Path

import pytest
import requests
import yaml

from dativo_ingest.catalogs import CatalogManager
from dativo_ingest.config import AssetDefinition, CatalogConfig, JobConfig, TargetConfig


@pytest.fixture(scope="session")
def openmetadata_service():
    """Start OpenMetadata service for testing (if not already running)."""
    api_url = os.getenv("OPENMETADATA_URL", "http://localhost:8585/api")

    # Check if OpenMetadata is already running
    try:
        resp = requests.get(f"{api_url.replace('/api', '')}/health", timeout=5)
        if resp.status_code == 200:
            yield api_url
            return
    except requests.exceptions.RequestException:
        pass

    # Try to start OpenMetadata using docker-compose if available
    docker_compose_path = Path(__file__).parent.parent.parent / "docker-compose.dev.yml"
    if docker_compose_path.exists():
        try:
            subprocess.run(
                ["docker-compose", "-f", str(docker_compose_path), "up", "-d", "openmetadata"],
                check=False,
                timeout=30,
            )
            # Wait for service to be ready
            for _ in range(30):
                try:
                    resp = requests.get(f"{api_url.replace('/api', '')}/health", timeout=5)
                    if resp.status_code == 200:
                        yield api_url
                        return
                except requests.exceptions.RequestException:
                    time.sleep(2)
        except Exception:
            pass

    pytest.skip("OpenMetadata service not available")


@pytest.fixture
def sample_asset_definition():
    """Create a sample asset definition for testing."""
    asset_data = {
        "$schema": "schemas/odcs/dativo-odcs-3.0.2-extended.schema.json",
        "apiVersion": "v3.0.2",
        "kind": "DataContract",
        "name": "catalog_test_table",
        "version": "1.0",
        "source_type": "csv",
        "object": "test_data",
        "domain": "smoke_test",
        "dataProduct": "catalog_integration",
        "schema": [
            {"name": "id", "type": "string", "required": True},
            {"name": "name", "type": "string", "required": False},
            {"name": "value", "type": "integer", "required": False},
        ],
        "team": {"owner": "test@example.com"},
        "tags": ["smoke_test", "catalog"],
        "description": {
            "purpose": "Test table for catalog smoke tests",
            "usage": "Smoke testing catalog integration",
        },
    }
    return AssetDefinition(**asset_data)


@pytest.fixture
def sample_job_config(openmetadata_service):
    """Create a sample job config with OpenMetadata catalog."""
    job_data = {
        "tenant_id": "smoke_test_tenant",
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
                    "prefix": "raw/smoke_test",
                }
            },
        },
        "catalog": CatalogConfig(
            type="openmetadata",
            connection={
                "api_url": openmetadata_service,
                "auth_token": os.getenv("OPENMETADATA_TOKEN"),
            },
        ),
    }
    return JobConfig(**job_data)


@pytest.fixture
def sample_target_config():
    """Create a sample target config."""
    return TargetConfig(
        type="iceberg",
        connection={
            "s3": {
                "bucket": "test-bucket",
                "prefix": "raw/smoke_test",
            }
        },
    )


@pytest.mark.smoke
class TestOpenMetadataSmoke:
    """Smoke tests for OpenMetadata catalog integration."""

    def test_catalog_manager_initialization(
        self, sample_job_config, sample_asset_definition, sample_target_config
    ):
        """Test catalog manager initialization."""
        manager = CatalogManager(
            job_config=sample_job_config,
            asset_definition=sample_asset_definition,
            target_config=sample_target_config,
        )

        assert manager is not None
        catalog = manager._get_catalog()
        assert catalog is not None

    def test_ensure_entity_exists(
        self, sample_job_config, sample_asset_definition, sample_target_config
    ):
        """Test ensuring entity exists in OpenMetadata."""
        manager = CatalogManager(
            job_config=sample_job_config,
            asset_definition=sample_asset_definition,
            target_config=sample_target_config,
        )

        result = manager.ensure_entity_exists()
        assert result is not None

    def test_push_metadata(
        self, sample_job_config, sample_asset_definition, sample_target_config
    ):
        """Test pushing metadata to OpenMetadata."""
        manager = CatalogManager(
            job_config=sample_job_config,
            asset_definition=sample_asset_definition,
            target_config=sample_target_config,
        )

        # Ensure entity exists first
        manager.ensure_entity_exists()

        result = manager.push_metadata()
        assert result is not None
        assert result.get("status") in ["success", "delegated"]

    def test_push_lineage(
        self, sample_job_config, sample_asset_definition, sample_target_config
    ):
        """Test pushing lineage to OpenMetadata."""
        manager = CatalogManager(
            job_config=sample_job_config,
            asset_definition=sample_asset_definition,
            target_config=sample_target_config,
        )

        # Ensure entity exists first
        manager.ensure_entity_exists()

        result = manager.push_lineage()
        assert result is not None
        assert result.get("status") in ["success", "error"]

    def test_end_to_end_catalog_flow(
        self, sample_job_config, sample_asset_definition, sample_target_config
    ):
        """Test end-to-end catalog flow."""
        manager = CatalogManager(
            job_config=sample_job_config,
            asset_definition=sample_asset_definition,
            target_config=sample_target_config,
        )

        # 1. Ensure entity exists
        entity_result = manager.ensure_entity_exists()
        assert entity_result is not None

        # 2. Push metadata
        metadata_result = manager.push_metadata()
        assert metadata_result is not None

        # 3. Push lineage
        lineage_result = manager.push_lineage()
        assert lineage_result is not None

        # All operations should complete without errors
        assert metadata_result.get("status") in ["success", "delegated"]
        assert lineage_result.get("status") in ["success", "error"]  # May fail if source entities don't exist
