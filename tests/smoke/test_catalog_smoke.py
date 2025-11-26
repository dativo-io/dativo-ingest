"""Smoke tests for catalog integration.

These tests verify basic catalog functionality with a real OpenMetadata instance.
Run these tests with: pytest tests/smoke/test_catalog_smoke.py
"""

import os
import pytest
import time
import subprocess

from dativo_ingest.catalog.base import CatalogConfig
from dativo_ingest.catalog.openmetadata_client import OpenMetadataClient
from dativo_ingest.catalog.factory import CatalogClientFactory


def is_docker_available():
    """Check if docker is available."""
    try:
        result = subprocess.run(
            ["docker", "ps"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def is_openmetadata_running():
    """Check if OpenMetadata is running."""
    try:
        import requests
        response = requests.get(
            "http://localhost:8585/api/v1/system/version",
            timeout=5
        )
        return response.status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="session", autouse=True)
def start_openmetadata():
    """Start OpenMetadata using docker-compose if not already running."""
    if not is_docker_available():
        pytest.skip("Docker not available")
    
    if is_openmetadata_running():
        print("\n✓ OpenMetadata already running")
        yield
        return
    
    print("\n⏳ Starting OpenMetadata (this may take 2-3 minutes)...")
    
    # Start docker-compose
    try:
        subprocess.run(
            ["docker-compose", "-f", "docker-compose.catalog.yml", "up", "-d"],
            check=True,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        )
        
        # Wait for OpenMetadata to be ready (max 3 minutes)
        max_wait = 180
        interval = 10
        elapsed = 0
        
        while elapsed < max_wait:
            if is_openmetadata_running():
                print(f"✓ OpenMetadata ready after {elapsed} seconds")
                break
            print(f"⏳ Waiting for OpenMetadata... ({elapsed}s/{max_wait}s)")
            time.sleep(interval)
            elapsed += interval
        else:
            pytest.fail("OpenMetadata failed to start within 3 minutes")
        
        yield
        
        # Optionally stop after tests (comment out to keep running)
        # print("\n⏳ Stopping OpenMetadata...")
        # subprocess.run(
        #     ["docker-compose", "-f", "docker-compose.catalog.yml", "down"],
        #     cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        # )
        
    except subprocess.CalledProcessError as e:
        pytest.fail(f"Failed to start OpenMetadata: {e}")


class TestCatalogSmoke:
    """Smoke tests for catalog integration."""

    def test_openmetadata_connection(self):
        """Test basic OpenMetadata connection."""
        config = CatalogConfig(
            type="openmetadata",
            connection={"host_port": "http://localhost:8585/api"},
        )
        
        client = OpenMetadataClient(config)
        client.connect()
        
        assert client._client is not None
        client.close()

    def test_create_table_openmetadata(self):
        """Test creating a table in OpenMetadata."""
        from dativo_ingest.catalog.base import TableMetadata
        
        config = CatalogConfig(
            type="openmetadata",
            connection={
                "host_port": "http://localhost:8585/api",
                "service_name": "dativo_smoke_test",
            },
        )
        
        client = OpenMetadataClient(config)
        client.connect()
        
        metadata = TableMetadata(
            name="smoke_test_table",
            database="smoke_test_db",
            schema="smoke_test_schema",
            description="Smoke test table",
            owner="test@example.com",
            tags={"test": "smoke", "env": "dev"},
            columns=[
                {"name": "id", "type": "INTEGER", "required": True},
                {"name": "value", "type": "STRING"},
            ],
        )
        
        # Should not raise exception
        client.create_or_update_table(metadata)
        client.close()

    def test_catalog_factory(self):
        """Test catalog factory creates correct client."""
        config = CatalogConfig(
            type="openmetadata",
            connection={"host_port": "http://localhost:8585/api"},
        )
        
        client = CatalogClientFactory.create_client(config)
        assert isinstance(client, OpenMetadataClient)

    def test_catalog_from_job_config(self):
        """Test creating catalog client from job configuration."""
        job_config = {
            "catalog": {
                "type": "openmetadata",
                "connection": {"host_port": "http://localhost:8585/api"},
                "enabled": True,
            }
        }
        
        client = CatalogClientFactory.create_from_job_config(job_config)
        assert client is not None
        assert isinstance(client, OpenMetadataClient)

    def test_full_workflow(self):
        """Test complete catalog workflow."""
        from dativo_ingest.catalog.base import TableMetadata, LineageInfo
        from dativo_ingest.catalog.lineage_tracker import LineageTracker
        
        # Create client
        config = CatalogConfig(
            type="openmetadata",
            connection={
                "host_port": "http://localhost:8585/api",
                "service_name": "dativo_smoke_workflow",
            },
            push_lineage=True,
            push_metadata=True,
        )
        
        client = OpenMetadataClient(config)
        client.connect()
        
        # Create tracker
        tracker = LineageTracker(client)
        tracker.start_tracking()
        
        # Create table metadata
        metadata = TableMetadata(
            name="workflow_test_table",
            database="workflow_db",
            schema="workflow_schema",
            description="Workflow test table",
            owner="workflow-test@example.com",
            tags={"workflow": "test", "step": "smoke"},
            columns=[
                {"name": "id", "type": "INTEGER", "required": True},
                {"name": "data", "type": "STRING"},
            ],
        )
        
        # Push table metadata
        tracker.push_table_metadata(metadata)
        
        # End tracking
        tracker.end_tracking()
        
        # Build FQN
        service_name = "dativo_smoke_workflow"
        target_fqn = f"{service_name}.{metadata.database}.{metadata.schema}.{metadata.name}"
        
        # Push lineage
        lineage = LineageInfo(
            source_fqn="csv.test_source",
            target_fqn=target_fqn,
            pipeline_name="smoke_test_pipeline",
            records_read=100,
            records_written=100,
            status="success",
        )
        tracker.push_lineage(lineage)
        
        # Push tags
        tracker.push_tags(target_fqn, metadata.tags)
        
        client.close()
        
        print("✓ Full workflow completed successfully")
