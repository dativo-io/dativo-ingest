"""Unit tests for catalog factory."""

import pytest

from dativo_ingest.catalog.base import CatalogConfig
from dativo_ingest.catalog.factory import CatalogClientFactory
from dativo_ingest.catalog.openmetadata_client import OpenMetadataClient
from dativo_ingest.catalog.glue_client import GlueClient
from dativo_ingest.catalog.unity_client import UnityClient
from dativo_ingest.catalog.nessie_client import NessieClient


class TestCatalogClientFactory:
    """Test cases for CatalogClientFactory."""

    def test_create_openmetadata_client(self):
        """Test creating OpenMetadata client."""
        config = CatalogConfig(
            type="openmetadata",
            connection={"host_port": "http://localhost:8585/api"},
        )
        client = CatalogClientFactory.create_client(config)
        assert isinstance(client, OpenMetadataClient)
        assert client.config.type == "openmetadata"

    def test_create_glue_client(self):
        """Test creating AWS Glue client."""
        config = CatalogConfig(
            type="aws_glue",
            connection={"region": "us-east-1"},
        )
        client = CatalogClientFactory.create_client(config)
        assert isinstance(client, GlueClient)
        assert client.config.type == "aws_glue"

    def test_create_unity_client(self):
        """Test creating Databricks Unity Catalog client."""
        config = CatalogConfig(
            type="databricks_unity",
            connection={"host": "https://my-workspace.databricks.com", "token": "test"},
        )
        client = CatalogClientFactory.create_client(config)
        assert isinstance(client, UnityClient)
        assert client.config.type == "databricks_unity"

    def test_create_nessie_client(self):
        """Test creating Nessie client."""
        config = CatalogConfig(
            type="nessie",
            connection={"uri": "http://localhost:19120", "branch": "main"},
        )
        client = CatalogClientFactory.create_client(config)
        assert isinstance(client, NessieClient)
        assert client.config.type == "nessie"

    def test_unsupported_catalog_type(self):
        """Test error for unsupported catalog type."""
        config = CatalogConfig(
            type="unsupported_catalog",
            connection={},
        )
        with pytest.raises(ValueError, match="Unsupported catalog type"):
            CatalogClientFactory.create_client(config)

    def test_create_from_job_config_enabled(self):
        """Test creating client from job config when enabled."""
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

    def test_create_from_job_config_disabled(self):
        """Test that no client is created when catalog is disabled."""
        job_config = {
            "catalog": {
                "type": "openmetadata",
                "connection": {"host_port": "http://localhost:8585/api"},
                "enabled": False,
            }
        }
        client = CatalogClientFactory.create_from_job_config(job_config)
        assert client is None

    def test_create_from_job_config_no_catalog(self):
        """Test that no client is created when catalog config is missing."""
        job_config = {}
        client = CatalogClientFactory.create_from_job_config(job_config)
        assert client is None

    def test_create_from_job_config_invalid(self):
        """Test error for invalid catalog configuration."""
        job_config = {
            "catalog": {
                # Missing required 'type' field
                "connection": {},
            }
        }
        with pytest.raises(ValueError, match="Invalid catalog configuration"):
            CatalogClientFactory.create_from_job_config(job_config)
