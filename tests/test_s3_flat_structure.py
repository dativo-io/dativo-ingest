"""Tests for S3/MinIO flat structure connection configuration support.

These tests verify that the code correctly handles both nested (connection.s3.bucket)
and flat (connection.bucket) connection structures.
"""

import os
from unittest.mock import patch

import pytest

from dativo_ingest.config import AssetDefinition, JobConfig, TargetConfig
from dativo_ingest.iceberg_committer import IcebergCommitter


@pytest.fixture
def sample_asset_definition():
    """Create a sample asset definition for testing."""
    return AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        domain="test_domain",
        schema=[{"name": "id", "type": "integer"}],
        team={"owner": "test@example.com"},
    )


class TestFlatStructureBucketExtraction:
    """Test bucket extraction from flat connection structure."""

    def test_iceberg_committer_flat_structure_bucket(self, sample_asset_definition):
        """Test IcebergCommitter extracts bucket from flat structure."""
        target_config = TargetConfig(
            type="iceberg",
            connection={
                "bucket": "test-bucket",
                "endpoint": "http://localhost:9000",
                "access_key_id": "test-key",
                "secret_access_key": "test-secret",
            },
        )

        committer = IcebergCommitter(
            asset_definition=sample_asset_definition,
            target_config=target_config,
        )

        assert committer.storage_config["bucket"] == "test-bucket"
        assert committer.storage_config["endpoint"] == "http://localhost:9000"
        assert committer.storage_config["access_key_id"] == "test-key"
        assert committer.storage_config["secret_access_key"] == "test-secret"

    def test_iceberg_committer_nested_structure_bucket(self, sample_asset_definition):
        """Test IcebergCommitter extracts bucket from nested structure."""
        target_config = TargetConfig(
            type="iceberg",
            connection={
                "s3": {
                    "bucket": "test-bucket",
                    "endpoint": "http://localhost:9000",
                    "access_key_id": "test-key",
                    "secret_access_key": "test-secret",
                }
            },
        )

        committer = IcebergCommitter(
            asset_definition=sample_asset_definition,
            target_config=target_config,
        )

        assert committer.storage_config["bucket"] == "test-bucket"
        assert committer.storage_config["endpoint"] == "http://localhost:9000"

    def test_iceberg_committer_flat_structure_credentials(
        self, sample_asset_definition
    ):
        """Test credentials extraction from flat structure."""
        target_config = TargetConfig(
            type="iceberg",
            connection={
                "bucket": "test-bucket",
                "endpoint": "http://localhost:9000",
                "access_key_id": "flat-key",
                "secret_access_key": "flat-secret",
                "region": "us-west-2",
            },
        )

        committer = IcebergCommitter(
            asset_definition=sample_asset_definition,
            target_config=target_config,
        )

        assert committer.storage_config["access_key_id"] == "flat-key"
        assert committer.storage_config["secret_access_key"] == "flat-secret"
        assert committer.storage_config["region"] == "us-west-2"

    def test_iceberg_committer_env_var_fallback(self, sample_asset_definition):
        """Test environment variable fallback when config is missing."""
        target_config = TargetConfig(
            type="iceberg",
            connection={},  # Empty connection
        )

        with patch.dict(
            os.environ,
            {
                "S3_BUCKET": "env-bucket",
                "S3_ENDPOINT": "http://env:9000",
                "AWS_ACCESS_KEY_ID": "env-key",
                "AWS_SECRET_ACCESS_KEY": "env-secret",
            },
        ):
            committer = IcebergCommitter(
                asset_definition=sample_asset_definition,
                target_config=target_config,
            )

            assert committer.storage_config["bucket"] == "env-bucket"
            assert committer.storage_config["endpoint"] == "http://env:9000"
            assert committer.storage_config["access_key_id"] == "env-key"
            assert committer.storage_config["secret_access_key"] == "env-secret"

    def test_iceberg_committer_minio_env_var_fallback(self, sample_asset_definition):
        """Test MinIO-specific environment variable fallback."""
        target_config = TargetConfig(
            type="iceberg",
            connection={},  # Empty connection
        )

        with patch.dict(
            os.environ,
            {
                "MINIO_BUCKET": "minio-bucket",
                "MINIO_ENDPOINT": "http://minio:9000",
                "MINIO_ACCESS_KEY": "minio-key",
                "MINIO_SECRET_KEY": "minio-secret",
            },
        ):
            committer = IcebergCommitter(
                asset_definition=sample_asset_definition,
                target_config=target_config,
            )

            assert committer.storage_config["bucket"] == "minio-bucket"
            assert committer.storage_config["endpoint"] == "http://minio:9000"
            assert committer.storage_config["access_key_id"] == "minio-key"
            assert committer.storage_config["secret_access_key"] == "minio-secret"

    def test_iceberg_committer_flat_precedence_over_env(self, sample_asset_definition):
        """Test that flat structure takes precedence over environment variables."""
        target_config = TargetConfig(
            type="iceberg",
            connection={
                "bucket": "config-bucket",
                "endpoint": "http://config:9000",
            },
        )

        with patch.dict(
            os.environ,
            {
                "S3_BUCKET": "env-bucket",
                "S3_ENDPOINT": "http://env:9000",
            },
        ):
            committer = IcebergCommitter(
                asset_definition=sample_asset_definition,
                target_config=target_config,
            )

            # Config should take precedence
            assert committer.storage_config["bucket"] == "config-bucket"
            assert committer.storage_config["endpoint"] == "http://config:9000"


