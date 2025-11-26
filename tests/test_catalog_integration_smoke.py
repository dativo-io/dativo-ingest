"""Smoke tests for catalog integration with OpenMetadata.

These tests verify that catalog integration works end-to-end with OpenMetadata.
For local testing, OpenMetadata should be running at http://localhost:8585.
"""

import os
from unittest.mock import Mock, patch

import pytest

from dativo_ingest.catalog_integration import OpenMetadataIntegration, create_catalog_integration
from dativo_ingest.config import AssetDefinition, JobConfig, TeamModel


@pytest.fixture
def sample_asset_definition():
    """Create a sample asset definition for smoke testing."""
    return AssetDefinition(
        name="smoke_test_table",
        version="1.0",
        source_type="csv",
        object="smoke_test_object",
        schema=[
            {"name": "id", "type": "string", "required": True},
            {"name": "value", "type": "string", "required": False},
        ],
        team=TeamModel(owner="smoke-test@example.com"),
        domain="smoke_domain",
        dataProduct="smoke_product",
        tags=["test", "smoke"],
    )


@pytest.fixture
def sample_job_config():
    """Create a sample job config for smoke testing."""
    return JobConfig(
        tenant_id="smoke_tenant",
        source_connector_path="connectors/csv.yaml",
        target_connector_path="connectors/iceberg.yaml",
        asset_path="assets/test.yaml",
        catalog={
            "type": "openmetadata",
            "api_url": os.getenv("OPENMETADATA_API_URL", "http://localhost:8585/api"),
            "auth_token": os.getenv("OPENMETADATA_AUTH_TOKEN"),
        },
        classification_overrides={"id": "pii"},
        finops={"cost_center": "SMOKE-001", "business_tags": ["testing"]},
    )


@pytest.mark.integration
class TestOpenMetadataSmoke:
    """Smoke tests for OpenMetadata integration."""

    @pytest.mark.skipif(
        not os.getenv("OPENMETADATA_API_URL") and not os.getenv("RUN_SMOKE_TESTS"),
        reason="OpenMetadata not available or smoke tests not enabled",
    )
    def test_catalog_integration_creation(self, sample_asset_definition, sample_job_config):
        """Test that catalog integration can be created."""
        integration = create_catalog_integration(
            catalog_config=sample_job_config.catalog,
            asset_definition=sample_asset_definition,
            job_config=sample_job_config,
        )

        assert integration is not None
        assert isinstance(integration, OpenMetadataIntegration)

    @pytest.mark.skipif(
        not os.getenv("OPENMETADATA_API_URL") and not os.getenv("RUN_SMOKE_TESTS"),
        reason="OpenMetadata not available or smoke tests not enabled",
    )
    @patch("dativo_ingest.catalog_integration.requests.put")
    def test_push_lineage_mocked(self, mock_put, sample_asset_definition, sample_job_config):
        """Test lineage push with mocked requests."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_response.content = b'{"status": "ok"}'
        mock_put.return_value = mock_response

        integration = create_catalog_integration(
            catalog_config=sample_job_config.catalog,
            asset_definition=sample_asset_definition,
            job_config=sample_job_config,
        )

        source_entities = [
            {
                "fqn": "csv.smoke_test_object",
                "type": "table",
                "table": "smoke_test_object",
            }
        ]
        target_entity = {
            "fqn": "smoke_domain.smoke_product.smoke_test_table",
            "type": "table",
            "database": "smoke_domain",
            "schema": "smoke_product",
            "table": "smoke_test_table",
        }

        result = integration.push_lineage(source_entities, target_entity)

        assert result["status"] == "success"
        assert result["edges_pushed"] == 1
        mock_put.assert_called_once()

    @pytest.mark.skipif(
        not os.getenv("OPENMETADATA_API_URL") and not os.getenv("RUN_SMOKE_TESTS"),
        reason="OpenMetadata not available or smoke tests not enabled",
    )
    @patch("dativo_ingest.catalog_integration.requests.get")
    @patch("dativo_ingest.catalog_integration.requests.put")
    def test_push_metadata_mocked(self, mock_put, mock_get, sample_asset_definition, sample_job_config):
        """Test metadata push with mocked requests."""
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            "id": "test-entity-id",
            "tags": [],
            "owners": [],
        }
        mock_get.return_value = mock_get_response

        mock_put_response = Mock()
        mock_put_response.status_code = 200
        mock_put.return_value = mock_put_response

        integration = create_catalog_integration(
            catalog_config=sample_job_config.catalog,
            asset_definition=sample_asset_definition,
            job_config=sample_job_config,
        )

        entity = {
            "fqn": "smoke_domain.smoke_product.smoke_test_table",
            "type": "table",
        }

        result = integration.push_metadata(entity)

        assert result["status"] == "success"
        assert result["action"] == "updated"
        mock_get.assert_called_once()
        mock_put.assert_called_once()

    def test_metadata_derivation(self, sample_asset_definition, sample_job_config):
        """Test that metadata is correctly derived from asset and job config."""
        integration = create_catalog_integration(
            catalog_config=sample_job_config.catalog,
            asset_definition=sample_asset_definition,
            job_config=sample_job_config,
        )

        metadata = integration._derive_metadata()

        # Check tags
        assert "tags" in metadata
        assert "classification.fields.id" in metadata["tags"]
        assert metadata["tags"]["classification.fields.id"] == "pii"

        # Check owners
        assert "owners" in metadata
        assert "smoke-test@example.com" in metadata["owners"]

        # Check domain and data product
        assert metadata["domain"] == "smoke_domain"
        assert metadata["data_product"] == "smoke_product"

        # Check asset tags
        assert "asset_tags" in metadata
        assert "test" in metadata["asset_tags"] or any("test" in tag for tag in metadata["asset_tags"])

        # Check FinOps tags
        assert any("cost_center" in tag or "SMOKE-001" in tag for tag in metadata["asset_tags"])
