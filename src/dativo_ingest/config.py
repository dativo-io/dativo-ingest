"""Configuration models and schema validation for Dativo jobs."""

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import jsonschema
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ConnectorRecipe(BaseModel):
    """Unified connector recipe - supports both source and target roles."""

    name: str
    type: str
    roles: List[str] = Field(
        default_factory=list
    )  # [source], [target], or [source, target]
    description: Optional[str] = None
    default_engine: Dict[str, Any]
    credentials: Optional[Dict[str, Any]] = None  # Optional for target-only connectors
    incremental: Optional[Dict[str, Any]] = None  # Optional for target-only connectors
    rate_limits: Optional[Dict[str, Any]] = None  # Optional for target-only connectors
    connection_template: Optional[Dict[str, Any]] = None
    catalog: Optional[str] = None  # Optional for source-only connectors
    file_format: Optional[str] = None  # Optional for source-only connectors
    partitioning_default: Optional[List[str]] = (
        None  # Optional for source-only connectors
    )

    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> "ConnectorRecipe":
        """Load connector recipe from YAML file."""
        path = Path(path)
        if not path.exists():
            raise ValueError(f"Connector recipe not found: {path}")

        with open(path, "r") as f:
            data = yaml.safe_load(f)

        return cls(**data)

    def supports_role(self, role: str) -> bool:
        """Check if connector supports the specified role.

        Args:
            role: Role to check ('source' or 'target')

        Returns:
            True if connector supports the role
        """
        return role in self.roles


class SourceConnectorRecipe(BaseModel):
    """Source connector recipe - tenant-agnostic reusable configuration.

    DEPRECATED: Use ConnectorRecipe instead. Kept for backward compatibility.
    """

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
    """Target connector recipe - tenant-agnostic reusable configuration.

    DEPRECATED: Use ConnectorRecipe instead. Kept for backward compatibility.
    """

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


class DescriptionModel(BaseModel):
    """Description model for ODCS data contracts."""

    purpose: Optional[str] = None
    limitations: Optional[str] = None
    usage: Optional[str] = None


class DataQualityMonitoringModel(BaseModel):
    """Data quality monitoring configuration."""

    enabled: bool
    oncall_rotation: Optional[str] = None


class DataQualityAlertsModel(BaseModel):
    """Data quality alerting configuration."""

    channels: Optional[List[str]] = None
    thresholds: Optional[Dict[str, Any]] = None


class DataQualityModel(BaseModel):
    """Data quality configuration."""

    expectations: Optional[List[Dict[str, Any]]] = None
    monitoring: Optional[DataQualityMonitoringModel] = None
    alerts: Optional[DataQualityAlertsModel] = None


class TeamRoleModel(BaseModel):
    """Team role definition."""

    name: Optional[str] = None
    email: Optional[str] = None
    responsibility: Optional[str] = None


class TeamModel(BaseModel):
    """Team ownership and roles."""

    owner: str
    roles: Optional[List[TeamRoleModel]] = None


class ComplianceSecurityModel(BaseModel):
    """Security configuration for compliance."""

    access_control: Optional[str] = None
    encryption_required: Optional[bool] = None


class ComplianceModel(BaseModel):
    """Compliance and regulatory information."""

    classification: Optional[List[str]] = None
    regulations: Optional[List[str]] = None
    retention_days: Optional[int] = None
    security: Optional[ComplianceSecurityModel] = None
    user_consent_required: Optional[bool] = None


class FinOpsModel(BaseModel):
    """FinOps and cost attribution metadata."""

    cost_center: Optional[str] = None
    business_tags: Optional[List[str]] = None
    project: Optional[str] = None
    environment: Optional[str] = None


class ChangeManagementModel(BaseModel):
    """Change management configuration."""

    policy: Optional[str] = None
    approval_required: Optional[bool] = None
    notification_channels: Optional[List[str]] = None
    version_history: Optional[bool] = None


