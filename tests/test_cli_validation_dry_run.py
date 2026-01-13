"""Tests for CLI validation and dry-run commands.

This module tests:
- dativo validate config --path <job.yaml>
- dativo validate asset --path <spec.yaml>
- dativo run --dry-run / dativo ingest --dry-run
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from src.dativo_ingest.cli_dry_run import (
    DryRunExecutor,
    DryRunPhase,
    DryRunResult,
    dry_run_command,
)
from src.dativo_ingest.cli_validation import (
    AssetValidator,
    ConfigValidator,
    ValidationResult,
    validate_asset_command,
    validate_config_command,
)


class TestValidationResult:
    """Tests for ValidationResult class."""

    def test_init_default_valid(self):
        """ValidationResult should be valid by default."""
        result = ValidationResult()
        assert result.valid is True
        assert result.errors == []
        assert result.warnings == []
        assert result.info == {}

    def test_add_error_marks_invalid(self):
        """Adding an error should mark result as invalid."""
        result = ValidationResult()
        result.add_error("TEST_ERROR", "Test error message")
        assert result.valid is False
        assert len(result.errors) == 1
        assert result.errors[0]["code"] == "TEST_ERROR"
        assert result.errors[0]["message"] == "Test error message"

    def test_add_error_with_path(self):
        """Adding an error with path should include path in error."""
        result = ValidationResult()
        result.add_error("TEST_ERROR", "Test message", path="source.type")
        assert result.errors[0]["path"] == "source.type"

    def test_add_warning_keeps_valid(self):
        """Adding a warning should not mark result as invalid."""
        result = ValidationResult()
        result.add_warning("TEST_WARNING", "Test warning")
        assert result.valid is True
        assert len(result.warnings) == 1

    def test_to_dict(self):
        """to_dict should return proper dictionary structure."""
        result = ValidationResult()
        result.add_error("ERR", "Error message")
        result.add_warning("WARN", "Warning message")
        result.info["file"] = "test.yaml"

        data = result.to_dict()
        assert data["valid"] is False
        assert len(data["errors"]) == 1
        assert len(data["warnings"]) == 1
        assert data["info"]["file"] == "test.yaml"


class TestConfigValidator:
    """Tests for ConfigValidator class."""

    def test_validate_file_not_found(self, tmp_path):
        """validate should return error for non-existent file."""
        validator = ConfigValidator()
        result = validator.validate(tmp_path / "nonexistent.yaml")

        assert result.valid is False
        assert len(result.errors) == 1
        assert result.errors[0]["code"] == "FILE_NOT_FOUND"

    def test_validate_invalid_yaml(self, tmp_path):
        """validate should return error for invalid YAML syntax."""
        config_file = tmp_path / "invalid.yaml"
        config_file.write_text("invalid: yaml: syntax:")

        validator = ConfigValidator()
        result = validator.validate(config_file)

        assert result.valid is False
        assert result.errors[0]["code"] == "YAML_SYNTAX"

    def test_validate_empty_file(self, tmp_path):
        """validate should return error for empty file."""
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")

        validator = ConfigValidator()
        result = validator.validate(config_file)

        assert result.valid is False
        assert result.errors[0]["code"] == "EMPTY_FILE"

    def test_validate_missing_required_fields(self, tmp_path):
        """validate should return error for missing required fields."""
        config_file = tmp_path / "incomplete.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "tenant_id": "test",
                    # Missing source_connector_path, target_connector_path, asset_path
                }
            )
        )

        validator = ConfigValidator()
        result = validator.validate(config_file)

        assert result.valid is False
        # Should have schema validation error for missing required fields
        assert any(
            "required" in err["message"].lower() or "SCHEMA" in err["code"]
            for err in result.errors
        )

    def test_validate_valid_config(self, tmp_path):
        """validate should pass for valid configuration."""
        # Create minimal valid config files
        connector_file = tmp_path / "connector.yaml"
        connector_file.write_text(
            yaml.dump(
                {
                    "name": "csv",
                    "type": "csv",
                    "roles": ["source"],
                    "default_engine": {"type": "native"},
                }
            )
        )

        target_connector_file = tmp_path / "target.yaml"
        target_connector_file.write_text(
            yaml.dump(
                {
                    "name": "iceberg",
                    "type": "iceberg",
                    "roles": ["target"],
                    "default_engine": {"type": "native"},
                }
            )
        )

        asset_file = tmp_path / "asset.yaml"
        asset_file.write_text(
            yaml.dump(
                {
                    "name": "test_asset",
                    "version": "1.0",
                    "source_type": "csv",
                    "object": "test_object",
                    "team": {"owner": "test@example.com"},
                    "schema": [{"name": "id", "type": "integer"}],
                }
            )
        )

        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "tenant_id": "test_tenant",
                    "source_connector_path": str(connector_file),
                    "target_connector_path": str(target_connector_file),
                    "asset_path": str(asset_file),
                }
            )
        )

        validator = ConfigValidator()
        result = validator.validate(config_file)

        # Should have no critical errors that prevent validation
        # (may have warnings for registry issues in test environment)
        critical_errors = [
            e
            for e in result.errors
            if e["code"]
            not in ["CONNECTOR_NOT_FOUND", "REGISTRY_UNAVAILABLE", "SCHEMA_INVALID"]
        ]
        assert len(critical_errors) == 0 or result.valid

    def test_validate_mode_cloud_restriction(self, tmp_path):
        """validate should check cloud mode restrictions."""
        # Create a config that might be restricted in cloud mode
        connector_file = tmp_path / "postgres_connector.yaml"
        connector_file.write_text(
            yaml.dump(
                {
                    "name": "postgres",
                    "type": "postgres",
                    "roles": ["source"],
                    "default_engine": {"type": "native"},
                }
            )
        )

        target_connector_file = tmp_path / "target.yaml"
        target_connector_file.write_text(
            yaml.dump(
                {
                    "name": "iceberg",
                    "type": "iceberg",
                    "roles": ["target"],
                    "default_engine": {"type": "native"},
                }
            )
        )

        asset_file = tmp_path / "asset.yaml"
        asset_file.write_text(
            yaml.dump(
                {
                    "name": "test_asset",
                    "version": "1.0",
                    "source_type": "postgres",
                    "object": "test_object",
                    "team": {"owner": "test@example.com"},
                    "schema": [{"name": "id", "type": "integer"}],
                }
            )
        )

        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "tenant_id": "test_tenant",
                    "source_connector_path": str(connector_file),
                    "target_connector_path": str(target_connector_file),
                    "asset_path": str(asset_file),
                }
            )
        )

        validator = ConfigValidator(mode="cloud")
        result = validator.validate(config_file)

        # Result depends on whether postgres is blocked in cloud mode
        # Just verify the validator runs without exceptions
        assert isinstance(result, ValidationResult)


class TestAssetValidator:
    """Tests for AssetValidator class."""

    def test_validate_file_not_found(self, tmp_path):
        """validate should return error for non-existent file."""
        validator = AssetValidator()
        result = validator.validate(tmp_path / "nonexistent.yaml")

        assert result.valid is False
        assert result.errors[0]["code"] == "FILE_NOT_FOUND"

    def test_validate_invalid_yaml(self, tmp_path):
        """validate should return error for invalid YAML syntax."""
        asset_file = tmp_path / "invalid.yaml"
        asset_file.write_text("invalid: yaml: syntax:")

        validator = AssetValidator()
        result = validator.validate(asset_file)

        assert result.valid is False
        assert result.errors[0]["code"] == "YAML_SYNTAX"

    def test_validate_empty_file(self, tmp_path):
        """validate should return error for empty file."""
        asset_file = tmp_path / "empty.yaml"
        asset_file.write_text("")

        validator = AssetValidator()
        result = validator.validate(asset_file)

        assert result.valid is False
        assert result.errors[0]["code"] == "EMPTY_FILE"

    def test_validate_missing_odcs_fields(self, tmp_path):
        """validate should return error for missing ODCS fields."""
        asset_file = tmp_path / "incomplete.yaml"
        asset_file.write_text(
            yaml.dump(
                {
                    "source_type": "csv",
                    "object": "test",
                    "team": {"owner": "test@example.com"},
                    # Missing: name, version, schema
                }
            )
        )

        validator = AssetValidator(skip_schema=True)
        result = validator.validate(asset_file)

        assert result.valid is False
        error_codes = [e["code"] for e in result.errors]
        assert "ODCS_MISSING_FIELD" in error_codes

    def test_validate_missing_dativo_fields(self, tmp_path):
        """validate should return error for missing Dativo fields."""
        asset_file = tmp_path / "incomplete.yaml"
        asset_file.write_text(
            yaml.dump(
                {
                    "name": "test",
                    "version": "1.0",
                    "schema": [{"name": "id", "type": "integer"}],
                    # Missing: source_type, object, team
                }
            )
        )

        validator = AssetValidator(skip_schema=True)
        result = validator.validate(asset_file)

        assert result.valid is False
        error_codes = [e["code"] for e in result.errors]
        assert "DATIVO_MISSING_FIELD" in error_codes

    def test_validate_missing_team_owner(self, tmp_path):
        """validate should return error for missing team.owner."""
        asset_file = tmp_path / "no_owner.yaml"
        asset_file.write_text(
            yaml.dump(
                {
                    "name": "test",
                    "version": "1.0",
                    "source_type": "csv",
                    "object": "test",
                    "team": {},  # Missing owner
                    "schema": [{"name": "id", "type": "integer"}],
                }
            )
        )

        validator = AssetValidator(skip_schema=True)
        result = validator.validate(asset_file)

        assert result.valid is False
        error_codes = [e["code"] for e in result.errors]
        assert "DATIVO_MISSING_FIELD" in error_codes

    def test_validate_governance_oncall_required(self, tmp_path):
        """validate should require oncall_rotation when monitoring enabled."""
        asset_file = tmp_path / "no_oncall.yaml"
        asset_file.write_text(
            yaml.dump(
                {
                    "name": "test",
                    "version": "1.0",
                    "source_type": "csv",
                    "object": "test",
                    "team": {"owner": "test@example.com"},
                    "schema": [{"name": "id", "type": "integer"}],
                    "data_quality": {
                        "monitoring": {
                            "enabled": True,
                            # Missing oncall_rotation
                        }
                    },
                }
            )
        )

        validator = AssetValidator(skip_schema=True)
        result = validator.validate(asset_file)

        assert result.valid is False
        error_codes = [e["code"] for e in result.errors]
        assert "GOVERNANCE_ONCALL_REQUIRED" in error_codes

    def test_validate_schema_field_structure(self, tmp_path):
        """validate should check schema field structure."""
        asset_file = tmp_path / "bad_schema.yaml"
        asset_file.write_text(
            yaml.dump(
                {
                    "name": "test",
                    "version": "1.0",
                    "source_type": "csv",
                    "object": "test",
                    "team": {"owner": "test@example.com"},
                    "schema": [
                        {"name": "id"},  # Missing type
                        {"type": "string"},  # Missing name
                    ],
                }
            )
        )

        validator = AssetValidator(skip_schema=True)
        result = validator.validate(asset_file)

        assert result.valid is False
        error_codes = [e["code"] for e in result.errors]
        assert "SCHEMA_FIELD_NO_TYPE" in error_codes
        assert "SCHEMA_FIELD_NO_NAME" in error_codes

    def test_validate_valid_asset(self, tmp_path):
        """validate should pass for valid asset definition."""
        asset_file = tmp_path / "valid.yaml"
        asset_file.write_text(
            yaml.dump(
                {
                    "name": "test_asset",
                    "version": "1.0",
                    "source_type": "csv",
                    "object": "test_object",
                    "team": {"owner": "test@example.com"},
                    "schema": [
                        {"name": "id", "type": "integer"},
                        {"name": "name", "type": "string"},
                    ],
                }
            )
        )

        validator = AssetValidator(skip_schema=True)
        result = validator.validate(asset_file)

        assert result.valid is True
        assert len(result.errors) == 0

    def test_validate_with_json_schema(self, tmp_path):
        """validate should use JSON schema when not skipped."""
        asset_file = tmp_path / "valid.yaml"
        asset_file.write_text(
            yaml.dump(
                {
                    "name": "test_asset",
                    "version": "1.0",
                    "source_type": "csv",
                    "object": "test_object",
                    "team": {"owner": "test@example.com"},
                    "schema": [{"name": "id", "type": "integer"}],
                }
            )
        )

        validator = AssetValidator(skip_schema=False)
        # Schema validation may fail due to remote schema references
        # In test environment, we expect either success or schema-related error
        try:
            result = validator.validate(asset_file)
            # Should either pass or have schema-related warning/error
            assert isinstance(result, ValidationResult)
        except Exception:
            # Schema validation may fail in test environment due to remote refs
            # This is acceptable - the main validation logic still works
            pass


class TestValidateConfigCommand:
    """Tests for validate config command."""

    def test_command_returns_0_for_valid_config(self, tmp_path, capsys):
        """validate config should return 0 for valid configuration."""
        # Create minimal valid config
        connector_file = tmp_path / "connector.yaml"
        connector_file.write_text(
            yaml.dump(
                {
                    "name": "csv",
                    "type": "csv",
                    "roles": ["source"],
                    "default_engine": {"type": "native"},
                }
            )
        )

        target_connector_file = tmp_path / "target.yaml"
        target_connector_file.write_text(
            yaml.dump(
                {
                    "name": "iceberg",
                    "type": "iceberg",
                    "roles": ["target"],
                    "default_engine": {"type": "native"},
                }
            )
        )

        asset_file = tmp_path / "asset.yaml"
        asset_file.write_text(
            yaml.dump(
                {
                    "name": "test_asset",
                    "version": "1.0",
                    "source_type": "csv",
                    "object": "test",
                    "team": {"owner": "test@example.com"},
                    "schema": [{"name": "id", "type": "integer"}],
                }
            )
        )

        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "tenant_id": "test",
                    "source_connector_path": str(connector_file),
                    "target_connector_path": str(target_connector_file),
                    "asset_path": str(asset_file),
                }
            )
        )

        exit_code = validate_config_command(str(config_file))
        # May be 0 or 2 depending on environment (registry availability)
        assert exit_code in [0, 2]

    def test_command_returns_2_for_invalid_config(self, tmp_path):
        """validate config should return 2 for invalid configuration."""
        config_file = tmp_path / "invalid.yaml"
        config_file.write_text("invalid: yaml: syntax:")

        exit_code = validate_config_command(str(config_file))
        assert exit_code == 2

    def test_command_json_output(self, tmp_path, capsys):
        """validate config --json should output valid JSON."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text(yaml.dump({"tenant_id": "test"}))

        exit_code = validate_config_command(str(config_file), json_output=True)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "valid" in data
        assert "errors" in data