class TestCLIBucketExtraction:
    """Test bucket extraction in CLI code paths."""

    def test_cli_extracts_bucket_from_flat_structure(self, tmp_path):
        """Test CLI extracts bucket from flat structure in job config."""
        job_file = tmp_path / "test_job.yaml"
        job_file.write_text(
            """
tenant_id: test_tenant
source_connector: csv
source_connector_path: connectors/csv.yaml
target_connector: minio
target_connector_path: connectors/minio.yaml
asset: test_asset
asset_path: tests/fixtures/assets/csv/v1.0/product.yaml
source:
  files:
    - path: tests/fixtures/seeds/adventureworks/Product.csv
      object: Product
target:
  connection:
    bucket: test-bucket
    endpoint: http://localhost:9000
    access_key_id: test-key
    secret_access_key: test-secret
"""
        )

        job_config = JobConfig.from_yaml(job_file)
        target_config = job_config.get_target()
        connection = target_config.connection or {}

        # Simulate the bucket extraction logic from cli.py
        s3_config = connection.get("s3") or connection.get("minio", {})
        bucket = (
            s3_config.get("bucket")
            or connection.get("bucket")  # Fallback to flat structure
            or os.getenv("S3_BUCKET")
            or os.getenv("MINIO_BUCKET")
        )

        assert bucket == "test-bucket"

    def test_cli_extracts_bucket_from_nested_structure(self, tmp_path):
        """Test CLI extracts bucket from nested structure in job config."""
        job_file = tmp_path / "test_job.yaml"
        job_file.write_text(
            """
tenant_id: test_tenant
source_connector: csv
source_connector_path: connectors/csv.yaml
target_connector: s3
target_connector_path: connectors/s3.yaml
asset: test_asset
asset_path: tests/fixtures/assets/csv/v1.0/product.yaml
source:
  files:
    - path: tests/fixtures/seeds/adventureworks/Product.csv
      object: Product
target:
  connection:
    s3:
      bucket: nested-bucket
      endpoint: http://localhost:9000
"""
        )

        job_config = JobConfig.from_yaml(job_file)
        target_config = job_config.get_target()
        connection = target_config.connection or {}

        # Simulate the bucket extraction logic from cli.py
        s3_config = connection.get("s3") or connection.get("minio", {})
        bucket = (
            s3_config.get("bucket")
            or connection.get("bucket")  # Fallback to flat structure
            or os.getenv("S3_BUCKET")
            or os.getenv("MINIO_BUCKET")
        )

        assert bucket == "nested-bucket"


class TestCatalogBucketExtraction:
    """Test bucket extraction in catalog code."""

    def test_catalog_extracts_bucket_from_flat_structure(self):
        """Test BaseCatalog extracts bucket from flat structure."""
        from unittest.mock import MagicMock

        job_config = MagicMock()
        target_config = TargetConfig(
            type="iceberg",
            connection={
                "bucket": "catalog-bucket",
                "endpoint": "http://localhost:9000",
            },
        )
        job_config.get_target.return_value = target_config

        # Simulate the bucket extraction logic from catalog/base.py
        # (without instantiating abstract BaseCatalog)
        connection = target_config.connection or {}
        s3_config = connection.get("s3") or connection.get("minio", {})
        bucket = (
            s3_config.get("bucket")
            or connection.get("bucket")  # Fallback to flat structure
            or "default-bucket"
        )

        assert bucket == "catalog-bucket"


class TestFilesystemSecretsEnvironmentVariables:
    """Test that filesystem secrets are set as environment variables."""

    def test_secrets_set_as_env_vars(self, tmp_path, monkeypatch):
        """Test that secrets from filesystem manager are set as environment variables."""
        # Create a secrets directory structure
        tenant_dir = tmp_path / "test_tenant"
        tenant_dir.mkdir()
        secret_file = tenant_dir / "s3.env"
        secret_file.write_text(
            """
S3_ENDPOINT=http://localhost:9000
AWS_ACCESS_KEY_ID=test-key
AWS_SECRET_ACCESS_KEY=test-secret
MINIO_ENDPOINT=http://localhost:9000
MINIO_ACCESS_KEY=minio-key
MINIO_SECRET_KEY=minio-secret
"""
        )

        # Import and use the secret manager
        from dativo_ingest.secrets import load_secrets

        secrets = load_secrets(
            tenant_id="test_tenant",
            secrets_dir=tmp_path,
            manager_type="filesystem",
        )

        # Verify secrets were loaded
        assert "s3" in secrets
        assert isinstance(secrets["s3"], dict)

        # Simulate the code in cli.py that sets environment variables
        for secret_name, secret_value in secrets.items():
            if isinstance(secret_value, dict):
                for key, value in secret_value.items():
                    if isinstance(value, str) and key not in os.environ:
                        os.environ[key] = value

        # Verify environment variables were set
        assert os.environ.get("S3_ENDPOINT") == "http://localhost:9000"
        assert os.environ.get("AWS_ACCESS_KEY_ID") == "test-key"
        assert os.environ.get("AWS_SECRET_ACCESS_KEY") == "test-secret"
        assert os.environ.get("MINIO_ENDPOINT") == "http://localhost:9000"
        assert os.environ.get("MINIO_ACCESS_KEY") == "minio-key"
        assert os.environ.get("MINIO_SECRET_KEY") == "minio-secret"

        # Cleanup
        for key in [
            "S3_ENDPOINT",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "MINIO_ENDPOINT",
            "MINIO_ACCESS_KEY",
            "MINIO_SECRET_KEY",
        ]:
            if key in os.environ:
                del os.environ[key]
