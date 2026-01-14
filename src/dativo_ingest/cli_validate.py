"""CLI validation commands for job configurations and asset definitions."""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .config import AssetDefinition, JobConfig
from .logging import get_logger, setup_logging
from .registry import ConnectorRegistry, RegistryLoadError, RegistryNotFoundError
from .validator import ConnectorValidator


class ValidationResult:
    """Result of a validation operation."""

    def __init__(self):
        self.valid: bool = True
        self.errors: List[Dict[str, Any]] = []
        self.warnings: List[Dict[str, Any]] = []
        self.info: List[Dict[str, Any]] = []

    def add_error(self, message: str, code: str, path: Optional[str] = None) -> None:
        """Add a validation error."""
        self.valid = False
        self.errors.append(
            {"message": message, "code": code, "path": path, "severity": "error"}
        )

    def add_warning(self, message: str, code: str, path: Optional[str] = None) -> None:
        """Add a validation warning."""
        self.warnings.append(
            {"message": message, "code": code, "path": path, "severity": "warning"}
        )

    def add_info(self, message: str, code: str, path: Optional[str] = None) -> None:
        """Add an info message."""
        self.info.append(
            {"message": message, "code": code, "path": path, "severity": "info"}
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "info": self.info,
            "summary": {
                "error_count": len(self.errors),
                "warning_count": len(self.warnings),
                "info_count": len(self.info),
            },
        }


class ConfigValidator:
    """Validates job configuration files."""

    def __init__(self, mode: str = "self_hosted"):
        """Initialize config validator.

        Args:
            mode: Execution mode for connector restrictions
        """
        self.mode = mode
        self.logger = get_logger()

    def validate(self, config_path: Path) -> ValidationResult:
        """Validate a job configuration file.

        Args:
            config_path: Path to job configuration YAML file

        Returns:
            ValidationResult with errors, warnings, and info
        """
        result = ValidationResult()

        # Step 1: Check file exists
        if not config_path.exists():
            result.add_error(
                f"Configuration file not found: {config_path}",
                "FILE_NOT_FOUND",
                str(config_path),
            )
            return result

        # Step 2: Validate YAML syntax
        try:
            with open(config_path, "r") as f:
                config_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            result.add_error(
                f"Invalid YAML syntax: {e}",
                "YAML_PARSE_ERROR",
                str(config_path),
            )
            return result

        if config_data is None:
            result.add_error(
                "Configuration file is empty",
                "EMPTY_CONFIG",
                str(config_path),
            )
            return result

        # Step 3: Validate against JSON schema
        try:
            JobConfig.validate_against_schema(config_data)
            result.add_info(
                "Job configuration schema validation passed",
                "SCHEMA_VALID",
            )
        except ValueError as e:
            result.add_error(
                f"Schema validation failed: {e}",
                "SCHEMA_VALIDATION_ERROR",
            )
        except FileNotFoundError as e:
            result.add_warning(
                f"Schema file not found, skipping schema validation: {e}",
                "SCHEMA_FILE_NOT_FOUND",
            )

        # Step 4: Validate connector references
        try:
            registry = ConnectorRegistry.from_default_paths()

            # Check source connector
            source_connector_path = config_data.get("source_connector_path")
            if source_connector_path:
                self._validate_connector_path(
                    result, source_connector_path, "source", registry
                )

            # Check target connector
            target_connector_path = config_data.get("target_connector_path")
            if target_connector_path:
                self._validate_connector_path(
                    result, target_connector_path, "target", registry
                )

        except RegistryNotFoundError as e:
            result.add_warning(
                f"Connector registry not found: {e}",
                "REGISTRY_NOT_FOUND",
            )
        except RegistryLoadError as e:
            result.add_warning(
                f"Failed to load connector registry: {e}",
                "REGISTRY_LOAD_ERROR",
            )

        # Step 5: Validate asset path
        asset_path = config_data.get("asset_path")
        if asset_path:
            self._validate_asset_path(result, asset_path)

        # Step 6: Try full config loading (Pydantic validation)
        try:
            job_config = JobConfig(**config_data)
            result.add_info(
                "Job configuration structure validation passed",
                "CONFIG_STRUCTURE_VALID",
            )

            # Step 7: Validate connector and mode restrictions
            try:
                validator = ConnectorValidator()
                validator.validate_job(job_config, mode=self.mode)
                result.add_info(
                    f"Connector validation passed for mode '{self.mode}'",
                    "CONNECTOR_VALIDATION_PASSED",
                )
            except SystemExit:
                # ConnectorValidator uses sys.exit on error
                result.add_error(
                    f"Connector validation failed for mode '{self.mode}'",
                    "CONNECTOR_VALIDATION_ERROR",
                )
            except Exception as e:
                result.add_error(
                    f"Connector validation error: {e}",
                    "CONNECTOR_VALIDATION_ERROR",
                )

        except Exception as e:
            result.add_error(
                f"Configuration structure validation failed: {e}",
                "CONFIG_STRUCTURE_ERROR",
            )

        return result

    def _validate_connector_path(
        self,
        result: ValidationResult,
        connector_path: str,
        role: str,
        registry: ConnectorRegistry,
    ) -> None:
        """Validate a connector path reference."""
        path = Path(connector_path)

        if not path.exists():
            result.add_error(
                f"{role.title()} connector file not found: {connector_path}",
                f"{role.upper()}_CONNECTOR_NOT_FOUND",
                connector_path,
            )
            return

        # Load connector recipe to check type
        try:
            with open(path, "r") as f:
                connector_data = yaml.safe_load(f)

            connector_type = connector_data.get("type")
            if connector_type:
                # Check if type exists in registry
                entry = registry.get_connector_entry(connector_type, role)
                if entry:
                    result.add_info(
                        f"{role.title()} connector '{connector_type}' found in registry",
                        f"{role.upper()}_CONNECTOR_REGISTERED",
                    )

                    # Check mode restrictions
                    if self.mode == "cloud" and entry.get("cloud_blocked", False):
                        result.add_error(
                            f"{role.title()} connector '{connector_type}' is blocked in cloud mode",
                            f"{role.upper()}_CONNECTOR_BLOCKED_IN_CLOUD",
                        )
                else:
                    result.add_warning(
                        f"{role.title()} connector type '{connector_type}' not found in registry",
                        f"{role.upper()}_CONNECTOR_NOT_REGISTERED",
                    )
        except Exception as e:
            result.add_warning(
                f"Failed to validate {role} connector recipe: {e}",
                f"{role.upper()}_CONNECTOR_LOAD_ERROR",
            )

    def _validate_asset_path(self, result: ValidationResult, asset_path: str) -> None:
        """Validate asset definition path."""
        path = Path(asset_path)
        if not path.exists():
            result.add_error(
                f"Asset definition file not found: {asset_path}",
                "ASSET_NOT_FOUND",
                asset_path,
            )
        else:
            result.add_info(
                f"Asset definition file exists: {asset_path}",
                "ASSET_FILE_EXISTS",
            )


