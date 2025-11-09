"""Tests for AI context API."""

import tempfile
from pathlib import Path

import pytest

from dativo_ingest.ai_context_api import AIContextAPI, PolicyGuard
from dativo_ingest.config import AssetDefinition
from dativo_ingest.contracts import ContractManager


@pytest.fixture
def temp_specs_dir():
    """Create temporary specs directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_asset():
    """Create sample asset definition."""
    return AssetDefinition(
        id="test-asset-123",
        name="test_customers",
        version="1.0.0",
        status="active",
        source_type="stripe",
        object="customers",
        team={"owner": "data-team@example.com"},
        schema=[
            {"name": "id", "type": "string", "required": True},
            {"name": "email", "type": "string", "required": True, "classification": "PII"},
        ],
        description={
            "purpose": "Customer data",
            "usage": "Analytics",
        },
        compliance={
            "classification": ["PII"],
            "retention_days": 90,
        },
        tags=["customers"],
    )


def test_policy_guard_check_access():
    """Test policy guard access check."""
    policy = PolicyGuard({
        "allowed_requesters": ["agent1", "agent2"],
    })
    
    is_allowed, reason = policy.check_access(
        "asset", "test-asset", "agent1"
    )
    
    assert is_allowed
    assert reason is None


def test_policy_guard_deny_access():
    """Test policy guard denying access."""
    policy = PolicyGuard({
        "allowed_requesters": ["agent1"],
    })
    
    is_allowed, reason = policy.check_access(
        "asset", "test-asset", "agent2"
    )
    
    assert not is_allowed
    assert reason is not None


def test_policy_guard_classification_restriction():
    """Test policy guard with classification restrictions."""
    policy = PolicyGuard({
        "restricted_classifications": ["PII"],
        "elevated_requesters": ["admin"],
    })
    
    # Non-admin should be denied
    is_allowed, reason = policy.check_access(
        "asset", "test-asset", "regular-user", classification=["PII"]
    )
    
    assert not is_allowed
    
    # Admin should be allowed
    is_allowed, reason = policy.check_access(
        "asset", "test-asset", "admin", classification=["PII"]
    )
    
    assert is_allowed


def test_ai_context_api_initialization(temp_specs_dir):
    """Test AI context API initialization."""
    contract_manager = ContractManager(specs_dir=temp_specs_dir)
    api = AIContextAPI(contract_manager=contract_manager)
    
    assert api.contract_manager is not None
    assert api.lineage_tracker is not None
    assert api.policy_guard is not None


def test_get_asset_context(temp_specs_dir, sample_asset):
    """Test getting asset context."""
    # Set up contract manager and save asset
    contract_manager = ContractManager(specs_dir=temp_specs_dir)
    contract_manager.save_contract(sample_asset)
    
    # Create API with no restrictions
    policy = PolicyGuard({})
    api = AIContextAPI(
        contract_manager=contract_manager,
        policy_guard=policy,
    )
    
    # Get context
    context = api.get_asset_context(
        "stripe", "customers", version="1.0.0", requester="test-agent"
    )
    
    assert "asset" in context
    assert context["asset"]["name"] == "test_customers"
    assert "schema" in context
    assert "governance" in context
    assert "description" in context


def test_get_asset_context_access_denied(temp_specs_dir, sample_asset):
    """Test getting asset context with access denied."""
    # Set up contract manager and save asset
    contract_manager = ContractManager(specs_dir=temp_specs_dir)
    contract_manager.save_contract(sample_asset)
    
    # Create API with restrictions
    policy = PolicyGuard({
        "allowed_requesters": ["allowed-agent"],
    })
    api = AIContextAPI(
        contract_manager=contract_manager,
        policy_guard=policy,
    )
    
    # Should raise PermissionError
    with pytest.raises(PermissionError):
        api.get_asset_context(
            "stripe", "customers", version="1.0.0", requester="unauthorized-agent"
        )


def test_get_finops_context():
    """Test getting FinOps context."""
    policy = PolicyGuard({})
    api = AIContextAPI(policy_guard=policy)
    
    context = api.get_finops_context("test-tenant", requester="test-agent")
    
    assert "tenant_id" in context
    assert "cost_summary" in context
    assert "resource_usage" in context


def test_search_assets(temp_specs_dir, sample_asset):
    """Test searching for assets."""
    # Set up contract manager and save multiple assets
    contract_manager = ContractManager(specs_dir=temp_specs_dir)
    contract_manager.save_contract(sample_asset)
    
    # Create API
    policy = PolicyGuard({})
    api = AIContextAPI(
        contract_manager=contract_manager,
        policy_guard=policy,
    )
    
    # Search by classification
    results = api.search_assets(
        classification=["PII"],
        requester="test-agent",
    )
    
    assert len(results) > 0
    assert any(r["name"] == "test_customers" for r in results)


def test_search_assets_by_owner(temp_specs_dir, sample_asset):
    """Test searching assets by owner."""
    contract_manager = ContractManager(specs_dir=temp_specs_dir)
    contract_manager.save_contract(sample_asset)
    
    policy = PolicyGuard({})
    api = AIContextAPI(
        contract_manager=contract_manager,
        policy_guard=policy,
    )
    
    # Search by owner
    results = api.search_assets(
        owner="data-team@example.com",
        requester="test-agent",
    )
    
    assert len(results) > 0
    assert all(r["owner"] == "data-team@example.com" for r in results)


def test_search_assets_by_tags(temp_specs_dir, sample_asset):
    """Test searching assets by tags."""
    contract_manager = ContractManager(specs_dir=temp_specs_dir)
    contract_manager.save_contract(sample_asset)
    
    policy = PolicyGuard({})
    api = AIContextAPI(
        contract_manager=contract_manager,
        policy_guard=policy,
    )
    
    # Search by tags
    results = api.search_assets(
        tags=["customers"],
        requester="test-agent",
    )
    
    assert len(results) > 0
    assert any("customers" in r["tags"] for r in results)


def test_search_assets_with_limit(temp_specs_dir):
    """Test searching assets with result limit."""
    contract_manager = ContractManager(specs_dir=temp_specs_dir)
    
    # Create multiple assets
    for i in range(10):
        asset = AssetDefinition(
            id=f"test-{i}",
            name=f"test_{i}",
            version="1.0.0",
            status="active",
            source_type="test",
            object=f"obj_{i}",
            team={"owner": "test@example.com"},
            schema=[{"name": "id", "type": "string"}],
        )
        contract_manager.save_contract(asset)
    
    policy = PolicyGuard({})
    api = AIContextAPI(
        contract_manager=contract_manager,
        policy_guard=policy,
    )
    
    # Search with limit
    results = api.search_assets(requester="test-agent", limit=5)
    
    assert len(results) <= 5
