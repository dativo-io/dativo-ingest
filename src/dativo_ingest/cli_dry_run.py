"""CLI dry-run functionality for validating job execution without side effects.

Provides dry-run capabilities that perform:
- Configuration validation
- Asset loading and validation
- Extractor initialization
- Discovery (available streams/tables)
- Schema negotiation (source vs asset schema)
- Sample data fetch
- Data contract validation on sample

Exit codes:
- 0: Dry-run passed
- 2: Dry-run failed
"""

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .cli_validation import ConfigValidator, ValidationResult
from .config import AssetDefinition, ConnectorRecipe, JobConfig
from .connectors.factory import ExtractorFactory
from .logging import get_logger, setup_logging
from .plugins import PluginLoader, extract_sandbox_config
from .registry import ConnectorRegistry, RegistryLoadError, RegistryNotFoundError
from .validator import ConnectorValidator


@dataclass
class DryRunPhase:
    """Represents a dry-run execution phase."""

    name: str
    status: str = "pending"  # pending, running, completed, failed, skipped
    duration_seconds: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class DryRunResult:
    """Container for dry-run results."""

    passed: bool = True
    phases: List[DryRunPhase] = field(default_factory=list)
    connector_info: Dict[str, Any] = field(default_factory=dict)
    asset_info: Dict[str, Any] = field(default_factory=dict)
    sample_data: Dict[str, Any] = field(default_factory=dict)
    validation_results: Dict[str, Any] = field(default_factory=dict)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    total_duration_seconds: float = 0.0

    def add_phase(self, phase: DryRunPhase) -> None:
        """Add a phase to the result.

        Args:
            phase: Phase to add
        """
        self.phases.append(phase)
        if phase.status == "failed":
            self.passed = False

    def add_error(self, code: str, message: str, phase: Optional[str] = None) -> None:
        """Add an error to the result.

        Args:
            code: Error code
            message: Error message
            phase: Phase where error occurred
        """
        self.passed = False
        error = {"code": code, "message": message}
        if phase:
            error["phase"] = phase
        self.errors.append(error)

    def add_warning(
        self, code: str, message: str, phase: Optional[str] = None
    ) -> None:
        """Add a warning to the result.

        Args:
            code: Warning code
            message: Warning message
            phase: Phase where warning occurred
        """
        warning = {"code": code, "message": message}
        if phase:
            warning["phase"] = phase
        self.warnings.append(warning)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for JSON output.

        Returns:
            Dictionary representation of the result
        """
        return {
            "valid": self.passed,
            "phases_completed": [
                p.name for p in self.phases if p.status == "completed"
            ],
            "connector_info": self.connector_info,
            "asset_info": self.asset_info,
            "sample_data": self.sample_data,
            "validation_results": self.validation_results,
            "errors": self.errors,
            "warnings": self.warnings,
            "total_duration_seconds": self.total_duration_seconds,
        }


class DryRunExecutor:
    """Executes dry-run validation for job configurations."""

    # Sample size constraints
    MIN_SAMPLE_SIZE = 10
    MAX_SAMPLE_SIZE = 50
    DEFAULT_SAMPLE_SIZE = 25

    # Timeout constraints
    MIN_TIMEOUT = 30
    DEFAULT_TIMEOUT = 300  # 5 minutes

    def __init__(
        self,
        job_config: JobConfig,
        mode: str = "self_hosted",
        sample_size: int = DEFAULT_SAMPLE_SIZE,
        timeout: int = DEFAULT_TIMEOUT,
        verbose: bool = False,
    ):
        """Initialize dry-run executor.

        Args:
            job_config: Job configuration to validate
            mode: Execution mode (self_hosted or cloud)
            sample_size: Number of sample rows to fetch (10-50)
            timeout: Timeout in seconds (minimum 30)
            verbose: Enable verbose output
        """
        self.job_config = job_config
        self.mode = mode
        self.sample_size = max(
            self.MIN_SAMPLE_SIZE, min(sample_size, self.MAX_SAMPLE_SIZE)
        )
        self.timeout = max(self.MIN_TIMEOUT, timeout)
        self.verbose = verbose
        self.logger = get_logger()
        self.start_time: Optional[float] = None

    def execute(self) -> DryRunResult:
        """Execute dry-run validation.

        Returns:
            DryRunResult with validation status and details
        """
        result = DryRunResult()
        self.start_time = time.time()

        self.logger.info(
            "Dry-run started",
            extra={
                "event_type": "dry_run_started",
                "tenant_id": self.job_config.tenant_id,
                "mode": self.mode,
                "sample_size": self.sample_size,
                "timeout": self.timeout,
            },
        )

        try:
            # Phase 1: Configuration Validation
            self._execute_phase(
                result,
                "configuration_validation",
                "Configuration Validation",
                self._validate_configuration,
            )
            if not result.passed:
                return self._finalize(result)

            # Phase 2: Asset Loading
            self._execute_phase(
                result,
                "asset_loading",
                "Asset Loading",
                self._load_asset,
            )
            if not result.passed:
                return self._finalize(result)

            # Phase 3: Extractor Initialization
            self._execute_phase(
                result,
                "extractor_initialization",
                "Extractor Initialization",
                self._init_extractor,
            )
            if not result.passed:
                return self._finalize(result)

            # Phase 4: Discovery
            self._execute_phase(
                result,
                "discovery",
                "Discovery",
                self._run_discovery,
            )

            # Phase 5: Schema Negotiation
            self._execute_phase(
                result,
                "schema_negotiation",
                "Schema Negotiation",
                self._negotiate_schema,
            )

            # Phase 6: Sample Fetch
            self._execute_phase(
                result,
                "sample_fetch",
                "Sample Fetch",
                self._fetch_sample,
            )

            # Phase 7: Sample Validation
            self._execute_phase(
                result,
                "sample_validation",
                "Sample Validation",
                self._validate_sample,
            )

        except TimeoutError as e:
            result.add_error(
                code="TIMEOUT",
                message=f"Dry-run timed out after {self.timeout} seconds: {e}",
            )
            self.logger.warning(
                "Dry-run timeout",
                extra={
                    "event_type": "dry_run_timeout",
                    "timeout": self.timeout,
                },
            )
        except Exception as e:
            result.add_error(
                code="UNEXPECTED_ERROR",
                message=f"Unexpected error during dry-run: {e}",
            )
            self.logger.error(
                f"Dry-run unexpected error: {e}",
                extra={"event_type": "dry_run_error"},
                exc_info=True,
            )

        return self._finalize(result)

    def _execute_phase(
        self,
        result: DryRunResult,
        phase_id: str,
        phase_name: str,
        phase_func,
    ) -> None:
        """Execute a single phase of the dry-run.

        Args:
            result: DryRunResult to update
            phase_id: Phase identifier for logging
            phase_name: Human-readable phase name
            phase_func: Function to execute for this phase
        """
        # Check timeout
        if self._check_timeout():
            raise TimeoutError(f"Timeout exceeded during phase: {phase_name}")

        phase = DryRunPhase(name=phase_name, status="running")
        phase_start = time.time()

        self.logger.info(
            f"Dry-run phase: {phase_name}",
            extra={
                "event_type": f"dry_run_{phase_id}",
                "phase": phase_id,
            },
        )

        try:
            phase_func(result, phase)
            phase.status = "completed"
        except Exception as e:
            phase.status = "failed"
            phase.error = str(e)
            result.add_error(
                code=f"{phase_id.upper()}_FAILED",
                message=str(e),
                phase=phase_name,
            )
            self.logger.error(
                f"Dry-run phase failed: {phase_name}: {e}",
                extra={
                    "event_type": f"dry_run_{phase_id}_failed",
                    "error": str(e),
                },
            )

        phase.duration_seconds = time.time() - phase_start
        result.add_phase(phase)

    def _check_timeout(self) -> bool:
        """Check if timeout has been exceeded.

        Returns:
            True if timeout exceeded
        """
        if self.start_time is None:
            return False
        return (time.time() - self.start_time) > self.timeout

    def _validate_configuration(
        self, result: DryRunResult, phase: DryRunPhase
    ) -> None:
        """Phase 1: Validate job configuration.

        Args:
            result: DryRunResult to update
            phase: Current phase
        """
        self.logger.info(
            "Validating configuration",
            extra={"event_type": "dry_run_validate_config"},
        )

        # Use ConfigValidator for comprehensive validation
        validator = ConfigValidator(mode=self.mode, verbose=self.verbose)
        config_path = Path(self.job_config.source_connector_path).parent / ".."

        # We can't easily get the original config path, so validate the resolved config
        # Check that we can resolve source and target
        source_config = self.job_config.get_source()
        target_config = self.job_config.get_target()

        result.connector_info = {
            "source_type": source_config.type,
            "target_type": target_config.type,
        }

        if source_config.custom_reader:
            result.connector_info["source_custom_reader"] = source_config.custom_reader

        if target_config.custom_writer:
            result.connector_info["target_custom_writer"] = target_config.custom_writer

        # Validate connector exists
        try:
            validator = ConnectorValidator()
            validator.validate_job(self.job_config, mode=self.mode)
        except SystemExit as e:
            raise RuntimeError(f"Configuration validation failed: exit code {e.code}")

        phase.details["source_type"] = source_config.type
        phase.details["target_type"] = target_config.type

    def _load_asset(self, result: DryRunResult, phase: DryRunPhase) -> None:
        """Phase 2: Load and validate asset definition.

        Args:
            result: DryRunResult to update
            phase: Current phase
        """
        self.logger.info(
            "Loading asset definition",
            extra={"event_type": "dry_run_load_asset"},
        )

        asset_path = Path(self.job_config.get_asset_path())

        if not asset_path.exists():
            raise FileNotFoundError(f"Asset definition not found: {asset_path}")

        # Load and validate asset
        asset = AssetDefinition.from_yaml(asset_path)

        result.asset_info = {
            "name": asset.name,
            "version": asset.version,
            "object": asset.object,
            "source_type": asset.source_type,
            "schema_field_count": len(asset.schema_fields),
        }

        if asset.team:
            result.asset_info["team_owner"] = asset.team.owner

        phase.details["asset_name"] = asset.name
        phase.details["asset_version"] = asset.version
        phase.details["schema_fields"] = len(asset.schema_fields)

        # Store for later phases
        self._asset = asset

    def _init_extractor(self, result: DryRunResult, phase: DryRunPhase) -> None:
        """Phase 3: Initialize the source extractor.

        Args:
            result: DryRunResult to update
            phase: Current phase
        """
        self.logger.info(
            "Initializing extractor",
            extra={"event_type": "dry_run_init_extractor"},
        )

        source_config = self.job_config.get_source()

        # For custom readers
        if source_config.custom_reader:
            sandbox_config, plugin_config = extract_sandbox_config(self.job_config)
            reader_class = PluginLoader.load_reader(
                source_config.custom_reader,
                mode=self.mode,
                sandbox_config=sandbox_config,
                plugin_config=plugin_config,
            )
            self._extractor = reader_class(source_config)
            phase.details["extractor_type"] = "custom_reader"
            result.connector_info["extractor_type"] = "custom_reader"
            return

        # For built-in extractors
        connector_recipe = None
        if self.job_config.source_connector_path:
            try:
                connector_recipe = ConnectorRecipe.from_yaml(
                    self.job_config.source_connector_path
                )
            except Exception as e:
                result.add_warning(
                    code="CONNECTOR_RECIPE_WARNING",
                    message=f"Could not load connector recipe: {e}",
                    phase="Extractor Initialization",
                )

        # Use ExtractorFactory to create extractor
        extractor, _ = ExtractorFactory.create(
            source_config=source_config,
            job_config=self.job_config,
            tenant_id=self.job_config.tenant_id,
            mode=self.mode,
        )

        self._extractor = extractor
        phase.details["extractor_type"] = type(extractor).__name__
        result.connector_info["extractor_type"] = type(extractor).__name__

    def _run_discovery(self, result: DryRunResult, phase: DryRunPhase) -> None:
        """Phase 4: Run discovery to list available streams/tables.

        Args:
            result: DryRunResult to update
            phase: Current phase
        """
        self.logger.info(
            "Running discovery",
            extra={"event_type": "dry_run_discovery"},
        )

        try:
            if hasattr(self._extractor, "discover"):
                discovery_result = self._extractor.discover()

                if isinstance(discovery_result, dict):
                    streams = discovery_result.get(
                        "streams", discovery_result.get("objects", [])
                    )
                    phase.details["streams_found"] = len(streams)
                    if streams:
                        phase.details["stream_names"] = [
                            s.get("name", "unknown") for s in streams[:5]
                        ]
                else:
                    phase.details["discovery_result"] = "non-standard format"
            else:
                phase.details["discovery"] = "not supported by extractor"
                result.add_warning(
                    code="DISCOVERY_NOT_SUPPORTED",
                    message="Extractor does not support discovery",
                    phase="Discovery",
                )
        except Exception as e:
            # Discovery failure is not fatal
            result.add_warning(
                code="DISCOVERY_FAILED",
                message=f"Discovery failed (non-fatal): {e}",
                phase="Discovery",
            )
            phase.details["discovery_error"] = str(e)

    def _negotiate_schema(self, result: DryRunResult, phase: DryRunPhase) -> None:
        """Phase 5: Negotiate schema between source and asset.

        Args:
            result: DryRunResult to update
            phase: Current phase
        """
        self.logger.info(
            "Negotiating schema",
            extra={"event_type": "dry_run_schema_negotiation"},
        )

        # Get asset schema fields
        asset_fields = {f["name"]: f for f in self._asset.schema_fields}
        phase.details["asset_field_count"] = len(asset_fields)

        # Try to get source schema if available
        source_fields = {}
        try:
            if hasattr(self._extractor, "get_schema"):
                source_schema = self._extractor.get_schema()
                if isinstance(source_schema, dict):
                    source_fields = {
                        f["name"]: f for f in source_schema.get("fields", [])
                    }
                elif isinstance(source_schema, list):
                    source_fields = {f.get("name", str(i)): f for i, f in enumerate(source_schema)}
        except Exception as e:
            result.add_warning(
                code="SOURCE_SCHEMA_UNAVAILABLE",
                message=f"Could not get source schema: {e}",
                phase="Schema Negotiation",
            )

        if source_fields:
            phase.details["source_field_count"] = len(source_fields)

            # Check for mismatches
            asset_only = set(asset_fields.keys()) - set(source_fields.keys())
            source_only = set(source_fields.keys()) - set(asset_fields.keys())

            if asset_only:
                phase.details["fields_in_asset_only"] = list(asset_only)[:10]
            if source_only:
                phase.details["fields_in_source_only"] = list(source_only)[:10]

            common_fields = set(asset_fields.keys()) & set(source_fields.keys())
            phase.details["common_fields"] = len(common_fields)
        else:
            phase.details["source_schema"] = "unavailable"
            result.add_warning(
                code="SCHEMA_NEGOTIATION_LIMITED",
                message="Source schema not available, negotiation limited to asset schema",
                phase="Schema Negotiation",
            )

        # Add schema field names to asset info
        result.asset_info["schema_fields"] = list(asset_fields.keys())[:20]

    def _fetch_sample(self, result: DryRunResult, phase: DryRunPhase) -> None:
        """Phase 6: Fetch sample data from source.

        Args:
            result: DryRunResult to update
            phase: Current phase
        """
        self.logger.info(
            "Fetching sample data",
            extra={
                "event_type": "dry_run_fetch_sample",
                "sample_size": self.sample_size,
                "timeout_remaining": self.timeout - (time.time() - self.start_time),
            },
        )

        fetch_start = time.time()
        rows_fetched = 0
        columns = []

        try:
            if hasattr(self._extractor, "extract_sample"):
                # Preferred method for dry-run
                sample = self._extractor.extract_sample(limit=self.sample_size)
                if hasattr(sample, "__len__"):
                    rows_fetched = len(sample)
                if hasattr(sample, "columns"):
                    columns = list(sample.columns)
                elif isinstance(sample, list) and sample:
                    if isinstance(sample[0], dict):
                        columns = list(sample[0].keys())
                self._sample_data = sample
            elif hasattr(self._extractor, "extract"):
                # Fall back to regular extract with limit
                sample = list(self._extractor.extract())[:self.sample_size]
                rows_fetched = len(sample)
                if sample and isinstance(sample[0], dict):
                    columns = list(sample[0].keys())
                self._sample_data = sample
            else:
                result.add_warning(
                    code="SAMPLE_FETCH_NOT_SUPPORTED",
                    message="Extractor does not support sample fetching",
                    phase="Sample Fetch",
                )
                self._sample_data = []
                return

        except Exception as e:
            result.add_warning(
                code="SAMPLE_FETCH_ERROR",
                message=f"Failed to fetch sample data: {e}",
                phase="Sample Fetch",
            )
            self._sample_data = []
            return

        fetch_duration = time.time() - fetch_start

        result.sample_data = {
            "rows_fetched": rows_fetched,
            "fetch_duration_seconds": round(fetch_duration, 3),
            "columns": columns[:20],  # Limit columns for readability
            "column_count": len(columns),
        }

        phase.details["rows_fetched"] = rows_fetched
        phase.details["fetch_duration_seconds"] = round(fetch_duration, 3)
        phase.details["columns"] = len(columns)

    def _validate_sample(self, result: DryRunResult, phase: DryRunPhase) -> None:
        """Phase 7: Validate sample data against data contract.

        Args:
            result: DryRunResult to update
            phase: Current phase
        """
        self.logger.info(
            "Validating sample data",
            extra={"event_type": "dry_run_validate_sample"},
        )

        if not hasattr(self, "_sample_data") or not self._sample_data:
            phase.details["validation"] = "skipped (no sample data)"
            result.add_warning(
                code="SAMPLE_VALIDATION_SKIPPED",
                message="No sample data available for validation",
                phase="Sample Validation",
            )
            return

        # Get validation mode from job config
        validation_mode = self.job_config.schema_validation_mode or "strict"

        # Basic validation: check that all required fields are present
        asset_fields = {f["name"]: f for f in self._asset.schema_fields}
        required_fields = [
            name for name, field in asset_fields.items() if not field.get("nullable", True)
        ]

        valid_rows = 0
        invalid_rows = 0
        validation_errors = []

        # Convert sample to list of dicts for validation
        sample_list = []
        if hasattr(self._sample_data, "to_dict"):
            sample_list = self._sample_data.to_dict("records")
        elif isinstance(self._sample_data, list):
            sample_list = self._sample_data
        else:
            # Try pandas DataFrame
            try:
                import pandas as pd

                if isinstance(self._sample_data, pd.DataFrame):
                    sample_list = self._sample_data.to_dict("records")
            except ImportError:
                pass

        for idx, row in enumerate(sample_list):
            row_valid = True
            if isinstance(row, dict):
                for field in required_fields:
                    if field not in row or row[field] is None:
                        row_valid = False
                        if len(validation_errors) < 5:  # Limit errors
                            validation_errors.append(
                                f"Row {idx}: missing required field '{field}'"
                            )
                        break

            if row_valid:
                valid_rows += 1
            else:
                invalid_rows += 1

        total_rows = valid_rows + invalid_rows
        data_contract_valid = invalid_rows == 0 or validation_mode == "warn"

        result.validation_results = {
            "data_contract_valid": data_contract_valid,
            "mode": validation_mode,
            "valid_rows": valid_rows,
            "invalid_rows": invalid_rows,
            "total_rows": total_rows,
        }

        if validation_errors:
            result.validation_results["sample_errors"] = validation_errors

        phase.details["data_contract_valid"] = data_contract_valid
        phase.details["valid_rows"] = valid_rows
        phase.details["invalid_rows"] = invalid_rows

        if not data_contract_valid:
            result.add_error(
                code="DATA_CONTRACT_INVALID",
                message=f"Data contract validation failed: {invalid_rows}/{total_rows} rows invalid",
                phase="Sample Validation",
            )

    def _finalize(self, result: DryRunResult) -> DryRunResult:
        """Finalize the dry-run result.

        Args:
            result: DryRunResult to finalize

        Returns:
            Finalized DryRunResult
        """
        if self.start_time:
            result.total_duration_seconds = round(time.time() - self.start_time, 3)

        status = "passed" if result.passed else "failed"
        self.logger.info(
            f"Dry-run completed: {status}",
            extra={
                "event_type": "dry_run_completed",
                "status": status,
                "duration_seconds": result.total_duration_seconds,
                "phases_completed": len(
                    [p for p in result.phases if p.status == "completed"]
                ),
                "errors": len(result.errors),
                "warnings": len(result.warnings),
            },
        )

        return result


def dry_run_command(
    config_path: str,
    mode: str = "self_hosted",
    sample_size: int = 25,
    timeout: int = 300,
    json_output: bool = False,
    verbose: bool = False,
) -> int:
    """Execute dry-run command.

    Args:
        config_path: Path to job configuration YAML file
        mode: Execution mode (self_hosted or cloud)
        sample_size: Number of sample rows to fetch (10-50)
        timeout: Timeout in seconds (minimum 30)
        json_output: Output results in JSON format
        verbose: Enable verbose output

    Returns:
        Exit code (0=passed, 2=failed)
    """
    # Record metric
    _record_dry_run_metric(None, None)

    # Set up logging
    logger = setup_logging(level="INFO", redact_secrets=True)

    # Load job configuration
    try:
        job_config = JobConfig.from_yaml(config_path)
    except SystemExit as e:
        if json_output:
            error_result = DryRunResult()
            error_result.add_error(
                code="CONFIG_LOAD_ERROR",
                message=f"Failed to load configuration: exit code {e.code}",
            )
            print(json.dumps(error_result.to_dict(), indent=2))
        else:
            print(f"\nERROR: Failed to load configuration from {config_path}")
        return 2
    except Exception as e:
        if json_output:
            error_result = DryRunResult()
            error_result.add_error(
                code="CONFIG_LOAD_ERROR",
                message=str(e),
            )
            print(json.dumps(error_result.to_dict(), indent=2))
        else:
            print(f"\nERROR: {e}")
        return 2

    # Execute dry-run
    executor = DryRunExecutor(
        job_config=job_config,
        mode=mode,
        sample_size=sample_size,
        timeout=timeout,
        verbose=verbose,
    )

    result = executor.execute()

    # Record result metric
    connector_type = result.connector_info.get("source_type", "unknown")
    _record_dry_run_metric(
        "success" if result.passed else "failure",
        connector_type,
    )

    # Format output
    _format_dry_run_output(result, json_output=json_output, verbose=verbose)

    return 0 if result.passed else 2


def _format_dry_run_output(
    result: DryRunResult,
    json_output: bool = False,
    verbose: bool = False,
) -> None:
    """Format and print dry-run results.

    Args:
        result: Dry-run result
        json_output: Whether to output JSON
        verbose: Whether to include verbose details
    """
    if json_output:
        print(json.dumps(result.to_dict(), indent=2))
        return

    # Text output
    status_symbol = "+" if result.passed else "-"
    status_text = "PASSED" if result.passed else "FAILED"

    print()
    print("=" * 60)
    print(f"DRY-RUN RESULTS: {status_symbol} {status_text}")
    print("=" * 60)

    # Phases
    completed_phases = [p for p in result.phases if p.status == "completed"]
    print(f"\nPhases Completed ({len(completed_phases)}):")
    for phase in result.phases:
        if phase.status == "completed":
            symbol = "[+]"
        elif phase.status == "failed":
            symbol = "[-]"
        elif phase.status == "skipped":
            symbol = "[~]"
        else:
            symbol = "[ ]"
        print(f"  {symbol} {phase.name}")
        if phase.status == "failed" and phase.error:
            print(f"      Error: {phase.error}")

    # Connector info
    if result.connector_info:
        print("\nConnector Info:")
        print(f"  Source: {result.connector_info.get('source_type', 'unknown')}")
        print(f"  Target: {result.connector_info.get('target_type', 'unknown')}")

    # Asset info
    if result.asset_info:
        print("\nAsset Info:")
        print(f"  Name: {result.asset_info.get('name', 'unknown')}")
        print(f"  Version: {result.asset_info.get('version', 'unknown')}")
        print(f"  Object: {result.asset_info.get('object', 'unknown')}")
        print(f"  Schema Fields: {result.asset_info.get('schema_field_count', 0)}")

    # Sample data
    if result.sample_data:
        print("\nSample Data:")
        print(f"  Rows Fetched: {result.sample_data.get('rows_fetched', 0)}")
        print(
            f"  Fetch Duration: {result.sample_data.get('fetch_duration_seconds', 0)}s"
        )
        columns = result.sample_data.get("columns", [])
        if columns:
            column_display = ", ".join(columns[:6])
            if len(columns) > 6:
                column_display += ", ..."
            print(f"  Columns: {column_display}")

    # Validation results
    if result.validation_results:
        print("\nData Contract Validation:")
        valid = result.validation_results.get("data_contract_valid", False)
        valid_symbol = "[+] Yes" if valid else "[-] No"
        print(f"  Contract Valid: {valid_symbol}")
        print(f"  Mode: {result.validation_results.get('mode', 'unknown')}")
        valid_rows = result.validation_results.get("valid_rows", 0)
        total_rows = result.validation_results.get("total_rows", 0)
        print(f"  Valid Rows: {valid_rows}/{total_rows}")

    # Errors
    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for error in result.errors:
            print(f"  - [{error['code']}] {error['message']}")
            if error.get("phase"):
                print(f"    Phase: {error['phase']}")

    # Warnings
    if result.warnings:
        print(f"\nWarnings ({len(result.warnings)}):")
        for warning in result.warnings:
            print(f"  - [{warning['code']}] {warning['message']}")

    # Duration
    print(f"\nTotal Duration: {result.total_duration_seconds}s")

    print("=" * 60)
    print()


def _record_dry_run_metric(result: Optional[str], connector_type: Optional[str]) -> None:
    """Record dry-run metrics to Prometheus.

    Args:
        result: Result of dry-run (success, failure, timeout, or None for start)
        connector_type: Type of source connector
    """
    if result and connector_type:
        try:
            from .metrics import record_dry_run_metric

            record_dry_run_metric(result, connector_type)
        except ImportError:
            # Metrics module not available
            pass
        except Exception:
            # Don't fail dry-run due to metrics error
            pass
