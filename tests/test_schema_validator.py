"""Unit tests for schema validator."""

import datetime
import pytest

from dativo_ingest.config import AssetDefinition
from dativo_ingest.schema_validator import SchemaValidator, ValidationError


@pytest.fixture
def sample_asset_definition():
    """Create a sample asset definition for testing."""
    return AssetDefinition(
        name="test_asset",
        version="1.0.0",
        source_type="csv",
        object="test_object",
        schema=[
            {"name": "id", "type": "integer", "required": True},
            {"name": "name", "type": "string", "required": True},
            {"name": "email", "type": "string", "required": False},
            {"name": "age", "type": "integer", "required": False},
            {"name": "active", "type": "boolean", "required": False},
            {"name": "created_at", "type": "timestamp", "required": True},
        ],
        team={"owner": "test@example.com"},
        compliance={"classification": ["INTERNAL"], "retention_days": 30},
        finops={"cost_center": "FIN-TEST"},
        lineage=[
            {
                "from_asset": "source.system",
                "to_asset": "test_asset",
                "contract_version": "1.0.0",
            }
        ],
        audit=[
            {
                "author": "test@example.com",
                "timestamp": "2025-01-01T00:00:00Z",
                "hash": "0" * 64,
            }
        ],
    )


def test_validate_record_strict_mode_valid(sample_asset_definition):
    """Test validation of valid record in strict mode."""
    validator = SchemaValidator(sample_asset_definition, validation_mode="strict")
    
    record = {
        "id": 1,
        "name": "Test User",
        "email": "test@example.com",
        "age": 30,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
    }
    
    is_valid, coerced = validator.validate_record(record, 0)
    
    assert is_valid
    assert coerced is not None
    assert coerced["id"] == 1
    assert coerced["name"] == "Test User"
    assert isinstance(coerced["created_at"], datetime.datetime)


def test_validate_record_strict_mode_missing_required(sample_asset_definition):
    """Test validation fails in strict mode when required field is missing."""
    validator = SchemaValidator(sample_asset_definition, validation_mode="strict")
    
    record = {
        "name": "Test User",
        # Missing required field "id"
    }
    
    is_valid, coerced = validator.validate_record(record, 0)
    
    assert not is_valid
    assert coerced is None
    assert len(validator.errors) > 0
    assert any(e.field_name == "id" and e.error_type == "missing_required" for e in validator.errors)


def test_validate_record_warn_mode(sample_asset_definition):
    """Test validation in warn mode allows records with errors."""
    validator = SchemaValidator(sample_asset_definition, validation_mode="warn")
    
    record = {
        "name": "Test User",
        # Missing required field "id"
    }
    
    is_valid, coerced = validator.validate_record(record, 0)
    
    assert is_valid  # Warn mode allows invalid records
    assert coerced is not None
    assert len(validator.errors) > 0


def test_type_coercion_string(sample_asset_definition):
    """Test type coercion for string fields."""
    validator = SchemaValidator(sample_asset_definition, validation_mode="strict")
    
    record = {
        "id": "123",  # String that should be integer
        "name": 12345,  # Integer that should be string
        "created_at": "2024-01-01T00:00:00",
    }
    
    is_valid, coerced = validator.validate_record(record, 0)
    
    assert is_valid
    assert isinstance(coerced["id"], int)
    assert coerced["id"] == 123
    assert isinstance(coerced["name"], str)
    assert coerced["name"] == "12345"


def test_type_coercion_boolean(sample_asset_definition):
    """Test type coercion for boolean fields."""
    validator = SchemaValidator(sample_asset_definition, validation_mode="strict")
    
    record = {
        "id": 1,
        "name": "Test",
        "active": "true",  # String boolean
        "created_at": "2024-01-01T00:00:00",
    }
    
    is_valid, coerced = validator.validate_record(record, 0)
    
    assert is_valid
    assert isinstance(coerced["active"], bool)
    assert coerced["active"] is True


def test_validate_batch(sample_asset_definition):
    """Test batch validation."""
    validator = SchemaValidator(sample_asset_definition, validation_mode="strict")
    
    records = [
        {"id": 1, "name": "User 1", "created_at": "2024-01-01T00:00:00"},
        {"id": 2, "name": "User 2", "created_at": "2024-01-01T00:00:00"},
        {"name": "User 3", "created_at": "2024-01-01T00:00:00"},  # Missing id
    ]
    
    valid_records, errors = validator.validate_batch(records)
    
    # In strict mode, only valid records should be returned
    assert len(valid_records) == 2
    assert len(errors) > 0


def test_get_error_summary(sample_asset_definition):
    """Test error summary generation."""
    validator = SchemaValidator(sample_asset_definition, validation_mode="strict")
    
    records = [
        {"name": "User 1", "created_at": "2024-01-01T00:00:00"},  # Missing id
        {"id": "invalid", "name": "User 2", "created_at": "2024-01-01T00:00:00"},  # Invalid id type
    ]
    
    validator.validate_batch(records)
    summary = validator.get_error_summary()
    
    assert summary["total_errors"] > 0
    assert "errors_by_type" in summary
    assert "errors_by_field" in summary

