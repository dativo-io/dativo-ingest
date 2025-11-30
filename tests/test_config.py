"""Unit tests for configuration loading and validation."""

import sys
import tempfile
from pathlib import Path

import pytest
import yaml

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dativo_ingest.config import ConnectorRecipe, JobConfig, SourceConnectorRecipe


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


class TestIncrementalStateConfig:
    """Test incremental state configuration merging."""

    def test_incremental_disabled_by_default(self, temp_dir):
        """Test that incremental is disabled by default when not specified in job."""
        # Create a connector recipe with incremental config
        recipe_path = temp_dir / "connector.yaml"
        recipe_data = {
            "name": "test_connector",
            "type": "csv",
            "roles": ["source"],
            "default_engine": {"type": "native", "options": {}},
            "incremental": {
                "strategy": "file_modified_time",
                "lookback_days_default": 0,
            },
        }
        with open(recipe_path, "w") as f:
            yaml.dump(recipe_data, f)

        # Create job config without incremental
        job_config = JobConfig(
            tenant_id="test_tenant",
            source_connector_path=str(recipe_path),
            target_connector_path="connectors/iceberg.yaml",
            asset_path="tests/fixtures/assets/csv/v1.0/employee.yaml",
            source={"files": [{"path": "test.csv"}]},
        )

        # Merge source config
        source_config = job_config.get_source()

        # Incremental should be None (disabled) even though recipe has it
        assert source_config.incremental is None

    def test_incremental_enabled_when_explicitly_configured(self, temp_dir):
        """Test that incremental is enabled when explicitly configured in job."""
        # Create a connector recipe with incremental config
        recipe_path = temp_dir / "connector.yaml"
        recipe_data = {
            "name": "test_connector",
            "type": "csv",
            "roles": ["source"],
            "default_engine": {"type": "native", "options": {}},
            "incremental": {
                "strategy": "file_modified_time",
                "lookback_days_default": 0,
            },
        }
        with open(recipe_path, "w") as f:
            yaml.dump(recipe_data, f)

        # Create job config with incremental explicitly enabled
        job_config = JobConfig(
            tenant_id="test_tenant",
            source_connector_path=str(recipe_path),
            target_connector_path="connectors/iceberg.yaml",
            asset_path="tests/fixtures/assets/csv/v1.0/employee.yaml",
            source={
                "files": [{"path": "test.csv"}],
                "incremental": {
                    "strategy": "file_modified_time",
                    "lookback_days": 0,
                },
            },
        )

        # Merge source config
        source_config = job_config.get_source()

        # Incremental should be enabled
        assert source_config.incremental is not None
        assert isinstance(source_config.incremental, dict)
        assert source_config.incremental["strategy"] == "file_modified_time"
        assert source_config.incremental["lookback_days"] == 0

    def test_incremental_disabled_with_empty_dict(self, temp_dir):
        """Test that incremental is disabled when set to empty dict in job."""
        # Create a connector recipe with incremental config
        recipe_path = temp_dir / "connector.yaml"
        recipe_data = {
            "name": "test_connector",
            "type": "csv",
            "roles": ["source"],
            "default_engine": {"type": "native", "options": {}},
            "incremental": {
                "strategy": "file_modified_time",
                "lookback_days_default": 0,
            },
        }
        with open(recipe_path, "w") as f:
            yaml.dump(recipe_data, f)

        # Create job config with incremental set to empty dict
        job_config = JobConfig(
            tenant_id="test_tenant",
            source_connector_path=str(recipe_path),
            target_connector_path="connectors/iceberg.yaml",
            asset_path="tests/fixtures/assets/csv/v1.0/employee.yaml",
            source={
                "files": [{"path": "test.csv"}],
                "incremental": {},  # Empty dict should disable incremental
            },
        )

        # Merge source config
        source_config = job_config.get_source()

        # Incremental should be None (disabled) even though recipe has it
        assert source_config.incremental is None

    def test_incremental_merges_with_recipe_defaults(self, temp_dir):
        """Test that job incremental config merges with recipe defaults."""
        # Create a connector recipe with incremental config
        recipe_path = temp_dir / "connector.yaml"
        recipe_data = {
            "name": "test_connector",
            "type": "csv",
            "roles": ["source"],
            "default_engine": {"type": "native", "options": {}},
            "incremental": {
                "strategy": "file_modified_time",
                "lookback_days_default": 7,  # Recipe default
            },
        }
        with open(recipe_path, "w") as f:
            yaml.dump(recipe_data, f)

        # Create job config with incremental enabled but only strategy specified
        job_config = JobConfig(
            tenant_id="test_tenant",
            source_connector_path=str(recipe_path),
            target_connector_path="connectors/iceberg.yaml",
            asset_path="tests/fixtures/assets/csv/v1.0/employee.yaml",
            source={
                "files": [{"path": "test.csv"}],
                "incremental": {
                    "strategy": "file_modified_time",
                    # lookback_days not specified - should use recipe default
                },
            },
        )

        # Merge source config
        source_config = job_config.get_source()

        # Incremental should be enabled and merged with recipe defaults
        assert source_config.incremental is not None
        assert isinstance(source_config.incremental, dict)
        assert source_config.incremental["strategy"] == "file_modified_time"
        # Should have state_path added automatically
        assert "state_path" in source_config.incremental
