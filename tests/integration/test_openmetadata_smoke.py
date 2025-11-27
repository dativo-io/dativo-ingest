"""OpenMetadata smoke tests for catalog integration.

These tests require OpenMetadata to be running via docker-compose.
Run: docker-compose -f tests/integration/docker-compose-openmetadata.yml up -d
"""

import os
import time
from datetime import datetime

import pytest

from dativo_ingest.catalog_integrations import LineageInfo, OpenMetadataCatalogClient
from dativo_ingest.config import AssetDefinition, CatalogConfig


@pytest.fixture(scope="module")
def openmetadata_available():
    """Check if OpenMetadata is available."""
    import requests

    om_host = os.getenv("OPENMETADATA_HOST_PORT", "http://localhost:8585/api")
    try:
        response = requests.get(f"{om_host}/v1/system/version", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


@pytest.fixture
def catalog_config():
    """Create OpenMetadata catalog configuration."""
    return CatalogConfig(
        type="openmetadata",
        enabled=True,
        connection={
            "host_port": os.getenv(
                "OPENMETADATA_HOST_PORT", "http://localhost:8585/api"
            ),
            "service_name": "dativo_test_ingestion",
        },
        options={
            "database": "test_db",
            "schema": "default",
        },
    )


@pytest.fixture
def sample_asset():
    """Create a sample asset definition."""
    return AssetDefinition(
        name="test_users_table",
        version="1.0",
        source_type="postgres",
        object="users",
        schema=[
            {
                "name": "id",
                "type": "integer",
                "required": True,
                "description": "User ID",
            },
            {
                "name": "email",
                "type": "string",
                "required": True,
                "description": "User email",
            },
            {
                "name": "name",
                "type": "string",
                "required": True,
                "description": "Full name",
            },
            {
                "name": "created_at",
                "type": "timestamp",
                "required": True,
                "description": "Creation timestamp",
            },
        ],
        team={"owner": "data-team@company.com"},
        domain="analytics",
        tags=["test", "users", "smoke-test"],
    )


@pytest.mark.skipif(
    not os.getenv("RUN_OPENMETADATA_TESTS"),
    reason="OpenMetadata tests disabled (set RUN_OPENMETADATA_TESTS=1 to enable)",
)
class TestOpenMetadataSmoke:
    """Smoke tests for OpenMetadata integration."""

    def test_client_connection(self, catalog_config, openmetadata_available):
        """Test that we can connect to OpenMetadata."""
        if not openmetadata_available:
            pytest.skip("OpenMetadata is not available")

        client = OpenMetadataCatalogClient(catalog_config)
        om_client = client._get_client()

        # Test basic connectivity
        assert om_client is not None

    def test_push_lineage_creates_entities(
        self, catalog_config, sample_asset, openmetadata_available
    ):
        """Test pushing lineage creates all necessary entities."""
        if not openmetadata_available:
            pytest.skip("OpenMetadata is not available")

        client = OpenMetadataCatalogClient(catalog_config)

        lineage_info = LineageInfo(
            source_type="postgres",
            source_name="users",
            target_type="iceberg",
            target_name="test_users_table",
            asset_definition=sample_asset,
            record_count=1000,
            file_count=5,
            total_bytes=1024000,
            file_paths=[
                "s3://test-bucket/analytics/users/file1.parquet",
                "s3://test-bucket/analytics/users/file2.parquet",
            ],
            execution_time=datetime.utcnow(),
        )

        # Push lineage
        result = client.push_lineage(lineage_info)

        # Verify result
        assert result["status"] == "success"
        assert result["catalog"] == "openmetadata"
        assert "table_fqn" in result
        assert "table_id" in result

        # Verify table FQN format
        expected_fqn = "dativo_test_ingestion.test_db.default.test_users_table"
        assert result["table_fqn"] == expected_fqn

    def test_push_lineage_with_tags_and_owner(
        self, catalog_config, openmetadata_available
    ):
        """Test pushing lineage with tags and owner information."""
        if not openmetadata_available:
            pytest.skip("OpenMetadata is not available")

        # Create asset with comprehensive metadata
        asset = AssetDefinition(
            name="test_orders_table",
            version="1.0",
            source_type="stripe",
            object="orders",
            schema=[
                {
                    "name": "order_id",
                    "type": "string",
                    "required": True,
                    "description": "Order ID",
                },
                {
                    "name": "customer_email",
                    "type": "string",
                    "required": True,
                    "description": "Customer email",
                },
                {
                    "name": "amount",
                    "type": "double",
                    "required": True,
                    "description": "Order amount",
                },
                {
                    "name": "created",
                    "type": "timestamp",
                    "required": True,
                    "description": "Order timestamp",
                },
            ],
            team={
                "owner": "finance-team@company.com",
                "roles": [
                    {
                        "name": "Data Engineer",
                        "email": "engineer@company.com",
                        "responsibility": "ingestion",
                    }
                ],
            },
            domain="sales",
            tags=["stripe", "orders", "revenue"],
            compliance={
                "classification": ["PII"],
                "regulations": ["GDPR", "CCPA"],
                "retention_days": 90,
            },
        )

        client = OpenMetadataCatalogClient(catalog_config)

        lineage_info = LineageInfo(
            source_type="stripe",
            source_name="orders",
            target_type="iceberg",
            target_name="test_orders_table",
            asset_definition=asset,
            record_count=500,
            file_count=2,
            total_bytes=512000,
            file_paths=["s3://test-bucket/sales/orders/file1.parquet"],
            execution_time=datetime.utcnow(),
            classification_overrides={"customer_email": "PII"},
        )

        # Push lineage
        result = client.push_lineage(lineage_info)

        # Verify result
        assert result["status"] == "success"
        assert "table_id" in result

    def test_push_lineage_idempotent(
        self, catalog_config, sample_asset, openmetadata_available
    ):
        """Test that pushing lineage multiple times is idempotent."""
        if not openmetadata_available:
            pytest.skip("OpenMetadata is not available")

        client = OpenMetadataCatalogClient(catalog_config)

        lineage_info = LineageInfo(
            source_type="postgres",
            source_name="users",
            target_type="iceberg",
            target_name="test_users_idempotent",
            asset_definition=AssetDefinition(
                name="test_users_idempotent",
                version="1.0",
                source_type="postgres",
                object="users",
                schema=[
                    {"name": "id", "type": "integer", "required": True},
                    {"name": "name", "type": "string", "required": True},
                ],
                team={"owner": "test@company.com"},
                domain="analytics",
            ),
            record_count=100,
            file_count=1,
            total_bytes=10240,
            file_paths=["s3://bucket/path/file.parquet"],
            execution_time=datetime.utcnow(),
        )

        # Push lineage first time
        result1 = client.push_lineage(lineage_info)
        assert result1["status"] == "success"
        table_id_1 = result1["table_id"]

        # Wait a bit to ensure timestamp difference
        time.sleep(1)

        # Push lineage second time (should update, not create new)
        result2 = client.push_lineage(lineage_info)
        assert result2["status"] == "success"
        table_id_2 = result2["table_id"]

        # Should be the same table ID
        assert table_id_1 == table_id_2


@pytest.mark.skipif(
    not os.getenv("RUN_OPENMETADATA_TESTS"),
    reason="OpenMetadata tests disabled",
)
class TestOpenMetadataEndToEnd:
    """End-to-end tests for OpenMetadata integration."""

    def test_full_ingestion_flow_with_catalog(
        self, catalog_config, openmetadata_available, tmp_path
    ):
        """Test full ingestion flow with catalog lineage push."""
        if not openmetadata_available:
            pytest.skip("OpenMetadata is not available")

        from dativo_ingest.config import JobConfig

        # Create test job with catalog config
        job_yaml = tmp_path / "test_job.yaml"
        job_yaml.write_text(
            """
tenant_id: test_tenant
source_connector_path: connectors/csv.yaml
target_connector_path: connectors/iceberg.yaml
asset_path: tests/fixtures/assets/csv/v1.0/employee.yaml

catalog:
  type: openmetadata
  enabled: true
  connection:
    host_port: http://localhost:8585/api
    service_name: dativo_e2e_test
  options:
    database: e2e_test_db
    schema: default

source:
  files:
    - path: tests/fixtures/seeds/employee/Employee_Train_Dataset.csv
      object: Employee

target:
  connection:
    s3:
      endpoint: ${S3_ENDPOINT}
      bucket: test-bucket
      access_key_id: ${AWS_ACCESS_KEY_ID}
      secret_access_key: ${AWS_SECRET_ACCESS_KEY}

logging:
  level: INFO
"""
        )

        # Note: This test would require full infrastructure setup
        # For now, we just verify the job config can be loaded with catalog
        job = JobConfig.from_yaml(job_yaml)
        assert job.catalog is not None
        assert job.catalog.type == "openmetadata"
        assert job.catalog.enabled is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
