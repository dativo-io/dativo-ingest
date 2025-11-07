"""Configuration models and schema validation for Dativo jobs."""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class SourceConnectorRecipe(BaseModel):
    """Source connector recipe - tenant-agnostic reusable configuration."""

    name: str
    type: str
    description: Optional[str] = None
    default_engine: Dict[str, Any]
    credentials: Dict[str, Any]
    incremental: Optional[Dict[str, Any]] = None
    rate_limits: Optional[Dict[str, Any]] = None
    connection_template: Optional[Dict[str, Any]] = None

    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> "SourceConnectorRecipe":
        """Load source connector recipe from YAML file."""
        path = Path(path)
        if not path.exists():
            raise ValueError(f"Source connector recipe not found: {path}")

        with open(path, "r") as f:
            data = yaml.safe_load(f)

        return cls(**data)


class TargetConnectorRecipe(BaseModel):
    """Target connector recipe - tenant-agnostic reusable configuration."""

    name: str
    type: str
    description: Optional[str] = None
    default_engine: Dict[str, Any]
    connection_template: Dict[str, Any]
    catalog: Optional[str] = None
    file_format: Optional[str] = None
    partitioning_default: Optional[List[str]] = None

    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> "TargetConnectorRecipe":
        """Load target connector recipe from YAML file."""
        path = Path(path)
        if not path.exists():
            raise ValueError(f"Target connector recipe not found: {path}")

        with open(path, "r") as f:
            data = yaml.safe_load(f)

        return cls(**data)


class AssetDefinition(BaseModel):
    """Asset definition - schema and governance metadata."""

    name: str
    source_type: str
    object: str
    version: str
    schema: List[Dict[str, Any]]
    governance: Optional[Dict[str, Any]] = None
    target: Optional[Dict[str, Any]] = None

    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> "AssetDefinition":
        """Load asset definition from YAML file."""
        path = Path(path)
        if not path.exists():
            raise ValueError(f"Asset definition not found: {path}")

        with open(path, "r") as f:
            data = yaml.safe_load(f)

        if "asset" not in data:
            raise ValueError(f"Asset definition missing 'asset' field: {path}")

        return cls(**data["asset"])


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
    connection: Optional[Dict[str, Any]] = None  # For database connections


class TargetConfig(BaseModel):
    """Target storage configuration."""

    type: str
    catalog: Optional[str] = None
    branch: Optional[str] = None
    warehouse: Optional[str] = None
    file_format: Optional[str] = None
    partitioning: Optional[List[str]] = None
    engine: Optional[Dict[str, Any]] = None
    connection: Optional[Dict[str, Any]] = None  # For storage connection details


class LoggingConfig(BaseModel):
    """Logging configuration."""

    redaction: bool = False
    level: str = "INFO"


