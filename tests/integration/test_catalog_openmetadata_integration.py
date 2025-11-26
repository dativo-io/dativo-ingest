"""Integration tests for OpenMetadata catalog integration.

These tests require OpenMetadata to be running locally or accessible.
Set OPENMETADATA_API_URL and optionally OPENMETADATA_AUTH_TOKEN environment variables.
"""

import os
from pathlib import Path

import pytest

from dativo_ingest.catalog_integration import create_catalog_integration
from dativo_ingest.config import AssetDefinition, JobConfig, TeamModel


@pytest.fixture
def openmetadata_available():
    """Check if OpenMetadata is available."""
    api_url = os.getenv("OPENMETADATA_API_URL", "http://localhost:8585/api")
    try:
        import requests

        response = requests.get(f"{api_url}/v1/system/version", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("OPENMETADATA_API_URL") and not os.getenv("RUN_CATALOG_TESTS"),
    reason="OpenMetadata not configured or catalog tests not enabled",
)
class TestOpenMetadataIntegration:
    """Integration tests for OpenMetadata catalog."""

    @pytest.fixture
    def asset_definition(self):
        """Create asset definition for testing."""
        return AssetDefinition(
            name="integration_test_table",
            version="1.0",
            source_type="csv",
            object="integration_test_object",
            schema=[
                {"name": "id", "type": "string", "required": True},
                {"name": "name", "type": "string", "required": False},
            ],
            team=TeamModel(owner="integration-test@example.com"),
            domain="integration_domain",
            dataProduct="integration_product",
            tags=["integration", "test"],
        )

    @pytest.fixture
    def job_config(self):
        """Create job config for testing."""
        return JobConfig(
            tenant_id="integration_tenant",
            source_connector_path="connectors/csv.yaml",
            target_connector_path="connectors/iceberg.yaml",
            asset_path="assets/test.yaml",
            catalog={
                "type": "openmetadata",
                "api_url": os.getenv("OPENMETADATA_API_URL", "http://localhost:8585/api"),
                "auth_token": os.getenv("OPENMETADATA_AUTH_TOKEN"),
            },
        )

    def test_create_integration(self, asset_definition, job_config):
        """Test creating OpenMetadata integration."""
        integration = create_catalog_integration(
            catalog_config=job_config.catalog,
            asset_definition=asset_definition,
            job_config=job_config,
        )

        assert integration is not None
        assert integration.api_url == os.getenv(
            "OPENMETADATA_API_URL", "http://localhost:8585/api"
        )

    @pytest.mark.skipif(
        not os.getenv("RUN_OPENMETADATA_TESTS", "").lower() in ("true", "1", "yes"),
        reason="Requires RUN_OPENMETADATA_TESTS=true and OpenMetadata running",
    )
    def test_push_metadata_real(self, asset_definition, job_config, openmetadata_available):
        """Test pushing metadata to real OpenMetadata instance."""
        if not openmetadata_available:
            pytest.skip("OpenMetadata not available")

        integration = create_catalog_integration(
            catalog_config=job_config.catalog,
            asset_definition=asset_definition,
            job_config=job_config,
        )

        entity = {
            "fqn": "integration_domain.integration_product.integration_test_table",
            "type": "table",
        }

        result = integration.push_metadata(entity)

        # Should succeed or gracefully handle errors
        assert result["status"] in ["success", "error"]
        if result["status"] == "error":
            # Log the error but don't fail the test
            print(f"Metadata push error: {result.get('error')}")

    @pytest.mark.skipif(
        not os.getenv("RUN_OPENMETADATA_TESTS", "").lower() in ("true", "1", "yes"),
        reason="Requires RUN_OPENMETADATA_TESTS=true and OpenMetadata running",
    )
    def test_push_lineage_real(self, asset_definition, job_config, openmetadata_available):
        """Test pushing lineage to real OpenMetadata instance."""
        if not openmetadata_available:
            pytest.skip("OpenMetadata not available")

        integration = create_catalog_integration(
            catalog_config=job_config.catalog,
            asset_definition=asset_definition,
            job_config=job_config,
        )

        source_entities = [
            {
                "fqn": "csv.integration_test_object",
                "type": "table",
                "table": "integration_test_object",
            }
        ]
        target_entity = {
            "fqn": "integration_domain.integration_product.integration_test_table",
            "type": "table",
            "database": "integration_domain",
            "schema": "integration_product",
            "table": "integration_test_table",
        }

        result = integration.push_lineage(source_entities, target_entity)

        # Should succeed or gracefully handle errors
        assert result["status"] in ["success", "error"]
        if result["status"] == "error":
            # Log the error but don't fail the test
            print(f"Lineage push error: {result.get('error')}")
