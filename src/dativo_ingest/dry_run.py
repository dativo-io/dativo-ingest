"""Dry-run execution support with structured phase reporting and safety guardrails."""

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class DryRunPhase(Enum):
    """Phases of dry-run execution."""
    
    CONFIGURATION_VALIDATION = "configuration_validation"
    ASSET_LOADING = "asset_loading"
    EXTRACTOR_INITIALIZATION = "extractor_initialization"
    DISCOVERY = "discovery"
    SCHEMA_NEGOTIATION = "schema_negotiation"
    SAMPLE_FETCH = "sample_fetch"
    SAMPLE_VALIDATION = "sample_validation"


class PhaseStatus(Enum):
    """Status of a dry-run phase."""
    
    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"
    PENDING = "pending"


@dataclass
class PhaseResult:
    """Result of a single dry-run phase."""
    
    phase: str
    status: str
    duration_seconds: float = 0.0
    error_message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "phase": self.phase,
            "status": self.status,
            "duration_seconds": round(self.duration_seconds, 3),
        }
        if self.error_message:
            result["error_message"] = self.error_message
        if self.details:
            result["details"] = self.details
        return result


@dataclass
class DryRunConfig:
    """Configuration for dry-run execution with safety guardrails."""
    
    # Sample size limits (enforced, not configurable beyond this range)
    SAMPLE_SIZE_MIN: int = 10
    SAMPLE_SIZE_MAX: int = 50
    
    # Timeout limits
    TIMEOUT_MIN_SECONDS: int = 30
    TIMEOUT_DEFAULT_SECONDS: int = 300
    
    # Actual configured values
    sample_size: int = 50
    timeout_seconds: int = 300
    verbose: bool = False
    
    def __post_init__(self):
        """Validate and clamp configuration values."""
        # Clamp sample_size to safe range
        original_sample_size = self.sample_size
        self.sample_size = max(self.SAMPLE_SIZE_MIN, min(self.SAMPLE_SIZE_MAX, self.sample_size))
        self._sample_size_clamped = original_sample_size != self.sample_size
        self._original_sample_size = original_sample_size
        
        # Validate timeout (warn if unusually low, but allow it)
        self._timeout_warning = None
        if self.timeout_seconds < self.TIMEOUT_MIN_SECONDS:
            self._timeout_warning = (
                f"Timeout {self.timeout_seconds}s is below recommended minimum "
                f"({self.TIMEOUT_MIN_SECONDS}s). This may cause premature termination."
            )
    
    @classmethod
    def validate_sample_size(cls, value: int) -> tuple[bool, str]:
        """Validate sample size before configuration.
        
        Args:
            value: Requested sample size
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if value < cls.SAMPLE_SIZE_MIN or value > cls.SAMPLE_SIZE_MAX:
            return False, (
                f"Sample size must be between {cls.SAMPLE_SIZE_MIN} and {cls.SAMPLE_SIZE_MAX}. "
                f"Got: {value}"
            )
        return True, ""
    
    @property
    def was_sample_size_clamped(self) -> bool:
        """Check if sample size was clamped from original value."""
        return self._sample_size_clamped
    
    @property
    def original_sample_size(self) -> int:
        """Get the originally requested sample size."""
        return self._original_sample_size
    
    @property
    def timeout_warning(self) -> Optional[str]:
        """Get timeout warning message if applicable."""
        return self._timeout_warning


class DryRunPhaseTracker:
    """Tracks execution phases with timing and status."""
    
    def __init__(self, verbose: bool = False, logger: Any = None):
        """Initialize phase tracker.
        
        Args:
            verbose: Enable verbose logging
            logger: Logger instance for observability
        """
        self.verbose = verbose
        self.logger = logger
        self.phases: List[PhaseResult] = []
        self._current_phase: Optional[str] = None
        self._phase_start_time: Optional[float] = None
    
    def start_phase(self, phase: DryRunPhase) -> None:
        """Start tracking a new phase.
        
        Args:
            phase: The phase being started
        """
        self._current_phase = phase.value
        self._phase_start_time = time.perf_counter()
        
        if self.verbose and self.logger:
            self.logger.info(
                f"Phase started: {phase.value}",
                extra={
                    "event_type": "dry_run_phase_started",
                    "phase": phase.value,
                },
            )
    
    def end_phase(
        self,
        status: PhaseStatus,
        error_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> PhaseResult:
        """End the current phase and record results.
        
        Args:
            status: Final status of the phase
            error_message: Optional error message if failed
            details: Optional additional details
            
        Returns:
            PhaseResult for the completed phase
        """
        if not self._current_phase or self._phase_start_time is None:
            raise RuntimeError("No phase currently in progress")
        
        duration = time.perf_counter() - self._phase_start_time
        
        result = PhaseResult(
            phase=self._current_phase,
            status=status.value,
            duration_seconds=duration,
            error_message=error_message,
            details=details,
        )
        
        self.phases.append(result)
        
        if self.verbose and self.logger:
            self.logger.info(
                f"Phase completed: {self._current_phase} ({status.value}) in {duration:.3f}s",
                extra={
                    "event_type": "dry_run_phase_completed",
                    "phase": self._current_phase,
                    "status": status.value,
                    "duration_seconds": round(duration, 3),
                },
            )
        
        self._current_phase = None
        self._phase_start_time = None
        
        return result
    
    def skip_phase(
        self,
        phase: DryRunPhase,
        reason: Optional[str] = None,
    ) -> PhaseResult:
        """Record a skipped phase.
        
        Args:
            phase: The phase being skipped
            reason: Optional reason for skipping
            
        Returns:
            PhaseResult for the skipped phase
        """
        result = PhaseResult(
            phase=phase.value,
            status=PhaseStatus.SKIPPED.value,
            duration_seconds=0.0,
            error_message=reason,
        )
        
        self.phases.append(result)
        
        if self.verbose and self.logger:
            self.logger.info(
                f"Phase skipped: {phase.value}" + (f" ({reason})" if reason else ""),
                extra={
                    "event_type": "dry_run_phase_skipped",
                    "phase": phase.value,
                    "reason": reason,
                },
            )
        
        return result
    
    def get_completed_phases(self) -> List[str]:
        """Get list of successfully completed phase names."""
        return [
            p.phase for p in self.phases 
            if p.status == PhaseStatus.SUCCESS.value
        ]
    
    def get_failed_phase(self) -> Optional[PhaseResult]:
        """Get the first failed phase, if any."""
        for p in self.phases:
            if p.status == PhaseStatus.FAILURE.value:
                return p
        return None
    
    def all_phases_passed(self) -> bool:
        """Check if all phases passed (success or skipped)."""
        return all(
            p.status in (PhaseStatus.SUCCESS.value, PhaseStatus.SKIPPED.value)
            for p in self.phases
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert all phase results to dictionary."""
        return {
            "phases": [p.to_dict() for p in self.phases],
            "phases_completed": self.get_completed_phases(),
            "all_passed": self.all_phases_passed(),
        }