class AssetValidator:
    """Validates asset definition files against ODCS schema."""

    def __init__(self):
        """Initialize asset validator."""
        self.logger = get_logger()

    def validate(self, asset_path: Path) -> ValidationResult:
        """Validate an asset definition file.

        Args:
            asset_path: Path to asset definition YAML file

        Returns:
            ValidationResult with errors, warnings, and info
        """
        result = ValidationResult()

        # Step 1: Check file exists
        if not asset_path.exists():
            result.add_error(
                f"Asset definition file not found: {asset_path}",
                "FILE_NOT_FOUND",
                str(asset_path),
            )
            return result

        # Step 2: Validate YAML syntax
        try:
            with open(asset_path, "r") as f:
                asset_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            result.add_error(
                f"Invalid YAML syntax: {e}",
                "YAML_PARSE_ERROR",
                str(asset_path),
            )
            return result

        if asset_data is None:
            result.add_error(
                "Asset definition file is empty",
                "EMPTY_ASSET",
                str(asset_path),
            )
            return result

        # Step 2.5: Validate that asset_data is a dictionary (not a list or scalar)
        if not isinstance(asset_data, dict):
            result.add_error(
                f"Asset definition must be a YAML mapping/dictionary, got {type(asset_data).__name__}",
                "INVALID_ASSET_TYPE",
                str(asset_path),
            )
            return result

        # Step 3: Validate required ODCS fields
        self._validate_odcs_required_fields(result, asset_data)

        # Step 4: Validate against extended JSON schema
        try:
            # Ensure $schema is present for validation
            if "$schema" not in asset_data:
                asset_data["$schema"] = (
                    "schemas/odcs/dativo-odcs-3.0.2-extended.schema.json"
                )

            AssetDefinition.validate_against_schema(asset_data)
            result.add_info(
                "Asset definition schema validation passed",
                "SCHEMA_VALID",
            )
        except ValueError as e:
            result.add_error(
                f"Schema validation failed: {e}",
                "SCHEMA_VALIDATION_ERROR",
            )
        except FileNotFoundError as e:
            result.add_warning(
                f"Schema file not found, skipping JSON schema validation: {e}",
                "SCHEMA_FILE_NOT_FOUND",
            )
        except Exception as e:
            # Handle jsonschema resolution errors (network issues, etc.)
            error_str = str(e)
            if (
                "RefResolutionError" in type(e).__name__
                or "RefResolutionError" in error_str
            ):
                result.add_warning(
                    f"Schema reference resolution failed (network/file issue): {e}",
                    "SCHEMA_RESOLUTION_ERROR",
                )
            else:
                result.add_warning(
                    f"Schema validation error: {e}",
                    "SCHEMA_VALIDATION_WARNING",
                )

        # Step 5: Validate Dativo extensions
        self._validate_dativo_extensions(result, asset_data)

        # Step 6: Try full asset loading (Pydantic validation)
        try:
            # Map $schema to schema_ref for Pydantic
            if "$schema" in asset_data:
                asset_data["schema_ref"] = asset_data.pop("$schema")

            asset = AssetDefinition(**asset_data)
            result.add_info(
                "Asset definition structure validation passed",
                "ASSET_STRUCTURE_VALID",
            )

            # Additional checks
            if asset.schema:
                result.add_info(
                    f"Schema defines {len(asset.schema)} field(s)",
                    "SCHEMA_FIELD_COUNT",
                )

            if asset.team and asset.team.owner:
                result.add_info(
                    f"Team owner: {asset.team.owner}",
                    "TEAM_OWNER_DEFINED",
                )

        except Exception as e:
            result.add_error(
                f"Asset definition structure validation failed: {e}",
                "ASSET_STRUCTURE_ERROR",
            )

        return result

    def _validate_odcs_required_fields(
        self, result: ValidationResult, asset_data: Dict[str, Any]
    ) -> None:
        """Validate required ODCS fields."""
        required_fields = ["name", "version", "schema", "team"]

        for field in required_fields:
            if field not in asset_data:
                result.add_error(
                    f"Required ODCS field missing: '{field}'",
                    f"MISSING_REQUIRED_FIELD_{field.upper()}",
                )
            elif asset_data[field] is None or (
                isinstance(asset_data[field], (list, dict)) and not asset_data[field]
            ):
                result.add_error(
                    f"Required ODCS field is empty: '{field}'",
                    f"EMPTY_REQUIRED_FIELD_{field.upper()}",
                )

        # Validate team.owner specifically
        team = asset_data.get("team", {})
        if isinstance(team, dict) and not team.get("owner"):
            result.add_error(
                "Required field 'team.owner' is missing or empty",
                "MISSING_TEAM_OWNER",
            )

    def _validate_dativo_extensions(
        self, result: ValidationResult, asset_data: Dict[str, Any]
    ) -> None:
        """Validate Dativo-specific extensions."""
        required_extensions = ["source_type", "object"]

        for field in required_extensions:
            if field not in asset_data:
                result.add_error(
                    f"Required Dativo extension field missing: '{field}'",
                    f"MISSING_DATIVO_EXTENSION_{field.upper()}",
                )
            elif not asset_data[field]:
                result.add_error(
                    f"Required Dativo extension field is empty: '{field}'",
                    f"EMPTY_DATIVO_EXTENSION_{field.upper()}",
                )

        # Optional extensions info
        if asset_data.get("finops"):
            result.add_info(
                "FinOps metadata configured",
                "FINOPS_CONFIGURED",
            )

        if asset_data.get("compliance"):
            result.add_info(
                "Compliance metadata configured",
                "COMPLIANCE_CONFIGURED",
            )

        if asset_data.get("data_quality"):
            result.add_info(
                "Data quality configuration present",
                "DATA_QUALITY_CONFIGURED",
            )