class AssetDefinition(BaseModel):
    """Asset definition - ODCS v3.0.2 aligned with dativo extensions."""

    model_config = ConfigDict(populate_by_name=True)

    # ODCS top-level fields
    schema_ref: Optional[str] = Field(None, alias="$schema")
    apiVersion: str = "v3.0.2"
    kind: str = "DataContract"
    id: Optional[str] = None
    name: str
    version: str
    status: str = "active"
    domain: Optional[str] = None
    dataProduct: Optional[str] = None
    tenant: Optional[str] = None
    description: Optional[DescriptionModel] = None
    tags: Optional[List[str]] = None

    # Dativo extensions (required)
    source_type: str
    object: str
    target: Optional[Dict[str, Any]] = None

    # ODCS sections
    schema: List[Dict[str, Any]]  # Schema fields array
    data_quality: Optional[DataQualityModel] = None
    team: TeamModel
    compliance: Optional[ComplianceModel] = None
    change_management: Optional[ChangeManagementModel] = None

    # Dativo FinOps extension
    finops: Optional[FinOpsModel] = None

    @model_validator(mode="after")
    def validate_governance(self) -> "AssetDefinition":
        """Validate governance requirements."""
        # Team owner is required
        if not self.team or not self.team.owner:
            raise ValueError("team.owner is required (strong ownership requirement)")

        # If monitoring is enabled, oncall_rotation is required
        if (
            self.data_quality
            and self.data_quality.monitoring
            and self.data_quality.monitoring.enabled
            and not self.data_quality.monitoring.oncall_rotation
        ):
            raise ValueError(
                "data_quality.monitoring.oncall_rotation is required when monitoring.enabled is true"
            )

        return self

    @classmethod
    def _migrate_old_format(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate old nested format to new ODCS flat format."""
        if "asset" in data:
            asset_data = data["asset"].copy()

            # Generate ID if not present
            if "id" not in asset_data:
                asset_data["id"] = str(uuid.uuid4())

            # Set ODCS fields
            asset_data.setdefault("apiVersion", "v3.0.2")
            asset_data.setdefault("kind", "DataContract")
            asset_data.setdefault("status", "active")

            # Migrate governance to team
            if "governance" in asset_data:
                governance = asset_data.pop("governance")
                if "owner" in governance:
                    asset_data["team"] = {"owner": governance["owner"]}
                    if "tags" in governance:
                        asset_data.setdefault("tags", governance.get("tags", []))

                # Migrate classification and retention_days to compliance
                if "classification" in governance or "retention_days" in governance:
                    compliance = {}
                    if "classification" in governance:
                        compliance["classification"] = governance["classification"]
                    if "retention_days" in governance:
                        compliance["retention_days"] = governance["retention_days"]
                    if compliance:
                        asset_data["compliance"] = compliance

            # Set schema reference
            asset_data.setdefault(
                "$schema", "schemas/odcs/dativo-odcs-3.0.2-extended.schema.json"
            )

            return asset_data
        return data

    @classmethod
    def validate_against_schema(
        cls, data: Dict[str, Any], schema_path: Optional[Path] = None
    ) -> None:
        """Validate asset definition against JSON schema.

        Args:
            data: Asset definition data dictionary
            schema_path: Optional path to extended schema file

        Raises:
            jsonschema.ValidationError: If validation fails
        """
        if schema_path is None:
            # Default to extended schema in schemas/odcs/
            schema_path = (
                Path(__file__).parent.parent.parent
                / "schemas"
                / "odcs"
                / "dativo-odcs-3.0.2-extended.schema.json"
            )

        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        with open(schema_path, "r") as f:
            schema = json.load(f)

        # Create resolver for relative $refs
        resolver = jsonschema.RefResolver(
            base_uri=f"file://{schema_path.parent}/",
            referrer=schema,
        )

        try:
            jsonschema.validate(instance=data, schema=schema, resolver=resolver)
        except jsonschema.ValidationError as e:
            raise ValueError(f"Schema validation failed: {e.message}") from e

    @classmethod
    def from_yaml(
        cls, path: Union[str, Path], validate_schema: bool = False
    ) -> "AssetDefinition":
        """Load asset definition from YAML file.

        Args:
            path: Path to YAML file
            validate_schema: Whether to validate against JSON schema (default: False)

        Returns:
            AssetDefinition instance
        """
        path = Path(path)
        if not path.exists():
            raise ValueError(f"Asset definition not found: {path}")

        with open(path, "r") as f:
            data = yaml.safe_load(f)

        if data is None:
            raise ValueError(f"Asset definition file is empty: {path}")

        # Support both old nested format and new flat ODCS format
        if "asset" in data:
            # Old format - migrate to new format
            data = cls._migrate_old_format(data)
        else:
            # New format - ensure required fields
            if "id" not in data:
                data["id"] = str(uuid.uuid4())
            if "$schema" not in data:
                data["$schema"] = "schemas/odcs/dativo-odcs-3.0.2-extended.schema.json"

        # Map $schema to schema_ref for Pydantic (since $schema is not a valid Python identifier)
        if "$schema" in data:
            data["schema_ref"] = data.pop("$schema")

        # Validate against JSON schema if requested
        if validate_schema:
            # Restore $schema for validation
            validation_data = data.copy()
            if "schema_ref" in validation_data:
                validation_data["$schema"] = validation_data.pop("schema_ref")
            cls.validate_against_schema(validation_data)

        return cls(**data)


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
    custom_reader: Optional[str] = (
        None  # Path to custom reader class (format: "path/to/module.py:ClassName")
    )


class TargetConfig(BaseModel):
    """Target storage configuration."""

    type: str
    catalog: Optional[str] = None
    branch: Optional[str] = None  # Defaults to tenant_id if not provided
    warehouse: Optional[str] = None
    file_format: Optional[str] = None
    partitioning: Optional[List[str]] = None
    engine: Optional[Dict[str, Any]] = None
    connection: Optional[Dict[str, Any]] = None  # For storage connection details
    markdown_kv_storage: Optional[Dict[str, Any]] = (
        None  # Markdown-KV storage configuration
    )
    parquet_target_size_mb: Optional[int] = (
        None  # Target Parquet file size in MB (default: 128-200 MB range)
    )
    custom_writer: Optional[str] = (
        None  # Path to custom writer class (format: "path/to/module.py:ClassName")
    )

    @model_validator(mode="after")
    def validate_markdown_kv_storage(self) -> "TargetConfig":
        """Validate markdown_kv_storage configuration."""
        if self.markdown_kv_storage:
            mode = self.markdown_kv_storage.get("mode")
            if mode not in ["string", "raw_file", "structured"]:
                raise ValueError(
                    f"markdown_kv_storage.mode must be one of: 'string', 'raw_file', 'structured'. Got: {mode}"
                )

            if mode == "structured":
                pattern = self.markdown_kv_storage.get("structured_pattern")
                if pattern not in ["row_per_kv", "document_level", "hybrid"]:
                    raise ValueError(
                        f"markdown_kv_storage.structured_pattern must be one of: 'row_per_kv', 'document_level', 'hybrid'. Got: {pattern}"
                    )

            if mode == "raw_file":
                file_extension = self.markdown_kv_storage.get("file_extension", ".mdkv")
                if file_extension not in [".md", ".mdkv"]:
                    raise ValueError(
                        f"markdown_kv_storage.file_extension must be '.md' or '.mdkv'. Got: {file_extension}"
                    )

        return self


class LoggingConfig(BaseModel):
    """Logging configuration."""

    redaction: bool = False
    level: str = "INFO"


class RetryConfig(BaseModel):
    """Retry configuration for transient failures."""

    max_retries: int = 3
    initial_delay_seconds: Optional[int] = (
        None  # Initial delay in seconds (defaults to retry_delay_seconds for backward compat)
    )
    max_delay_seconds: int = 300
    backoff_multiplier: float = 2.0
    retryable_exit_codes: List[int] = Field(
        default=[1, 2]
    )  # Exit codes that should trigger retries
    retryable_error_patterns: Optional[List[str]] = (
        None  # Regex patterns for error messages
    )
    retry_delay_seconds: Optional[int] = 5  # Deprecated: use initial_delay_seconds
    retryable_errors: Optional[List[str]] = (
        None  # List of error types to retry (deprecated, use retryable_error_patterns)
    )

    @model_validator(mode="after")
    def set_initial_delay(self) -> "RetryConfig":
        """Set initial_delay_seconds from retry_delay_seconds if not provided (backward compat)."""
        if self.initial_delay_seconds is None:
            self.initial_delay_seconds = self.retry_delay_seconds or 5
        return self


class InfrastructureConfig(BaseModel):
    """Infrastructure configuration for external Terraform-provisioned resources.

    This block describes the runtime environment and metadata that must flow
    into Terraform modules for cloud-agnostic deployment (AWS/GCP) via Dagster.
    Enables comprehensive tag propagation for cost allocation, compliance, and
    resource traceability.
    """

    # Cloud provider
    provider: str = Field(
        ..., description="Cloud provider: 'aws' or 'gcp'"
    )  # Required: aws or gcp

    # Runtime environment metadata
    runtime: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Runtime environment metadata (e.g., compute type, memory, vCPU)",
    )
    compute_type: Optional[str] = Field(
        default=None, description="Compute instance type (e.g., 'fargate', 'ec2', 'cloud-run')"
    )
    memory_mb: Optional[int] = Field(
        default=None, description="Memory allocation in MB"
    )
    vcpu: Optional[float] = Field(
        default=None, description="Virtual CPU allocation"
    )

    # Resource references (for Terraform module inputs)
    resource_refs: Optional[Dict[str, str]] = Field(
        default=None,
        description="References to Terraform-provisioned resources (e.g., ECS task definition ARN, Cloud Run service name)",
    )

    # Tags for Terraform propagation (merged with job/asset tags)
    tags: Optional[Dict[str, str]] = Field(
        default=None,
        description="Additional tags to propagate to Terraform-provisioned resources",
    )

    # Terraform module configuration
    terraform_module: Optional[str] = Field(
        default=None,
        description="Terraform module path or reference (e.g., 'modules/dativo-job')",
    )
    terraform_vars: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional Terraform variables to pass to the module",
    )

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        """Validate cloud provider."""
        if v.lower() not in ["aws", "gcp"]:
            raise ValueError(f"provider must be 'aws' or 'gcp', got '{v}'")
        return v.lower()


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

    # Source and target configurations (flat structure, merged with recipes)
    source: Optional[Dict[str, Any]] = None  # Source configuration
    target: Optional[Dict[str, Any]] = None  # Target configuration

    # Metadata overrides for tag propagation
    classification_overrides: Optional[Dict[str, str]] = (
        None  # Field-level classification overrides
    )
    finops: Optional[Dict[str, Any]] = (
        None  # FinOps metadata (cost_center, business_tags, etc.)
    )
    governance_overrides: Optional[Dict[str, Any]] = (
        None  # Governance metadata overrides
    )

    # Execution configuration
    schema_validation_mode: str = "strict"  # 'strict' or 'warn'
    retry_config: Optional[RetryConfig] = None

    logging: Optional[LoggingConfig] = None

    # Infrastructure configuration (optional - for external Terraform-provisioned resources)
    infrastructure: Optional[InfrastructureConfig] = Field(
        default=None,
        description="Infrastructure configuration for cloud-agnostic deployment via Terraform",
    )

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

    def _resolve_source_recipe(self) -> Union[ConnectorRecipe, SourceConnectorRecipe]:
        """Resolve source connector recipe (supports unified and legacy formats)."""
        if self.source_connector_path is None:
            raise ValueError("Source connector path not provided")

        path = Path(os.path.expandvars(self.source_connector_path))

        # Try unified format first
        try:
            recipe = ConnectorRecipe.from_yaml(path)
            if recipe.supports_role("source"):
                return recipe
            raise ValueError(
                f"Connector '{recipe.name}' does not support source role. Supported roles: {recipe.roles}"
            )
        except (ValueError, KeyError, AttributeError) as e:
            # Fall back to legacy SourceConnectorRecipe format
            try:
                return SourceConnectorRecipe.from_yaml(path)
            except Exception:
                # Re-raise original error if both fail
                raise ValueError(f"Failed to load source connector: {e}")

    def _resolve_target_recipe(self) -> Union[ConnectorRecipe, TargetConnectorRecipe]:
        """Resolve target connector recipe (supports unified and legacy formats)."""
        if self.target_connector_path is None:
            raise ValueError("Target connector path not provided")

        path = Path(os.path.expandvars(self.target_connector_path))

        # Try unified format first
        try:
            recipe = ConnectorRecipe.from_yaml(path)
            if recipe.supports_role("target"):
                return recipe
            raise ValueError(
                f"Connector '{recipe.name}' does not support target role. Supported roles: {recipe.roles}"
            )
        except (ValueError, KeyError, AttributeError) as e:
            # Fall back to legacy TargetConnectorRecipe format
            try:
                return TargetConnectorRecipe.from_yaml(path)
            except Exception:
                # Re-raise original error if both fail
                raise ValueError(f"Failed to load target connector: {e}")

    def _resolve_asset(self) -> AssetDefinition:
        """Resolve asset definition."""
        if self.asset_path is None:
            raise ValueError("Asset path not provided")

        path = Path(os.path.expandvars(self.asset_path))
        return AssetDefinition.from_yaml(path)

    def _merge_source_with_recipe(
        self, recipe: Union[ConnectorRecipe, SourceConnectorRecipe]
    ) -> SourceConfig:
        """Merge source connector recipe with job source configuration."""
        # Handle both unified and legacy formats
        if isinstance(recipe, ConnectorRecipe):
            credentials = recipe.credentials or {}
            incremental = recipe.incremental
            rate_limits = recipe.rate_limits
        else:  # SourceConnectorRecipe
            credentials = recipe.credentials
            incremental = recipe.incremental
            rate_limits = recipe.rate_limits

        # Start with recipe defaults
        source_data = {
            "type": recipe.type,
            "description": recipe.description,
            "engine": recipe.default_engine,
            "credentials": credentials,
            "incremental": incremental,
            "rate_limits": rate_limits,
        }

        # Apply job-specific source configuration (overrides/extends recipe)
        if self.source:
            # Deep merge for nested dicts
            for key, value in self.source.items():
                if (
                    isinstance(value, dict)
                    and key in source_data
                    and isinstance(source_data[key], dict)
                ):
                    source_data[key] = {**source_data[key], **value}
                else:
                    source_data[key] = value

        # Add tenant-specific state_path if incremental is present
        if source_data.get("incremental") and "state_path" not in source_data.get(
            "incremental", {}
        ):
            if self.tenant_id:
                # Determine object name from source config
                object_name = "default"
                if self.source:
                    if self.source.get("objects"):
                        object_name = (
                            self.source["objects"][0]
                            if isinstance(self.source["objects"], list)
                            else str(self.source["objects"])
                        )
                    elif self.source.get("files") and len(self.source["files"]) > 0:
                        object_name = self.source["files"][0].get("object", "default")
                    elif self.source.get("tables") and len(self.source["tables"]) > 0:
                        object_name = self.source["tables"][0].get("object", "default")

                # Use relative state directory (.local/state/tenant_id/...) for development
                # Can be overridden with STATE_DIR env var for production (e.g., database, S3)
                # Default to .local/state to keep state out of repo root
                state_dir = os.getenv("STATE_DIR", ".local/state")
                source_data["incremental"][
                    "state_path"
                ] = f"{state_dir}/{self.tenant_id}/{recipe.type}.{object_name}.state.json"

        return SourceConfig(**source_data)

    def _merge_target_with_recipe(
        self, recipe: Union[ConnectorRecipe, TargetConnectorRecipe]
    ) -> TargetConfig:
        """Merge target connector recipe with job target configuration."""
        # Handle both unified and legacy formats
        if isinstance(recipe, ConnectorRecipe):
            catalog = recipe.catalog
            file_format = recipe.file_format
            partitioning_default = recipe.partitioning_default
            connection_template = recipe.connection_template
        else:  # TargetConnectorRecipe
            catalog = recipe.catalog
            file_format = recipe.file_format
            partitioning_default = recipe.partitioning_default
            connection_template = recipe.connection_template

        # Start with recipe defaults
        target_data = {
            "type": recipe.type,
            "catalog": catalog,  # Can be None if not set in recipe
            "file_format": file_format,
            "partitioning": partitioning_default,
            "engine": recipe.default_engine,
        }

        # Apply connection template from recipe
        if connection_template:
            target_data["connection"] = connection_template.copy()

        # Apply job-specific target configuration (overrides/extends recipe)
        if self.target:
            # Deep merge for nested dicts
            for key, value in self.target.items():
                if (
                    isinstance(value, dict)
                    and key in target_data
                    and isinstance(target_data[key], dict)
                ):
                    target_data[key] = {**target_data[key], **value}
                else:
                    target_data[key] = value

        # Set branch default to tenant_id if not provided (only if catalog is configured)
        if target_data.get("catalog") and (
            "branch" not in target_data or target_data["branch"] is None
        ):
            target_data["branch"] = self.tenant_id

        return TargetConfig(**target_data)

    def _resolve_source(self) -> SourceConfig:
        """Resolve source config from connector recipe."""
        recipe = self._resolve_source_recipe()
        return self._merge_source_with_recipe(recipe)

    def _resolve_target(self) -> TargetConfig:
        """Resolve target config from connector recipe."""
        recipe = self._resolve_target_recipe()
        return self._merge_target_with_recipe(recipe)

    def get_source(self) -> SourceConfig:
        """Get resolved source config."""
        return self._resolve_source()

    def get_target(self) -> TargetConfig:
        """Get resolved target config."""
        return self._resolve_target()

    def get_asset_path(self) -> str:
        """Get asset definition path."""
        return os.path.expandvars(self.asset_path)

    def validate_schema_presence(self) -> None:
        """Validate that asset definition file exists and contains schema field."""
        asset_path = Path(self.get_asset_path())
        if not asset_path.exists():
            print(
                f"ERROR: Asset definition file not found: {asset_path}\n"
                f"Job: {self.tenant_id}",
                file=sys.stderr,
            )
            sys.exit(2)

        try:
            with open(asset_path, "r") as f:
                asset_data = yaml.safe_load(f)
        except Exception as e:
            print(
                f"ERROR: Failed to read asset definition: {asset_path}\n" f"Error: {e}",
                file=sys.stderr,
            )
            sys.exit(2)

        if not asset_data or "schema" not in asset_data:
            print(
                f"ERROR: Asset definition missing 'schema' field: {asset_path}\n"
                f"Job: {self.tenant_id}",
                file=sys.stderr,
            )
            sys.exit(2)

        # Check if schema is empty
        schema = asset_data.get("schema", [])
        if not schema or (isinstance(schema, list) and len(schema) == 0):
            print(
                f"ERROR: Asset definition has empty 'schema' field: {asset_path}\n"
                f"Job: {self.tenant_id}",
                file=sys.stderr,
            )
            sys.exit(2)

    def validate_environment_variables(self) -> None:
        """Validate that all required environment variables are set."""
        import re

        env_var_pattern = re.compile(r"\$\{([^}]+)\}|\$([A-Z_][A-Z0-9_]*)")

        missing_vars = set()

        try:
            source_recipe = self._resolve_source_recipe()
            target_recipe = self._resolve_target_recipe()

            # Check source connector connection template
            if isinstance(source_recipe, ConnectorRecipe):
                connection_template = source_recipe.connection_template
            else:
                connection_template = getattr(
                    source_recipe, "connection_template", None
                )

            if connection_template:
                template_str = str(connection_template)
                matches = env_var_pattern.findall(template_str)
                for match in matches:
                    var_name = match[0] if match[0] else match[1]
                    if not os.getenv(var_name):
                        missing_vars.add(var_name)

            # Check target connector connection template
            if isinstance(target_recipe, ConnectorRecipe):
                connection_template = target_recipe.connection_template
            else:
                connection_template = getattr(
                    target_recipe, "connection_template", None
                )

            if connection_template:
                template_str = str(connection_template)
                matches = env_var_pattern.findall(template_str)
                for match in matches:
                    var_name = match[0] if match[0] else match[1]
                    if not os.getenv(var_name):
                        missing_vars.add(var_name)

            # Check asset path
            asset_path = self.get_asset_path()
            matches = env_var_pattern.findall(asset_path)
            for match in matches:
                var_name = match[0] if match[0] else match[1]
                if not os.getenv(var_name):
                    missing_vars.add(var_name)

        except Exception as e:
            # If we can't resolve recipes, skip validation
            # This allows for partial validation
            pass

        if missing_vars:
            raise ValueError(
                f"Missing required environment variables: {', '.join(sorted(missing_vars))}"
            )

    @classmethod
    def load_jobs_from_directory(cls, job_dir: Path) -> List["JobConfig"]:
        """Load all job configurations from a directory.

        Args:
            job_dir: Directory containing job YAML files

        Returns:
            List of JobConfig instances

        Raises:
            ValueError: If directory doesn't exist or no valid jobs found
        """
        job_dir = Path(job_dir)
        if not job_dir.exists():
            raise ValueError(f"Job directory not found: {job_dir}")
        if not job_dir.is_dir():
            raise ValueError(f"Path is not a directory: {job_dir}")

        jobs = []
        errors = []

        # Scan directory recursively for YAML files
        for job_file in job_dir.rglob("*.yaml"):
            if job_file.is_file():
                try:
                    job = cls.from_yaml(job_file)
                    jobs.append(job)
                except SystemExit as e:
                    errors.append(f"{job_file}: SystemExit {e.code}")
                except Exception as e:
                    errors.append(f"{job_file}: {e}")

        # Also check for .yml files
        for job_file in job_dir.rglob("*.yml"):
            if job_file.is_file():
                try:
                    job = cls.from_yaml(job_file)
                    jobs.append(job)
                except SystemExit as e:
                    errors.append(f"{job_file}: SystemExit {e.code}")
                except Exception as e:
                    errors.append(f"{job_file}: {e}")

        # Report errors but don't fail if some jobs loaded successfully
        if errors and not jobs:
            raise ValueError(
                f"Failed to load any jobs from {job_dir}. Errors:\n" + "\n".join(errors)
            )
        elif errors:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                f"Some jobs failed to load from {job_dir}",
                extra={"errors": errors, "loaded_count": len(jobs)},
            )

        return jobs

    @classmethod
    def validate_against_schema(
        cls, data: Dict[str, Any], schema_path: Optional[Path] = None
    ) -> None:
        """Validate job configuration against JSON schema.

        Args:
            data: Job configuration dictionary
            schema_path: Optional path to schema file

        Raises:
            ValueError: If validation fails
        """
        if schema_path is None:
            # Default to job config schema in schemas/
            schema_path = (
                Path(__file__).parent.parent.parent
                / "schemas"
                / "job-config.schema.json"
            )

        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        with open(schema_path, "r") as f:
            schema = json.load(f)

        # Create resolver for $ref resolution
        resolver = jsonschema.RefResolver(
            base_uri=f"file://{schema_path.parent}/",
            referrer=schema,
        )

        try:
            jsonschema.validate(instance=data, schema=schema, resolver=resolver)
        except jsonschema.ValidationError as e:
            path_str = ".".join(str(p) for p in e.path) if e.path else "root"
            raise ValueError(
                f"Job configuration schema validation failed: {e.message}\n"
                f"Path: {path_str}\n"
                f"Schema path: {'.'.join(str(p) for p in e.schema_path)}"
            ) from e

    @classmethod
    def from_yaml(
        cls, path: Union[str, Path], validate_schema: bool = True
    ) -> "JobConfig":
        """Load job configuration from YAML file.

        Args:
            path: Path to YAML file
            validate_schema: Whether to validate against JSON schema (default: True)

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
            data["source_connector_path"] = os.path.expandvars(
                data["source_connector_path"]
            )
        if "target_connector_path" in data and data["target_connector_path"]:
            data["target_connector_path"] = os.path.expandvars(
                data["target_connector_path"]
            )

        # Validate against JSON schema if requested
        if validate_schema:
            try:
                cls.validate_against_schema(data)
            except ValueError as e:
                print(
                    f"ERROR: Job configuration schema validation failed: {path}\n{e}",
                    file=sys.stderr,
                )
                sys.exit(2)
            except FileNotFoundError as e:
                # Schema file not found - log warning but don't fail
                print(
                    f"WARNING: Schema validation skipped - schema file not found: {e}",
                    file=sys.stderr,
                )

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
    cron: Optional[str] = (
        None  # Cron expression (mutually exclusive with interval_seconds)
    )
    interval_seconds: Optional[int] = (
        None  # Interval-based scheduling (mutually exclusive with cron)
    )
    enabled: bool = True  # Enable/disable schedule without deployment
    timezone: str = "UTC"  # Timezone for schedule execution
    max_concurrent_runs: int = 1  # Maximum concurrent runs for this schedule
    tags: Optional[Dict[str, str]] = None  # Custom tags for filtering

    @model_validator(mode="after")
    def validate_schedule_type(self) -> "ScheduleConfig":
        """Validate that either cron or interval_seconds is provided, but not both."""
        if self.cron is None and self.interval_seconds is None:
            raise ValueError(
                "Either 'cron' or 'interval_seconds' must be provided for schedule"
            )
        if self.cron is not None and self.interval_seconds is not None:
            raise ValueError(
                "Cannot specify both 'cron' and 'interval_seconds' for schedule"
            )
        return self


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