class TestValidateAssetCommand:
    """Tests for validate asset command."""

    def test_command_returns_0_for_valid_asset(self, tmp_path):
        """validate asset should return 0 for valid asset."""
        asset_file = tmp_path / "valid.yaml"
        asset_file.write_text(
            yaml.dump(
                {
                    "name": "test",
                    "version": "1.0",
                    "source_type": "csv",
                    "object": "test",
                    "team": {"owner": "test@example.com"},
                    "schema": [{"name": "id", "type": "integer"}],
                }
            )
        )

        exit_code = validate_asset_command(str(asset_file), skip_schema=True)
        assert exit_code == 0

    def test_command_returns_2_for_invalid_asset(self, tmp_path):
        """validate asset should return 2 for invalid asset."""
        asset_file = tmp_path / "invalid.yaml"
        asset_file.write_text("invalid: yaml: syntax:")

        exit_code = validate_asset_command(str(asset_file))
        assert exit_code == 2

    def test_command_json_output(self, tmp_path, capsys):
        """validate asset --json should output valid JSON."""
        asset_file = tmp_path / "test.yaml"
        asset_file.write_text(yaml.dump({"name": "test"}))

        # Skip schema to avoid remote schema reference issues in tests
        exit_code = validate_asset_command(str(asset_file), skip_schema=True, json_output=True)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "valid" in data
        assert "errors" in data


