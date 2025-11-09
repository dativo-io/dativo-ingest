"""Tests for contract management."""

import tempfile
from pathlib import Path

import pytest

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
            {"name": "created_at", "type": "timestamp", "required": True},
        ],
    )


def test_contract_manager_initialization(temp_specs_dir):
    """Test contract manager initialization."""
    manager = ContractManager(specs_dir=temp_specs_dir)
    assert manager.specs_dir == temp_specs_dir


def test_save_contract(temp_specs_dir, sample_asset):
    """Test saving a contract."""
    manager = ContractManager(specs_dir=temp_specs_dir)
    
    version = manager.save_contract(sample_asset, author="test-user")
    
    assert version.version == "1.0.0"
    assert version.author == "test-user"
    assert version.change_type in ["initial", "non-breaking"]
    
    # Check file was created
    contract_path = manager.get_contract_path("stripe", "customers", "1.0.0")
    assert contract_path.exists()


def test_validate_contract(sample_asset):
    """Test contract validation."""
    manager = ContractManager()
    
    is_valid, errors = manager.validate_contract(sample_asset)
    
    assert is_valid
    assert len(errors) == 0


def test_validate_contract_missing_fields():
    """Test contract validation with missing fields."""
    manager = ContractManager()
    
    # Create invalid asset (missing required fields)
    invalid_asset = AssetDefinition(
        name="test",
        version="1.0.0",
        status="active",
        source_type="test",
        object="test",
        team={"owner": "test@example.com"},
        schema=[],  # Empty schema
    )
    
    is_valid, errors = manager.validate_contract(invalid_asset)
    
    assert not is_valid
    assert len(errors) > 0
    assert any("schema cannot be empty" in error.lower() for error in errors)


def test_detect_breaking_changes(temp_specs_dir):
    """Test breaking change detection."""
    manager = ContractManager(specs_dir=temp_specs_dir)
    
    # Create original contract
    original = AssetDefinition(
        id="test-123",
        name="test",
        version="1.0.0",
        status="active",
        source_type="test",
        object="test",
        team={"owner": "test@example.com"},
        schema=[
            {"name": "id", "type": "string", "required": True},
            {"name": "email", "type": "string", "required": True},
        ],
    )
    
    # Create modified contract (remove required field)
    modified = AssetDefinition(
        id="test-123",
        name="test",
        version="1.0.0",
        status="active",
        source_type="test",
        object="test",
        team={"owner": "test@example.com"},
        schema=[
            {"name": "id", "type": "string", "required": True},
            # email field removed - breaking change!
        ],
    )
    
    breaking_changes = manager._detect_breaking_changes(original, modified)
    
    assert len(breaking_changes) > 0
    assert any("email" in change.lower() for change in breaking_changes)


def test_contract_version_increment():
    """Test version increment logic."""
    manager = ContractManager()
    
    # Test minor version bump (non-breaking)
    new_version = manager._increment_version("1.2.3", "non-breaking")
    assert new_version == "1.3.0"
    
    # Test major version bump (breaking)
    new_version = manager._increment_version("1.2.3", "breaking")
    assert new_version == "2.0.0"


def test_get_contract_history(temp_specs_dir, sample_asset):
    """Test getting contract history."""
    manager = ContractManager(specs_dir=temp_specs_dir)
    
    # Save multiple versions
    manager.save_contract(sample_asset, author="user1")
    
    sample_asset.version = "1.1.0"
    manager.save_contract(sample_asset, author="user2")
    
    history = manager.get_contract_history("stripe", "customers")
    
    assert len(history) >= 1


def test_compare_contracts(temp_specs_dir):
    """Test contract comparison."""
    manager = ContractManager(specs_dir=temp_specs_dir)
    
    # Create and save original version
    original = AssetDefinition(
        id="test-123",
        name="test",
        version="1.0.0",
        status="active",
        source_type="test",
        object="test",
        team={"owner": "test@example.com"},
        schema=[
            {"name": "id", "type": "string", "required": True},
            {"name": "email", "type": "string", "required": True},
        ],
    )
    manager.save_contract(original)
    
    # Create and save new version with changes
    new = AssetDefinition(
        id="test-123",
        name="test",
        version="1.1.0",
        status="active",
        source_type="test",
        object="test",
        team={"owner": "test@example.com"},
        schema=[
            {"name": "id", "type": "string", "required": True},
            {"name": "email", "type": "string", "required": True},
            {"name": "phone", "type": "string", "required": False},  # New field
        ],
    )
    manager.save_contract(new, force=True)
    
    # Compare versions
    comparison = manager.compare_contracts("1.0.0", "1.1.0", "test", "test")
    
    assert comparison["old_version"] == "1.0.0"
    assert comparison["new_version"] == "1.1.0"
    assert "phone" in comparison["fields"]["added"]
