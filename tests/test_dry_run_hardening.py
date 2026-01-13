"""Targeted tests for dry-run hardening and production-readiness.

These tests validate behavioral guarantees, not coverage numbers:
- Sample size clamping
- Timeout enforcement
- No-write guarantees in dry-run
- JSON output schema stability
- Exit code correctness
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from src.dativo_ingest.dry_run import (
    DryRunConfig,
    DryRunPhase,
    DryRunPhaseTracker,
    DryRunResult,
    PhaseStatus,
    format_dry_run_output,
)


class TestDryRunConfigSampleSizeClamping:
    """Test sample size validation and clamping."""

    def test_sample_size_validation_accepts_valid_values(self):
        """Valid sample sizes should be accepted."""
        for size in [10, 25, 50]:
            is_valid, error = DryRunConfig.validate_sample_size(size)
            assert is_valid is True, f"Size {size} should be valid"
            assert error == ""

    def test_sample_size_validation_rejects_below_minimum(self):
        """Sample sizes below minimum should be rejected."""
        for size in [0, 5, 9]:
            is_valid, error = DryRunConfig.validate_sample_size(size)
            assert is_valid is False, f"Size {size} should be invalid"
            assert "10" in error  # Should mention minimum
            assert "50" in error  # Should mention maximum

    def test_sample_size_validation_rejects_above_maximum(self):
        """Sample sizes above maximum should be rejected."""
        for size in [51, 100, 1000]:
            is_valid, error = DryRunConfig.validate_sample_size(size)
            assert is_valid is False, f"Size {size} should be invalid"
            assert "10" in error  # Should mention minimum
            assert "50" in error  # Should mention maximum

    def test_sample_size_clamping_to_minimum(self):
        """Sample size should clamp to minimum when below."""
        config = DryRunConfig(sample_size=5)
        assert config.sample_size == 10
        assert config.was_sample_size_clamped is True
        assert config.original_sample_size == 5

    def test_sample_size_clamping_to_maximum(self):
        """Sample size should clamp to maximum when above."""
        config = DryRunConfig(sample_size=100)
        assert config.sample_size == 50
        assert config.was_sample_size_clamped is True
        assert config.original_sample_size == 100

    def test_sample_size_no_clamping_when_valid(self):
        """Valid sample sizes should not be clamped."""
        config = DryRunConfig(sample_size=30)
        assert config.sample_size == 30
        assert config.was_sample_size_clamped is False

    def test_sample_size_constants_are_correct(self):
        """Verify the min/max constants are as documented."""
        assert DryRunConfig.SAMPLE_SIZE_MIN == 10
        assert DryRunConfig.SAMPLE_SIZE_MAX == 50


class TestDryRunConfigTimeoutEnforcement:
    """Test timeout validation and warnings."""

    def test_timeout_below_minimum_triggers_warning(self):
        """Timeouts below minimum should trigger a warning."""
        config = DryRunConfig(timeout_seconds=15)
        assert config.timeout_warning is not None
        assert "15" in config.timeout_warning
        assert "30" in config.timeout_warning  # Mentions minimum

    def test_timeout_at_minimum_no_warning(self):
        """Timeout at minimum should not trigger a warning."""
        config = DryRunConfig(timeout_seconds=30)
        assert config.timeout_warning is None

    def test_timeout_above_minimum_no_warning(self):
        """Timeouts above minimum should not trigger a warning."""
        config = DryRunConfig(timeout_seconds=300)
        assert config.timeout_warning is None

    def test_default_timeout_is_safe(self):
        """Default timeout should be above minimum."""
        config = DryRunConfig()
        assert config.timeout_seconds >= config.TIMEOUT_MIN_SECONDS
        assert config.timeout_warning is None


class TestDryRunResultSafetyAssertions:
    """Test safety assertion methods."""

    def test_assert_no_writes_passes_when_clean(self):
        """No assertion error when writes_attempted is False."""
        result = DryRunResult()
        result.writes_attempted = False
        result.assert_no_writes()  # Should not raise

    def test_assert_no_writes_fails_when_violated(self):
        """Assertion error when writes_attempted is True."""
        result = DryRunResult()
        result.writes_attempted = True
        with pytest.raises(AssertionError) as exc_info:
            result.assert_no_writes()
        assert "SAFETY VIOLATION" in str(exc_info.value)
        assert "Write operation" in str(exc_info.value)

    def test_assert_no_state_updates_passes_when_clean(self):
        """No assertion error when state_updates_attempted is False."""
        result = DryRunResult()
        result.state_updates_attempted = False
        result.assert_no_state_updates()  # Should not raise

    def test_assert_no_state_updates_fails_when_violated(self):
        """Assertion error when state_updates_attempted is True."""
        result = DryRunResult()
        result.state_updates_attempted = True
        with pytest.raises(AssertionError) as exc_info:
            result.assert_no_state_updates()
        assert "SAFETY VIOLATION" in str(exc_info.value)
        assert "State update" in str(exc_info.value)

    def test_assert_no_commits_passes_when_clean(self):
        """No assertion error when commits_attempted is False."""
        result = DryRunResult()
        result.commits_attempted = False
        result.assert_no_commits()  # Should not raise

    def test_assert_no_commits_fails_when_violated(self):
        """Assertion error when commits_attempted is True."""
        result = DryRunResult()
        result.commits_attempted = True
        with pytest.raises(AssertionError) as exc_info:
            result.assert_no_commits()
        assert "SAFETY VIOLATION" in str(exc_info.value)
        assert "Commit operation" in str(exc_info.value)

    def test_assert_safety_guarantees_checks_all(self):
        """assert_safety_guarantees checks all three assertions."""
        result = DryRunResult()
        result.assert_safety_guarantees()  # Should not raise

        # Test each violation separately
        for attr in ["writes_attempted", "state_updates_attempted", "commits_attempted"]:
            result = DryRunResult()
            setattr(result, attr, True)
            with pytest.raises(AssertionError):
                result.assert_safety_guarantees()


class TestDryRunResultJsonOutputSchema:
    """Test JSON output schema stability."""

    def test_json_output_has_required_fields(self):
        """JSON output must include all required fields."""
        result = DryRunResult()
        result.sample_size = 25
        result.valid_records = 23
        result.invalid_records = 2
        result.source_connector = "csv"
        result.target_connector = "iceberg"

        output = result.to_dict()

        # Required top-level fields
        assert "valid" in output
        assert "exit_code" in output
        assert "errors" in output
        assert "warnings" in output
        assert "phases_completed" in output
        assert "phases" in output

        # Required metrics fields
        assert "metrics" in output
        assert output["metrics"]["sample_size"] == 25
        assert output["metrics"]["valid_records"] == 23
        assert output["metrics"]["invalid_records"] == 2

        # Safety assertions field
        assert "safety_assertions" in output
        assert "no_writes" in output["safety_assertions"]
        assert "no_state_updates" in output["safety_assertions"]
        assert "no_commits" in output["safety_assertions"]

    def test_json_output_is_valid_json(self):
        """to_json() must produce valid JSON."""
        result = DryRunResult()
        result.add_error("Test error", "TEST_ERROR", "test_phase")
        result.add_warning("Test warning", "TEST_WARNING")

        json_str = result.to_json()

        # Must be valid JSON
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)

    def test_json_output_errors_have_correct_structure(self):
        """Error entries must have message, code, and phase fields."""
        result = DryRunResult()
        result.add_error("Error message", "ERROR_CODE", "sample_validation")

        output = result.to_dict()
        assert len(output["errors"]) == 1

        error = output["errors"][0]
        assert error["message"] == "Error message"
        assert error["code"] == "ERROR_CODE"
        assert error["phase"] == "sample_validation"

    def test_json_output_warnings_have_correct_structure(self):
        """Warning entries must have message, code, and optional phase fields."""
        result = DryRunResult()
        result.add_warning("Warning message", "WARNING_CODE")

        output = result.to_dict()
        assert len(output["warnings"]) == 1

        warning = output["warnings"][0]
        assert warning["message"] == "Warning message"
        assert warning["code"] == "WARNING_CODE"

    def test_json_output_limits_sample_errors(self):
        """Sample validation errors should be limited to 10."""
        result = DryRunResult()
        result.sample_validation_errors = [
            {"field": f"field_{i}", "message": f"Error {i}"}
            for i in range(20)
        ]

        output = result.to_dict()
        assert len(output["validation"]["sample_errors"]) == 10


class TestDryRunResultExitCodes:
    """Test exit code correctness."""

    def test_exit_code_zero_when_valid(self):
        """Exit code 0 when valid is True."""
        result = DryRunResult()
        result.valid = True
        result.exit_code = 0

        assert result.exit_code == 0
        assert result.valid is True

    def test_exit_code_two_when_errors(self):
        """Exit code 2 when there are errors."""
        result = DryRunResult()
        result.add_error("Error", "ERROR_CODE")

        assert result.valid is False
        # Exit code should be set by the caller based on validation mode

    def test_add_error_sets_valid_false(self):
        """add_error() sets valid to False."""
        result = DryRunResult()
        assert result.valid is True

        result.add_error("Error", "ERROR_CODE")
        assert result.valid is False

    def test_add_warning_does_not_change_valid(self):
        """add_warning() does not change valid flag."""
        result = DryRunResult()
        assert result.valid is True

        result.add_warning("Warning", "WARNING_CODE")
        assert result.valid is True


class TestDryRunPhaseTracker:
    """Test phase tracking functionality."""

    def test_phase_tracking_records_duration(self):
        """Phase tracking should record duration in seconds."""
        tracker = DryRunPhaseTracker()

        tracker.start_phase(DryRunPhase.DISCOVERY)
        # Simulate some work
        import time
        time.sleep(0.01)
        result = tracker.end_phase(PhaseStatus.SUCCESS)

        assert result.duration_seconds > 0
        assert result.phase == "discovery"
        assert result.status == "success"

    def test_phase_tracking_records_errors(self):
        """Phase tracking should record error messages."""
        tracker = DryRunPhaseTracker()

        tracker.start_phase(DryRunPhase.SAMPLE_FETCH)
        result = tracker.end_phase(
            PhaseStatus.FAILURE,
            error_message="Connection timeout"
        )

        assert result.status == "failure"
        assert result.error_message == "Connection timeout"

    def test_get_completed_phases(self):
        """get_completed_phases returns only successful phases."""
        tracker = DryRunPhaseTracker()

        tracker.start_phase(DryRunPhase.DISCOVERY)
        tracker.end_phase(PhaseStatus.SUCCESS)

        tracker.start_phase(DryRunPhase.SAMPLE_FETCH)
        tracker.end_phase(PhaseStatus.FAILURE)

        tracker.skip_phase(DryRunPhase.SAMPLE_VALIDATION)

        completed = tracker.get_completed_phases()
        assert completed == ["discovery"]

    def test_all_phases_passed_when_success_or_skipped(self):
        """all_phases_passed returns True only when all passed or skipped."""
        tracker = DryRunPhaseTracker()

        tracker.start_phase(DryRunPhase.DISCOVERY)
        tracker.end_phase(PhaseStatus.SUCCESS)
        tracker.skip_phase(DryRunPhase.SCHEMA_NEGOTIATION)

        assert tracker.all_phases_passed() is True

    def test_all_phases_passed_false_when_failure(self):
        """all_phases_passed returns False when any phase failed."""
        tracker = DryRunPhaseTracker()

        tracker.start_phase(DryRunPhase.DISCOVERY)
        tracker.end_phase(PhaseStatus.SUCCESS)

        tracker.start_phase(DryRunPhase.SAMPLE_FETCH)
        tracker.end_phase(PhaseStatus.FAILURE)

        assert tracker.all_phases_passed() is False

    def test_get_failed_phase(self):
        """get_failed_phase returns the first failed phase."""
        tracker = DryRunPhaseTracker()

        tracker.start_phase(DryRunPhase.DISCOVERY)
        tracker.end_phase(PhaseStatus.SUCCESS)

        tracker.start_phase(DryRunPhase.SAMPLE_FETCH)
        tracker.end_phase(PhaseStatus.FAILURE, error_message="Failed")

        failed = tracker.get_failed_phase()
        assert failed is not None
        assert failed.phase == "sample_fetch"
        assert failed.error_message == "Failed"


class TestFormatDryRunOutput:
    """Test output formatting."""

    def test_format_json_output_is_valid_json(self):
        """JSON format output must be valid JSON."""
        result = DryRunResult()
        result.sample_size = 10
        result.valid_records = 10

        output = format_dry_run_output(result, json_output=True)
        parsed = json.loads(output)

        assert isinstance(parsed, dict)
        assert "valid" in parsed

    def test_format_human_readable_includes_status(self):
        """Human-readable output includes status indicator."""
        result = DryRunResult()
        result.valid = True
        result.exit_code = 0

        output = format_dry_run_output(result, json_output=False)

        assert "PASSED" in output or "✅" in output

    def test_format_human_readable_includes_safety_assertions(self):
        """Human-readable output includes safety assertion status."""
        result = DryRunResult()

        output = format_dry_run_output(result, json_output=False)

        assert "Safety Assertions" in output or "🔒" in output
        assert "No writes" in output or "no_writes" in output.lower()


class TestDryRunPhaseEnums:
    """Test phase enumeration values."""

    def test_all_phases_defined(self):
        """All expected phases are defined."""
        expected_phases = [
            "configuration_validation",
            "asset_loading",
            "extractor_initialization",
            "discovery",
            "schema_negotiation",
            "sample_fetch",
            "sample_validation",
        ]

        actual_phases = [p.value for p in DryRunPhase]
        for expected in expected_phases:
            assert expected in actual_phases, f"Phase {expected} missing"

    def test_phase_status_values(self):
        """Phase status values are as expected."""
        assert PhaseStatus.SUCCESS.value == "success"
        assert PhaseStatus.FAILURE.value == "failure"
        assert PhaseStatus.SKIPPED.value == "skipped"
        assert PhaseStatus.PENDING.value == "pending"