class JobConfig(BaseModel):
    """Complete job configuration model - new architecture only."""

    tenant_id: str
    environment: Optional[str] = None
    
    # Connector recipes (required)
    source_connector: Optional[str] = None  # Connector name
    source_connector_path: str  # Path to source connector recipe
    target_connector: Optional[str] = None  # Connector name
    target_connector_path: str  # Path to target connector recipe
    asset: Optional[str] = None  # Asset name
    asset_path: str  # Path to asset definition
    source_overrides: Optional[Dict[str, Any]] = None  # Tenant-specific overrides
    target_overrides: Optional[Dict[str, Any]] = None  # Tenant-specific overrides
    
    logging: Optional[LoggingConfig] = None

    @model_validator(mode="after")
    def validate_source_target(self) -> "JobConfig":
        """Validate that all required connector paths are provided."""
        if not self.source_connector_path:
            raise ValueError("source_connector_path is required")
        if not self.target_connector_path:
            raise ValueError("target_connector_path is required")
        if not self.asset_path:
            raise ValueError("asset_path is required")
        return self

    def _resolve_source_recipe(self) -> SourceConnectorRecipe:
        """Resolve source connector recipe."""
        if self.source_connector_path is None:
            raise ValueError("Source connector path not provided")
        
        path = Path(os.path.expandvars(self.source_connector_path))
        return SourceConnectorRecipe.from_yaml(path)

    def _resolve_target_recipe(self) -> TargetConnectorRecipe:
        """Resolve target connector recipe."""
        if self.target_connector_path is None:
            raise ValueError("Target connector path not provided")
        
        path = Path(os.path.expandvars(self.target_connector_path))
        return TargetConnectorRecipe.from_yaml(path)

    def _resolve_asset(self) -> AssetDefinition:
        """Resolve asset definition."""
        if self.asset_path is None:
            raise ValueError("Asset path not provided")
        
        path = Path(os.path.expandvars(self.asset_path))
        return AssetDefinition.from_yaml(path)

    def _merge_source_with_overrides(self, recipe: SourceConnectorRecipe) -> SourceConfig:
        """Merge source connector recipe with job overrides."""
        source_data = {
            "type": recipe.type,
            "description": recipe.description,
            "engine": recipe.default_engine,
            "credentials": recipe.credentials,
            "incremental": recipe.incremental,
            "rate_limits": recipe.rate_limits,
        }
        
        # Apply overrides
        if self.source_overrides:
            source_data.update(self.source_overrides)
            # Deep merge for nested dicts
            if "incremental" in self.source_overrides and source_data.get("incremental"):
                source_data["incremental"].update(self.source_overrides["incremental"])
        
        # Add tenant-specific state_path if incremental is present
        if source_data.get("incremental") and "state_path" not in source_data.get("incremental", {}):
            if self.tenant_id:
                # Determine object name from overrides
                object_name = "default"
                if self.source_overrides:
                    if self.source_overrides.get("objects"):
                        object_name = self.source_overrides["objects"][0]
                    elif self.source_overrides.get("files") and len(self.source_overrides["files"]) > 0:
                        object_name = self.source_overrides["files"][0].get("object", "default")
                    elif self.source_overrides.get("tables") and len(self.source_overrides["tables"]) > 0:
                        object_name = self.source_overrides["tables"][0].get("object", "default")
                
                source_data["incremental"]["state_path"] = (
                    f"/state/{self.tenant_id}/{recipe.type}.{object_name}.state.json"
                )
        
        return SourceConfig(**source_data)

    def _merge_target_with_overrides(self, recipe: TargetConnectorRecipe) -> TargetConfig:
        """Merge target connector recipe with job overrides."""
        target_data = {
            "type": recipe.type,
            "catalog": recipe.catalog,
            "file_format": recipe.file_format or (self.target_overrides.get("file_format") if self.target_overrides else None),
            "partitioning": recipe.partitioning_default or (self.target_overrides.get("partitioning") if self.target_overrides else None),
            "engine": recipe.default_engine,
        }
        
        # Apply connection template and overrides
        if recipe.connection_template:
            connection = recipe.connection_template.copy()
            if self.target_overrides and "connection" in self.target_overrides:
                # Deep merge connection
                for key, value in self.target_overrides["connection"].items():
                    if isinstance(value, dict) and key in connection:
                        connection[key].update(value)
                    else:
                        connection[key] = value
            target_data["connection"] = connection
        
        # Apply other overrides
        if self.target_overrides:
            for key, value in self.target_overrides.items():
                if key != "connection":
                    target_data[key] = value
        
        return TargetConfig(**target_data)

    def _resolve_source(self) -> SourceConfig:
        """Resolve source config from connector recipe."""
        recipe = self._resolve_source_recipe()
        return self._merge_source_with_overrides(recipe)

    def _resolve_target(self) -> TargetConfig:
        """Resolve target config from connector recipe."""
        recipe = self._resolve_target_recipe()
        return self._merge_target_with_overrides(recipe)

    def get_source(self) -> SourceConfig:
        """Get resolved source config."""
        return self._resolve_source()

    def get_target(self) -> TargetConfig:
        """Get resolved target config."""
        return self._resolve_target()

    def get_asset_path(self) -> str:
        """Get asset definition path."""
        return os.path.expandvars(self.asset_path)

    @field_validator("asset_path")
    @classmethod
    def validate_asset_path(cls, v: str) -> str:
        """Validate asset definition path exists."""
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
        asset_path = self.get_asset_path()
        spec_path = Path(asset_path)
        if not spec_path.exists():
            print(
                f"ERROR: Asset definition file not found: {asset_path}",
                file=sys.stderr,
            )
            sys.exit(2)

        try:
            with open(spec_path, "r") as f:
                spec_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(
                f"ERROR: Failed to parse asset definition YAML: {asset_path}\n"
                f"YAML Error: {e}",
                file=sys.stderr,
            )
            sys.exit(2)
        except Exception as e:
            print(
                f"ERROR: Failed to read asset definition: {asset_path}\n"
                f"Error: {e}",
                file=sys.stderr,
            )
            sys.exit(2)

        # Check if asset field exists
        if not isinstance(spec_data, dict) or "asset" not in spec_data:
            print(
                f"ERROR: Asset definition missing 'asset' field: {asset_path}",
                file=sys.stderr,
            )
            sys.exit(2)

        asset = spec_data["asset"]
        if not isinstance(asset, dict):
            print(
                f"ERROR: Asset definition 'asset' field must be an object: {asset_path}",
                file=sys.stderr,
            )
            sys.exit(2)

        # Check if schema field exists
        if "schema" not in asset:
            print(
                f"ERROR: Asset definition missing 'schema' field: {asset_path}",
                file=sys.stderr,
            )
            sys.exit(2)

        schema = asset["schema"]

        # Check if schema is an array
        if not isinstance(schema, list):
            print(
                f"ERROR: Asset definition 'schema' must be an array: {asset_path}",
                file=sys.stderr,
            )
            sys.exit(2)

        # Check if schema has at least one column
        if len(schema) == 0:
            print(
                f"ERROR: Asset definition 'schema' must contain at least one column: {asset_path}",
                file=sys.stderr,
            )
            sys.exit(2)

        # Validate each column has required fields
        for idx, column in enumerate(schema):
            if not isinstance(column, dict):
                print(
                    f"ERROR: Asset definition schema column {idx} must be an object: {asset_path}",
                    file=sys.stderr,
                )
                sys.exit(2)
            if "name" not in column:
                print(
                    f"ERROR: Asset definition schema column {idx} missing 'name' field: {asset_path}",
                    file=sys.stderr,
                )
                sys.exit(2)
            if "type" not in column:
                print(
                    f"ERROR: Asset definition schema column {idx} missing 'type' field: {asset_path}",
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

        # Resolve environment variables in paths
        if "asset_path" in data and data["asset_path"]:
            data["asset_path"] = os.path.expandvars(data["asset_path"])
        if "source_connector_path" in data and data["source_connector_path"]:
            data["source_connector_path"] = os.path.expandvars(data["source_connector_path"])
        if "target_connector_path" in data and data["target_connector_path"]:
            data["target_connector_path"] = os.path.expandvars(data["target_connector_path"])

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