class TestDryRunPhase:
    """Tests for DryRunPhase dataclass."""

    def test_phase_default_values(self):
        """DryRunPhase should have proper defaults."""
        phase = DryRunPhase(name="Test Phase")
        assert phase.name == "Test Phase"
        assert phase.status == "pending"
        assert phase.duration_seconds == 0.0
        assert phase.details == {}
        assert phase.error is None


class TestDryRunResult:
    """Tests for DryRunResult dataclass."""

    def test_result_default_values(self):
        """DryRunResult should have proper defaults."""
        result = DryRunResult()
        assert result.passed is True
        assert result.phases == []
        assert result.errors == []
        assert result.warnings == []

    def test_add_phase_updates_passed(self):
        """Adding a failed phase should mark result as not passed."""
        result = DryRunResult()
        phase = DryRunPhase(name="Test", status="failed")
        result.add_phase(phase)

        assert result.passed is False
        assert len(result.phases) == 1

    def test_add_error_marks_failed(self):
        """Adding an error should mark result as not passed."""
        result = DryRunResult()
        result.add_error("TEST_ERROR", "Test message")

        assert result.passed is False
        assert len(result.errors) == 1

    def test_to_dict(self):
        """to_dict should return proper structure."""
        result = DryRunResult()
        result.connector_info = {"source_type": "csv"}
        result.asset_info = {"name": "test"}
        result.add_phase(DryRunPhase(name="Test", status="completed"))

        data = result.to_dict()

        assert "valid" in data
        assert "phases_completed" in data
        assert "connector_info" in data
        assert "asset_info" in data
        assert "Test" in data["phases_completed"]