@dataclass
class DryRunResult:
    """Complete result of a dry-run execution."""
    
    valid: bool = True
    exit_code: int = 0
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    phases_completed: List[str] = field(default_factory=list)
    phases: List[Dict[str, Any]] = field(default_factory=list)
    
    # Execution metrics
    sample_size: int = 0
    valid_records: int = 0
    invalid_records: int = 0
    
    # Validation details
    validation_errors_by_type: Dict[str, int] = field(default_factory=dict)
    validation_errors_by_field: Dict[str, int] = field(default_factory=dict)
    sample_validation_errors: List[Dict[str, Any]] = field(default_factory=list)
    
    # Safety assertions
    writes_attempted: bool = False
    state_updates_attempted: bool = False
    commits_attempted: bool = False
    
    # Source/target info
    source_connector: Optional[str] = None
    target_connector: Optional[str] = None
    asset_name: Optional[str] = None
    
    def add_error(self, message: str, code: str, phase: Optional[str] = None) -> None:
        """Add an error to the result."""
        self.valid = False
        self.errors.append({
            "message": message,
            "code": code,
            "phase": phase,
        })
    
    def add_warning(self, message: str, code: str, phase: Optional[str] = None) -> None:
        """Add a warning to the result."""
        self.warnings.append({
            "message": message,
            "code": code,
            "phase": phase,
        })
    
    def assert_no_writes(self) -> None:
        """Assert that no writes were attempted during dry-run.
        
        Raises:
            AssertionError: If writes were attempted
        """
        assert not self.writes_attempted, (
            "SAFETY VIOLATION: Write operation was attempted during dry-run mode. "
            "This indicates a bug in the dry-run implementation."
        )
    
    def assert_no_state_updates(self) -> None:
        """Assert that no state updates were attempted during dry-run.
        
        Raises:
            AssertionError: If state updates were attempted
        """
        assert not self.state_updates_attempted, (
            "SAFETY VIOLATION: State update was attempted during dry-run mode. "
            "This indicates a bug in the dry-run implementation."
        )
    
    def assert_no_commits(self) -> None:
        """Assert that no commits were attempted during dry-run.
        
        Raises:
            AssertionError: If commits were attempted
        """
        assert not self.commits_attempted, (
            "SAFETY VIOLATION: Commit operation was attempted during dry-run mode. "
            "This indicates a bug in the dry-run implementation."
        )
    
    def assert_safety_guarantees(self) -> None:
        """Assert all safety guarantees for dry-run mode.
        
        Raises:
            AssertionError: If any safety guarantee is violated
        """
        self.assert_no_writes()
        self.assert_no_state_updates()
        self.assert_no_commits()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "valid": self.valid,
            "exit_code": self.exit_code,
            "errors": self.errors,
            "warnings": self.warnings,
            "phases_completed": self.phases_completed,
            "phases": self.phases,
            "metrics": {
                "sample_size": self.sample_size,
                "valid_records": self.valid_records,
                "invalid_records": self.invalid_records,
            },
            "validation": {
                "errors_by_type": self.validation_errors_by_type,
                "errors_by_field": self.validation_errors_by_field,
                "sample_errors": self.sample_validation_errors[:10],  # Limit to 10
            },
            "safety_assertions": {
                "no_writes": not self.writes_attempted,
                "no_state_updates": not self.state_updates_attempted,
                "no_commits": not self.commits_attempted,
            },
            "source_connector": self.source_connector,
            "target_connector": self.target_connector,
            "asset_name": self.asset_name,
        }
        return result
    
    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


