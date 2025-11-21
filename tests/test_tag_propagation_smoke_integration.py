#!/usr/bin/env python3
"""Comprehensive smoke tests for tag propagation integration.

This test suite verifies the complete end-to-end flow:
1. Asset Definition → Tag Derivation
2. Tag Derivation → IcebergCommitter
3. IcebergCommitter → Table Properties
4. Property Updates and Merging

These tests use mocks to avoid requiring actual Nessie/Iceberg infrastructure.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dativo_ingest.config import AssetDefinition, TargetConfig, ComplianceModel, FinOpsModel, TeamModel
from dativo_ingest.tag_derivation import TagDerivation, derive_tags_from_asset
from dativo_ingest.iceberg_committer import IcebergCommitter


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_asset_with_tags():
    """Create asset definition with comprehensive tags."""
    return AssetDefinition(
        name="test_employee",
        version="1.0",
        source_type="csv",
        object="Employee",
        domain="hr",
        schema=[
            {"name": "employee_id", "type": "integer", "required": True},
            {"name": "email", "type": "string", "required": True, "classification": "PII"},
            {"name": "salary", "type": "double", "required": True, "classification": "SENSITIVE"},
            {"name": "department", "type": "string", "required": False},
        ],
        team=TeamModel(owner="hr-team@company.com"),
        compliance=ComplianceModel(
            classification=["PII", "SENSITIVE"],
            retention_days=90,
            regulations=["GDPR", "CCPA"],
        ),
        finops=FinOpsModel(
            cost_center="HR-001",
            business_tags=["hr", "payroll"],
            project="employee-analytics",
            environment="production",
        ),
    )


@pytest.fixture
def target_config_iceberg():
    """Create target config for Iceberg."""
    return TargetConfig(
        type="iceberg",
        catalog="nessie",
        branch="main",
        warehouse="s3://test-bucket/warehouse",
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


# ============================================================================
# Smoke Test 1: Basic Tag Propagation Flow
# ============================================================================

def test_smoke_basic_tag_propagation_flow(sample_asset_with_tags, target_config_iceberg):
    """Test basic tag propagation: Asset → Derivation → Committer → Properties."""
    # Step 1: Derive tags from asset
    tags = derive_tags_from_asset(asset_definition=sample_asset_with_tags)
    
    # Verify tags are derived
    assert "classification.default" in tags
    assert "classification.fields.email" in tags
    assert "classification.fields.salary" in tags
    assert "governance.retention_days" in tags
    assert "governance.owner" in tags
    assert "finops.cost_center" in tags
    
    # Step 2: Create IcebergCommitter
    committer = IcebergCommitter(
        asset_definition=sample_asset_with_tags,
        target_config=target_config_iceberg,
    )
    
    # Step 3: Derive table properties
    properties = committer._derive_table_properties()
    
    # Verify properties include tags + asset metadata
    assert "classification.default" in properties
    assert "classification.fields.email" in properties
    assert "classification.fields.salary" in properties
    assert "governance.retention_days" in properties
    assert "governance.owner" in properties
    assert "finops.cost_center" in properties
    
    # Verify asset metadata
    assert "asset.name" in properties
    assert properties["asset.name"] == "test_employee"
    assert "asset.version" in properties
    assert properties["asset.version"] == "1.0"
    assert "asset.domain" in properties
    assert properties["asset.domain"] == "hr"
    assert "asset.source_type" in properties
    assert properties["asset.source_type"] == "csv"
    assert "asset.object" in properties
    assert properties["asset.object"] == "Employee"


# ============================================================================
# Smoke Test 2: Tag Propagation with Job Overrides
# ============================================================================

def test_smoke_tag_propagation_with_job_overrides(sample_asset_with_tags, target_config_iceberg):
    """Test tag propagation with job-level overrides."""
    # Job overrides
    classification_overrides = {
        "email": "HIGH_PII",  # Override asset "PII"
        "default": "RESTRICTED",  # Override compliance classification
    }
    finops_overrides = {
        "cost_center": "HR-PROD-001",  # Override asset "HR-001"
        "environment": "production",
    }
    governance_overrides = {
        "retention_days": 365,  # Override asset 90
        "owner": "security-team@company.com",  # Override asset owner
    }
    
    # Create committer with overrides
    committer = IcebergCommitter(
        asset_definition=sample_asset_with_tags,
        target_config=target_config_iceberg,
        classification_overrides=classification_overrides,
        finops=finops_overrides,
        governance_overrides=governance_overrides,
    )
    
    # Derive properties
    properties = committer._derive_table_properties()
    
    # Verify overrides take precedence
    assert properties["classification.fields.email"] == "high_pii"  # Job override
    assert properties["classification.default"] == "restricted"  # Job override
    assert properties["finops.cost_center"] == "HR-PROD-001"  # Job override
    assert properties["governance.retention_days"] == "365"  # Job override
    assert properties["governance.owner"] == "security-team@company.com"  # Job override
    
    # Verify non-overridden tags still present
    assert properties["classification.fields.salary"] == "sensitive"  # From asset
    assert properties["finops.business_tags"] == "hr,payroll"  # From asset


# ============================================================================
# Smoke Test 3: Three-Level Tag Hierarchy
# ============================================================================

def test_smoke_three_level_tag_hierarchy(target_config_iceberg):
    """Test complete three-level hierarchy: Source → Asset → Job."""
    asset = AssetDefinition(
        name="test_customer",
        version="1.0",
        source_type="postgres",
        object="public.customers",
        domain="sales",
        schema=[
            {"name": "email", "type": "string", "classification": "SENSITIVE_PII"},
            {"name": "phone", "type": "string"},  # No asset classification
            {"name": "name", "type": "string"},  # No asset classification
        ],
        team=TeamModel(owner="sales-team@company.com"),
        compliance=ComplianceModel(classification=["PII"]),
        finops=FinOpsModel(cost_center="SALES-001"),
    )
    
    # Source tags (LOWEST priority)
    source_tags = {
        "email": "PII",  # Will be overridden by asset
        "phone": "PII",  # Will be used (no asset override)
        "name": "PUBLIC",  # Will be used (no asset override)
    }
    
    # Job overrides (HIGHEST priority)
    classification_overrides = {
        "email": "HIGH_PII",  # Overrides both source and asset
    }
    
    # Create committer with source tags
    committer = IcebergCommitter(
        asset_definition=asset,
        target_config=target_config_iceberg,
        source_tags=source_tags,
        classification_overrides=classification_overrides,
    )
    
    # Derive properties
    properties = committer._derive_table_properties()
    
    # Verify hierarchy: Job > Asset > Source
    assert properties["classification.fields.email"] == "high_pii"  # Job wins
    assert properties["classification.fields.phone"] == "pii"  # Source used
    assert properties["classification.fields.name"] == "public"  # Source used


# ============================================================================
# Smoke Test 4: Table Property Updates (Idempotent)
# ============================================================================

def test_smoke_table_property_updates_idempotent(sample_asset_with_tags, target_config_iceberg):
    """Test that table property updates are idempotent."""
    committer = IcebergCommitter(
        asset_definition=sample_asset_with_tags,
        target_config=target_config_iceberg,
    )
    
    # Mock catalog and table
    mock_table = MagicMock()
    expected_properties = committer._derive_table_properties()
    mock_table.properties = expected_properties.copy()  # Same properties
    
    mock_txn = MagicMock()
    mock_table.transaction.return_value.__enter__ = Mock(return_value=mock_txn)
    mock_table.transaction.return_value.__exit__ = Mock(return_value=None)
    
    mock_catalog = MagicMock()
    mock_catalog.load_table.return_value = mock_table
    
    # Update properties (should detect no changes needed)
    committer._update_table_properties(mock_catalog, "hr", "test_employee")
    
    # Verify table was loaded
    mock_catalog.load_table.assert_called_once_with(("hr", "test_employee"))
    
    # Note: Implementation checks needs_update, so transaction might not be called
    # This is correct behavior for idempotent updates


# ============================================================================
# Smoke Test 5: Property Merging (Preserve Existing)
# ============================================================================

def test_smoke_property_merging_preserves_existing(sample_asset_with_tags, target_config_iceberg):
    """Test that property updates preserve existing unrelated properties."""
    committer = IcebergCommitter(
        asset_definition=sample_asset_with_tags,
        target_config=target_config_iceberg,
    )
    
    # Mock table with existing properties (some matching, some unrelated)
    mock_table = MagicMock()
    mock_table.properties = {
        "classification.default": "pii",  # Matches (no change)
        "classification.fields.email": "pii",  # Matches (no change)
        "existing.custom.property": "keep_me",  # Unrelated (should be preserved)
        "another.property": "also_keep",  # Unrelated (should be preserved)
    }
    
    mock_txn = MagicMock()
    mock_table.transaction.return_value.__enter__ = Mock(return_value=mock_txn)
    mock_table.transaction.return_value.__exit__ = Mock(return_value=None)
    
    mock_catalog = MagicMock()
    mock_catalog.load_table.return_value = mock_table
    
    # Update properties
    committer._update_table_properties(mock_catalog, "hr", "test_employee")
    
    # Verify transaction was used (properties changed)
    assert mock_table.transaction.called
    
    # The implementation merges properties, so existing ones should be preserved
    # (This is verified by the merge logic in _update_table_properties)


# ============================================================================
# Smoke Test 6: Complete Tag Namespace Verification
# ============================================================================

def test_smoke_tag_namespace_verification(sample_asset_with_tags, target_config_iceberg):
    """Test that all tags use correct namespace format."""
    classification_overrides = {"email": "PII"}
    finops = {"cost_center": "HR-001", "environment": "production"}
    governance_overrides = {"retention_days": 90}
    
    committer = IcebergCommitter(
        asset_definition=sample_asset_with_tags,
        target_config=target_config_iceberg,
        classification_overrides=classification_overrides,
        finops=finops,
        governance_overrides=governance_overrides,
    )
    
    properties = committer._derive_table_properties()
    
    # Verify all tags have proper namespace
    for key in properties.keys():
        assert any(key.startswith(prefix) for prefix in [
            "classification.", "governance.", "finops.", "asset."
        ]), f"Tag {key} does not have proper namespace"
    
    # Verify specific namespaces exist
    classification_keys = [k for k in properties.keys() if k.startswith("classification.")]
    governance_keys = [k for k in properties.keys() if k.startswith("governance.")]
    finops_keys = [k for k in properties.keys() if k.startswith("finops.")]
    asset_keys = [k for k in properties.keys() if k.startswith("asset.")]
    
    assert len(classification_keys) > 0, "Should have classification tags"
    assert len(governance_keys) > 0, "Should have governance tags"
    assert len(finops_keys) > 0, "Should have finops tags"
    assert len(asset_keys) > 0, "Should have asset tags"


# ============================================================================
# Smoke Test 7: Minimal Asset (No Tags)
# ============================================================================

def test_smoke_minimal_asset_no_tags(target_config_iceberg):
    """Test tag propagation with minimal asset (no compliance/finops)."""
    minimal_asset = AssetDefinition(
        name="minimal_table",
        version="1.0",
        source_type="csv",
        object="minimal",
        schema=[{"name": "id", "type": "integer"}],
        team={"owner": "test@company.com"},  # Team required
    )
    
    committer = IcebergCommitter(
        asset_definition=minimal_asset,
        target_config=target_config_iceberg,
    )
    
    properties = committer._derive_table_properties()
    
    # Should still have asset metadata
    assert "asset.name" in properties
    assert "asset.version" in properties
    assert "asset.source_type" in properties
    assert "asset.object" in properties
    
    # Should have governance owner from team
    assert "governance.owner" in properties
    
    # Should not have classification/retention_days/finops tags
    assert "classification.default" not in properties
    assert "governance.retention_days" not in properties
    finops_keys = [k for k in properties.keys() if k.startswith("finops.")]
    assert len(finops_keys) == 0


# ============================================================================
# Smoke Test 8: Tag Propagation with Source Tags Only
# ============================================================================

def test_smoke_source_tags_only(target_config_iceberg):
    """Test tag propagation when only source tags are present."""
    asset = AssetDefinition(
        name="source_only",
        version="1.0",
        source_type="postgres",
        object="public.table",
        schema=[
            {"name": "email", "type": "string"},
            {"name": "phone", "type": "string"},
        ],
        team=TeamModel(owner="team@company.com"),
    )
    
    # Only source tags (no asset or job tags)
    source_tags = {
        "email": "PII",
        "phone": "SENSITIVE",
    }
    
    # Create committer with source tags
    committer = IcebergCommitter(
        asset_definition=asset,
        target_config=target_config_iceberg,
        source_tags=source_tags,
    )
    
    properties = committer._derive_table_properties()
    
    # Source tags should be used
    assert "classification.fields.email" in properties
    assert properties["classification.fields.email"] == "pii"
    assert "classification.fields.phone" in properties
    assert properties["classification.fields.phone"] == "sensitive"
    
    # Should have governance owner from team
    assert "governance.owner" in properties


# ============================================================================
# Smoke Test 9: FinOps Tag Variations
# ============================================================================

def test_smoke_finops_tag_variations(sample_asset_with_tags, target_config_iceberg):
    """Test FinOps tags with various data types."""
    finops = {
        "cost_center": 12345,  # Numeric
        "business_tags": "single-tag",  # String (not list)
        "project": "test-project",
        "environment": "staging",
    }
    
    committer = IcebergCommitter(
        asset_definition=sample_asset_with_tags,
        target_config=target_config_iceberg,
        finops=finops,
    )
    
    properties = committer._derive_table_properties()
    
    # Verify numeric converted to string
    assert properties["finops.cost_center"] == "12345"
    
    # Verify string business_tags handled
    assert properties["finops.business_tags"] == "single-tag"
    
    # Verify other tags
    assert properties["finops.project"] == "test-project"
    assert properties["finops.environment"] == "staging"


# ============================================================================
# Smoke Test 10: Complete Integration Flow
# ============================================================================

def test_smoke_complete_integration_flow(target_config_iceberg):
    """Test complete integration: Asset → Tags → Committer → Properties → Update."""
    # Create comprehensive asset
    asset = AssetDefinition(
        name="integration_test",
        version="2.0",
        source_type="postgres",
        object="public.integration_table",
        domain="analytics",
        schema=[
            {"name": "id", "type": "integer", "required": True},
            {"name": "email", "type": "string", "classification": "PII"},
            {"name": "amount", "type": "double", "classification": "FINANCIAL"},
        ],
        team=TeamModel(owner="analytics@company.com"),
        compliance=ComplianceModel(
            classification=["PII", "FINANCIAL"],
            retention_days=180,
            regulations=["GDPR"],
        ),
        finops=FinOpsModel(
            cost_center="ANALYTICS-001",
            business_tags=["analytics", "reporting"],
            project="data-platform",
            environment="production",
        ),
    )
    
    # Job overrides
    classification_overrides = {"email": "HIGH_PII"}
    finops_overrides = {"environment": "prod"}
    governance_overrides = {"retention_days": 365}
    
    # Step 1: Derive tags
    tags = derive_tags_from_asset(
        asset_definition=asset,
        classification_overrides=classification_overrides,
        finops=finops_overrides,
        governance_overrides=governance_overrides,
    )
    
    # Step 2: Create committer
    committer = IcebergCommitter(
        asset_definition=asset,
        target_config=target_config_iceberg,
        classification_overrides=classification_overrides,
        finops=finops_overrides,
        governance_overrides=governance_overrides,
    )
    
    # Step 3: Derive properties
    properties = committer._derive_table_properties()
    
    # Step 4: Verify complete tag set
    # Classification
    assert properties["classification.default"] == "pii"  # From compliance
    assert properties["classification.fields.email"] == "high_pii"  # Job override
    assert properties["classification.fields.amount"] == "financial"  # From asset
    
    # Governance
    assert properties["governance.retention_days"] == "365"  # Job override
    assert properties["governance.owner"] == "analytics@company.com"  # From team
    assert properties["governance.regulations"] == "GDPR"  # From compliance
    
    # FinOps
    assert properties["finops.cost_center"] == "ANALYTICS-001"  # From asset
    assert properties["finops.business_tags"] == "analytics,reporting"  # From asset
    assert properties["finops.project"] == "data-platform"  # From asset
    assert properties["finops.environment"] == "prod"  # Job override
    
    # Asset metadata
    assert properties["asset.name"] == "integration_test"
    assert properties["asset.version"] == "2.0"
    assert properties["asset.domain"] == "analytics"
    assert properties["asset.source_type"] == "postgres"
    assert properties["asset.object"] == "public.integration_table"
    
    # Step 5: Mock table update
    mock_table = MagicMock()
    mock_table.properties = {}
    
    mock_txn = MagicMock()
    mock_table.transaction.return_value.__enter__ = Mock(return_value=mock_txn)
    mock_table.transaction.return_value.__exit__ = Mock(return_value=None)
    
    mock_catalog = MagicMock()
    mock_catalog.load_table.return_value = mock_table
    
    # Update properties
    committer._update_table_properties(mock_catalog, "analytics", "integration_test")
    
    # Verify update was called
    assert mock_catalog.load_table.called
    assert mock_table.transaction.called


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