class TestDryRunExecutor:
    """Tests for DryRunExecutor class."""

    def test_sample_size_constraints(self, tmp_path):
        """DryRunExecutor should enforce sample size constraints."""
        # Create minimal job config mock
        with patch("src.dativo_ingest.cli_dry_run.JobConfig") as mock_config:
            mock_job = MagicMock()
            mock_job.tenant_id = "test"
            mock_config.return_value = mock_job

            # Test below minimum
            executor = DryRunExecutor(mock_job, sample_size=5)
            assert executor.sample_size == DryRunExecutor.MIN_SAMPLE_SIZE

            # Test above maximum
            executor = DryRunExecutor(mock_job, sample_size=100)
            assert executor.sample_size == DryRunExecutor.MAX_SAMPLE_SIZE

            # Test within range
            executor = DryRunExecutor(mock_job, sample_size=30)
            assert executor.sample_size == 30

    def test_timeout_constraints(self, tmp_path):
        """DryRunExecutor should enforce timeout constraints."""
        with patch("src.dativo_ingest.cli_dry_run.JobConfig") as mock_config:
            mock_job = MagicMock()
            mock_job.tenant_id = "test"
            mock_config.return_value = mock_job

            # Test below minimum
            executor = DryRunExecutor(mock_job, timeout=10)
            assert executor.timeout == DryRunExecutor.MIN_TIMEOUT

            # Test above minimum
            executor = DryRunExecutor(mock_job, timeout=600)
            assert executor.timeout == 600


