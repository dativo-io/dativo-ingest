#!/usr/bin/env python3
"""Smoke test for tag propagation to Iceberg tables.

This test verifies that tags defined in asset definitions and job configurations
are properly propagated to Iceberg table properties.
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dativo_ingest.config import (
    AssetDefinition,
    ComplianceModel,
    FinOpsModel,
    TeamModel,
)
from dativo_ingest.tag_derivation import TagDerivation, derive_tags_from_asset


def test_tag_derivation_basic():
    """Test basic tag derivation from asset definition."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[
            {"name": "id", "type": "integer", "required": True},
            {
                "name": "email",
                "type": "string",
                "required": False,
                "classification": "PII",
            },
        ],
        compliance=ComplianceModel(
            classification=["PII"],
            retention_days=90,
        ),
        finops=FinOpsModel(
            cost_center="TEST-001",
            business_tags=["testing"],
        ),
        team=TeamModel(owner="test@company.com"),
    )

    tags = derive_tags_from_asset(asset_definition=asset)

    # Verify classification tags
    assert "classification.default" in tags
    assert tags["classification.default"] == "pii"
    assert "classification.fields.email" in tags
    assert tags["classification.fields.email"] == "pii"

    # Verify governance tags
    assert "governance.retention_days" in tags
    assert tags["governance.retention_days"] == "90"

    # Verify finops tags
    assert "finops.cost_center" in tags
    assert tags["finops.cost_center"] == "TEST-001"


def test_tag_hierarchy_source_to_job():
    """Test three-level tag hierarchy: Source → Asset → Job."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="postgres",
        object="test_table",
        schema=[
            {"name": "email", "type": "string", "classification": "SENSITIVE_PII"},
            {"name": "phone", "type": "string"},  # No classification
        ],
        compliance=ComplianceModel(
            classification=["PII"],
            retention_days=90,
        ),
        finops=FinOpsModel(
            cost_center="ENG-001",
        ),
        team=TeamModel(owner="eng@company.com"),
    )

    # Source system tags (LOWEST priority)
    source_tags = {
        "email": "PII",  # Will be overridden by asset
        "phone": "PII",  # Will be used (not in asset)
    }

    # Job overrides (HIGHEST priority)
    classification_overrides = {
        "email": "HIGH_PII",  # Override asset "SENSITIVE_PII"
    }

    finops_overrides = {
        "cost_center": "ENG-PROD-001",  # Override asset "ENG-001"
        "environment": "production",  # Add new tag
    }

    tags = derive_tags_from_asset(
        asset_definition=asset,
        source_tags=source_tags,
        classification_overrides=classification_overrides,
        finops=finops_overrides,
    )

    # Verify hierarchy
    # email: Job override wins
    assert tags["classification.fields.email"] == "high_pii"

    # phone: Source tag used (no asset or job override)
    assert tags["classification.fields.phone"] == "pii"

    # FinOps: Job override wins
    assert tags["finops.cost_center"] == "ENG-PROD-001"
    assert tags["finops.environment"] == "production"


def test_explicit_tags_only():
    """Test that NO automatic classification is performed."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[
            {"name": "email", "type": "string"},  # No explicit classification
            {"name": "phone", "type": "string"},  # No explicit classification
            {"name": "salary", "type": "double"},  # No explicit classification
        ],
        team=TeamModel(owner="test@company.com"),
    )

    derivation = TagDerivation(asset_definition=asset)

    # Should NOT auto-detect email, phone, or salary
    field_classifications = derivation.derive_field_classifications()
    assert len(field_classifications) == 0, "Should not auto-detect any classifications"


def test_job_override_precedence():
    """Test that job config always overrides asset definition."""
    asset = AssetDefinition(
        name="test_asset",
        version="1.0",
        source_type="csv",
        object="test_object",
        schema=[
            {"name": "email", "type": "string", "classification": "PII"},
        ],
        compliance=ComplianceModel(
            retention_days=90,
        ),
        finops=FinOpsModel(
            cost_center="DEV-001",
        ),
        team=TeamModel(owner="dev@company.com"),
    )

    # Job overrides
    classification_overrides = {"email": "RESTRICTED"}
    governance_overrides = {"retention_days": 365}
    finops_overrides = {"cost_center": "PROD-001"}

    tags = derive_tags_from_asset(
        asset_definition=asset,
        classification_overrides=classification_overrides,
        governance_overrides=governance_overrides,
        finops=finops_overrides,
    )

    # Job overrides should win
    assert tags["classification.fields.email"] == "restricted"
    assert tags["governance.retention_days"] == "365"
    assert tags["finops.cost_center"] == "PROD-001"


def test_asset_metadata_tags():
    """Test that asset metadata is included in governance tags (domain, data_product)."""
    asset = AssetDefinition(
        name="customers",
        version="2.1",
        source_type="postgres",
        object="public.customers",
        domain="sales",
        schema=[
            {"name": "id", "type": "integer", "required": True},
        ],
        team=TeamModel(owner="data@company.com"),
    )

    tags = derive_tags_from_asset(asset_definition=asset)

    # Verify governance tags include domain
    assert "governance.domain" in tags
    assert tags["governance.domain"] == "sales"

    # Verify governance owner
    assert "governance.owner" in tags
    assert tags["governance.owner"] == "data@company.com"

    # Note: asset.name, asset.version, asset.source_type, asset.object are added
    # by IcebergCommitter._derive_table_properties(), not by derive_tags_from_asset()


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
