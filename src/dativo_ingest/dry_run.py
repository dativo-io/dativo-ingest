"""Dry-run execution support with simplified phase tracking and safety guardrails."""

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Phase names as constants (no enum needed for simplicity)
PHASE_DISCOVERY = "discovery"
PHASE_SCHEMA_NEGOTIATION = "schema_negotiation"
PHASE_SAMPLE_FETCH = "sample_fetch"
PHASE_SAMPLE_VALIDATION = "sample_validation"

# All phases in execution order
ALL_PHASES = [
    PHASE_DISCOVERY,
    PHASE_SCHEMA_NEGOTIATION,
    PHASE_SAMPLE_FETCH,
    PHASE_SAMPLE_VALIDATION,
]


@dataclass
class DryRunConfig:
    """Configuration for dry-run execution with safety guardrails."""

    # Sample size limits
    SAMPLE_SIZE_MIN: int = 10
    SAMPLE_SIZE_MAX: int = 50

    # Timeout limits
    TIMEOUT_MIN_SECONDS: int = 10
    TIMEOUT_DEFAULT_SECONDS: int = 300

    # Actual configured values
    sample_size: int = 50
    timeout_seconds: int = 300
    verbose: bool = False
    json_output: bool = False

    # Tracking for clamping
    _sample_size_clamped: bool = field(default=False, init=False)
    _original_sample_size: int = field(default=50, init=False)
    _clamping_warning: Optional[str] = field(default=None, init=False)

    def __post_init__(self):
        """Clamp sample size to valid range and record warning."""
        self._original_sample_size = self.sample_size

        # Clamp sample_size to safe range (don't fail, just warn)
        if self.sample_size < self.SAMPLE_SIZE_MIN:
            self._sample_size_clamped = True
            self._clamping_warning = (
                f"Sample size {self.sample_size} is below minimum ({self.SAMPLE_SIZE_MIN}). "
                f"Clamping to {self.SAMPLE_SIZE_MIN}."
            )
            self.sample_size = self.SAMPLE_SIZE_MIN
        elif self.sample_size > self.SAMPLE_SIZE_MAX:
            self._sample_size_clamped = True
            self._clamping_warning = (
                f"Sample size {self.sample_size} exceeds maximum ({self.SAMPLE_SIZE_MAX}). "
                f"Clamping to {self.SAMPLE_SIZE_MAX}."
            )
            self.sample_size = self.SAMPLE_SIZE_MAX
        else:
            self._sample_size_clamped = False

    @classmethod
    def validate_timeout(cls, value: int) -> tuple[bool, str]:
        """Validate timeout value. Returns (is_valid, error_message).

        Timeout below minimum is a hard error (exit code 2).
        """
        if value < cls.TIMEOUT_MIN_SECONDS:
            return False, (
                f"Timeout too low; minimum is {cls.TIMEOUT_MIN_SECONDS} seconds. "
                f"Got: {value}"
            )
        return True, ""

    @property
    def was_sample_size_clamped(self) -> bool:
        """Check if sample size was clamped from original value."""
        return self._sample_size_clamped

    @property
    def clamping_warning(self) -> Optional[str]:
        """Get clamping warning message if sample size was adjusted."""
        return self._clamping_warning


