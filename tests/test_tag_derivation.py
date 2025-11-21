"""Tests for tag derivation module."""

import pytest

from dativo_ingest.config import AssetDefinition
from dativo_ingest.tag_derivation import TagDerivation, derive_tags_from_asset


@pytest.fixture
def sample_asset_definition():
    """Create a sample asset definition for testing."""
    return AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[
            {"name": "id", "type": "integer", "required": True},
            {"name": "email", "type": "string", "required": False},
            {"name": "first_name", "type": "string", "required": False},
            {"name": "salary", "type": "double", "required": False},
            {"name": "status", "type": "string", "required": False},
        ],
        team={"owner": "data-team@company.com"},
        compliance={
            "classification": ["PII", "SENSITIVE"],
            "retention_days": 90,
            "regulations": ["GDPR", "CCPA"],
        },
        finops={
            "cost_center": "FIN-001",
            "business_tags": ["finance", "reporting"],
            "project": "data-platform",
        },
    )


def test_derive_field_classifications(sample_asset_definition):
    """Test field-level classification derivation - ONLY explicit tags."""
    derivation = TagDerivation(asset_definition=sample_asset_definition)
    
    classifications = derivation.derive_field_classifications()
    
    # NO automatic detection - fields without explicit classification are skipped
    # email, first_name, salary do NOT have explicit classification in the schema
    # so they should NOT appear in classifications
    assert len(classifications) == 0, "Should not auto-detect any classifications"


def test_derive_field_classifications_with_overrides(sample_asset_definition):
    """Test field-level classification with overrides - ONLY explicit tags."""
    classification_overrides = {
        "status": "confidential",
        "email": "high_pii",
    }
    
    derivation = TagDerivation(
        asset_definition=sample_asset_definition,
        classification_overrides=classification_overrides,
    )
    
    classifications = derivation.derive_field_classifications()
    
    # Only overrides should be present - NO auto-detection
    assert classifications["email"] == "high_pii"
    assert classifications["status"] == "confidential"
    
    # No automatic detection - other fields not present
    assert "first_name" not in classifications
    assert "salary" not in classifications


def test_derive_default_classification(sample_asset_definition):
    """Test default table-level classification derivation."""
    derivation = TagDerivation(asset_definition=sample_asset_definition)
    
    default_classification = derivation.derive_default_classification()
    
    # Should use first classification from compliance section
    assert default_classification == "pii"


def test_derive_governance_tags(sample_asset_definition):
    """Test governance tag derivation."""
    derivation = TagDerivation(asset_definition=sample_asset_definition)
    
    governance_tags = derivation.derive_governance_tags()
    
    assert governance_tags["retention_days"] == "90"
    assert governance_tags["owner"] == "data-team@company.com"
    assert governance_tags["regulations"] == "GDPR,CCPA"


def test_derive_finops_tags(sample_asset_definition):
    """Test FinOps tag derivation."""
    derivation = TagDerivation(asset_definition=sample_asset_definition)
    
    finops_tags = derivation.derive_finops_tags()
    
    assert finops_tags["cost_center"] == "FIN-001"
    assert finops_tags["business_tags"] == "finance,reporting"
    assert finops_tags["project"] == "data-platform"


def test_derive_all_tags(sample_asset_definition):
    """Test complete tag derivation - ONLY explicit tags."""
    derivation = TagDerivation(asset_definition=sample_asset_definition)
    
    all_tags = derivation.derive_all_tags()
    
    # Classification tags - only from compliance section, NO auto-detection
    assert "classification.default" in all_tags
    assert all_tags["classification.default"] == "pii"
    # NO field-level classifications since they're not explicit in schema
    assert "classification.fields.email" not in all_tags
    assert "classification.fields.salary" not in all_tags
    
    # Governance tags
    assert "governance.retention_days" in all_tags
    assert all_tags["governance.retention_days"] == "90"
    assert "governance.owner" in all_tags
    assert all_tags["governance.owner"] == "data-team@company.com"
    
    # FinOps tags
    assert "finops.cost_center" in all_tags
    assert all_tags["finops.cost_center"] == "FIN-001"
    assert "finops.business_tags" in all_tags
    assert all_tags["finops.business_tags"] == "finance,reporting"