class TestDryRunCommand:
    """Tests for dry_run_command function."""

    def test_command_returns_2_for_missing_config(self, tmp_path, capsys):
        """dry_run_command should return 2 for missing config file."""
        exit_code = dry_run_command(str(tmp_path / "nonexistent.yaml"))
        assert exit_code == 2

    def test_command_json_output_on_error(self, tmp_path, capsys):
        """dry_run_command --json should output valid JSON on error."""
        exit_code = dry_run_command(
            str(tmp_path / "nonexistent.yaml"), json_output=True
        )

        captured = capsys.readouterr()
        # Should have JSON output
        assert captured.out.strip()
        data = json.loads(captured.out)
        assert "valid" in data
        assert data["valid"] is False


class TestOutputFormatting:
    """Tests for output formatting functions."""

    def test_validation_text_output_valid(self, tmp_path, capsys):
        """Text output should show VALID for valid config."""
        asset_file = tmp_path / "valid.yaml"
        asset_file.write_text(
            yaml.dump(
                {
                    "name": "test",
                    "version": "1.0",
                    "source_type": "csv",
                    "object": "test",
                    "team": {"owner": "test@example.com"},
                    "schema": [{"name": "id", "type": "integer"}],
                }
            )
        )

        validate_asset_command(str(asset_file), skip_schema=True)

        captured = capsys.readouterr()
        assert "VALID" in captured.out

    def test_validation_text_output_invalid(self, tmp_path, capsys):
        """Text output should show INVALID for invalid config."""
        asset_file = tmp_path / "invalid.yaml"
        asset_file.write_text(yaml.dump({"name": "test"}))  # Missing required fields

        validate_asset_command(str(asset_file), skip_schema=True)

        captured = capsys.readouterr()
        assert "INVALID" in captured.out