def format_dry_run_output(
    result: DryRunResult,
    json_output: bool = False,
    verbose: bool = False,
) -> str:
    """Format dry-run result for output.
    
    Args:
        result: DryRunResult to format
        json_output: Output as JSON
        verbose: Include verbose details
        
    Returns:
        Formatted string output
    """
    if json_output:
        return result.to_json()
    
    lines = []
    lines.append("")
    lines.append("=" * 60)
    lines.append("DRY-RUN EXECUTION RESULTS")
    lines.append("=" * 60)
    
    # Overall status
    status_icon = "✅" if result.valid else "❌"
    status_text = "PASSED" if result.valid else "FAILED"
    lines.append(f"\nStatus: {status_icon} {status_text}")
    lines.append(f"Exit Code: {result.exit_code}")
    
    # Phase summary
    lines.append(f"\nPhases Completed: {len(result.phases_completed)}/{len(result.phases)}")
    
    if verbose:
        lines.append("\nPhase Details:")
        for phase in result.phases:
            status_icon = "✓" if phase["status"] == "success" else "✗" if phase["status"] == "failure" else "○"
            lines.append(f"  {status_icon} {phase['phase']}: {phase['status']} ({phase['duration_seconds']:.3f}s)")
            if phase.get("error_message"):
                lines.append(f"      Error: {phase['error_message']}")
    
    # Metrics
    lines.append(f"\nSample Metrics:")
    lines.append(f"  Records fetched: {result.sample_size}")
    lines.append(f"  Valid records: {result.valid_records}")
    lines.append(f"  Invalid records: {result.invalid_records}")
    
    # Errors
    if result.errors:
        lines.append(f"\n❌ Errors ({len(result.errors)}):")
        for error in result.errors:
            phase_info = f" [{error['phase']}]" if error.get("phase") else ""
            lines.append(f"  - [{error['code']}]{phase_info} {error['message']}")
    
    # Warnings
    if result.warnings:
        lines.append(f"\n⚠️  Warnings ({len(result.warnings)}):")
        for warning in result.warnings:
            phase_info = f" [{warning['phase']}]" if warning.get("phase") else ""
            lines.append(f"  - [{warning['code']}]{phase_info} {warning['message']}")
    
    # Validation errors detail
    if result.validation_errors_by_type and verbose:
        lines.append("\nValidation Errors by Type:")
        for error_type, count in result.validation_errors_by_type.items():
            lines.append(f"  - {error_type}: {count}")
    
    if result.validation_errors_by_field and verbose:
        lines.append("\nValidation Errors by Field:")
        for field_name, count in result.validation_errors_by_field.items():
            lines.append(f"  - {field_name}: {count}")
    
    # Safety assertions
    lines.append("\n🔒 Safety Assertions:")
    lines.append(f"  No writes attempted: {'✓' if not result.writes_attempted else '✗'}")
    lines.append(f"  No state updates: {'✓' if not result.state_updates_attempted else '✗'}")
    lines.append(f"  No commits: {'✓' if not result.commits_attempted else '✗'}")
    
    # Source/target info
    if result.source_connector or result.target_connector or result.asset_name:
        lines.append("\nConfiguration:")
        if result.source_connector:
            lines.append(f"  Source: {result.source_connector}")
        if result.target_connector:
            lines.append(f"  Target: {result.target_connector}")
        if result.asset_name:
            lines.append(f"  Asset: {result.asset_name}")
    
    lines.append("\n" + "=" * 60)
    
    return "\n".join(lines)
