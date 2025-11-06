"""Unit tests for M1.1 CLI and validation functionality."""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
import yaml

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dativo_ingest.config import JobConfig, RunnerConfig
from dativo_ingest.validator import ConnectorValidator, IncrementalStateManager


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
        "source": {
            "type": "stripe",
            "credentials": {"from_env": "STRIPE_API_KEY"},
            "objects": ["customers"],
        },
        "target": {
            "type": "iceberg",
            "catalog": "nessie",
            "branch": "test_tenant",
            "warehouse": "s3://lake/test/",
        },
        "asset_definition": str(temp_dir / "spec.yaml"),
    }
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)
    return config_path


@pytest.fixture
def valid_spec_file(temp_dir):
    """Create a valid spec file with schema."""
    spec_path = temp_dir / "spec.yaml"
    spec_data = {
        "asset": {
            "tenant_id": "test_tenant",
            "source": "stripe",
            "object": "customers",
            "schema": [
                {"name": "id", "type": "string", "required": True},
                {"name": "email", "type": "string", "required": False},
            ],
        }
    }
    with open(spec_path, "w") as f:
        yaml.dump(spec_data, f)
    return spec_path


@pytest.fixture
def registry_file(temp_dir):
    """Create a minimal registry file."""
    registry_path = temp_dir / "registry.yaml"
    registry_data = {
        "version": 2,
        "sources": {
            "stripe": {
                "category": "payments",
                "default_engine": "airbyte",
                "engines_supported": ["airbyte"],
                "allowed_in_cloud": True,
                "supports_incremental": True,
                "incremental_strategy_default": "created",
                "auth": {
                    "type": "api_key",
                    "credentials_spec": {"from_env": ["STRIPE_API_KEY"]},
                },
            },
            "postgres": {
                "category": "database",
                "default_engine": "jdbc",
                "engines_supported": ["jdbc"],
                "allowed_in_cloud": False,
                "supports_incremental": True,
                "incremental_strategy_default": "updated_at",
                "auth": {
                    "type": "basic",
                    "credentials_spec": {"from_env": ["PGHOST"]},
                },
            },
        },
        "targets": {
            "iceberg": {
                "default_engine": "native",
                "engines_supported": ["native"],
            }
        },
    }
    with open(registry_path, "w") as f:
        yaml.dump(registry_data, f)
    return registry_path