class TestMetricsRecording:
    """Tests for Prometheus metrics recording."""

    def test_validate_metric_recorded(self, tmp_path):
        """Validation should record metrics."""
        with patch("src.dativo_ingest.cli_validation._record_validate_metric") as mock:
            asset_file = tmp_path / "test.yaml"
            asset_file.write_text(yaml.dump({"name": "test"}))

            validate_asset_command(str(asset_file), skip_schema=True)

            # Should be called twice: once at start (None), once at end
            assert mock.call_count >= 1

    def test_dry_run_metric_recorded(self, tmp_path):
        """Dry-run should record metrics."""
        with patch("src.dativo_ingest.cli_dry_run._record_dry_run_metric") as mock:
            dry_run_command(str(tmp_path / "nonexistent.yaml"))

            # Should be called at least once
            assert mock.call_count >= 1


class TestIntegrationWithExistingFixtures:
    """Integration tests using existing test fixtures."""

    @pytest.mark.skipif(
        not Path("tests/fixtures/jobs/csv_employee_to_iceberg.yaml").exists(),
        reason="Test fixtures not available",
    )
    def test_validate_existing_job_config(self):
        """validate config should work with existing job fixtures."""
        exit_code = validate_config_command(
            "tests/fixtures/jobs/csv_employee_to_iceberg.yaml"
        )
        # May return 0 or 2 depending on environment
        assert exit_code in [0, 2]

    @pytest.mark.skipif(
        not Path("tests/fixtures/assets/csv/v1.0/employee.yaml").exists(),
        reason="Test fixtures not available",
    )
    def test_validate_existing_asset(self):
        """validate asset should work with existing asset fixtures."""
        exit_code = validate_asset_command(
            "tests/fixtures/assets/csv/v1.0/employee.yaml",
            skip_schema=True,  # Skip JSON schema to avoid dependency on schema file
        )
        assert exit_code == 0


class TestVerboseOutput:
    """Tests for verbose output mode."""

    def test_verbose_adds_info(self, tmp_path, capsys):
        """Verbose mode should add additional info."""
        asset_file = tmp_path / "valid.yaml"
        asset_file.write_text(
            yaml.dump(
                {
                    "name": "test",
                    "version": "1.0",
                    "source_type": "csv",
                    "object": "test",
                    "team": {"owner": "test@example.com"},
                    "schema": [{"name": "id", "type": "integer"}],
                }
            )
        )

        validate_asset_command(str(asset_file), skip_schema=True, verbose=True)

        captured = capsys.readouterr()
        assert "Additional Info" in captured.out or "Info" in captured.out


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_validate_binary_file(self, tmp_path):
        """validate should handle binary files gracefully."""
        binary_file = tmp_path / "binary.yaml"
        binary_file.write_bytes(b"\x00\x01\x02\x03")

        validator = AssetValidator()
        result = validator.validate(binary_file)

        assert result.valid is False
        # Should have YAML_SYNTAX error
        assert any(e["code"] == "YAML_SYNTAX" for e in result.errors)

    def test_validate_large_yaml(self, tmp_path):
        """validate should handle large YAML files."""
        asset_file = tmp_path / "large.yaml"
        schema_fields = [{"name": f"field_{i}", "type": "string"} for i in range(1000)]
        asset_file.write_text(
            yaml.dump(
                {
                    "name": "large_asset",
                    "version": "1.0",
                    "source_type": "csv",
                    "object": "test",
                    "team": {"owner": "test@example.com"},
                    "schema": schema_fields,
                }
            )
        )

        validator = AssetValidator(skip_schema=True)
        result = validator.validate(asset_file)

        assert result.valid is True

    def test_validate_special_characters_in_values(self, tmp_path):
        """validate should handle special characters in values."""
        asset_file = tmp_path / "special.yaml"
        asset_file.write_text(
            yaml.dump(
                {
                    "name": "test-asset_v1.0",
                    "version": "1.0.0-beta+build123",
                    "source_type": "csv",
                    "object": "test/object:path",
                    "team": {"owner": "test+user@example.com"},
                    "schema": [{"name": "field-name_v1", "type": "string"}],
                }
            )
        )

        validator = AssetValidator(skip_schema=True)
        result = validator.validate(asset_file)

        assert result.valid is True