def validate_config_command(
    path: str,
    mode: str = "self_hosted",
    json_output: bool = False,
    verbose: bool = False,
) -> int:
    """Validate job configuration command implementation.

    Args:
        path: Path to job configuration YAML file
        mode: Execution mode for connector restrictions
        json_output: Output results in JSON format
        verbose: Show verbose output

    Returns:
        Exit code (0=valid, 2=invalid)
    """
    config_path = Path(path)
    validator = ConfigValidator(mode=mode)
    result = validator.validate(config_path)

    _output_result(result, config_path, "Job Configuration", json_output, verbose)

    return 0 if result.valid else 2


def validate_asset_command(
    path: str,
    json_output: bool = False,
    verbose: bool = False,
) -> int:
    """Validate asset definition command implementation.

    Args:
        path: Path to asset definition YAML file
        json_output: Output results in JSON format
        verbose: Show verbose output

    Returns:
        Exit code (0=valid, 2=invalid)
    """
    asset_path = Path(path)
    validator = AssetValidator()
    result = validator.validate(asset_path)

    _output_result(result, asset_path, "Asset Definition", json_output, verbose)

    return 0 if result.valid else 2


def _output_result(
    result: ValidationResult,
    path: Path,
    resource_type: str,
    json_output: bool,
    verbose: bool,
) -> None:
    """Output validation result."""
    if json_output:
        output = result.to_dict()
        output["path"] = str(path)
        output["resource_type"] = resource_type
        print(json.dumps(output, indent=2))
    else:
        print("\n" + "=" * 60)
        print(f"{resource_type} Validation Results")
        print("=" * 60)
        print(f"\nFile: {path}")

        # Status
        status = "✅ VALID" if result.valid else "❌ INVALID"
        print(f"Status: {status}")

        # Summary
        print(
            f"\nSummary: {len(result.errors)} error(s), {len(result.warnings)} warning(s)"
        )

        # Errors
        if result.errors:
            print("\n❌ Errors:")
            for error in result.errors:
                print(f"  - [{error['code']}] {error['message']}")
                if error.get("path"):
                    print(f"    Path: {error['path']}")

        # Warnings
        if result.warnings:
            print("\n⚠️  Warnings:")
            for warning in result.warnings:
                print(f"  - [{warning['code']}] {warning['message']}")
                if warning.get("path"):
                    print(f"    Path: {warning['path']}")

        # Info (only in verbose mode)
        if verbose and result.info:
            print("\nℹ️  Info:")
            for info in result.info:
                print(f"  - [{info['code']}] {info['message']}")

        print("\n" + "=" * 60)