class TestConfigValidation:
    """Test configuration loading and validation."""

    def test_valid_job_config(self, valid_job_config, valid_spec_file):
        """Test loading a valid job config."""
        config = JobConfig.from_yaml(valid_job_config)
        assert config.tenant_id == "test_tenant"
        assert config.source.type == "stripe"
        assert config.target.type == "iceberg"

    def test_missing_config_file(self, temp_dir):
        """Test error when config file doesn't exist."""
        config_path = temp_dir / "nonexistent.yaml"
        with pytest.raises(SystemExit) as exc_info:
            JobConfig.from_yaml(config_path)
        assert exc_info.value.code == 2

    def test_invalid_yaml(self, temp_dir):
        """Test error when config has invalid YAML."""
        config_path = temp_dir / "invalid.yaml"
        with open(config_path, "w") as f:
            f.write("invalid: yaml: content: [")
        with pytest.raises(SystemExit) as exc_info:
            JobConfig.from_yaml(config_path)
        assert exc_info.value.code == 2

    def test_schema_validation_missing_file(self, valid_job_config, temp_dir):
        """Test schema validation fails when spec file doesn't exist."""
        config = JobConfig.from_yaml(valid_job_config)
        # Point to non-existent file
        config.asset_definition = str(temp_dir / "nonexistent.yaml")
        with pytest.raises(SystemExit) as exc_info:
            config.validate_schema_presence()
        assert exc_info.value.code == 2

    def test_schema_validation_missing_asset_field(self, valid_job_config, temp_dir):
        """Test schema validation fails when asset field is missing."""
        spec_path = temp_dir / "spec.yaml"
        with open(spec_path, "w") as f:
            yaml.dump({"not_asset": {}}, f)
        config = JobConfig.from_yaml(valid_job_config)
        with pytest.raises(SystemExit) as exc_info:
            config.validate_schema_presence()
        assert exc_info.value.code == 2

    def test_schema_validation_missing_schema_field(
        self, valid_job_config, temp_dir
    ):
        """Test schema validation fails when schema field is missing."""
        spec_path = temp_dir / "spec.yaml"
        spec_data = {"asset": {"tenant_id": "test"}}
        with open(spec_path, "w") as f:
            yaml.dump(spec_data, f)
        config = JobConfig.from_yaml(valid_job_config)
        with pytest.raises(SystemExit) as exc_info:
            config.validate_schema_presence()
        assert exc_info.value.code == 2

    def test_schema_validation_empty_schema_array(
        self, valid_job_config, temp_dir
    ):
        """Test schema validation fails when schema array is empty."""
        spec_path = temp_dir / "spec.yaml"
        spec_data = {"asset": {"schema": []}}
        with open(spec_path, "w") as f:
            yaml.dump(spec_data, f)
        config = JobConfig.from_yaml(valid_job_config)
        with pytest.raises(SystemExit) as exc_info:
            config.validate_schema_presence()
        assert exc_info.value.code == 2

    def test_schema_validation_valid_schema(self, valid_job_config, valid_spec_file):
        """Test schema validation passes with valid schema."""
        config = JobConfig.from_yaml(valid_job_config)
        # Should not raise
        config.validate_schema_presence()


class TestConnectorValidation:
    """Test connector validation."""

    def test_validate_connector_type_exists(self, registry_file):
        """Test validating a connector that exists in registry."""
        validator = ConnectorValidator(registry_file)
        connector_def = validator.validate_connector_type("stripe")
        assert connector_def["category"] == "payments"

    def test_validate_connector_type_missing(self, registry_file):
        """Test error when connector type doesn't exist."""
        validator = ConnectorValidator(registry_file)
        with pytest.raises(SystemExit) as exc_info:
            validator.validate_connector_type("nonexistent")
        assert exc_info.value.code == 2

    def test_validate_mode_restriction_cloud_blocked(
        self, registry_file, valid_job_config, valid_spec_file, temp_dir
    ):
        """Test database connectors blocked in cloud mode."""
        # Create postgres job config
        config_path = temp_dir / "postgres_job.yaml"
        config_data = {
            "tenant_id": "test",
            "source": {"type": "postgres", "tables": [{"name": "test"}]},
            "target": {"type": "iceberg", "warehouse": "s3://test/"},
        }
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        config = JobConfig.from_yaml(config_path)
        validator = ConnectorValidator(registry_file)
        with pytest.raises(SystemExit) as exc_info:
            validator.validate_mode_restriction(
                "postgres", "cloud", validator.registry["sources"]["postgres"]
            )
        assert exc_info.value.code == 2

    def test_validate_mode_restriction_self_hosted_allowed(
        self, registry_file, valid_job_config, valid_spec_file, temp_dir
    ):
        """Test database connectors allowed in self_hosted mode."""
        config_path = temp_dir / "postgres_job.yaml"
        config_data = {
            "tenant_id": "test",
            "source": {"type": "postgres", "tables": [{"name": "test"}]},
            "target": {"type": "iceberg", "warehouse": "s3://test/"},
        }
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        config = JobConfig.from_yaml(config_path)
        validator = ConnectorValidator(registry_file)
        # Should not raise
        validator.validate_mode_restriction(
            "postgres",
            "self_hosted",
            validator.registry["sources"]["postgres"],
        )

    def test_validate_incremental_strategy_valid(
        self, registry_file, valid_job_config, valid_spec_file
    ):
        """Test incremental strategy validation with valid strategy."""
        config = JobConfig.from_yaml(valid_job_config)
        config.source.incremental = {
            "strategy": "created",
            "cursor_field": "created",
        }
        validator = ConnectorValidator(registry_file)
        # Should not raise
        validator.validate_incremental_strategy(
            config, validator.registry["sources"]["stripe"]
        )

    def test_validate_incremental_strategy_missing_cursor_field(
        self, registry_file, valid_job_config, valid_spec_file
    ):
        """Test incremental strategy validation fails without cursor_field."""
        config = JobConfig.from_yaml(valid_job_config)
        config.source.incremental = {"strategy": "created"}
        validator = ConnectorValidator(registry_file)
        with pytest.raises(SystemExit) as exc_info:
            validator.validate_incremental_strategy(
                config, validator.registry["sources"]["stripe"]
            )
        assert exc_info.value.code == 2

    def test_validate_incremental_strategy_invalid(
        self, registry_file, valid_job_config, valid_spec_file
    ):
        """Test incremental strategy validation fails with invalid strategy."""
        config = JobConfig.from_yaml(valid_job_config)
        config.source.incremental = {
            "strategy": "invalid_strategy",
            "cursor_field": "created",
        }
        validator = ConnectorValidator(registry_file)
        with pytest.raises(SystemExit) as exc_info:
            validator.validate_incremental_strategy(
                config, validator.registry["sources"]["stripe"]
            )
        assert exc_info.value.code == 2


