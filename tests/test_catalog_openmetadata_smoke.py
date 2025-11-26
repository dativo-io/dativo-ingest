"""OpenMetadata smoke tests for catalog integration."""

import os
import time
from pathlib import Path

import pytest
import requests

from dativo_ingest.catalog.openmetadata import OpenMetadataCatalog
from dativo_ingest.catalog.base import CatalogLineage, CatalogMetadata


@pytest.fixture(scope="module")
def openmetadata_available():
    """Check if OpenMetadata is available for smoke tests."""
    api_endpoint = os.getenv(
        "OPENMETADATA_API_ENDPOINT", "http://localhost:8585/api"
    )
    try:
        response = requests.get(
            f"{api_endpoint}/v1/system/version", timeout=5
        )
        return response.status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def openmetadata_catalog(openmetadata_available):
    """Create OpenMetadata catalog instance for smoke tests."""
    if not openmetadata_available:
        pytest.skip("OpenMetadata not available for smoke tests")

    connection = {
        "api_endpoint": os.getenv(
            "OPENMETADATA_API_ENDPOINT", "http://localhost:8585/api"
        ),
        "auth_provider": "basic",
        "username": os.getenv("OPENMETADATA_USERNAME", "admin"),
        "password": os.getenv("OPENMETADATA_PASSWORD", "admin"),
        "database_service": os.getenv("OPENMETADATA_DATABASE_SERVICE", "default"),
    }

    return OpenMetadataCatalog(connection, database="test_schema")


@pytest.mark.smoke
class TestOpenMetadataSmoke:
    """Smoke tests for OpenMetadata catalog integration."""

    def test_table_exists_nonexistent(self, openmetadata_catalog):
        """Test checking if non-existent table returns False."""
        assert openmetadata_catalog.table_exists("nonexistent_table") is False

    def test_create_table_and_push_metadata(self, openmetadata_catalog):
        """Test creating a table and pushing metadata."""
        table_name = f"test_table_{int(time.time())}"
        schema = [
            {"name": "id", "type": "int", "description": "ID field"},
            {"name": "name", "type": "string", "description": "Name field"},
        ]

        # Create table
        openmetadata_catalog.create_table_if_not_exists(
            table_name=table_name,
            schema=schema,
            location="s3://test-bucket/test-table/",
            metadata=CatalogMetadata(
                name=table_name,
                description="Test table for smoke tests",
                tags=["test", "smoke"],
                owners=["admin"],
            ),
        )

        # Verify table exists
        assert openmetadata_catalog.table_exists(table_name) is True

        # Push updated metadata
        openmetadata_catalog.push_metadata(
            table_name=table_name,
            metadata=CatalogMetadata(
                name=table_name,
                description="Updated description",
                tags=["test", "smoke", "updated"],
            ),
        )

    def test_push_lineage(self, openmetadata_catalog):
        """Test pushing lineage information."""
        source_table = f"source_table_{int(time.time())}"
        target_table = f"target_table_{int(time.time())}"

        # Create source and target tables
        schema = [{"name": "id", "type": "int"}]
        openmetadata_catalog.create_table_if_not_exists(
            table_name=source_table,
            schema=schema,
            location="s3://test-bucket/source/",
        )
        openmetadata_catalog.create_table_if_not_exists(
            table_name=target_table,
            schema=schema,
            location="s3://test-bucket/target/",
        )

        # Push lineage
        lineage = CatalogLineage(
            source_entities=[
                {
                    "database": "test_schema",
                    "table": source_table,
                    "fqn": f"default.test_schema.{source_table}",
                }
            ],
            target_entity={
                "database": "test_schema",
                "table": target_table,
                "fqn": f"default.test_schema.{target_table}",
            },
            process_name="test_etl_process",
            process_type="etl",
        )

        openmetadata_catalog.push_lineage(lineage)

    def test_full_integration(self, openmetadata_catalog):
        """Test full integration: create table, push metadata, push lineage."""
        table_name = f"integration_test_{int(time.time())}"
        schema = [
            {"name": "id", "type": "int", "nullable": False},
            {"name": "email", "type": "string", "nullable": True},
            {"name": "created_at", "type": "timestamp", "nullable": False},
        ]

        # Step 1: Create table with metadata
        metadata = CatalogMetadata(
            name=table_name,
            description="Integration test table",
            tags=["integration", "test"],
            owners=["admin"],
            classification=["PII"],
            custom_properties={"domain": "test", "dataProduct": "test_product"},
        )

        openmetadata_catalog.create_table_if_not_exists(
            table_name=table_name,
            schema=schema,
            location="s3://test-bucket/integration/",
            metadata=metadata,
        )

        # Step 2: Verify table exists
        assert openmetadata_catalog.table_exists(table_name) is True

        # Step 3: Update metadata
        updated_metadata = CatalogMetadata(
            name=table_name,
            description="Updated integration test table",
            tags=["integration", "test", "updated"],
        )
        openmetadata_catalog.push_metadata(table_name, updated_metadata)

        # Step 4: Push lineage
        lineage = CatalogLineage(
            source_entities=[
                {
                    "database": "test_schema",
                    "table": "source_table",
                    "fqn": "default.test_schema.source_table",
                }
            ],
            target_entity={
                "database": "test_schema",
                "table": table_name,
                "fqn": f"default.test_schema.{table_name}",
            },
            process_name="integration_test_process",
        )
        openmetadata_catalog.push_lineage(lineage)