@dataclass
class DryRunResult:
    """Complete result of a dry-run execution with flattened structure."""

    valid: bool = True
    exit_code: int = 0

    # Simple flat lists for errors and warnings (strings only for simplicity)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Phases completed successfully (names only)
    phases_completed: List[str] = field(default_factory=list)

    # All phases with timing (flattened: name + duration only, no status field)
    # If duration_seconds is None, phase failed or was skipped
    phases: List[Dict[str, Any]] = field(default_factory=list)

    # Total duration
    dry_run_duration_seconds: float = 0.0

    # Metrics
    sample_size: int = 0
    valid_records: int = 0
    invalid_records: int = 0

    # Source/target info
    source_connector: Optional[str] = None
    target_connector: Optional[str] = None
    asset_name: Optional[str] = None

    def add_error(self, message: str) -> None:
        """Add an error message. Sets valid=False."""
        self.valid = False
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        """Add a warning message. Does not affect valid status."""
        self.warnings.append(message)

    def record_phase(
        self,
        name: str,
        duration_seconds: Optional[float] = None,
        error: Optional[str] = None,
    ) -> None:
        """Record a phase result.

        Args:
            name: Phase name
            duration_seconds: Duration in seconds (None if failed/skipped)
            error: Error message if phase failed
        """
        phase_record: Dict[str, Any] = {"name": name}

        if duration_seconds is not None:
            phase_record["duration_seconds"] = round(duration_seconds, 3)
            self.phases_completed.append(name)
        elif error:
            phase_record["error"] = error

        self.phases.append(phase_record)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to flattened dictionary for JSON serialization."""
        return {
            "valid": self.valid,
            "exit_code": self.exit_code,
            "errors": self.errors,
            "warnings": self.warnings,
            "phases_completed": self.phases_completed,
            "phases": self.phases,
            "dry_run_duration_seconds": round(self.dry_run_duration_seconds, 3),
            "sample_size": self.sample_size,
            "valid_records": self.valid_records,
            "invalid_records": self.invalid_records,
            "source_connector": self.source_connector,
            "target_connector": self.target_connector,
            "asset_name": self.asset_name,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


def format_phase_checklist(result: DryRunResult) -> str:
    """Format a human-readable phase checklist for verbose output.

    Args:
        result: DryRunResult with phase information

    Returns:
        Formatted checklist string
    """
    lines = ["", "Dry-run phases:"]

    for phase in result.phases:
        name = phase["name"]
        if "duration_seconds" in phase:
            # Success
            duration = phase["duration_seconds"]
            lines.append(f"  [✓] {name} ({duration:.3f}s)")
        elif "error" in phase:
            # Failed
            error = phase["error"]
            lines.append(f"  [✗] {name} ({error})")
        else:
            # Skipped (no duration, no error)
            lines.append(f"  [○] {name} (skipped)")

    return "\n".join(lines)


def format_dry_run_output(
    result: DryRunResult,
    json_output: bool = False,
    verbose: bool = False,
) -> str:
    """Format dry-run result for output.

    Args:
        result: DryRunResult to format
        json_output: Output as JSON
        verbose: Include verbose details (phase checklist)

    Returns:
        Formatted string output
    """
    if json_output:
        return result.to_json()

    lines = []
    lines.append("")
    lines.append("=" * 60)
    lines.append("DRY-RUN RESULTS")
    lines.append("=" * 60)

    # Overall status
    status_icon = "✅" if result.valid else "❌"
    status_text = "PASSED" if result.valid else "FAILED"
    lines.append(f"\nStatus: {status_icon} {status_text}")
    lines.append(f"Duration: {result.dry_run_duration_seconds:.2f}s")

    # Phase checklist (always shown in verbose mode)
    if verbose:
        lines.append(format_phase_checklist(result))
    else:
        # Brief summary
        lines.append(
            f"\nPhases: {len(result.phases_completed)}/{len(result.phases)} completed"
        )

    # Metrics
    lines.append(f"\nSample: {result.sample_size} records fetched")
    if result.valid_records > 0 or result.invalid_records > 0:
        lines.append(f"  Valid: {result.valid_records}")
        lines.append(f"  Invalid: {result.invalid_records}")

    # Errors
    if result.errors:
        lines.append(f"\n❌ Errors ({len(result.errors)}):")
        for error in result.errors:
            lines.append(f"  - {error}")

    # Warnings
    if result.warnings:
        lines.append(f"\n⚠️  Warnings ({len(result.warnings)}):")
        for warning in result.warnings:
            lines.append(f"  - {warning}")

    # Configuration
    lines.append("\nConfiguration:")
    if result.source_connector:
        lines.append(f"  Source: {result.source_connector}")
    if result.target_connector:
        lines.append(f"  Target: {result.target_connector}")
    if result.asset_name:
        lines.append(f"  Asset: {result.asset_name}")

    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)


def create_error_result(error_message: str, exit_code: int = 2) -> DryRunResult:
    """Create a DryRunResult for an error condition.

    Useful for producing valid JSON output even when errors occur early.

    Args:
        error_message: The error message
        exit_code: Exit code (default: 2 for usage/validation errors)

    Returns:
        DryRunResult with the error recorded
    """
    result = DryRunResult()
    result.add_error(error_message)
    result.exit_code = exit_code
    return result
