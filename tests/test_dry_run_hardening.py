"""Targeted tests for dry-run hardening and production-readiness.

These tests validate behavioral guarantees:
- Sample size clamping (with warning, not error)
- Timeout enforcement (hard error if below minimum)
- JSON output schema stability
- Exit code correctness
- Phase tracking
"""

import json

import pytest

from src.dativo_ingest.dry_run import (
    ALL_PHASES,
    PHASE_DISCOVERY,
    PHASE_SAMPLE_FETCH,
    PHASE_SAMPLE_VALIDATION,
    PHASE_SCHEMA_NEGOTIATION,
    DryRunConfig,
    DryRunResult,
    create_error_result,
    format_dry_run_output,
    format_phase_checklist,
)


class TestDryRunConfigSampleSizeClamping:
    """Test sample size clamping behavior (clamp with warning, don't fail)."""

    def test_sample_size_clamped_below_minimum(self):
        """Sample sizes below minimum should be clamped to minimum."""
        config = DryRunConfig(sample_size=5)
        assert config.sample_size == 10  # Clamped to minimum
        assert config.was_sample_size_clamped is True
        assert config.clamping_warning is not None
        assert "5" in config.clamping_warning
        assert "10" in config.clamping_warning

    def test_sample_size_clamped_above_maximum(self):
        """Sample sizes above maximum should be clamped to maximum."""
        config = DryRunConfig(sample_size=100)
        assert config.sample_size == 50  # Clamped to maximum
        assert config.was_sample_size_clamped is True
        assert config.clamping_warning is not None
        assert "100" in config.clamping_warning
        assert "50" in config.clamping_warning

    def test_sample_size_no_clamping_when_valid(self):
        """Valid sample sizes should not be clamped."""
        for size in [10, 25, 50]:
            config = DryRunConfig(sample_size=size)
            assert config.sample_size == size
            assert config.was_sample_size_clamped is False
            assert config.clamping_warning is None

    def test_sample_size_at_boundaries(self):
        """Test boundary values for sample size."""
        # At minimum
        config_min = DryRunConfig(sample_size=10)
        assert config_min.sample_size == 10
        assert config_min.was_sample_size_clamped is False

        # At maximum
        config_max = DryRunConfig(sample_size=50)
        assert config_max.sample_size == 50
        assert config_max.was_sample_size_clamped is False

    def test_sample_size_constants(self):
        """Verify sample size constants."""
        assert DryRunConfig.SAMPLE_SIZE_MIN == 10
        assert DryRunConfig.SAMPLE_SIZE_MAX == 50


class TestDryRunConfigTimeoutEnforcement:
    """Test timeout validation (hard error if below minimum)."""

    def test_timeout_below_minimum_is_invalid(self):
        """Timeout below minimum should be rejected."""
        is_valid, error = DryRunConfig.validate_timeout(5)
        assert is_valid is False
        assert "minimum" in error.lower()
        assert "10" in error

    def test_timeout_at_minimum_is_valid(self):
        """Timeout at minimum should be accepted."""
        is_valid, error = DryRunConfig.validate_timeout(10)
        assert is_valid is True
        assert error == ""

    def test_timeout_above_minimum_is_valid(self):
        """Timeout above minimum should be accepted."""
        is_valid, error = DryRunConfig.validate_timeout(300)
        assert is_valid is True
        assert error == ""

    def test_timeout_constants(self):
        """Verify timeout constants."""
        assert DryRunConfig.TIMEOUT_MIN_SECONDS == 10
        assert DryRunConfig.TIMEOUT_DEFAULT_SECONDS == 300


class TestDryRunResultFlattenedStructure:
    """Test the flattened JSON structure."""

    def test_to_dict_has_required_fields(self):
        """JSON output must include all required top-level fields."""
        result = DryRunResult()
        result.sample_size = 25
        result.valid_records = 23
        result.invalid_records = 2
        result.source_connector = "csv"
        result.target_connector = "iceberg"
        result.asset_name = "test_asset"
        result.dry_run_duration_seconds = 1.234

        output = result.to_dict()

        # Required top-level fields (flattened)
        assert "valid" in output
        assert "exit_code" in output
        assert "errors" in output
        assert "warnings" in output
        assert "phases_completed" in output
        assert "phases" in output
        assert "dry_run_duration_seconds" in output
        assert "sample_size" in output
        assert "valid_records" in output
        assert "invalid_records" in output
        assert "source_connector" in output
        assert "target_connector" in output
        assert "asset_name" in output

    def test_to_json_is_valid_json(self):
        """to_json() must produce valid JSON."""
        result = DryRunResult()
        result.add_error("Test error")
        result.add_warning("Test warning")

        json_str = result.to_json()
        parsed = json.loads(json_str)

        assert isinstance(parsed, dict)
        assert parsed["valid"] is False
        assert "Test error" in parsed["errors"]
        assert "Test warning" in parsed["warnings"]

    def test_errors_are_simple_strings(self):
        """Errors should be simple strings, not nested objects."""
        result = DryRunResult()
        result.add_error("Error message 1")
        result.add_error("Error message 2")

        output = result.to_dict()
        assert output["errors"] == ["Error message 1", "Error message 2"]

    def test_warnings_are_simple_strings(self):
        """Warnings should be simple strings, not nested objects."""
        result = DryRunResult()
        result.add_warning("Warning 1")
        result.add_warning("Warning 2")

        output = result.to_dict()
        assert output["warnings"] == ["Warning 1", "Warning 2"]


