"""Tests for DBT integration."""

import tempfile
from pathlib import Path

import pytest
import yaml

from dativo_ingest.config import AssetDefinition
from dativo_ingest.dbt_integration import DBTGenerator


@pytest.fixture
def temp_dbt_dir():
    """Create temporary dbt directory."""
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
            {"name": "id", "type": "string", "required": True, "unique": True},
            {"name": "email", "type": "string", "required": True, "classification": "PII"},
            {"name": "created_at", "type": "timestamp", "required": True},
        ],
        description={
            "purpose": "Customer data from Stripe",
            "usage": "Used for analytics and reporting",
        },
        compliance={
            "classification": ["PII"],
            "retention_days": 90,
        },
        tags=["stripe", "customers"],
    )


def test_dbt_generator_initialization(temp_dbt_dir):
    """Test DBT generator initialization."""
    generator = DBTGenerator(output_dir=temp_dbt_dir)
    assert generator.output_dir == temp_dbt_dir


def test_generate_source_yaml(sample_asset):
    """Test generating dbt source YAML."""
    generator = DBTGenerator()
    
    source_yaml = generator.generate_source_yaml(sample_asset)
    
    assert "version" in source_yaml
    assert source_yaml["version"] == 2
    assert "sources" in source_yaml
    
    sources = source_yaml["sources"]
    assert len(sources) > 0
    
    source = sources[0]
    assert source["name"] == "stripe"
    assert "tables" in source
    
    tables = source["tables"]
    assert len(tables) > 0
    
    table = tables[0]
    assert table["name"] == "customers"
    assert "columns" in table
    assert len(table["columns"]) == 3


def test_generate_model_yaml(sample_asset):
    """Test generating dbt model YAML."""
    generator = DBTGenerator()
    
    model_yaml = generator.generate_model_yaml(sample_asset)
    
    assert "version" in model_yaml
    assert model_yaml["version"] == 2
    assert "models" in model_yaml
    
    models = model_yaml["models"]
    assert len(models) > 0
    
    model = models[0]
    assert "stg_" in model["name"]
    assert "columns" in model
    assert len(model["columns"]) == 3
    
    # Check tests are included
    id_column = next(c for c in model["columns"] if c["name"] == "id")
    assert "tests" in id_column
    assert "unique" in id_column["tests"]


def test_generate_exposure_yaml(sample_asset):
    """Test generating dbt exposure YAML."""
    generator = DBTGenerator()
    
    exposure_yaml = generator.generate_exposure_yaml(
        sample_asset,
        exposure_name="customers_dashboard",
        exposure_type="dashboard",
    )
    
    assert "version" in exposure_yaml
    assert exposure_yaml["version"] == 2
    assert "exposures" in exposure_yaml
    
    exposures = exposure_yaml["exposures"]
    assert len(exposures) > 0
    
    exposure = exposures[0]
    assert exposure["name"] == "customers_dashboard"
    assert exposure["type"] == "dashboard"
    assert "owner" in exposure


def test_save_dbt_yaml(temp_dbt_dir, sample_asset):
    """Test saving dbt YAML file."""
    generator = DBTGenerator(output_dir=temp_dbt_dir)
    
    file_path = generator.save_dbt_yaml(sample_asset, yaml_type="source")
    
    assert file_path.exists()
    assert file_path.suffix == ".yml"
    
    # Verify content
    with open(file_path) as f:
        content = yaml.safe_load(f)
    
    assert content["version"] == 2
    assert "sources" in content


def test_generate_dbt_project_yml():
    """Test generating dbt_project.yml."""
    generator = DBTGenerator()
    
    project_yml = generator.generate_dbt_project_yml(
        project_name="dativo_analytics"
    )
    
    assert project_yml["name"] == "dativo_analytics"
    assert project_yml["config-version"] == 2
    assert "models" in project_yml


def test_generate_schema_test(sample_asset):
    """Test generating dbt schema tests."""
    generator = DBTGenerator()
    
    test_sql = generator.generate_schema_test(sample_asset)
    
    assert isinstance(test_sql, str)
    assert len(test_sql) > 0
    assert "select" in test_sql.lower()
    assert "is null" in test_sql.lower()  # not_null test


def test_map_odcs_type_to_dbt():
    """Test ODCS to dbt type mapping."""
    generator = DBTGenerator()
    
    assert generator._map_odcs_type_to_dbt("string") == "string"
    assert generator._map_odcs_type_to_dbt("integer") == "integer"
    assert generator._map_odcs_type_to_dbt("timestamp") == "timestamp"
    assert generator._map_odcs_type_to_dbt("boolean") == "boolean"


def test_classification_tags_in_columns(sample_asset):
    """Test that classification tags are included in column definitions."""
    generator = DBTGenerator()
    
    source_yaml = generator.generate_source_yaml(sample_asset)
    
    # Find email column
    columns = source_yaml["sources"][0]["tables"][0]["columns"]
    email_column = next(c for c in columns if c["name"] == "email")
    
    assert "tags" in email_column
    assert "pii" in email_column["tags"]
