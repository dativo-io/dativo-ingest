"""Integration tests for ConnectorValidator with ConnectorRegistry."""

import sys
import tempfile
from pathlib import Path

import pytest
import yaml

from src.dativo_ingest.registry import RegistryLoadError, RegistryNotFoundError
from src.dativo_ingest.validator import ConnectorValidator


class TestValidatorRegistryIntegration:
    """Test ConnectorValidator integration with ConnectorRegistry."""

    def test_missing_registry_file_deterministic_error(self, tmp_path):
        """Missing registry file should fail with deterministic error."""
        non_existent = tmp_path / "nonexistent.yaml"

        with pytest.raises(RegistryNotFoundError) as exc_info:
            ConnectorValidator(registry_path=non_existent)

        error_msg = str(exc_info.value)
        assert "not found" in error_msg.lower() or "does not exist" in error_msg.lower()
        assert (
            "mount" in error_msg.lower()
            or "docker" in error_msg.lower()
            or "env var" in error_msg.lower()
        )

    def test_malformed_registry_yaml_deterministic_error(self, tmp_path):
        """Malformed registry YAML should fail with deterministic error."""
        invalid_yaml = tmp_path / "invalid.yaml"
        invalid_yaml.write_text("invalid: yaml: content: [")

        with pytest.raises(RegistryLoadError) as exc_info:
            ConnectorValidator(registry_path=invalid_yaml)

        error_msg = str(exc_info.value)
        assert (
            "parse" in error_msg.lower()
            or "yaml" in error_msg.lower()
            or "load" in error_msg.lower()
        )

    def test_empty_registry_yaml_deterministic_error(self, tmp_path):
        """Empty registry YAML should fail with deterministic error."""
        empty_yaml = tmp_path / "empty.yaml"
        empty_yaml.write_text("")

        with pytest.raises(RegistryLoadError) as exc_info:
            ConnectorValidator(registry_path=empty_yaml)

        error_msg = str(exc_info.value)
        assert "empty" in error_msg.lower() or "load" in error_msg.lower()

    def test_unknown_connector_fails_fast(self, tmp_path):
        """Unknown connector in job config should fail fast with clear error."""
        # Create valid registry without the connector we'll test
        registry_data = {
            "version": "1.0",
            "connectors": {
                "hubspot": {
                    "roles": ["source"],
                    "default_engine": "airbyte",
                }
            },
        }
        registry_file = tmp_path / "connectors.yaml"
        with open(registry_file, "w") as f:
            yaml.dump(registry_data, f)

        validator = ConnectorValidator(registry_path=registry_file)

        # Try to validate unknown connector
        with pytest.raises(SystemExit) as exc_info:
            validator.validate_connector_type("nonexistent_connector", role="source")

        # Should exit with code 2
        assert exc_info.value.code == 2

    def test_connector_role_mismatch_fails_fast(self, tmp_path):
        """Connector that doesn't support requested role should fail fast."""
        # Create registry with source-only connector
        registry_data = {
            "version": "1.0",
            "connectors": {
                "hubspot": {
                    "roles": ["source"],  # Source only
                    "default_engine": "airbyte",
                }
            },
        }
        registry_file = tmp_path / "connectors.yaml"
        with open(registry_file, "w") as f:
            yaml.dump(registry_data, f)

        validator = ConnectorValidator(registry_path=registry_file)

        # Try to validate as target (should fail)
        with pytest.raises(SystemExit) as exc_info:
            validator.validate_connector_type("hubspot", role="target")

        # Should exit with code 2
        assert exc_info.value.code == 2

    def test_valid_connector_passes_validation(self, tmp_path):
        """Valid connector with correct role should pass validation."""
        registry_data = {
            "version": "1.0",
            "connectors": {
                "hubspot": {
                    "roles": ["source"],
                    "default_engine": "airbyte",
                    "allowed_in_cloud": True,
                }
            },
        }
        registry_file = tmp_path / "connectors.yaml"
        with open(registry_file, "w") as f:
            yaml.dump(registry_data, f)

        validator = ConnectorValidator(registry_path=registry_file)

        # Should not raise
        entry = validator.validate_connector_type("hubspot", role="source")
        assert entry is not None
        assert entry["roles"] == ["source"]

    def test_mode_restriction_enforced(self, tmp_path):
        """Cloud mode restriction should be enforced."""
        registry_data = {
            "version": "1.0",
            "connectors": {
                "postgres": {
                    "roles": ["source"],
                    "default_engine": "native",
                    "allowed_in_cloud": False,  # Not allowed in cloud
                }
            },
        }
        registry_file = tmp_path / "connectors.yaml"
        with open(registry_file, "w") as f:
            yaml.dump(registry_data, f)

        validator = ConnectorValidator(registry_path=registry_file)
        connector_def = validator.validate_connector_type("postgres", role="source")

        # Try to validate in cloud mode (should fail)
        with pytest.raises(SystemExit) as exc_info:
            validator.validate_mode_restriction("postgres", "cloud", connector_def)

        # Should exit with code 2
        assert exc_info.value.code == 2
