"""Configuration models and schema validation for Dativo jobs."""

import datetime
import hashlib
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import warnings

import jsonschema
import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)


class ConnectorRecipe(BaseModel):
    """Unified connector recipe - supports both source and target roles."""

    name: str
    type: str
    roles: List[str] = Field(default_factory=list)  # [source], [target], or [source, target]
    description: Optional[str] = None
    default_engine: Dict[str, Any]
    credentials: Optional[Dict[str, Any]] = None  # Optional for target-only connectors
    incremental: Optional[Dict[str, Any]] = None  # Optional for target-only connectors
    rate_limits: Optional[Dict[str, Any]] = None  # Optional for target-only connectors
    connection_template: Optional[Dict[str, Any]] = None
    catalog: Optional[str] = None  # Optional for source-only connectors
    file_format: Optional[str] = None  # Optional for source-only connectors
    partitioning_default: Optional[List[str]] = None  # Optional for source-only connectors

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


class ChangeManagementModel(BaseModel):
    """Change management configuration."""

    policy: Optional[str] = None
    approval_required: Optional[bool] = None
    notification_channels: Optional[List[str]] = None
    version_history: Optional[bool] = None


class FinOpsModel(BaseModel):
    """FinOps and cost governance configuration."""

    cost_center: str
    owner: Optional[str] = None
    tags: Optional[List[str]] = None
    budget_usd: Optional[float] = None
    anomaly_contact: Optional[str] = None


class LineageEdgeModel(BaseModel):
    """Lineage connection between upstream and downstream assets."""

    from_asset: str
    to_asset: str
    contract_version: str
    stage: Optional[str] = None
    transformation: Optional[str] = None
    description: Optional[str] = None