def test_derive_tags_convenience_function(sample_asset_definition):
    """Test convenience function for tag derivation - ONLY explicit tags."""
    tags = derive_tags_from_asset(
        asset_definition=sample_asset_definition,
        classification_overrides={"email": "high_pii"},
        finops={"environment": "production"},
    )
    
    # Should include tags from asset + overrides
    assert "classification.default" in tags
    # email has override, so it should appear
    assert "classification.fields.email" in tags
    assert tags["classification.fields.email"] == "high_pii"  # Override applied
    assert "governance.retention_days" in tags
    assert "finops.cost_center" in tags
    assert "finops.environment" in tags
    assert tags["finops.environment"] == "production"


def test_derive_tags_without_finops(sample_asset_definition):
    """Test tag derivation when asset has no FinOps metadata."""
    # Create asset without finops
    asset_no_finops = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[
            {"name": "id", "type": "integer", "required": True},
            {"name": "email", "type": "string", "required": False, "classification": "PII"},
        ],
        team={"owner": "data-team@company.com"},
    )
    
    tags = derive_tags_from_asset(asset_definition=asset_no_finops)
    
    # Should have classification for email (explicit in schema)
    assert "classification.fields.email" in tags
    
    # Should not have finops tags
    finops_keys = [k for k in tags.keys() if k.startswith("finops.")]
    assert len(finops_keys) == 0


def test_governance_overrides(sample_asset_definition):
    """Test governance overrides."""
    governance_overrides = {
        "retention_days": 365,
        "owner": "security-team@company.com",
    }
    
    tags = derive_tags_from_asset(
        asset_definition=sample_asset_definition,
        governance_overrides=governance_overrides,
    )
    
    # Overrides should take precedence
    assert tags["governance.retention_days"] == "365"
    assert tags["governance.owner"] == "security-team@company.com"


def test_explicit_field_classification_in_schema():
    """Test that explicit field classifications in schema are used."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[
            {"name": "email", "type": "string", "required": False, "classification": "HIGH_PII"},
            {"name": "phone", "type": "string", "required": False},
        ],
        team={"owner": "data-team@company.com"},
    )
    
    tags = derive_tags_from_asset(asset_definition=asset)
    
    # Explicit classification should be used
    assert tags["classification.fields.email"] == "high_pii"
    
    # phone has NO explicit classification, so it should NOT appear
    assert "classification.fields.phone" not in tags


# ============================================================================
# Source Tags Tests (Three-Level Hierarchy)
# ============================================================================

def test_source_tags_lowest_priority():
    """Test that source tags are used when no asset/job override exists."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="postgres",
        object="test_table",
        schema=[
            {"name": "email", "type": "string"},
            {"name": "phone", "type": "string"},
        ],
        team={"owner": "test@company.com"},
    )
    
    source_tags = {
        "email": "PII",
        "phone": "SENSITIVE",
    }
    
    derivation = TagDerivation(
        asset_definition=asset,
        source_tags=source_tags,
    )
    
    classifications = derivation.derive_field_classifications()
    
    # Source tags should be used (lowest priority)
    assert classifications["email"] == "pii"
    assert classifications["phone"] == "sensitive"


def test_source_tags_overridden_by_asset():
    """Test that asset definition overrides source tags."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="postgres",
        object="test_table",
        schema=[
            {"name": "email", "type": "string", "classification": "SENSITIVE_PII"},
            {"name": "phone", "type": "string"},  # No asset classification
        ],
        team={"owner": "test@company.com"},
    )
    
    source_tags = {
        "email": "PII",  # Will be overridden by asset
        "phone": "PII",  # Will be used (no asset override)
    }
    
    derivation = TagDerivation(
        asset_definition=asset,
        source_tags=source_tags,
    )
    
    classifications = derivation.derive_field_classifications()
    
    # Asset classification overrides source
    assert classifications["email"] == "sensitive_pii"
    # Source tag used for phone (no asset override)
    assert classifications["phone"] == "pii"


def test_source_tags_overridden_by_job():
    """Test that job config overrides both source and asset tags."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="postgres",
        object="test_table",
        schema=[
            {"name": "email", "type": "string", "classification": "SENSITIVE_PII"},
            {"name": "phone", "type": "string"},
        ],
        team={"owner": "test@company.com"},
    )
    
    source_tags = {
        "email": "PII",
        "phone": "PII",
    }
    
    classification_overrides = {
        "email": "HIGH_PII",  # Overrides both source and asset
        "phone": "RESTRICTED",  # Overrides source
    }
    
    derivation = TagDerivation(
        asset_definition=asset,
        source_tags=source_tags,
        classification_overrides=classification_overrides,
    )
    
    classifications = derivation.derive_field_classifications()
    
    # Job override wins
    assert classifications["email"] == "high_pii"
    assert classifications["phone"] == "restricted"