class TestDryRunPhaseTracking:
    """Test inline phase tracking."""

    def test_record_phase_success(self):
        """Successful phase should be recorded with duration."""
        result = DryRunResult()
        result.record_phase("discovery", duration_seconds=0.5)

        assert len(result.phases) == 1
        assert result.phases[0]["name"] == "discovery"
        assert result.phases[0]["duration_seconds"] == 0.5
        assert "error" not in result.phases[0]
        assert "discovery" in result.phases_completed

    def test_record_phase_failure(self):
        """Failed phase should be recorded with error."""
        result = DryRunResult()
        result.record_phase("sample_fetch", error="Connection timeout")

        assert len(result.phases) == 1
        assert result.phases[0]["name"] == "sample_fetch"
        assert result.phases[0]["error"] == "Connection timeout"
        assert "duration_seconds" not in result.phases[0]
        assert "sample_fetch" not in result.phases_completed

    def test_phases_completed_only_includes_successful(self):
        """phases_completed should only include successful phases."""
        result = DryRunResult()
        result.record_phase("discovery", duration_seconds=0.1)
        result.record_phase("schema_negotiation", duration_seconds=0.05)
        result.record_phase("sample_fetch", error="Failed")
        result.record_phase("sample_validation")  # No duration, no error = skipped

        assert result.phases_completed == ["discovery", "schema_negotiation"]

    def test_phase_constants(self):
        """Verify phase name constants."""
        assert PHASE_DISCOVERY == "discovery"
        assert PHASE_SCHEMA_NEGOTIATION == "schema_negotiation"
        assert PHASE_SAMPLE_FETCH == "sample_fetch"
        assert PHASE_SAMPLE_VALIDATION == "sample_validation"

    def test_all_phases_list(self):
        """Verify all phases are defined."""
        assert len(ALL_PHASES) == 4
        assert PHASE_DISCOVERY in ALL_PHASES
        assert PHASE_SCHEMA_NEGOTIATION in ALL_PHASES
        assert PHASE_SAMPLE_FETCH in ALL_PHASES
        assert PHASE_SAMPLE_VALIDATION in ALL_PHASES


class TestDryRunExitCodes:
    """Test exit code correctness."""

    def test_exit_code_defaults_to_zero(self):
        """Default exit code should be 0."""
        result = DryRunResult()
        assert result.exit_code == 0
        assert result.valid is True

    def test_add_error_sets_valid_false(self):
        """add_error() should set valid=False."""
        result = DryRunResult()
        assert result.valid is True

        result.add_error("Error")
        assert result.valid is False

    def test_add_warning_does_not_change_valid(self):
        """add_warning() should not change valid status."""
        result = DryRunResult()
        assert result.valid is True

        result.add_warning("Warning")
        assert result.valid is True


class TestFormatDryRunOutput:
    """Test output formatting."""

    def test_json_output_is_valid_json(self):
        """JSON format output must be valid JSON."""
        result = DryRunResult()
        result.sample_size = 10
        result.valid_records = 10
        result.dry_run_duration_seconds = 1.5

        output = format_dry_run_output(result, json_output=True)
        parsed = json.loads(output)

        assert isinstance(parsed, dict)
        assert "valid" in parsed
        assert parsed["dry_run_duration_seconds"] == 1.5

    def test_human_readable_includes_status(self):
        """Human-readable output should include status."""
        result = DryRunResult()
        result.valid = True

        output = format_dry_run_output(result, json_output=False)

        assert "PASSED" in output or "✅" in output

    def test_human_readable_includes_duration(self):
        """Human-readable output should include duration."""
        result = DryRunResult()
        result.dry_run_duration_seconds = 2.34

        output = format_dry_run_output(result, json_output=False)

        assert "2.34" in output or "Duration" in output


class TestFormatPhaseChecklist:
    """Test phase checklist formatting for verbose mode."""

    def test_checklist_shows_success(self):
        """Successful phases should show checkmark."""
        result = DryRunResult()
        result.record_phase("discovery", duration_seconds=0.5)

        checklist = format_phase_checklist(result)

        assert "[✓]" in checklist
        assert "discovery" in checklist
        assert "0.5" in checklist

    def test_checklist_shows_failure(self):
        """Failed phases should show X mark."""
        result = DryRunResult()
        result.record_phase("sample_fetch", error="Connection failed")

        checklist = format_phase_checklist(result)

        assert "[✗]" in checklist
        assert "sample_fetch" in checklist
        assert "Connection failed" in checklist

    def test_checklist_shows_skipped(self):
        """Skipped phases should show circle."""
        result = DryRunResult()
        result.record_phase("sample_validation")  # No duration, no error

        checklist = format_phase_checklist(result)

        assert "[○]" in checklist
        assert "sample_validation" in checklist
        assert "skipped" in checklist.lower()


class TestCreateErrorResult:
    """Test error result creation helper."""

    def test_create_error_result(self):
        """create_error_result should create a properly structured error."""
        result = create_error_result("Timeout too low", exit_code=2)

        assert result.valid is False
        assert result.exit_code == 2
        assert "Timeout too low" in result.errors

    def test_create_error_result_default_exit_code(self):
        """Default exit code should be 2."""
        result = create_error_result("Some error")
        assert result.exit_code == 2
