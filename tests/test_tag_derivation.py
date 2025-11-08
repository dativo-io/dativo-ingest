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
    """Test field-level classification derivation."""
    derivation = TagDerivation(asset_definition=sample_asset_definition)
    
    classifications = derivation.derive_field_classifications()
    
    # Should detect PII fields
    assert "email" in classifications
    assert classifications["email"] == "pii"
    assert "first_name" in classifications
    assert classifications["first_name"] == "pii"
    
    # Should detect sensitive fields
    assert "salary" in classifications
    assert classifications["salary"] == "sensitive"
    
    # Should not classify non-sensitive fields
    assert "id" not in classifications
    assert "status" not in classifications


def test_derive_field_classifications_with_overrides(sample_asset_definition):
    """Test field-level classification with overrides."""
    classification_overrides = {
        "status": "confidential",
        "email": "high_pii",  # Override automatic detection
    }
    
    derivation = TagDerivation(
        asset_definition=sample_asset_definition,
        classification_overrides=classification_overrides,
    )
    
    classifications = derivation.derive_field_classifications()
    
    # Override should take precedence
    assert classifications["email"] == "high_pii"
    assert classifications["status"] == "confidential"
    
    # Other fields should still be auto-detected
    assert classifications["first_name"] == "pii"
    assert classifications["salary"] == "sensitive"


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
    """Test complete tag derivation."""
    derivation = TagDerivation(asset_definition=sample_asset_definition)
    
    all_tags = derivation.derive_all_tags()
    
    # Classification tags
    assert "classification.default" in all_tags
    assert all_tags["classification.default"] == "pii"
    assert "classification.fields.email" in all_tags
    assert all_tags["classification.fields.email"] == "pii"
    assert "classification.fields.salary" in all_tags
    assert all_tags["classification.fields.salary"] == "sensitive"
    
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
    """Test convenience function for tag derivation."""
    tags = derive_tags_from_asset(
        asset_definition=sample_asset_definition,
        classification_overrides={"email": "high_pii"},
        finops={"environment": "production"},
    )
    
    # Should include all tags
    assert "classification.default" in tags
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
            {"name": "email", "type": "string", "required": False},
        ],
        team={"owner": "data-team@company.com"},
    )
    
    tags = derive_tags_from_asset(asset_definition=asset_no_finops)
    
    # Should still have classification and governance tags
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
    """Test that explicit field classifications in schema take precedence."""
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
    
    # Auto-detection should still work for other fields
    assert tags["classification.fields.phone"] == "pii"