def test_source_tags_three_level_hierarchy():
    """Test complete three-level hierarchy: source → asset → job."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="postgres",
        object="test_table",
        schema=[
            {"name": "email", "type": "string", "classification": "SENSITIVE_PII"},
            {"name": "phone", "type": "string"},  # No asset classification
            {"name": "name", "type": "string"},  # No asset classification
        ],
        team={"owner": "test@company.com"},
    )
    
    source_tags = {
        "email": "PII",  # Level 3: Source (will be overridden)
        "phone": "PII",  # Level 3: Source (will be used)
        "name": "PUBLIC",  # Level 3: Source (will be used)
    }
    
    classification_overrides = {
        "email": "HIGH_PII",  # Level 1: Job (overrides all)
    }
    
    derivation = TagDerivation(
        asset_definition=asset,
        source_tags=source_tags,
        classification_overrides=classification_overrides,
    )
    
    classifications = derivation.derive_field_classifications()
    
    # email: Job override (HIGHEST) wins over asset and source
    assert classifications["email"] == "high_pii"
    # phone: Source tag used (no asset or job override)
    assert classifications["phone"] == "pii"
    # name: Source tag used (no asset or job override)
    assert classifications["name"] == "public"


# ============================================================================
# Edge Cases for derive_field_classifications
# ============================================================================

def test_derive_field_classifications_empty_schema():
    """Test field classification derivation with empty schema."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[],
        team={"owner": "test@company.com"},
    )
    
    derivation = TagDerivation(asset_definition=asset)
    classifications = derivation.derive_field_classifications()
    
    assert len(classifications) == 0


def test_derive_field_classifications_case_insensitive():
    """Test that classification values are lowercased."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[
            {"name": "email", "type": "string", "classification": "HIGH_PII"},
            {"name": "phone", "type": "string", "classification": "Sensitive"},
        ],
        team={"owner": "test@company.com"},
    )
    
    derivation = TagDerivation(asset_definition=asset)
    classifications = derivation.derive_field_classifications()
    
    assert classifications["email"] == "high_pii"
    assert classifications["phone"] == "sensitive"


def test_derive_field_classifications_multiple_overrides():
    """Test multiple fields with overrides."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[
            {"name": "email", "type": "string"},
            {"name": "phone", "type": "string"},
            {"name": "ssn", "type": "string"},
        ],
        team={"owner": "test@company.com"},
    )
    
    classification_overrides = {
        "email": "PII",
        "phone": "SENSITIVE",
        "ssn": "RESTRICTED",
    }
    
    derivation = TagDerivation(
        asset_definition=asset,
        classification_overrides=classification_overrides,
    )
    
    classifications = derivation.derive_field_classifications()
    
    assert len(classifications) == 3
    assert classifications["email"] == "pii"
    assert classifications["phone"] == "sensitive"
    assert classifications["ssn"] == "restricted"


# ============================================================================
# Edge Cases for derive_default_classification
# ============================================================================

def test_derive_default_classification_no_compliance():
    """Test default classification when no compliance section exists."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[{"name": "id", "type": "integer"}],
        team={"owner": "test@company.com"},
    )
    
    derivation = TagDerivation(asset_definition=asset)
    default_classification = derivation.derive_default_classification()
    
    assert default_classification is None


def test_derive_default_classification_empty_list():
    """Test default classification when classification list is empty."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[{"name": "id", "type": "integer"}],
        team={"owner": "test@company.com"},
        compliance={"classification": []},
    )
    
    derivation = TagDerivation(asset_definition=asset)
    default_classification = derivation.derive_default_classification()
    
    assert default_classification is None


def test_derive_default_classification_multiple_classifications():
    """Test that first classification from list is used."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[{"name": "id", "type": "integer"}],
        team={"owner": "test@company.com"},
        compliance={"classification": ["PII", "SENSITIVE", "RESTRICTED"]},
    )
    
    derivation = TagDerivation(asset_definition=asset)
    default_classification = derivation.derive_default_classification()
    
    # Should use first classification
    assert default_classification == "pii"


def test_derive_default_classification_override_default_key():
    """Test classification_overrides['default'] override."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[{"name": "id", "type": "integer"}],
        team={"owner": "test@company.com"},
        compliance={"classification": ["PII"]},
    )
    
    classification_overrides = {"default": "RESTRICTED"}
    
    derivation = TagDerivation(
        asset_definition=asset,
        classification_overrides=classification_overrides,
    )
    
    default_classification = derivation.derive_default_classification()
    
    # Override should win
    assert default_classification == "restricted"