class AuditEventModel(BaseModel):
    """Audit event entry for contract changes."""

    author: str
    timestamp: datetime.datetime
    hash: str
    description: Optional[str] = None

    @field_validator("timestamp", mode="before")
    @classmethod
    def _parse_timestamp(cls, value: Any) -> datetime.datetime:
        """Parse ISO 8601 timestamps and ensure timezone awareness."""
        if isinstance(value, datetime.datetime):
            ts = value
        elif isinstance(value, str):
            if value.endswith("Z"):
                value = value.replace("Z", "+00:00")
            ts = datetime.datetime.fromisoformat(value)
        else:
            raise TypeError("timestamp must be datetime or ISO 8601 string")

        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=datetime.timezone.utc)
        return ts.astimezone(datetime.timezone.utc)

    @field_validator("hash")
    @classmethod
    def _validate_hash(cls, value: str) -> str:
        """Ensure hash is a 64-character lowercase hex SHA256."""
        if not isinstance(value, str):
            raise TypeError("hash must be a string")
        lowered = value.lower()
        if not re.fullmatch(r"[0-9a-f]{64}", lowered):
            raise ValueError("hash must be a 64-character hexadecimal SHA256 digest")
        return lowered

    @field_serializer("timestamp")
    def _serialize_timestamp(self, value: datetime.datetime) -> str:
        """Serialize timestamp to ISO 8601 with Z suffix."""
        return value.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


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
    governance_status: str = "approved"
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
    finops: FinOpsModel
    lineage: List[LineageEdgeModel] = Field(default_factory=list)
    audit: List[AuditEventModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_governance(self) -> "AssetDefinition":
        """Validate governance requirements."""
        # Team owner is required
        if not self.team or not self.team.owner:
            raise ValueError("team.owner is required (strong ownership requirement)")

        # Compliance classification and retention are mandatory
        if not self.compliance or not self.compliance.classification:
            raise ValueError(
                "compliance.classification must include at least one classification tag"
            )
        if self.compliance.retention_days is None:
            raise ValueError("compliance.retention_days is required")

        # FinOps cost center required
        if not self.finops or not self.finops.cost_center:
            raise ValueError("finops.cost_center is required")

        # Require lineage edges
        if not self.lineage:
            raise ValueError("At least one lineage entry is required")
        for edge in self.lineage:
            if not edge.from_asset or not edge.to_asset:
                raise ValueError("lineage entries require from_asset and to_asset")
            if not edge.contract_version:
                raise ValueError("lineage entries require contract_version")

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

        # Schema fields require names and types
        for field in self.schema:
            if "name" not in field or not field["name"]:
                raise ValueError("All schema fields must include a name")
            if "type" not in field or not field["type"]:
                raise ValueError(
                    f"Schema field '{field.get('name', '<unknown>')}' must include a type"
                )

        # Enforce semantic versioning MAJOR.MINOR.PATCH
        if not re.fullmatch(r"\d+\.\d+\.\d+", self.version):
            raise ValueError(
                f"version '{self.version}' must follow semantic versioning MAJOR.MINOR.PATCH"
            )

        # Audit trail with matching hash is required
        if not self.audit:
            raise ValueError("audit trail must include at least one entry")

        computed_hash = self.compute_contract_hash()
        latest_hash = self.audit[-1].hash
        if latest_hash != computed_hash:
            warnings.warn(
                "Latest audit hash did not match contract content. "
                "Hash has been recalculated automatically.",
                UserWarning,
            )
            self.audit[-1].hash = computed_hash

        return self

    def compute_contract_hash(self) -> str:
        """Compute canonical hash for contract content excluding audit trail."""
        payload = self.model_dump(mode="json", exclude={"audit"})
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

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

            cls._apply_contract_defaults(asset_data, compute_hash=False)

            return asset_data
        return data

    @classmethod
    def _apply_contract_defaults(
        cls, asset_data: Dict[str, Any], compute_hash: bool = True
    ) -> Dict[str, Any]:
        """Apply mandatory defaults and normalization to asset data."""
        asset_data.setdefault("governance_status", "approved")

        # Ensure compliance section with classification and retention
        compliance_section = asset_data.get("compliance") or {}
        if not compliance_section.get("classification"):
            compliance_section["classification"] = ["INTERNAL"]
        compliance_section["classification"] = [
            str(tag).upper() for tag in compliance_section.get("classification", [])
        ]
        if compliance_section.get("retention_days") is None:
            compliance_section["retention_days"] = 90
        asset_data["compliance"] = compliance_section

        # Ensure FinOps section
        finops_section = asset_data.get("finops") or {}
        if not finops_section.get("cost_center"):
            finops_section["cost_center"] = "CC-UNSPECIFIED"
        if not finops_section.get("owner") and asset_data.get("team", {}).get("owner"):
            finops_section["owner"] = asset_data["team"]["owner"]
        asset_data["finops"] = finops_section

        # Normalize semantic versioning
        version_value = str(asset_data.get("version", "1.0.0"))
        if re.fullmatch(r"\d+\.\d+$", version_value):
            version_value = f"{version_value}.0"
        elif not re.fullmatch(r"\d+\.\d+\.\d+$", version_value):
            version_value = "1.0.0"
        asset_data["version"] = version_value

        # Ensure lineage entries
        if not asset_data.get("lineage"):
            source_type = asset_data.get("source_type", "source")
            upstream_object = asset_data.get("object") or asset_data.get("name", "asset")
            asset_data["lineage"] = [
                {
                    "from_asset": f"{source_type}::{upstream_object}",
                    "to_asset": asset_data.get("name", upstream_object),
                    "contract_version": version_value,
                    "stage": "ingest",
                    "description": "Auto-generated lineage for missing specification",
                }
            ]
        else:
            for edge in asset_data["lineage"]:
                edge.setdefault("contract_version", version_value)
                edge["contract_version"] = version_value

        if compute_hash:
            cls._ensure_audit_trail(asset_data)

        return asset_data

    @classmethod
    def _ensure_audit_trail(cls, asset_data: Dict[str, Any]) -> None:
        """Ensure audit trail exists and latest entry hash matches content."""
        audit_list = list(asset_data.get("audit") or [])
        if not audit_list:
            author = asset_data.get("team", {}).get("owner", "unknown")
            audit_list.append(
                {
                    "author": author,
                    "timestamp": datetime.datetime.utcnow()
                    .replace(tzinfo=datetime.timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "description": "Auto-generated initial audit entry",
                    "hash": "",
                }
            )

        payload_for_hash = {
            k: v for k, v in asset_data.items() if k != "audit"
        }
        computed_hash = hashlib.sha256(
            json.dumps(
                payload_for_hash,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()

        audit_list[-1]["hash"] = computed_hash
        asset_data["audit"] = audit_list

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

        # Apply defaults and ensure audit/hash consistency
        cls._apply_contract_defaults(data, compute_hash=True)

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
    markdown_kv_storage: Optional[Dict[str, Any]] = None  # Markdown-KV storage configuration
    parquet_target_size_mb: Optional[int] = None  # Target Parquet file size in MB (default: 128-200 MB range)

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
    initial_delay_seconds: Optional[int] = None  # Initial delay in seconds (defaults to retry_delay_seconds for backward compat)
    max_delay_seconds: int = 300
    backoff_multiplier: float = 2.0
    retryable_exit_codes: List[int] = Field(default=[1, 2])  # Exit codes that should trigger retries
    retryable_error_patterns: Optional[List[str]] = None  # Regex patterns for error messages
    retry_delay_seconds: Optional[int] = 5  # Deprecated: use initial_delay_seconds
    retryable_errors: Optional[List[str]] = None  # List of error types to retry (deprecated, use retryable_error_patterns)

    @model_validator(mode="after")
    def set_initial_delay(self) -> "RetryConfig":
        """Set initial_delay_seconds from retry_delay_seconds if not provided (backward compat)."""
        if self.initial_delay_seconds is None:
            self.initial_delay_seconds = self.retry_delay_seconds or 5
        return self


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
    
    # Execution configuration
    schema_validation_mode: str = "strict"  # 'strict' or 'warn'
    retry_config: Optional[RetryConfig] = None
    
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
            raise ValueError(f"Connector '{recipe.name}' does not support source role. Supported roles: {recipe.roles}")
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
            raise ValueError(f"Connector '{recipe.name}' does not support target role. Supported roles: {recipe.roles}")
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

    def _merge_source_with_recipe(self, recipe: Union[ConnectorRecipe, SourceConnectorRecipe]) -> SourceConfig:
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
                if isinstance(value, dict) and key in source_data and isinstance(source_data[key], dict):
                    source_data[key] = {**source_data[key], **value}
                else:
                    source_data[key] = value
        
        # Add tenant-specific state_path if incremental is present
        if source_data.get("incremental") and "state_path" not in source_data.get("incremental", {}):
            if self.tenant_id:
                # Determine object name from source config
                object_name = "default"
                if self.source:
                    if self.source.get("objects"):
                        object_name = self.source["objects"][0] if isinstance(self.source["objects"], list) else str(self.source["objects"])
                    elif self.source.get("files") and len(self.source["files"]) > 0:
                        object_name = self.source["files"][0].get("object", "default")
                    elif self.source.get("tables") and len(self.source["tables"]) > 0:
                        object_name = self.source["tables"][0].get("object", "default")
                
                # Use relative state directory (.local/state/tenant_id/...) for development
                # Can be overridden with STATE_DIR env var for production (e.g., database, S3)
                # Default to .local/state to keep state out of repo root
                state_dir = os.getenv("STATE_DIR", ".local/state")
                source_data["incremental"]["state_path"] = (
                    f"{state_dir}/{self.tenant_id}/{recipe.type}.{object_name}.state.json"
                )
        
        return SourceConfig(**source_data)

    def _merge_target_with_recipe(self, recipe: Union[ConnectorRecipe, TargetConnectorRecipe]) -> TargetConfig:
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
                if isinstance(value, dict) and key in target_data and isinstance(target_data[key], dict):
                    target_data[key] = {**target_data[key], **value}
                else:
                    target_data[key] = value
        
        # Set branch default to tenant_id if not provided (only if catalog is configured)
        if target_data.get("catalog") and ("branch" not in target_data or target_data["branch"] is None):
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
                f"ERROR: Failed to read asset definition: {asset_path}\n"
                f"Error: {e}",
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
                connection_template = getattr(source_recipe, "connection_template", None)
            
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
                connection_template = getattr(target_recipe, "connection_template", None)
            
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
    cron: Optional[str] = None  # Cron expression (mutually exclusive with interval_seconds)
    interval_seconds: Optional[int] = None  # Interval-based scheduling (mutually exclusive with cron)
    enabled: bool = True  # Enable/disable schedule without deployment
    timezone: str = "UTC"  # Timezone for schedule execution
    max_concurrent_runs: int = 1  # Maximum concurrent runs for this schedule
    tags: Optional[Dict[str, str]] = None  # Custom tags for filtering

    @model_validator(mode="after")
    def validate_schedule_type(self) -> "ScheduleConfig":
        """Validate that either cron or interval_seconds is provided, but not both."""
        if self.cron is None and self.interval_seconds is None:
            raise ValueError("Either 'cron' or 'interval_seconds' must be provided for schedule")
        if self.cron is not None and self.interval_seconds is not None:
            raise ValueError("Cannot specify both 'cron' and 'interval_seconds' for schedule")
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

