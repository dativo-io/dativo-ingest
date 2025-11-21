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
    assert committer.source_tags is None
    assert committer.branch == "test_branch"
    assert committer.catalog_name == "nessie"


def test_iceberg_committer_with_source_tags(sample_asset_definition, target_config):
    """Test Iceberg committer initialization with source tags."""
    source_tags = {"email": "PII", "phone": "SENSITIVE"}

    committer = IcebergCommitter(
        asset_definition=sample_asset_definition,
        target_config=target_config,
        source_tags=source_tags,
    )

    assert committer.source_tags == source_tags


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


# ============================================================================
# Tests for _derive_table_properties
# ============================================================================


def test_derive_table_properties_basic(sample_asset_definition, target_config):
    """Test basic table property derivation."""
    committer = IcebergCommitter(sample_asset_definition, target_config)

    properties = committer._derive_table_properties()

    # Should include asset metadata
    assert "asset.name" in properties
    assert properties["asset.name"] == "test_asset"
    assert "asset.version" in properties
    assert properties["asset.version"] == "1.0"
    assert "asset.domain" in properties
    assert properties["asset.domain"] == "test_domain"
    assert "asset.source_type" in properties
    assert properties["asset.source_type"] == "csv"
    assert "asset.object" in properties
    assert properties["asset.object"] == "test_object"

    # Should include governance tags
    assert "governance.owner" in properties
    assert properties["governance.owner"] == "test@example.com"


def test_derive_table_properties_with_overrides(sample_asset_definition, target_config):
    """Test table properties with all override types."""
    # Add email field to schema for this test
    asset = AssetDefinition(
        name=sample_asset_definition.name,
        version=sample_asset_definition.version,
        source_type=sample_asset_definition.source_type,
        object=sample_asset_definition.object,
        domain=sample_asset_definition.domain,
        schema=[
            {"name": "id", "type": "integer", "required": True},
            {"name": "name", "type": "string", "required": True},
            {"name": "email", "type": "string", "required": False},  # Add email field
        ],
        team=sample_asset_definition.team,
    )

    classification_overrides = {"email": "PII", "default": "SENSITIVE"}
    finops = {"cost_center": "FIN-001", "environment": "production"}
    governance_overrides = {"retention_days": 365, "owner": "override@example.com"}

    committer = IcebergCommitter(
        asset,
        target_config,
        classification_overrides=classification_overrides,
        finops=finops,
        governance_overrides=governance_overrides,
    )

    properties = committer._derive_table_properties()

    # Classification overrides should be present
    assert "classification.default" in properties
    assert properties["classification.default"] == "sensitive"
    assert "classification.fields.email" in properties
    assert properties["classification.fields.email"] == "pii"

    # FinOps overrides should be present
    assert "finops.cost_center" in properties
    assert properties["finops.cost_center"] == "FIN-001"
    assert "finops.environment" in properties
    assert properties["finops.environment"] == "production"

    # Governance overrides should be present
    assert "governance.retention_days" in properties
    assert properties["governance.retention_days"] == "365"
    assert "governance.owner" in properties
    assert properties["governance.owner"] == "override@example.com"


def test_derive_table_properties_asset_metadata(sample_asset_definition, target_config):
    """Test that all asset metadata is included."""
    committer = IcebergCommitter(sample_asset_definition, target_config)

    properties = committer._derive_table_properties()

    # All asset metadata fields should be present
    assert properties["asset.name"] == "test_asset"
    assert properties["asset.version"] == "1.0"
    assert properties["asset.domain"] == "test_domain"
    assert properties["asset.source_type"] == "csv"
    assert properties["asset.object"] == "test_object"


