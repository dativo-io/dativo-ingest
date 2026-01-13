"""CLI validation commands for job configurations and asset definitions.

Provides validation capabilities for:
- Job configuration YAML files (dativo validate config)
- Asset definition YAML files (dativo validate asset)

Exit codes:
- 0: Valid configuration
- 2: Invalid configuration
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from .config import AssetDefinition, JobConfig
from .logging import get_logger
from .registry import ConnectorRegistry, RegistryLoadError, RegistryNotFoundError
from .validator import ConnectorValidator


class ValidationResult:
    """Container for validation results."""

    def __init__(self, valid: bool = True):
        """Initialize validation result.

        Args:
            valid: Whether validation passed
        """
        self.valid = valid
        self.errors: List[Dict[str, Any]] = []
        self.warnings: List[Dict[str, Any]] = []
        self.info: Dict[str, Any] = {}

    def add_error(
        self, code: str, message: str, path: Optional[str] = None, **kwargs
    ) -> None:
        """Add an error to the result.

        Args:
            code: Error code (e.g., 'YAML_SYNTAX', 'SCHEMA_INVALID')
            message: Human-readable error message
            path: Optional path in the document where error occurred
            **kwargs: Additional error context
        """
        self.valid = False
        error = {"code": code, "message": message}
        if path:
            error["path"] = path
        error.update(kwargs)
        self.errors.append(error)

    def add_warning(
        self, code: str, message: str, path: Optional[str] = None, **kwargs
    ) -> None:
        """Add a warning to the result.

        Args:
            code: Warning code
            message: Human-readable warning message
            path: Optional path in the document where warning occurred
            **kwargs: Additional warning context
        """
        warning = {"code": code, "message": message}
        if path:
            warning["path"] = path
        warning.update(kwargs)
        self.warnings.append(warning)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for JSON output.

        Returns:
            Dictionary representation of the result
        """
        result = {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }
        if self.info:
            result["info"] = self.info
        return result


