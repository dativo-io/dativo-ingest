"""Utilities for generating ODCS-compliant asset definitions and dbt metadata from Specs-as-Code contracts."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from .config import AssetDefinition

SEMVER_PATTERN = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)(?:\.(?P<patch>\d+))?$")


def _parse_semver(version: str) -> Tuple[int, int, int]:
    match = SEMVER_PATTERN.fullmatch(version)
    if not match:
        raise ValueError(f"Version '{version}' must follow semantic versioning (MAJOR.MINOR or MAJOR.MINOR.PATCH)")
    major = int(match.group("major"))
    minor = int(match.group("minor"))
    patch = int(match.group("patch") or 0)
    return major, minor, patch


class DescriptionSpec(BaseModel):
    purpose: Optional[str] = None
    limitations: Optional[str] = None
    usage: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.model_dump().items() if v is not None}


class FieldSpec(BaseModel):
    name: str
    type: str
    required: bool = False
    classification: Optional[str] = None
    description: Optional[str] = None
    tests: Optional[List[str]] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        allowed = {"string", "integer", "float", "double", "boolean", "date", "datetime", "timestamp", "array"}
        if value not in allowed:
            raise ValueError(f"Unsupported field type '{value}'. Allowed types: {sorted(allowed)}")
        return value


class SchemaSpec(BaseModel):
    fields: List[FieldSpec]

    @model_validator(mode="after")
    def ensure_fields(self) -> "SchemaSpec":
        if not self.fields:
            raise ValueError("schema.fields must contain at least one entry")
        return self


class SourceSpec(BaseModel):
    type: str
    object: str
    database: Optional[str] = None
    schema: Optional[str] = None


class TargetSpec(BaseModel):
    file_format: str
    partitioning: Optional[List[str]] = None
    mode: str = "strict"


class GovernanceSpec(BaseModel):
    owner: str
    cost_center: str
    classification: List[str]
    retention_days: int
    owner_email: Optional[str] = None
    regulations: Optional[List[str]] = None
    tags: Optional[List[str]] = None

    @model_validator(mode="after")
    def validate_governance(self) -> "GovernanceSpec":
        if not self.classification:
            raise ValueError("governance.classification must contain at least one classification tag")
        if self.retention_days <= 0:
            raise ValueError("governance.retention_days must be positive")
        return self


class LineageSpec(BaseModel):
    from_asset: str
    to_asset: Optional[str] = None
    contract_version: Optional[str] = None
    description: Optional[str] = None

    def resolved_to_asset(self, default_asset: str) -> str:
        return self.to_asset or default_asset

    def resolved_contract_version(self, default_version: str) -> str:
        return self.contract_version or default_version


class AuditSpec(BaseModel):
    author: str
    timestamp: datetime
    hash: Optional[str] = None
    change_type: Optional[str] = None
    comment: Optional[str] = None

    @model_validator(mode="after")
    def ensure_hash(self) -> "AuditSpec":
        if not self.hash:
            seed = f"{self.author}-{self.timestamp.isoformat()}-{self.change_type or ''}"
            self.hash = hashlib.sha256(seed.encode()).hexdigest()
        return self


class ChangeManagementSpec(BaseModel):
    policy: str = "non-breaking"
    approval_required: Optional[bool] = None
    notification_channels: Optional[List[str]] = None
    version_history: Optional[bool] = None


class DbtSourceSpec(BaseModel):
    name: str
    database: str
    schema: str
    table_name: Optional[str] = None
    description: Optional[str] = None


class DbtModelSpec(BaseModel):
    name: str
    materialized: str = "table"
    description: Optional[str] = None
    tags: Optional[List[str]] = None


class DbtExposureSpec(BaseModel):
    name: str
    type: str
    url: Optional[str] = None
    owner_name: Optional[str] = None
    owner_email: Optional[str] = None
    depends_on: Optional[List[str]] = None
    description: Optional[str] = None


class DbtSpec(BaseModel):
    source: DbtSourceSpec
    model: Optional[DbtModelSpec] = None
    exposure: Optional[DbtExposureSpec] = None


class FinOpsSpec(BaseModel):
    tags: Optional[List[str]] = None
    budget_guardrails: Optional[str] = None


class ContractSpec(BaseModel):
    name: str
    version: str
    domain: str
    data_product: str = Field(alias="data_product")
    status: str = "active"
    tenant: Optional[str] = None
    description: Optional[DescriptionSpec] = None
    tags: Optional[List[str]] = None

    source: SourceSpec
    target: TargetSpec
    schema: SchemaSpec
    governance: GovernanceSpec
    lineage: List[LineageSpec]
    audit: Optional[List[AuditSpec]] = None
    change_management: Optional[ChangeManagementSpec] = None
    dbt: Optional[DbtSpec] = None
    finops: Optional[FinOpsSpec] = None

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        _parse_semver(value)
        return value

    @model_validator(mode="after")
    def validate_contract(self) -> "ContractSpec":
        if not self.lineage:
            raise ValueError("lineage must contain at least one relationship")
        return self

    @classmethod
    def from_yaml(cls, path: Path) -> "ContractSpec":
        with open(path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        if data is None:
            raise ValueError(f"Spec file is empty: {path}")
        return cls.model_validate(data)

    def combined_tags(self) -> List[str]:
        tags: List[str] = []
        for candidate in (self.tags, self.governance.tags, self.finops.tags if self.finops else None):
            if candidate:
                tags.extend(candidate)
        # Preserve order but remove duplicates
        seen: set[str] = set()
        result: List[str] = []
        for tag in tags:
            if tag not in seen:
                seen.add(tag)
                result.append(tag)
        return result

    def enforce_version_policy(self, existing_version: Optional[str]) -> None:
        if not existing_version:
            return
        new_major, new_minor, new_patch = _parse_semver(self.version)
        old_major, old_minor, old_patch = _parse_semver(existing_version)

        policy = (self.change_management.policy if self.change_management else "non-breaking").lower()
        if policy == "breaking":
            if new_major <= old_major:
                raise ValueError(
                    f"Breaking change requires a MAJOR version bump (existing={existing_version}, new={self.version})"
                )
        else:
            if (new_major, new_minor, new_patch) <= (old_major, old_minor, old_patch):
                raise ValueError(
                    f"Non-breaking change requires version to advance (existing={existing_version}, new={self.version})"
                )

    def _build_schema_fields(self) -> List[Dict[str, Any]]:
        fields: List[Dict[str, Any]] = []
        for field in self.schema.fields:
            field_dict: Dict[str, Any] = {
                "name": field.name,
                "type": field.type,
                "required": field.required,
            }
            if field.classification:
                field_dict["classification"] = field.classification
            if field.description:
                field_dict["description"] = field.description
            fields.append(field_dict)
        return fields

    def _build_lineage(self) -> List[Dict[str, Any]]:
        edges: List[Dict[str, Any]] = []
        for link in self.lineage:
            edges.append(
                {
                    "from_asset": link.from_asset,
                    "to_asset": link.resolved_to_asset(self.name),
                    "contract_version": link.resolved_contract_version(self.version),
                    "description": link.description,
                }
            )
        return edges

    def _build_audit(self) -> List[Dict[str, Any]]:
        audits: Sequence[AuditSpec] = self.audit or [
            AuditSpec(
                author=self.governance.owner,
                timestamp=datetime.now(tz=timezone.utc),
                change_type="initial_publish",
            )
        ]
        return [
            {
                "author": entry.author,
                "timestamp": entry.timestamp,
                "hash": entry.hash,
                "change_type": entry.change_type,
                "comment": entry.comment,
            }
            for entry in audits
        ]

    def to_asset_definition(self) -> AssetDefinition:
        team_roles: List[Dict[str, Any]] = []
        owner_email = self.governance.owner_email or self.governance.owner
        team_roles.append(
            {
                "name": "Data Steward",
                "email": owner_email,
                "responsibility": "contract_owner",
            }
        )

        description_dict = self.description.to_dict() if self.description else None
        target_dict = {
            "file_format": self.target.file_format,
            "partitioning": self.target.partitioning,
            "mode": self.target.mode,
        }

        compliance_dict = {
            "classification": self.governance.classification,
            "regulations": self.governance.regulations,
            "retention_days": self.governance.retention_days,
        }

        change_mgmt_dict = (
            self.change_management.model_dump(exclude_none=True) if self.change_management else None
        )

        asset = AssetDefinition(
            name=self.name,
            version=self.version,
            source_type=self.source.type,
            object=self.source.object,
            domain=self.domain,
            dataProduct=self.data_product,
            status=self.status,
            tenant=self.tenant,
            description=description_dict,
            tags=self.combined_tags(),
            schema=self._build_schema_fields(),
            target=target_dict,
            team={
                "owner": self.governance.owner,
                "cost_center": self.governance.cost_center,
                "roles": team_roles,
            },
            compliance=compliance_dict,
            change_management=change_mgmt_dict,
            lineage=self._build_lineage(),
            audit=self._build_audit(),
        )
        return asset

    def to_dbt_dict(self) -> Dict[str, Any]:
        if not self.dbt:
            raise ValueError("DBT configuration not provided in contract spec")

        dbt_dict: Dict[str, Any] = {}

        # Sources
        columns: List[Dict[str, Any]] = []
        for field in self.schema.fields:
            column_entry: Dict[str, Any] = {"name": field.name}
            if field.description:
                column_entry["description"] = field.description
            tests: List[str] = []
            if field.required:
                tests.append("not_null")
            if field.tests:
                tests.extend(field.tests)
            if tests:
                column_entry["tests"] = tests
            meta: Dict[str, Any] = {}
            if field.classification:
                meta["classification"] = field.classification
            if meta:
                column_entry["meta"] = meta
            columns.append(column_entry)

        table_entry: Dict[str, Any] = {
            "name": self.dbt.source.table_name or self.name,
            "columns": columns,
            "meta": {
                "owner": self.governance.owner,
                "owner_email": self.governance.owner_email or self.governance.owner,
                "classification": self.governance.classification,
                "cost_center": self.governance.cost_center,
            },
        }
        table_description = self.dbt.source.description or (
            self.description.purpose if self.description and self.description.purpose else None
        )
        if table_description:
            table_entry["description"] = table_description

        source_entry: Dict[str, Any] = {
            "name": self.dbt.source.name,
            "database": self.dbt.source.database,
            "schema": self.dbt.source.schema,
            "tables": [table_entry],
        }
        source_meta = {
            "domain": self.domain,
            "data_product": self.data_product,
            "classification": self.governance.classification,
            "tags": self.combined_tags(),
        }
        source_entry["meta"] = source_meta

        dbt_dict["sources"] = [source_entry]

        # Models
        if self.dbt.model:
            tags = (self.dbt.model.tags or []) + self.combined_tags()
            # deduplicate while preserving order
            deduped_tags: List[str] = []
            seen_tag: set[str] = set()
            for tag in tags:
                if tag not in seen_tag:
                    seen_tag.add(tag)
                    deduped_tags.append(tag)

            model_entry: Dict[str, Any] = {
                "name": self.dbt.model.name,
                "config": {"materialized": self.dbt.model.materialized},
                "meta": {
                    "owner": self.governance.owner,
                    "owner_email": self.governance.owner_email or self.governance.owner,
                    "classification": self.governance.classification,
                    "cost_center": self.governance.cost_center,
                },
                "tags": deduped_tags,
            }
            model_description = self.dbt.model.description or (
                self.description.usage if self.description and self.description.usage else None
            )
            if model_description:
                model_entry["description"] = model_description
            dbt_dict["models"] = [model_entry]

        # Exposures
        if self.dbt.exposure:
            exposure_entry: Dict[str, Any] = {
                "name": self.dbt.exposure.name,
                "type": self.dbt.exposure.type,
                "owner": {
                    "name": self.dbt.exposure.owner_name or self.governance.owner,
                    "email": self.dbt.exposure.owner_email
                    or self.governance.owner_email
                    or self.governance.owner,
                },
                "meta": {
                    "classification": self.governance.classification,
                    "cost_center": self.governance.cost_center,
                },
            }
            if self.dbt.exposure.url:
                exposure_entry["url"] = self.dbt.exposure.url
            if self.dbt.exposure.depends_on:
                exposure_entry["depends_on"] = self.dbt.exposure.depends_on
            elif self.dbt.model:
                exposure_entry["depends_on"] = [f"ref('{self.dbt.model.name}')" ]
            if self.dbt.exposure.description:
                exposure_entry["description"] = self.dbt.exposure.description
            dbt_dict["exposures"] = [exposure_entry]

        return dbt_dict


def _serialize_asset_definition(asset: AssetDefinition) -> Dict[str, Any]:
    data = asset.model_dump(by_alias=True, exclude_none=True)
    if "schema_ref" in data:
        data["$schema"] = data.pop("schema_ref")
    return data


def generate_contract_artifacts(
    spec_path: Path,
    asset_output_path: Path,
    dbt_output_path: Path,
    *,
    existing_asset_path: Optional[Path] = None,
) -> Dict[str, Path]:
    """Generate ODCS asset definition and dbt YAML artifacts from a Specs-as-Code contract."""

    spec = ContractSpec.from_yaml(spec_path)

    if existing_asset_path and existing_asset_path.exists():
        existing_asset = AssetDefinition.from_yaml(existing_asset_path)
        spec.enforce_version_policy(existing_asset.version)

    asset_definition = spec.to_asset_definition()
    asset_payload = _serialize_asset_definition(asset_definition)

    asset_output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(asset_output_path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(asset_payload, handle, sort_keys=False)

    dbt_payload = spec.to_dbt_dict()
    dbt_output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dbt_output_path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(dbt_payload, handle, sort_keys=False)

    return {
        "asset": asset_output_path,
        "dbt": dbt_output_path,
    }


__all__ = ["ContractSpec", "generate_contract_artifacts"]