class TestIncrementalStateManager:
    """Test incremental state management."""

    def test_read_state_nonexistent(self, temp_dir):
        """Test reading state from non-existent file returns empty dict."""
        state_path = temp_dir / "state.json"
        state = IncrementalStateManager.read_state(state_path)
        assert state == {}

    def test_read_write_state(self, temp_dir):
        """Test reading and writing state."""
        state_path = temp_dir / "state.json"
        test_state = {"file_123": {"last_modified": "2024-01-01T00:00:00Z"}}
        IncrementalStateManager.write_state(state_path, test_state)
        read_state = IncrementalStateManager.read_state(state_path)
        assert read_state == test_state

    def test_should_skip_file_no_state(self, temp_dir):
        """Test file should not be skipped if no state exists."""
        state_path = temp_dir / "state.json"
        result = IncrementalStateManager.should_skip_file(
            "file_123", "2024-01-01T00:00:00Z", state_path
        )
        assert result is False

    def test_should_skip_file_not_modified(self, temp_dir):
        """Test file should be skipped if not modified."""
        state_path = temp_dir / "state.json"
        # Write initial state
        IncrementalStateManager.write_state(
            state_path, {"file_123": {"last_modified": "2024-01-02T00:00:00Z"}}
        )
        # Check with older timestamp
        result = IncrementalStateManager.should_skip_file(
            "file_123", "2024-01-01T00:00:00Z", state_path, lookback_days=0
        )
        assert result is True

    def test_update_file_state(self, temp_dir):
        """Test updating file state."""
        state_path = temp_dir / "state.json"
        IncrementalStateManager.update_file_state(
            "file_123", "2024-01-01T00:00:00Z", state_path
        )
        state = IncrementalStateManager.read_state(state_path)
        assert "file_file_123" in state
        assert state["file_file_123"]["last_modified"] == "2024-01-01T00:00:00Z"


class TestErrorMessages:
    """Test error messages include connector context."""

    def test_error_includes_connector_type(self, registry_file, temp_dir):
        """Test error messages include connector type."""
        config_path = temp_dir / "job.yaml"
        config_data = {
            "tenant_id": "test",
            "source": {"type": "nonexistent"},
            "target": {"type": "iceberg", "warehouse": "s3://test/"},
        }
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        config = JobConfig.from_yaml(config_path)
        validator = ConnectorValidator(registry_file)
        with pytest.raises(SystemExit) as exc_info:
            validator.validate_connector_type("nonexistent")
        assert exc_info.value.code == 2