class ConfigValidator:
    """Validates job configuration YAML files."""

    def __init__(self, mode: str = "self_hosted", verbose: bool = False):
        """Initialize config validator.

        Args:
            mode: Execution mode (self_hosted or cloud)
            verbose: Enable verbose output
        """
        self.mode = mode
        self.verbose = verbose
        self.logger = get_logger()

    def validate(self, config_path: Path) -> ValidationResult:
        """Validate a job configuration file.

        Validates:
        - YAML syntax
        - JSON schema compliance
        - Connector references in registry
        - Mode restrictions (cloud vs self_hosted)
        - Asset definition existence and schema presence
        - Incremental configuration requirements

        Args:
            config_path: Path to job configuration YAML file

        Returns:
            ValidationResult with validation status and any errors/warnings
        """
        result = ValidationResult()

        # Step 1: Check file exists
        if not config_path.exists():
            result.add_error(
                code="FILE_NOT_FOUND",
                message=f"Configuration file not found: {config_path}",
            )
            return result

        # Step 2: Validate YAML syntax
        try:
            with open(config_path, "r") as f:
                config_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            result.add_error(
                code="YAML_SYNTAX",
                message=f"Invalid YAML syntax: {e}",
            )
            return result

        if config_data is None:
            result.add_error(
                code="EMPTY_FILE",
                message="Configuration file is empty",
            )
            return result

        result.info["file"] = str(config_path)

        # Step 3: Validate JSON schema
        try:
            JobConfig.validate_against_schema(config_data)
            if self.verbose:
                result.info["schema_validation"] = "passed"
        except ValueError as e:
            result.add_error(
                code="SCHEMA_INVALID",
                message=str(e),
            )
            # Continue validation to gather more errors
        except FileNotFoundError as e:
            result.add_warning(
                code="SCHEMA_NOT_FOUND",
                message=f"Schema file not found: {e}. Skipping schema validation.",
            )

        # Step 4: Load and validate JobConfig
        try:
            job_config = JobConfig(**config_data)
            result.info["tenant_id"] = job_config.tenant_id
        except Exception as e:
            result.add_error(
                code="CONFIG_INVALID",
                message=f"Invalid job configuration: {e}",
            )
            return result

        # Step 5: Validate connector references
        self._validate_connectors(job_config, result)

        # Step 6: Validate mode restrictions
        self._validate_mode_restrictions(job_config, result)

        # Step 7: Validate asset definition
        self._validate_asset(job_config, result)

        # Step 8: Validate incremental configuration
        self._validate_incremental(job_config, result)

        return result

    def _validate_connectors(
        self, job_config: JobConfig, result: ValidationResult
    ) -> None:
        """Validate connector references exist in registry.

        Args:
            job_config: Job configuration to validate
            result: Validation result to update
        """
        try:
            registry = ConnectorRegistry.from_default_paths()
        except (RegistryNotFoundError, RegistryLoadError) as e:
            result.add_warning(
                code="REGISTRY_UNAVAILABLE",
                message=f"Could not load connector registry: {e}. Skipping connector validation.",
            )
            return

        # Validate source connector
        try:
            source_config = job_config.get_source()
            source_type = source_config.type

            if not source_config.custom_reader:
                entry = registry.get_connector_entry(source_type, "source")
                if not entry:
                    available = registry.list_connectors("source")
                    result.add_error(
                        code="CONNECTOR_NOT_FOUND",
                        message=f"Source connector '{source_type}' not found in registry",
                        available_connectors=available[:10],  # Limit for readability
                    )
                else:
                    if self.verbose:
                        result.info["source_connector"] = {
                            "type": source_type,
                            "found": True,
                        }
        except Exception as e:
            result.add_error(
                code="SOURCE_RESOLUTION_ERROR",
                message=f"Failed to resolve source configuration: {e}",
            )

        # Validate target connector
        try:
            target_config = job_config.get_target()
            target_type = target_config.type

            if not target_config.custom_writer:
                entry = registry.get_connector_entry(target_type, "target")
                if not entry:
                    available = registry.list_connectors("target")
                    result.add_error(
                        code="CONNECTOR_NOT_FOUND",
                        message=f"Target connector '{target_type}' not found in registry",
                        available_connectors=available[:10],
                    )
                else:
                    if self.verbose:
                        result.info["target_connector"] = {
                            "type": target_type,
                            "found": True,
                        }
        except Exception as e:
            result.add_error(
                code="TARGET_RESOLUTION_ERROR",
                message=f"Failed to resolve target configuration: {e}",
            )

    def _validate_mode_restrictions(
        self, job_config: JobConfig, result: ValidationResult
    ) -> None:
        """Validate connector mode restrictions.

        Args:
            job_config: Job configuration to validate
            result: Validation result to update
        """
        if self.mode != "cloud":
            return  # No restrictions in self_hosted mode

        try:
            registry = ConnectorRegistry.from_default_paths()
            source_config = job_config.get_source()
            source_type = source_config.type

            if not source_config.custom_reader:
                entry = registry.get_connector_entry(source_type, "source")
                if entry:
                    cloud_blocked = entry.get("cloud_blocked", False)
                    if cloud_blocked:
                        result.add_error(
                            code="MODE_RESTRICTED",
                            message=f"Connector '{source_type}' is not allowed in cloud mode",
                            hint="Use self_hosted mode or choose a different connector",
                        )
        except Exception:
            pass  # Already handled in connector validation

    def _validate_asset(
        self, job_config: JobConfig, result: ValidationResult
    ) -> None:
        """Validate asset definition exists and has schema.

        Args:
            job_config: Job configuration to validate
            result: Validation result to update
        """
        try:
            asset_path = Path(job_config.get_asset_path())

            if not asset_path.exists():
                result.add_error(
                    code="ASSET_NOT_FOUND",
                    message=f"Asset definition file not found: {asset_path}",
                )
                return

            with open(asset_path, "r") as f:
                asset_data = yaml.safe_load(f)

            if not asset_data:
                result.add_error(
                    code="ASSET_EMPTY",
                    message="Asset definition file is empty",
                    path=str(asset_path),
                )
                return

            # Check required ODCS fields
            if "schema" not in asset_data:
                result.add_error(
                    code="ASSET_NO_SCHEMA",
                    message="Asset definition missing required 'schema' field",
                    path=str(asset_path),
                )
            elif not asset_data.get("schema"):
                result.add_error(
                    code="ASSET_EMPTY_SCHEMA",
                    message="Asset definition has empty 'schema' field",
                    path=str(asset_path),
                )
            else:
                if self.verbose:
                    result.info["asset"] = {
                        "path": str(asset_path),
                        "name": asset_data.get("name"),
                        "version": asset_data.get("version"),
                        "schema_field_count": len(asset_data.get("schema", [])),
                    }

        except Exception as e:
            result.add_error(
                code="ASSET_VALIDATION_ERROR",
                message=f"Failed to validate asset definition: {e}",
            )

    def _validate_incremental(
        self, job_config: JobConfig, result: ValidationResult
    ) -> None:
        """Validate incremental configuration requirements.

        Args:
            job_config: Job configuration to validate
            result: Validation result to update
        """
        try:
            source_config = job_config.get_source()

            if not source_config.incremental:
                return  # No incremental config, skip validation

            incremental = source_config.incremental
            strategy = incremental.get("strategy")

            if not strategy:
                result.add_error(
                    code="INCREMENTAL_NO_STRATEGY",
                    message="Incremental configuration requires 'strategy' field",
                    path="source.incremental.strategy",
                )
                return

            # Validate cursor_field for cursor-based strategies
            cursor_strategies = ["updated_at", "created", "updated_after"]
            if strategy in cursor_strategies and "cursor_field" not in incremental:
                result.add_error(
                    code="INCREMENTAL_NO_CURSOR",
                    message=f"Incremental strategy '{strategy}' requires 'cursor_field'",
                    path="source.incremental.cursor_field",
                )

            # Validate file strategies
            if strategy == "file_modified_time" and not source_config.files:
                result.add_error(
                    code="INCREMENTAL_NO_FILES",
                    message="Incremental strategy 'file_modified_time' requires 'files' configuration",
                    path="source.files",
                )

            if strategy == "spreadsheet_modified_time" and not source_config.sheets:
                result.add_error(
                    code="INCREMENTAL_NO_SHEETS",
                    message="Incremental strategy 'spreadsheet_modified_time' requires 'sheets' configuration",
                    path="source.sheets",
                )

            if self.verbose and strategy:
                result.info["incremental"] = {
                    "strategy": strategy,
                    "cursor_field": incremental.get("cursor_field"),
                }

        except Exception as e:
            result.add_warning(
                code="INCREMENTAL_VALIDATION_WARNING",
                message=f"Could not validate incremental configuration: {e}",
            )


