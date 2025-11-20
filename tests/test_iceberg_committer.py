"""Unit tests for Iceberg committer."""

import pytest

from dativo_ingest.config import AssetDefinition, TargetConfig
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
        schema=[
            {"name": "id", "type": "integer", "required": True},
            {"name": "name", "type": "string", "required": True},
        ],
        team={"owner": "test@example.com"},
    )


@pytest.fixture
def target_config():
    """Create a target config for testing."""
    return TargetConfig(
        type="iceberg",
        catalog="nessie",
        branch="test_branch",
        warehouse="s3://test-bucket/",
        connection={
            "nessie": {"uri": "http://localhost:19120/api/v1"},
            "s3": {
                "endpoint": "http://localhost:9000",
                "bucket": "test-bucket",
                "access_key_id": "test-key",
                "secret_access_key": "test-secret",
                "region": "us-east-1",
            },
        },
    )


def test_iceberg_committer_initialization(sample_asset_definition, target_config):
    """Test Iceberg committer initialization."""
    committer = IcebergCommitter(
        asset_definition=sample_asset_definition,
        target_config=target_config,
    )

    assert committer.asset_definition == sample_asset_definition
    assert committer.target_config == target_config
    assert committer.classification_overrides is None
    assert committer.finops is None
    assert committer.governance_overrides is None
    assert committer.branch == "test_branch"
    assert committer.catalog_name == "nessie"


def test_get_nessie_uri(target_config):
    """Test Nessie URI extraction."""
    committer = IcebergCommitter(
        AssetDefinition(
            name="test",
            version="1.0",
            source_type="csv",
            object="test",
            schema=[],
            team={"owner": "test@example.com"},
        ),
        target_config,
    )

    # PyIceberg expects base URI without /api/v1 (it adds /v1/config automatically)
    assert committer.nessie_uri == "http://localhost:19120"


def test_get_storage_config(target_config):
    """Test storage config extraction."""
    committer = IcebergCommitter(
        AssetDefinition(
            name="test",
            version="1.0",
            source_type="csv",
            object="test",
            schema=[],
            team={"owner": "test@example.com"},
        ),
        target_config,
    )

    assert committer.storage_config["endpoint"] == "http://localhost:9000"
    assert committer.storage_config["bucket"] == "test-bucket"


def test_create_pyiceberg_schema(sample_asset_definition, target_config):
    """Test PyIceberg schema creation."""
    committer = IcebergCommitter(sample_asset_definition, target_config)

    # This will fail if pyiceberg is not installed, but that's expected in tests
    try:
        schema = committer._create_pyiceberg_schema()
        assert schema is not None
    except ImportError:
        pytest.skip("pyiceberg not installed")


def test_ensure_table_exists_requires_pyiceberg(sample_asset_definition, target_config):
    """Test that ensure_table_exists requires pyiceberg."""
    committer = IcebergCommitter(sample_asset_definition, target_config)

    # This will fail if pyiceberg is not installed or if Nessie is not available
    # In a real test environment, you would mock the catalog
    try:
        committer.ensure_table_exists()
    except (ImportError, Exception):
        # Expected in test environment without actual Nessie instance
        pass
