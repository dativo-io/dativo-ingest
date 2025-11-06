"""Configuration models and schema validation for Dativo jobs."""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class SourceConfig(BaseModel):
    """Source connector configuration."""

    type: str
    description: Optional[str] = None
    credentials: Optional[Dict[str, Any]] = None
    objects: Optional[List[str]] = None
    files: Optional[List[Dict[str, Any]]] = None
    sheets: Optional[List[Dict[str, Any]]] = None
    tables: Optional[List[Dict[str, Any]]] = None
    incremental: Optional[Dict[str, Any]] = None
    rate_limits: Optional[Dict[str, Any]] = None
    engine: Optional[Dict[str, Any]] = None
    dsn: Optional[str] = None


class TargetConfig(BaseModel):
    """Target storage configuration."""

    type: str
    catalog: Optional[str] = None
    branch: Optional[str] = None
    warehouse: Optional[str] = None
    file_format: Optional[str] = None
    partitioning: Optional[List[str]] = None
    engine: Optional[Dict[str, Any]] = None


class LoggingConfig(BaseModel):
    """Logging configuration."""

    redaction: bool = False
    level: str = "INFO"


class JobConfig(BaseModel):
    """Complete job configuration model."""

    tenant_id: str
    environment: Optional[str] = None
    source: SourceConfig
    target: TargetConfig
    asset_definition: Optional[str] = None
    logging: Optional[LoggingConfig] = None

    @field_validator("asset_definition")
    @classmethod
    def validate_asset_definition_path(cls, v: Optional[str]) -> Optional[str]:
        """Validate asset definition path exists."""
        if v is None:
            return v
        path = Path(v)
        if not path.exists():
            raise ValueError(f"Asset definition file not found: {v}")
        if not path.is_file():
            raise ValueError(f"Asset definition path is not a file: {v}")
        return v

    def validate_schema_presence(self) -> None:
        """Validate that asset definition has a non-empty schema.

        Raises:
            SystemExit: Exit code 2 if validation fails
        """
        if not self.asset_definition:
            return  # Optional field, skip if not provided

        spec_path = Path(self.asset_definition)
        if not spec_path.exists():
            print(
                f"ERROR: Asset definition file not found: {self.asset_definition}",
                file=sys.stderr,
            )
            sys.exit(2)

        try:
            with open(spec_path, "r") as f:
                spec_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(
                f"ERROR: Failed to parse asset definition YAML: {self.asset_definition}\n"
                f"YAML Error: {e}",
                file=sys.stderr,
            )
            sys.exit(2)
        except Exception as e:
            print(
                f"ERROR: Failed to read asset definition: {self.asset_definition}\n"
                f"Error: {e}",
                file=sys.stderr,
            )
            sys.exit(2)

        # Check if asset field exists
        if not isinstance(spec_data, dict) or "asset" not in spec_data:
            print(
                f"ERROR: Asset definition missing 'asset' field: {self.asset_definition}",
                file=sys.stderr,
            )
            sys.exit(2)

        asset = spec_data["asset"]
        if not isinstance(asset, dict):
            print(
                f"ERROR: Asset definition 'asset' field must be an object: {self.asset_definition}",
                file=sys.stderr,
            )
            sys.exit(2)

        # Check if schema field exists
        if "schema" not in asset:
            print(
                f"ERROR: Asset definition missing 'schema' field: {self.asset_definition}",
                file=sys.stderr,
            )
            sys.exit(2)

        schema = asset["schema"]

        # Check if schema is an array
        if not isinstance(schema, list):
            print(
                f"ERROR: Asset definition 'schema' must be an array: {self.asset_definition}",
                file=sys.stderr,
            )
            sys.exit(2)

        # Check if schema has at least one column
        if len(schema) == 0:
            print(
                f"ERROR: Asset definition 'schema' must contain at least one column: {self.asset_definition}",
                file=sys.stderr,
            )
            sys.exit(2)

        # Validate each column has required fields
        for idx, column in enumerate(schema):
            if not isinstance(column, dict):
                print(
                    f"ERROR: Asset definition schema column {idx} must be an object: {self.asset_definition}",
                    file=sys.stderr,
                )
                sys.exit(2)
            if "name" not in column:
                print(
                    f"ERROR: Asset definition schema column {idx} missing 'name' field: {self.asset_definition}",
                    file=sys.stderr,
                )
                sys.exit(2)
            if "type" not in column:
                print(
                    f"ERROR: Asset definition schema column {idx} missing 'type' field: {self.asset_definition}",
                    file=sys.stderr,
                )
                sys.exit(2)

    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> "JobConfig":
        """Load job configuration from YAML file.

        Args:
            path: Path to YAML file

        Returns:
            JobConfig instance

        Raises:
            SystemExit: Exit code 2 if file cannot be loaded or parsed
        """
        path = Path(path)
        if not path.exists():
            print(f"ERROR: Config file not found: {path}", file=sys.stderr)
            sys.exit(2)

        try:
            with open(path, "r") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(
                f"ERROR: Failed to parse config YAML: {path}\nYAML Error: {e}",
                file=sys.stderr,
            )
            sys.exit(2)
        except Exception as e:
            print(
                f"ERROR: Failed to read config file: {path}\nError: {e}",
                file=sys.stderr,
            )
            sys.exit(2)

        if data is None:
            print(f"ERROR: Config file is empty: {path}", file=sys.stderr)
            sys.exit(2)

        # Resolve environment variables in asset_definition path
        if "asset_definition" in data and data["asset_definition"]:
            data["asset_definition"] = os.path.expandvars(data["asset_definition"])

        try:
            return cls(**data)
        except Exception as e:
            print(
                f"ERROR: Invalid job configuration: {path}\nValidation Error: {e}",
                file=sys.stderr,
            )
            sys.exit(2)


class ScheduleConfig(BaseModel):
    """Schedule configuration for orchestrated mode."""

    name: str
    config: str
    cron: str


class OrchestratorConfig(BaseModel):
    """Orchestrator configuration."""

    type: str = "dagster"
    schedules: List[ScheduleConfig]
    concurrency_per_tenant: int = Field(default=1, ge=1)


class RunnerConfig(BaseModel):
    """Runner configuration model."""

    mode: str = Field(default="orchestrated", pattern="^(orchestrated|oneshot)$")
    orchestrator: OrchestratorConfig

    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> "RunnerConfig":
        """Load runner configuration from YAML file.

        Args:
            path: Path to YAML file

        Returns:
            RunnerConfig instance

        Raises:
            SystemExit: Exit code 2 if file cannot be loaded or parsed
        """
        path = Path(path)
        if not path.exists():
            print(f"ERROR: Runner config file not found: {path}", file=sys.stderr)
            sys.exit(2)

        try:
            with open(path, "r") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(
                f"ERROR: Failed to parse runner config YAML: {path}\nYAML Error: {e}",
                file=sys.stderr,
            )
            sys.exit(2)
        except Exception as e:
            print(
                f"ERROR: Failed to read runner config file: {path}\nError: {e}",
                file=sys.stderr,
            )
            sys.exit(2)

        if data is None:
            print(f"ERROR: Runner config file is empty: {path}", file=sys.stderr)
            sys.exit(2)

        try:
            return cls(**data)
        except Exception as e:
            print(
                f"ERROR: Invalid runner configuration: {path}\nValidation Error: {e}",
                file=sys.stderr,
            )
            sys.exit(2)