class AssetValidator:
    """Validates asset definition YAML files."""

    def __init__(self, skip_schema: bool = False, verbose: bool = False):
        """Initialize asset validator.

        Args:
            skip_schema: Skip JSON schema validation
            verbose: Enable verbose output
        """
        self.skip_schema = skip_schema
        self.verbose = verbose
        self.logger = get_logger()

    def validate(self, asset_path: Path) -> ValidationResult:
        """Validate an asset definition file.

        Validates:
        - YAML syntax
        - JSON schema (dativo-odcs-3.0.2-extended.schema.json)
        - Required ODCS fields (name, version, schema)
        - Required Dativo fields (source_type, object, team.owner)
        - Governance requirements (oncall_rotation when monitoring enabled)
        - Schema field structure

        Args:
            asset_path: Path to asset definition YAML file

        Returns:
            ValidationResult with validation status and any errors/warnings
        """
        result = ValidationResult()

        # Step 1: Check file exists
        if not asset_path.exists():
            result.add_error(
                code="FILE_NOT_FOUND",
                message=f"Asset definition file not found: {asset_path}",
            )
            return result

        # Step 2: Validate YAML syntax
        try:
            with open(asset_path, "r") as f:
                asset_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            result.add_error(
                code="YAML_SYNTAX",
                message=f"Invalid YAML syntax: {e}",
            )
            return result

        if asset_data is None:
            result.add_error(
                code="EMPTY_FILE",
                message="Asset definition file is empty",
            )
            return result

        result.info["file"] = str(asset_path)

        # Step 3: Validate JSON schema (unless skipped)
        if not self.skip_schema:
            try:
                AssetDefinition.validate_against_schema(asset_data)
                if self.verbose:
                    result.info["schema_validation"] = "passed"
            except ValueError as e:
                result.add_error(
                    code="SCHEMA_INVALID",
                    message=str(e),
                )
                # Continue validation to gather more errors
            except FileNotFoundError as e:
                result.add_warning(
                    code="SCHEMA_NOT_FOUND",
                    message=f"Schema file not found: {e}. Skipping schema validation.",
                )

        # Step 4: Validate required ODCS fields
        self._validate_odcs_fields(asset_data, result)

        # Step 5: Validate required Dativo fields
        self._validate_dativo_fields(asset_data, result)

        # Step 6: Validate governance requirements
        self._validate_governance(asset_data, result)

        # Step 7: Validate schema field structure
        self._validate_schema_fields(asset_data, result)

        # Add info for verbose output
        if self.verbose and result.valid:
            result.info["name"] = asset_data.get("name")
            result.info["version"] = asset_data.get("version")
            result.info["source_type"] = asset_data.get("source_type")
            result.info["object"] = asset_data.get("object")

        return result

    def _validate_odcs_fields(
        self, asset_data: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate required ODCS fields.

        Args:
            asset_data: Asset definition data
            result: Validation result to update
        """
        required_fields = ["name", "version", "schema"]

        for field in required_fields:
            if field not in asset_data:
                result.add_error(
                    code="ODCS_MISSING_FIELD",
                    message=f"Required ODCS field missing: '{field}'",
                    path=field,
                )
            elif not asset_data.get(field):
                if field == "schema":
                    result.add_error(
                        code="ODCS_EMPTY_FIELD",
                        message=f"Required ODCS field is empty: '{field}'",
                        path=field,
                    )

    def _validate_dativo_fields(
        self, asset_data: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate required Dativo extension fields.

        Args:
            asset_data: Asset definition data
            result: Validation result to update
        """
        required_fields = ["source_type", "object"]

        for field in required_fields:
            if field not in asset_data:
                result.add_error(
                    code="DATIVO_MISSING_FIELD",
                    message=f"Required Dativo field missing: '{field}'",
                    path=field,
                )

        # Validate team.owner
        team = asset_data.get("team", {})
        if not team:
            result.add_error(
                code="DATIVO_MISSING_FIELD",
                message="Required field 'team' is missing",
                path="team",
            )
        elif not team.get("owner"):
            result.add_error(
                code="DATIVO_MISSING_FIELD",
                message="Required field 'team.owner' is missing",
                path="team.owner",
            )

    def _validate_governance(
        self, asset_data: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate governance requirements.

        Args:
            asset_data: Asset definition data
            result: Validation result to update
        """
        data_quality = asset_data.get("data_quality", {})
        if not data_quality:
            return

        monitoring = data_quality.get("monitoring", {})
        if not monitoring:
            return

        if monitoring.get("enabled") and not monitoring.get("oncall_rotation"):
            result.add_error(
                code="GOVERNANCE_ONCALL_REQUIRED",
                message="When monitoring.enabled is true, oncall_rotation is required",
                path="data_quality.monitoring.oncall_rotation",
            )

    def _validate_schema_fields(
        self, asset_data: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate schema field structure.

        Args:
            asset_data: Asset definition data
            result: Validation result to update
        """
        schema_fields = asset_data.get("schema", [])

        if not isinstance(schema_fields, list):
            result.add_error(
                code="SCHEMA_NOT_LIST",
                message="Schema field must be a list/array",
                path="schema",
            )
            return

        for idx, field in enumerate(schema_fields):
            if not isinstance(field, dict):
                result.add_error(
                    code="SCHEMA_FIELD_INVALID",
                    message=f"Schema field at index {idx} must be an object",
                    path=f"schema[{idx}]",
                )
                continue

            # Check required field attributes
            if "name" not in field:
                result.add_error(
                    code="SCHEMA_FIELD_NO_NAME",
                    message=f"Schema field at index {idx} missing 'name' attribute",
                    path=f"schema[{idx}].name",
                )

            if "type" not in field:
                result.add_error(
                    code="SCHEMA_FIELD_NO_TYPE",
                    message=f"Schema field at index {idx} missing 'type' attribute",
                    path=f"schema[{idx}].type",
                )


def validate_config_command(
    config_path: str,
    mode: str = "self_hosted",
    json_output: bool = False,
    verbose: bool = False,
) -> int:
    """Execute validate config command.

    Args:
        config_path: Path to job configuration YAML file
        mode: Execution mode (self_hosted or cloud)
        json_output: Output results in JSON format
        verbose: Enable verbose output

    Returns:
        Exit code (0=valid, 2=invalid)
    """
    # Record metric
    _record_validate_metric("config", None)

    validator = ConfigValidator(mode=mode, verbose=verbose)
    result = validator.validate(Path(config_path))

    # Record result metric
    _record_validate_metric("config", "success" if result.valid else "failure")

    # Format output
    _format_validation_output(
        result,
        "CONFIG",
        config_path,
        json_output=json_output,
        verbose=verbose,
    )

    return 0 if result.valid else 2


def validate_asset_command(
    asset_path: str,
    skip_schema: bool = False,
    json_output: bool = False,
    verbose: bool = False,
) -> int:
    """Execute validate asset command.

    Args:
        asset_path: Path to asset definition YAML file
        skip_schema: Skip JSON schema validation
        json_output: Output results in JSON format
        verbose: Enable verbose output

    Returns:
        Exit code (0=valid, 2=invalid)
    """
    # Record metric
    _record_validate_metric("asset", None)

    validator = AssetValidator(skip_schema=skip_schema, verbose=verbose)
    result = validator.validate(Path(asset_path))

    # Record result metric
    _record_validate_metric("asset", "success" if result.valid else "failure")

    # Format output
    _format_validation_output(
        result,
        "ASSET",
        asset_path,
        json_output=json_output,
        verbose=verbose,
    )

    return 0 if result.valid else 2


def _format_validation_output(
    result: ValidationResult,
    validation_type: str,
    file_path: str,
    json_output: bool = False,
    verbose: bool = False,
) -> None:
    """Format and print validation results.

    Args:
        result: Validation result
        validation_type: Type of validation (CONFIG or ASSET)
        file_path: Path to validated file
        json_output: Whether to output JSON
        verbose: Whether to include verbose details
    """
    if json_output:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        if result.valid:
            print(f"\n✓ {validation_type} VALIDATION: VALID")
            print(f"  File: {file_path}")
            print("\n  No issues found.")
        else:
            print(f"\n✗ {validation_type} VALIDATION: INVALID")
            print(f"  File: {file_path}")

            if result.errors:
                print(f"\n  Errors ({len(result.errors)}):")
                for error in result.errors:
                    print(f"    - [{error['code']}] {error['message']}")
                    if error.get("path"):
                        print(f"      Path: {error['path']}")

        if result.warnings:
            print(f"\n  Warnings ({len(result.warnings)}):")
            for warning in result.warnings:
                print(f"    - [{warning['code']}] {warning['message']}")

        if verbose and result.info:
            print("\n  Additional Info:")
            for key, value in result.info.items():
                if isinstance(value, dict):
                    print(f"    {key}:")
                    for k, v in value.items():
                        print(f"      {k}: {v}")
                else:
                    print(f"    {key}: {value}")

        print()


def _record_validate_metric(validate_type: str, result: Optional[str]) -> None:
    """Record validation metrics to Prometheus.

    Args:
        validate_type: Type of validation (config or asset)
        result: Result of validation (success, failure, or None for start)
    """
    if result:
        try:
            from .metrics import record_validate_metric

            record_validate_metric(validate_type, result)
        except ImportError:
            # Metrics module not available
            pass
        except Exception:
            # Don't fail validation due to metrics error
            pass
