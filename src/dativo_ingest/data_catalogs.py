"""Data catalog lineage publishing helpers."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

try:  # pragma: no cover - boto3 is optional at import time
    import boto3
    from botocore.exceptions import ClientError
except ImportError:  # pragma: no cover - handled per provider
    boto3 = None
    ClientError = Exception

from .config import (
    AssetDefinition,
    CatalogConfig,
    CatalogTargetConfig,
    JobConfig,
    SourceConfig,
    TargetConfig,
)
from .iceberg_committer import IcebergCommitter
from .tag_derivation import derive_tags_from_asset

logger = logging.getLogger(__name__)

_SENSITIVE_TOKENS = {
    "password",
    "secret",
    "token",
    "key",
    "credential",
    "access_key",
    "secret_key",
}


def _model_to_dict(data: Any) -> Dict[str, Any]:
    """Best-effort conversion of Pydantic/BaseModel objects to plain dicts."""
    if data is None:
        return {}
    if hasattr(data, "model_dump"):
        return data.model_dump(exclude_none=True)
    if hasattr(data, "dict"):
        return data.dict(exclude_none=True)
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if v is not None}
    return {}


def _sanitize_connection(value: Any, parent_key: str = "") -> Any:
    """Remove/obfuscate sensitive connection fields."""
    if isinstance(value, dict):
        sanitized: Dict[str, Any] = {}
        for key, nested in value.items():
            sanitized[key] = _sanitize_connection(nested, key)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_connection(item, parent_key) for item in value]
    if isinstance(value, str):
        lowered = (parent_key or "").lower()
        if any(token in lowered for token in _SENSITIVE_TOKENS):
            return "***"
    return value


def _unique(items: List[Optional[str]]) -> List[str]:
    """Maintain order while removing duplicates and falsy values."""
    seen = set()
    result: List[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _normalize_identifier(value: Optional[str], fallback: str) -> str:
    """Normalize catalog identifiers."""
    identifier = (value or fallback or "").strip()
    return identifier.replace(" ", "_") if identifier else fallback


def _safe_get(data: Optional[Dict[str, Any]], key: str, default: Any = None) -> Any:
    if not data:
        return default
    return data.get(key, default)


@dataclass
class LineagePayload:
    """Normalized lineage payload shared by catalog publishers."""

    tenant_id: str
    environment: Optional[str]
    asset_name: str
    asset_version: str
    domain: str
    data_product: Optional[str]
    object_name: str
    source_type: str
    target_type: str
    tags: Dict[str, str]
    owners: List[str]
    schema_fields: List[Dict[str, Any]]
    finops: Dict[str, Any]
    governance: Dict[str, Any]
    finops_overrides: Dict[str, Any]
    governance_overrides: Dict[str, Any]
    classification_overrides: Dict[str, str]
    totals: Dict[str, Any]
    files: List[Dict[str, Any]]
    commit: Dict[str, Any]
    lineage_edges: Dict[str, str]
    job_metadata: Dict[str, Any]
    source_details: Dict[str, Any]
    target_details: Dict[str, Any]
    source_tags: Dict[str, str]
    asset_definition: AssetDefinition = field(repr=False)
    source_config: SourceConfig = field(repr=False)
    target_config: TargetConfig = field(repr=False)
    derived_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )

    def as_metadata(self) -> Dict[str, Any]:
        """Return JSON-serializable metadata document."""
        return {
            "asset": {
                "name": self.asset_name,
                "version": self.asset_version,
                "domain": self.domain,
                "data_product": self.data_product,
                "object": self.object_name,
                "tags": getattr(self.asset_definition, "tags", []),
            },
            "tenant_id": self.tenant_id,
            "environment": self.environment,
            "owners": self.owners,
            "tags": self.tags,
            "schema": self.schema_fields,
            "finops": self.finops,
            "governance": self.governance,
            "stats": self.totals,
            "files": self.files,
            "commit": self.commit,
            "lineage": self.lineage_edges,
            "job": self.job_metadata,
            "source": {
                **self.source_details,
                "tags": self.source_tags,
            },
            "target": self.target_details,
            "timestamp": self.derived_at,
        }

    def as_flat_properties(self, prefix: str = "dativo.metadata") -> Dict[str, str]:
        """Flatten metadata for key-value property stores (e.g., Glue parameters)."""
        metadata = self.as_metadata()
        flattened: Dict[str, str] = {}

        def _walk(node: Any, path: List[str]) -> None:
            if node is None:
                return
            if isinstance(node, dict):
                for key, value in node.items():
                    _walk(value, path + [key])
            elif isinstance(node, list):
                for idx, value in enumerate(node):
                    _walk(value, path + [str(idx)])
            else:
                key = ".".join(path)
                flattened[f"{prefix}.{key}"] = str(node)

        _walk(metadata, [])
        return flattened

    def columns_lineage(
        self, upstream_fqn: str, downstream_fqn: str
    ) -> List[Dict[str, Any]]:
        """Build column-level lineage mapping for OpenMetadata/Unity."""
        lineage = []
        for field_info in self.schema_fields:
            column = field_info["name"]
            lineage.append(
                {
                    "fromColumns": [f"{upstream_fqn}.{column}"],
                    "toColumns": [f"{downstream_fqn}.{column}"],
                    "details": {
                        "classification": field_info.get("classification"),
                        "required": field_info.get("required", False),
                    },
                }
            )
        return lineage


def build_lineage_payload(
    job_config: JobConfig,
    asset_definition: AssetDefinition,
    source_config: SourceConfig,
    target_config: TargetConfig,
    file_metadata: List[Dict[str, Any]],
    commit_result: Optional[Dict[str, Any]],
    totals: Dict[str, Any],
    source_tags: Optional[Dict[str, str]] = None,
) -> LineagePayload:
    """Construct a normalized lineage payload."""

    tags = derive_tags_from_asset(
        asset_definition=asset_definition,
        classification_overrides=job_config.classification_overrides,
        finops=job_config.finops,
        governance_overrides=job_config.governance_overrides,
        source_tags=source_tags,
    )

    owners = _unique(
        [
            getattr(asset_definition.team, "owner", None)
            if asset_definition.team
            else None,
            *(
                [role.email for role in asset_definition.team.roles]
                if asset_definition.team and asset_definition.team.roles
                else []
            ),
        ]
    )

    schema_fields = []
    for field_def in asset_definition.schema:
        schema_fields.append(
            {
                "name": field_def["name"],
                "type": field_def.get("type", "string"),
                "description": field_def.get("description"),
                "required": bool(field_def.get("required", False)),
                "classification": tags.get(
                    f"classification.fields.{field_def['name']}"
                ),
            }
        )

    asset_finops = _model_to_dict(asset_definition.finops)
    finops = {**asset_finops, **(job_config.finops or {})}

    governance = {
        "owner": owners[0] if owners else None,
        "domain": asset_definition.domain,
        "data_product": getattr(asset_definition, "dataProduct", None),
    }

    compliance = getattr(asset_definition, "compliance", None)
    if compliance:
        compliance_dict = _model_to_dict(compliance)
        governance.update(
            {
                "classification": compliance_dict.get("classification"),
                "retention_days": compliance_dict.get("retention_days"),
                "regulations": compliance_dict.get("regulations"),
            }
        )

    if job_config.governance_overrides:
        governance.update(job_config.governance_overrides)

    sanitized_files = [
        {
            "path": meta.get("path"),
            "size_bytes": meta.get("size_bytes"),
            "record_count": meta.get("record_count"),
            "partition": meta.get("partition"),
        }
        for meta in file_metadata
    ]

    domain = asset_definition.domain or "default"
    commit_info = {
        "commit_id": None,
        "branch": commit_result.get("branch") if commit_result else None,
        "table_name": (
            commit_result.get("table_name")
            if commit_result and commit_result.get("table_name")
            else f"{domain}.{asset_definition.name}"
        ),
        "files_added": commit_result.get("files_added")
        if commit_result
        else totals.get("files_written", len(file_metadata)),
    }
    if commit_result:
        for key in ("snapshot_id", "warning", "note"):
            if commit_result.get(key):
                commit_info[key] = commit_result[key]

    lineage_edges = {
        "upstream": f"{source_config.type}.{asset_definition.object}".lower(),
        "downstream": (
            f"{target_config.type}.{domain}.{asset_definition.name}".lower()
        ),
    }

    source_details = {
        "type": source_config.type,
        "objects": source_config.objects or [],
        "tables": source_config.tables or [],
        "files": [entry.get("path") for entry in (source_config.files or [])],
        "engine": _safe_get(source_config.engine, "type"),
        "incremental": bool(source_config.incremental),
        "connection": _sanitize_connection(source_config.connection or {}),
    }

    target_details = {
        "type": target_config.type,
        "catalog": target_config.catalog,
        "branch": target_config.branch,
        "warehouse": target_config.warehouse,
        "file_format": target_config.file_format,
        "connection": _sanitize_connection(target_config.connection or {}),
    }

    job_metadata = {
        "asset_name": job_config.asset or asset_definition.name,
        "asset_path": job_config.asset_path,
        "source_connector": job_config.source_connector or job_config.source_connector_path,
        "target_connector": job_config.target_connector or job_config.target_connector_path,
        "schema_validation_mode": job_config.schema_validation_mode,
    }
    if job_config.finops:
        job_metadata["job_finops_overrides"] = job_config.finops
    if job_config.governance_overrides:
        job_metadata["job_governance_overrides"] = job_config.governance_overrides
    if job_config.classification_overrides:
        job_metadata["classification_overrides"] = job_config.classification_overrides

    return LineagePayload(
        tenant_id=job_config.tenant_id,
        environment=job_config.environment,
        asset_name=asset_definition.name,
        asset_version=str(asset_definition.version),
        domain=domain,
        data_product=getattr(asset_definition, "dataProduct", None),
        object_name=asset_definition.object,
        source_type=source_config.type,
        target_type=target_config.type,
        tags=tags,
        owners=owners,
        schema_fields=schema_fields,
        finops=finops,
        governance={k: v for k, v in governance.items() if v is not None},
        finops_overrides=job_config.finops or {},
        governance_overrides=job_config.governance_overrides or {},
        classification_overrides=job_config.classification_overrides or {},
        totals=totals,
        files=sanitized_files,
        commit=commit_info,
        lineage_edges=lineage_edges,
        job_metadata=job_metadata,
        source_details=source_details,
        target_details=target_details,
        source_tags=source_tags or {},
        asset_definition=asset_definition,
        source_config=source_config,
        target_config=target_config,
    )


class BaseCatalogPublisher:
    """Base publisher for data catalog targets."""

    def __init__(self, target: CatalogTargetConfig):
        self.target = target
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}.{target.type}"
        )

    def publish(self, payload: LineagePayload) -> Dict[str, Any]:  # pragma: no cover
        raise NotImplementedError


class AwsGlueCatalogPublisher(BaseCatalogPublisher):
    """Publishes lineage metadata into AWS Glue table parameters."""

    def publish(self, payload: LineagePayload) -> Dict[str, Any]:
        if boto3 is None:
            raise RuntimeError(
                "boto3 is required for AWS Glue integration. Install boto3 to use this catalog."
            )

        database = (
            self.target.database
            or (self.target.connection or {}).get("database")
            or payload.domain
        )
        table_name = self.target.table or payload.asset_name
        region = (
            self.target.region
            or (self.target.connection or {}).get("region")
            or os.getenv("AWS_REGION")
            or "us-east-1"
        )

        glue_client = boto3.client("glue", region_name=region)
        response = glue_client.get_table(DatabaseName=database, Name=table_name)
        table = response["Table"]
        table_input = self._build_table_input(table)

        parameters = table_input.setdefault("Parameters", {})
        parameters.update(payload.as_flat_properties())
        parameters["dativo.lineage_json"] = json.dumps(
            payload.as_metadata(), default=str
        )

        if payload.owners:
            table_input["Owner"] = payload.owners[0]

        glue_client.update_table(DatabaseName=database, TableInput=table_input)
        return {
            "database": database,
            "table": table_name,
            "parameters_published": len(parameters),
        }

    @staticmethod
    def _build_table_input(table: Dict[str, Any]) -> Dict[str, Any]:
        """Strip read-only Glue fields."""
        skip_keys = {
            "CreateTime",
            "UpdateTime",
            "CreatedBy",
            "IsRegisteredWithLakeFormation",
            "VersionId",
            "DatabaseName",
            "CatalogId",
        }
        table_input = {k: v for k, v in table.items() if k not in skip_keys}
        if "StorageDescriptor" in table_input:
            storage_descriptor = table_input["StorageDescriptor"].copy()
            for key in ["SortColumns", "StoredAsSubDirectories"]:
                if key in storage_descriptor and storage_descriptor[key] is None:
                    storage_descriptor.pop(key)
            table_input["StorageDescriptor"] = storage_descriptor
        return table_input


class DatabricksUnityCatalogPublisher(BaseCatalogPublisher):
    """Publishes lineage into Databricks Unity Catalog using REST API."""

    def publish(self, payload: LineagePayload) -> Dict[str, Any]:
        workspace_url = (
            self.target.workspace_url
            or (self.target.connection or {}).get("workspace_url")
        )
        if not workspace_url:
            raise ValueError(
                "Databricks Unity catalog target requires 'workspace_url'"
            )
        token = (
            self.target.token or (self.target.connection or {}).get("token") or os.getenv("DATABRICKS_TOKEN")
        )
        if not token:
            raise ValueError(
                "Databricks Unity catalog target requires an access token via 'token' or environment variable DATABRICKS_TOKEN"
            )

        catalog_name = (
            self.target.catalog
            or (self.target.connection or {}).get("catalog")
            or payload.domain
        )
        schema_name = (
            self.target.schema
            or (self.target.connection or {}).get("schema")
            or payload.data_product
            or payload.domain
        )
        table_name = self.target.table or payload.asset_name
        table_full_name = ".".join(
            [
                _normalize_identifier(catalog_name, "main"),
                _normalize_identifier(schema_name, "default"),
                _normalize_identifier(table_name, payload.asset_name),
            ]
        )

        upstream_name = self.target.upstream or payload.lineage_edges["upstream"]
        endpoint = f"{workspace_url.rstrip('/')}/api/2.1/unity-catalog/lineage"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        body = {
            "table_name": table_full_name,
            "downstream": {"name": table_full_name, "type": "TABLE"},
            "upstreams": [
                {
                    "name": upstream_name,
                    "type": "EXTERNAL",
                    "dataset_type": payload.source_type,
                }
            ],
            "reporter": "dativo-ingest",
            "timestamp": payload.derived_at,
            "details": {
                "dativoMetadata": payload.as_metadata(),
                "columnsLineage": payload.columns_lineage(
                    upstream_name, table_full_name
                ),
            },
        }

        response = requests.post(
            endpoint,
            json=body,
            headers=headers,
            timeout=self.target.timeout_seconds,
        )
        response.raise_for_status()
        return {"table": table_full_name, "status_code": response.status_code}


class NessieCatalogPublisher(BaseCatalogPublisher):
    """Updates Nessie catalog table properties with lineage metadata."""

    def publish(self, payload: LineagePayload) -> Dict[str, Any]:
        target_config = self._build_target_config(payload)
        committer = IcebergCommitter(
            asset_definition=payload.asset_definition,
            target_config=target_config,
            classification_overrides=payload.classification_overrides or None,
            finops=payload.finops_overrides or None,
            governance_overrides=payload.governance_overrides or None,
            source_tags=payload.source_tags,
        )
        catalog = committer._create_catalog()
        committer._update_table_properties(
            catalog, payload.domain, payload.asset_definition.name
        )
        return {
            "table": f"{payload.domain}.{payload.asset_definition.name}",
            "branch": target_config.branch,
        }

    def _build_target_config(self, payload: LineagePayload) -> TargetConfig:
        merged_connection: Dict[str, Any] = {}
        if payload.target_config.connection:
            merged_connection.update(payload.target_config.connection)
        if self.target.connection:
            merged_connection.update(self.target.connection)

        return TargetConfig(
            type=payload.target_config.type,
            catalog=self.target.catalog or payload.target_config.catalog or "nessie",
            branch=self.target.branch or payload.target_config.branch,
            warehouse=self.target.warehouse or payload.target_config.warehouse,
            connection=merged_connection,
            file_format=payload.target_config.file_format,
        )


class OpenMetadataCatalogPublisher(BaseCatalogPublisher):
    """Publishes lineage to OpenMetadata REST API."""

    def publish(self, payload: LineagePayload) -> Dict[str, Any]:
        base_server = self.target.uri or (self.target.connection or {}).get("server")
        if not base_server:
            raise ValueError(
                "OpenMetadata catalog target requires 'uri' or connection.server"
            )
        base_uri = base_server.rstrip("/")
        token = (
            self.target.token or (self.target.connection or {}).get("token") or os.getenv("OPENMETADATA_TOKEN")
        )
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        downstream_fqn = self._build_downstream_fqn(payload)
        upstream_fqn = (
            self.target.upstream
            or f"{payload.source_type}.{payload.object_name}".lower()
        )

        lineage_edge = {
            "edge": {
                "fromEntity": {
                    "type": self.target.options.get("from_type", "Table"),
                    "fullyQualifiedName": upstream_fqn,
                },
                "toEntity": {
                    "type": self.target.options.get("to_type", "Table"),
                    "fullyQualifiedName": downstream_fqn,
                },
                "lineageDetails": {
                    "pipeline": {
                        "name": payload.job_metadata.get("asset_name", payload.asset_name),
                        "tasks": [
                            {
                                "name": "dativo_ingest",
                                "type": payload.source_type,
                                "source": payload.source_details,
                            }
                        ],
                    },
                    "columnsLineage": payload.columns_lineage(
                        upstream_fqn, downstream_fqn
                    ),
                    "dativoMetadata": payload.as_metadata(),
                },
            }
        }

        lineage_resp = requests.post(
            f"{base_uri}/v1/lineage/addLineage",
            json=lineage_edge,
            headers=headers,
            timeout=self.target.timeout_seconds,
        )
        lineage_resp.raise_for_status()
        return {
            "downstream": downstream_fqn,
            "status_code": lineage_resp.status_code,
        }

    def _build_downstream_fqn(self, payload: LineagePayload) -> str:
        service = self.target.service or (self.target.connection or {}).get("service")
        database = self.target.database or payload.domain
        schema = self.target.schema or payload.data_product or payload.domain
        table = self.target.table or payload.asset_name
        parts = [
            _normalize_identifier(service, payload.target_type or "lake"),
            _normalize_identifier(database, payload.domain),
            _normalize_identifier(schema, payload.data_product or payload.domain),
            _normalize_identifier(table, payload.asset_name),
        ]
        return ".".join(parts)


def _create_publisher(target: CatalogTargetConfig) -> BaseCatalogPublisher:
    """Factory for catalog publishers."""
    mapping = {
        "aws_glue": AwsGlueCatalogPublisher,
        "databricks_unity": DatabricksUnityCatalogPublisher,
        "nessie": NessieCatalogPublisher,
        "openmetadata": OpenMetadataCatalogPublisher,
    }
    publisher_cls = mapping.get(target.type)
    if not publisher_cls:
        raise ValueError(f"Unsupported catalog target type: {target.type}")
    return publisher_cls(target)


class DataCatalogDispatcher:
    """Coordinates publishing lineage to multiple targets."""

    def __init__(self, catalog_config: CatalogConfig):
        self.catalog_config = catalog_config
        self.publishers = [
            _create_publisher(target) for target in catalog_config.enabled_targets()
        ]

    def publish(self, payload: LineagePayload) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for publisher in self.publishers:
            target_name = publisher.target.name or publisher.target.type
            try:
                response = publisher.publish(payload)
                results.append(
                    {"target": target_name, "status": "success", "response": response}
                )
            except Exception as exc:  # pragma: no cover - network failures
                logger.warning(
                    "Lineage publishing failed",
                    extra={"catalog_target": target_name, "error": str(exc)},
                )
                results.append(
                    {"target": target_name, "status": "error", "error": str(exc)}
                )
        return results


def publish_catalog_lineage(
    job_config: JobConfig,
    asset_definition: AssetDefinition,
    source_config: SourceConfig,
    target_config: TargetConfig,
    file_metadata: List[Dict[str, Any]],
    commit_result: Optional[Dict[str, Any]],
    totals: Dict[str, Any],
    source_tags: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Entry point for CLI to publish lineage when catalog block is configured."""
    if not job_config.catalog:
        return []
    targets = job_config.catalog.enabled_targets()
    if not targets:
        return []

    payload = build_lineage_payload(
        job_config=job_config,
        asset_definition=asset_definition,
        source_config=source_config,
        target_config=target_config,
        file_metadata=file_metadata,
        commit_result=commit_result,
        totals=totals,
        source_tags=source_tags,
    )
    dispatcher = DataCatalogDispatcher(job_config.catalog)
    return dispatcher.publish(payload)