def test_derive_default_classification_override_only():
    """Test override without compliance section."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[{"name": "id", "type": "integer"}],
        team={"owner": "test@company.com"},
    )
    
    classification_overrides = {"default": "SENSITIVE"}
    
    derivation = TagDerivation(
        asset_definition=asset,
        classification_overrides=classification_overrides,
    )
    
    default_classification = derivation.derive_default_classification()
    
    # Override should be used even without compliance
    assert default_classification == "sensitive"


# ============================================================================
# Edge Cases for derive_governance_tags
# ============================================================================

def test_derive_governance_tags_no_compliance():
    """Test governance tags when no compliance section exists."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[{"name": "id", "type": "integer"}],
        team={"owner": "test@company.com"},
    )
    
    derivation = TagDerivation(asset_definition=asset)
    governance_tags = derivation.derive_governance_tags()
    
    # Should still have owner from team
    assert "owner" in governance_tags
    assert governance_tags["owner"] == "test@company.com"
    # Should not have retention_days or regulations
    assert "retention_days" not in governance_tags
    assert "regulations" not in governance_tags


def test_derive_governance_tags_no_team():
    """Test governance tags when team owner is not set (using override to clear)."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[{"name": "id", "type": "integer"}],
        team={"owner": "placeholder@company.com"},  # Team required
        compliance={"retention_days": 90},
    )
    
    # Use governance override with empty string to test clearing owner
    derivation = TagDerivation(
        asset_definition=asset,
        governance_overrides={"owner": ""},  # Override to empty string
    )
    governance_tags = derivation.derive_governance_tags()
    
    # Should have retention_days from compliance
    assert "retention_days" in governance_tags
    assert governance_tags["retention_days"] == "90"
    # Should not have owner (empty string is falsy)
    assert "owner" not in governance_tags


def test_derive_governance_tags_no_domain():
    """Test governance tags when domain is not set."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[{"name": "id", "type": "integer"}],
        team={"owner": "test@company.com"},
    )
    
    derivation = TagDerivation(asset_definition=asset)
    governance_tags = derivation.derive_governance_tags()
    
    # Should not have domain
    assert "domain" not in governance_tags


def test_derive_governance_tags_with_domain():
    """Test governance tags when domain is set."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        domain="finance",
        schema=[{"name": "id", "type": "integer"}],
        team={"owner": "test@company.com"},
    )
    
    derivation = TagDerivation(asset_definition=asset)
    governance_tags = derivation.derive_governance_tags()
    
    # Should have domain
    assert "domain" in governance_tags
    assert governance_tags["domain"] == "finance"


def test_derive_governance_tags_regulations_empty():
    """Test governance tags with empty regulations list."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[{"name": "id", "type": "integer"}],
        team={"owner": "test@company.com"},
        compliance={"regulations": []},
    )
    
    derivation = TagDerivation(asset_definition=asset)
    governance_tags = derivation.derive_governance_tags()
    
    # Should not have regulations tag when empty
    assert "regulations" not in governance_tags


def test_derive_governance_tags_retention_days_zero():
    """Test governance tags with zero retention days."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[{"name": "id", "type": "integer"}],
        team={"owner": "test@company.com"},
        compliance={"retention_days": 0},
    )
    
    derivation = TagDerivation(asset_definition=asset)
    governance_tags = derivation.derive_governance_tags()
    
    # Zero should be included (falsy but valid)
    assert "retention_days" in governance_tags
    assert governance_tags["retention_days"] == "0"


# ============================================================================
# Edge Cases for derive_finops_tags
# ============================================================================

def test_derive_finops_tags_empty_dict():
    """Test FinOps tags with empty finops dict."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[{"name": "id", "type": "integer"}],
        team={"owner": "test@company.com"},
    )
    
    derivation = TagDerivation(asset_definition=asset, finops={})
    finops_tags = derivation.derive_finops_tags()
    
    assert len(finops_tags) == 0


