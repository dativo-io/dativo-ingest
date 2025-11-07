"""Unit tests for configuration loading and validation."""

import sys
import tempfile
from pathlib import Path

import pytest
import yaml

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dativo_ingest.config import JobConfig


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def valid_job_config(temp_dir):
    """Create a valid job config file."""
    config_path = temp_dir / "job.yaml"
    config_data = {
        "tenant_id": "test_tenant",
        "source_connector_path": "connectors/stripe.yaml",
        "target_connector_path": "connectors/iceberg.yaml",
        "asset_path": str(temp_dir / "asset.yaml"),
        "source": {
            "objects": ["customers"],
        },
        "target": {
            "branch": "test_tenant",
            "warehouse": "s3://lake/test/",
        },
    }
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)
    return config_path


@pytest.fixture
def valid_asset_file(temp_dir):
    """Create a valid asset definition file."""
    asset_path = temp_dir / "asset.yaml"
    asset_data = {
        "$schema": "schemas/odcs/dativo-odcs-3.0.2-extended.schema.json",
        "apiVersion": "v3.0.2",
        "kind": "DataContract",
        "name": "test_asset",
        "version": "1.0",
        "status": "active",
        "schema": [
            {"name": "id", "type": "string", "required": True},
            {"name": "email", "type": "string", "required": False},
        ],
        "team": {
            "owner": "test@example.com",
        },
        "data_quality": {
            "monitoring": {
                "enabled": True,
                "oncall_rotation": "test@example.com",
            },
        },
    }
    with open(asset_path, "w") as f:
        yaml.dump(asset_data, f)
    return asset_path


class TestJobConfigLoading:
    """Test JobConfig loading from YAML files."""

    def test_load_valid_job_config(self, valid_job_config, valid_asset_file):
        """Test loading a valid job config."""
        config = JobConfig.from_yaml(valid_job_config)
        assert config.tenant_id == "test_tenant"
        assert config.source_connector_path == "connectors/stripe.yaml"
        assert config.target_connector_path == "connectors/iceberg.yaml"

    def test_load_missing_config_file(self, temp_dir):
        """Test error when config file doesn't exist."""
        config_path = temp_dir / "nonexistent.yaml"
        with pytest.raises((FileNotFoundError, SystemExit)):
            JobConfig.from_yaml(config_path)

    def test_load_invalid_yaml(self, temp_dir):
        """Test error when config has invalid YAML."""
        config_path = temp_dir / "invalid.yaml"
        with open(config_path, "w") as f:
            f.write("invalid: yaml: content: [")
        with pytest.raises((yaml.YAMLError, SystemExit)):
            JobConfig.from_yaml(config_path)


class TestAssetDefinitionValidation:
    """Test asset definition schema validation."""

    def test_validate_schema_presence_missing_file(self, valid_job_config, temp_dir):
        """Test schema validation fails when asset file doesn't exist."""
        config = JobConfig.from_yaml(valid_job_config)
        config.asset_path = str(temp_dir / "nonexistent.yaml")
        with pytest.raises((FileNotFoundError, SystemExit)):
            config.validate_schema_presence()

    def test_validate_schema_presence_missing_schema_field(
        self, valid_job_config, temp_dir
    ):
        """Test schema validation fails when schema field is missing."""
        asset_path = temp_dir / "asset.yaml"
        asset_data = {
            "$schema": "schemas/odcs/dativo-odcs-3.0.2-extended.schema.json",
            "apiVersion": "v3.0.2",
            "kind": "DataContract",
            "name": "test_asset",
            "version": "1.0",
            "status": "active",
            # Missing schema field
            "team": {"owner": "test@example.com"},
        }
        with open(asset_path, "w") as f:
            yaml.dump(asset_data, f)

        config = JobConfig.from_yaml(valid_job_config)
        config.asset_path = str(asset_path)
        with pytest.raises((ValueError, SystemExit)):
            config.validate_schema_presence()

    def test_validate_schema_presence_empty_schema_array(
        self, valid_job_config, temp_dir
    ):
        """Test schema validation fails when schema array is empty."""
        asset_path = temp_dir / "asset.yaml"
        asset_data = {
            "$schema": "schemas/odcs/dativo-odcs-3.0.2-extended.schema.json",
            "apiVersion": "v3.0.2",
            "kind": "DataContract",
            "name": "test_asset",
            "version": "1.0",
            "status": "active",
            "schema": [],  # Empty schema
            "team": {"owner": "test@example.com"},
        }
        with open(asset_path, "w") as f:
            yaml.dump(asset_data, f)

        config = JobConfig.from_yaml(valid_job_config)
        config.asset_path = str(asset_path)
        with pytest.raises((ValueError, SystemExit)):
            config.validate_schema_presence()

    def test_validate_schema_presence_valid_schema(
        self, valid_job_config, valid_asset_file
    ):
        """Test schema validation passes with valid schema."""
        config = JobConfig.from_yaml(valid_job_config)
        config.asset_path = str(valid_asset_file)
        # Should not raise
        config.validate_schema_presence()