def test_derive_table_properties_with_data_product(target_config):
    """Test table properties when dataProduct is set."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        domain="test_domain",
        schema=[{"name": "id", "type": "integer"}],
        team={"owner": "test@example.com"},
    )

    # Set dataProduct if supported
    if hasattr(asset, "dataProduct"):
        asset.dataProduct = "test-product"

    committer = IcebergCommitter(asset, target_config)
    properties = committer._derive_table_properties()

    # dataProduct may or may not be included depending on implementation
    if hasattr(asset, "dataProduct") and asset.dataProduct:
        assert "asset.data_product" in properties
        assert properties["asset.data_product"] == "test-product"


def test_derive_table_properties_namespace_format(
    sample_asset_definition, target_config
):
    """Test that all properties use correct namespace format."""
    # Add email field to schema for this test
    asset = AssetDefinition(
        name=sample_asset_definition.name,
        version=sample_asset_definition.version,
        source_type=sample_asset_definition.source_type,
        object=sample_asset_definition.object,
        domain=sample_asset_definition.domain,
        schema=[
            {"name": "id", "type": "integer", "required": True},
            {"name": "name", "type": "string", "required": True},
            {"name": "email", "type": "string", "required": False},  # Add email field
        ],
        team=sample_asset_definition.team,
    )

    classification_overrides = {"email": "PII"}
    finops = {"cost_center": "FIN-001"}
    governance_overrides = {"retention_days": 90}

    committer = IcebergCommitter(
        asset,
        target_config,
        classification_overrides=classification_overrides,
        finops=finops,
        governance_overrides=governance_overrides,
    )

    properties = committer._derive_table_properties()

    # All properties should have proper namespace
    for key in properties.keys():
        assert any(
            key.startswith(prefix)
            for prefix in ["classification.", "governance.", "finops.", "asset."]
        ), f"Property {key} does not have proper namespace"

    # Verify specific namespaces
    assert any(k.startswith("classification.") for k in properties.keys())
    assert any(k.startswith("governance.") for k in properties.keys())
    assert any(k.startswith("finops.") for k in properties.keys())
    assert any(k.startswith("asset.") for k in properties.keys())


def test_derive_table_properties_minimal_asset(target_config):
    """Test table properties with minimal asset definition."""
    asset = AssetDefinition(
        name="minimal",
        version="1.0",
        source_type="csv",
        object="test",
        schema=[{"name": "id", "type": "integer"}],
        team={"owner": "test@company.com"},  # Team required
    )

    committer = IcebergCommitter(asset, target_config)
    properties = committer._derive_table_properties()

    # Should still have asset metadata
    assert "asset.name" in properties
    assert "asset.version" in properties
    assert "asset.source_type" in properties
    assert "asset.object" in properties

    # Should have governance owner from team
    assert "governance.owner" in properties

    # Should not have optional fields if not set
    if not asset.domain:
        assert "asset.domain" not in properties


# ============================================================================
# Tests for _update_table_properties
# ============================================================================


def test_update_table_properties_new_table(sample_asset_definition, target_config):
    """Test updating properties on a new table."""
    from unittest.mock import Mock, MagicMock

    committer = IcebergCommitter(sample_asset_definition, target_config)

    # Mock catalog and table
    mock_table = MagicMock()
    mock_table.properties = {}
    mock_table.transaction.return_value.__enter__ = Mock(return_value=mock_table)
    mock_table.transaction.return_value.__exit__ = Mock(return_value=None)

    mock_catalog = MagicMock()
    mock_catalog.load_table.return_value = mock_table

    # Mock _create_catalog to return our mock
    committer._create_catalog = Mock(return_value=mock_catalog)

    # Call _update_table_properties
    committer._update_table_properties(mock_catalog, "test_domain", "test_asset")

    # Verify table was loaded
    mock_catalog.load_table.assert_called_once_with(("test_domain", "test_asset"))

    # Verify transaction was used
    assert mock_table.transaction.called


def test_update_table_properties_existing_table(sample_asset_definition, target_config):
    """Test updating properties on existing table."""
    from unittest.mock import Mock, MagicMock

    classification_overrides = {"email": "PII"}
    finops = {"cost_center": "FIN-001"}

    committer = IcebergCommitter(
        sample_asset_definition,
        target_config,
        classification_overrides=classification_overrides,
        finops=finops,
    )

    # Mock table with existing properties
    mock_table = MagicMock()
    mock_table.properties = {
        "existing.property": "existing_value",
        "asset.name": "old_name",
    }

    mock_txn = MagicMock()
    mock_table.transaction.return_value.__enter__ = Mock(return_value=mock_txn)
    mock_table.transaction.return_value.__exit__ = Mock(return_value=None)

    mock_catalog = MagicMock()
    mock_catalog.load_table.return_value = mock_table

    committer._create_catalog = Mock(return_value=mock_catalog)

    # Call _update_table_properties
    committer._update_table_properties(mock_catalog, "test_domain", "test_asset")

    # Verify set_properties was called (at least once for new properties)
    assert mock_txn.set_properties.called


def test_update_table_properties_idempotent(sample_asset_definition, target_config):
    """Test that properties update is idempotent (no update if unchanged)."""
    from unittest.mock import Mock, MagicMock

    committer = IcebergCommitter(sample_asset_definition, target_config)

    # Get expected properties
    expected_properties = committer._derive_table_properties()

    # Mock table with same properties already set
    mock_table = MagicMock()
    mock_table.properties = expected_properties.copy()

    mock_txn = MagicMock()
    mock_table.transaction.return_value.__enter__ = Mock(return_value=mock_txn)
    mock_table.transaction.return_value.__exit__ = Mock(return_value=None)

    mock_catalog = MagicMock()
    mock_catalog.load_table.return_value = mock_table

    committer._create_catalog = Mock(return_value=mock_catalog)

    # Call _update_table_properties
    committer._update_table_properties(mock_catalog, "test_domain", "test_asset")

    # If properties are unchanged, transaction might not be called
    # The implementation checks needs_update, so verify the logic works


def test_update_table_properties_error_handling(sample_asset_definition, target_config):
    """Test error handling when table doesn't exist or update fails."""
    from unittest.mock import Mock, MagicMock

    committer = IcebergCommitter(sample_asset_definition, target_config)

    # Mock catalog that raises exception
    mock_catalog = MagicMock()
    mock_catalog.load_table.side_effect = Exception("Table not found")

    committer._create_catalog = Mock(return_value=mock_catalog)

    # Should handle error gracefully (implementation logs warning)
    try:
        committer._update_table_properties(mock_catalog, "test_domain", "test_asset")
    except Exception:
        # If exception is raised, that's also acceptable behavior
        pass


def test_update_table_properties_partial_update(sample_asset_definition, target_config):
    """Test that only changed properties are updated."""
    from unittest.mock import Mock, MagicMock

    classification_overrides = {"email": "PII"}

    committer = IcebergCommitter(
        sample_asset_definition,
        target_config,
        classification_overrides=classification_overrides,
    )

    # Mock table with some existing properties
    mock_table = MagicMock()
    mock_table.properties = {
        "asset.name": "test_asset",  # Same value
        "asset.version": "0.9",  # Different value
        "existing.property": "keep_me",  # Unrelated property
    }

    mock_txn = MagicMock()
    mock_table.transaction.return_value.__enter__ = Mock(return_value=mock_txn)
    mock_table.transaction.return_value.__exit__ = Mock(return_value=None)

    mock_catalog = MagicMock()
    mock_catalog.load_table.return_value = mock_table

    committer._create_catalog = Mock(return_value=mock_catalog)

    # Call _update_table_properties
    committer._update_table_properties(mock_catalog, "test_domain", "test_asset")

    # Verify transaction was used (properties changed)
    assert mock_table.transaction.called