def test_derive_finops_tags_business_tags_string():
    """Test FinOps tags with business_tags as string (not list)."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[{"name": "id", "type": "integer"}],
        team={"owner": "test@company.com"},
    )
    
    finops = {"business_tags": "single-tag"}
    
    derivation = TagDerivation(asset_definition=asset, finops=finops)
    finops_tags = derivation.derive_finops_tags()
    
    assert finops_tags["business_tags"] == "single-tag"


def test_derive_finops_tags_business_tags_empty_list():
    """Test FinOps tags with empty business_tags list."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[{"name": "id", "type": "integer"}],
        team={"owner": "test@company.com"},
    )
    
    finops = {"business_tags": []}
    
    derivation = TagDerivation(asset_definition=asset, finops=finops)
    finops_tags = derivation.derive_finops_tags()
    
    # Empty list should not create a tag
    assert "business_tags" not in finops_tags


def test_derive_finops_tags_partial_fields():
    """Test FinOps tags with only some fields present."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[{"name": "id", "type": "integer"}],
        team={"owner": "test@company.com"},
    )
    
    finops = {"cost_center": "FIN-001"}  # Only cost_center, no other fields
    
    derivation = TagDerivation(asset_definition=asset, finops=finops)
    finops_tags = derivation.derive_finops_tags()
    
    assert len(finops_tags) == 1
    assert finops_tags["cost_center"] == "FIN-001"
    assert "business_tags" not in finops_tags
    assert "project" not in finops_tags
    assert "environment" not in finops_tags


def test_derive_finops_tags_numeric_values():
    """Test FinOps tags with numeric values converted to strings."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[{"name": "id", "type": "integer"}],
        team={"owner": "test@company.com"},
    )
    
    finops = {
        "cost_center": 12345,  # Numeric value
        "project": "data-platform",
    }
    
    derivation = TagDerivation(asset_definition=asset, finops=finops)
    finops_tags = derivation.derive_finops_tags()
    
    # Numeric values should be converted to strings
    assert finops_tags["cost_center"] == "12345"
    assert finops_tags["project"] == "data-platform"


# ============================================================================
# Edge Cases for derive_all_tags
# ============================================================================

def test_derive_all_tags_empty_asset():
    """Test tag derivation with minimal asset definition."""
    asset = AssetDefinition(
        name="minimal_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[{"name": "id", "type": "integer"}],
        team={"owner": "test@company.com"},  # Team required
    )
    
    tags = derive_tags_from_asset(asset_definition=asset)
    
    # Should have governance owner from team
    assert "governance.owner" in tags
    
    # Should not have classification, retention_days, or finops tags
    assert "classification.default" not in tags
    assert "governance.retention_days" not in tags
    finops_keys = [k for k in tags.keys() if k.startswith("finops.")]
    assert len(finops_keys) == 0


def test_derive_all_tags_namespace_format():
    """Test that all tags use correct namespace format."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[
            {"name": "email", "type": "string", "classification": "PII"},
        ],
        team={"owner": "test@company.com"},
        compliance={"classification": ["SENSITIVE"], "retention_days": 90},
        finops={"cost_center": "FIN-001"},
    )
    
    tags = derive_tags_from_asset(asset_definition=asset)
    
    # Check namespace format
    assert "classification.default" in tags
    assert "classification.fields.email" in tags
    assert "governance.retention_days" in tags
    assert "governance.owner" in tags
    assert "finops.cost_center" in tags
    
    # All tags should have namespace prefix (asset.* tags are added by IcebergCommitter, not TagDerivation)
    for key in tags.keys():
        assert any(key.startswith(prefix) for prefix in [
            "classification.", "governance.", "finops."
        ]), f"Tag {key} does not have proper namespace"


def test_derive_all_tags_asset_metadata():
    """Test that asset metadata is included in governance tags (domain, data_product)."""
    asset = AssetDefinition(
        name="customers",
        version="2.1",
        source_type="postgres",
        object="public.customers",
        domain="sales",
        schema=[{"name": "id", "type": "integer"}],
        team={"owner": "data@company.com"},
    )
    
    # Set dataProduct if supported
    if hasattr(asset, 'dataProduct'):
        asset.dataProduct = "customer-analytics"
    
    tags = derive_tags_from_asset(asset_definition=asset)
    
    # Verify governance tags include domain
    assert "governance.domain" in tags
    assert tags["governance.domain"] == "sales"
    
    # dataProduct may or may not be set depending on AssetDefinition implementation
    if hasattr(asset, 'dataProduct') and asset.dataProduct:
        assert "governance.data_product" in tags
    
    # Note: asset.name, asset.version, etc. are added by IcebergCommitter, not TagDerivation
