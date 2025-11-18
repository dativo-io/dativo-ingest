"""Data catalog synchronization helpers."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Sequence, Callable

import requests
from requests import Session

from .config import (
    AssetDefinition,
    TargetConfig,
    BaseDataCatalogConfig,
    OpenMetadataCatalogConfig,
    AwsGlueCatalogConfig,
)


class DataCatalogSyncError(Exception):
    """Raised when data catalog synchronization fails."""


class DataCatalogSyncManager:
    """Synchronizes asset metadata with configured data catalogs."""

    def __init__(
        self,
        asset_definition: AssetDefinition,
        target_config: TargetConfig,
        output_base_path: str,
        catalog_configs: Sequence[BaseDataCatalogConfig],
        logger: Optional[logging.Logger] = None,
        http_session_factory: Callable[[], Session] = requests.Session,
        glue_client_factory: Optional[Callable[[AwsGlueCatalogConfig], Any]] = None,
    ):
        self.asset_definition = asset_definition
        self.target_config = target_config
        self.output_base_path = output_base_path
        self.catalog_configs = catalog_configs
        self.logger = logger or logging.getLogger(__name__)
        self.http_session_factory = http_session_factory
        self.glue_client_factory = glue_client_factory or self._default_glue_client_factory

    def sync(self) -> None:
        """Sync metadata to all configured data catalogs."""
        for catalog_config in self.catalog_configs:
            if not catalog_config.enabled:
                self.logger.debug(
                    "Skipping disabled data catalog",
                    extra={"catalog_type": catalog_config.type, "catalog_name": catalog_config.name},
                )
                continue

            if isinstance(catalog_config, OpenMetadataCatalogConfig):
                self._sync_openmetadata(catalog_config)
            elif isinstance(catalog_config, AwsGlueCatalogConfig):
                self._sync_aws_glue(catalog_config)
            else:
                self.logger.warning(
                    "Unsupported data catalog type",
                    extra={"catalog_type": catalog_config.type},
                )

    # ---- OpenMetadata helpers -------------------------------------------------

    def _sync_openmetadata(self, config: OpenMetadataCatalogConfig) -> None:
        session = self.http_session_factory()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "dativo-ingest/1.0",
        }

        auth_token = self._expand_env_var(config.auth_token)
        if auth_token:
            header_name = config.auth_header_name or "Authorization"
            scheme = config.auth_scheme or ""
            headers[header_name] = f"{scheme} {auth_token}".strip()

        session.headers.update(headers)

        base_url = self._expand_env_var(config.server_url).rstrip("/")
        api_prefix = f"{base_url}/api/{config.api_version}"
        schema_fqn = f"{config.service_name}.{config.database}.{config.schema_name}"
        table_name = config.table_name or self._normalized_asset_name()
        table_fqn = f"{schema_fqn}.{table_name}"

        try:
            schema_resp = session.get(
                f"{api_prefix}/databaseSchemas/name/{schema_fqn}",
                timeout=config.timeout_seconds,
                verify=config.verify_ssl,
            )
            schema_resp.raise_for_status()
        except Exception as exc:
            self.logger.warning(
                "Failed to resolve OpenMetadata database schema",
                extra={
                    "catalog_type": "openmetadata",
                    "schema_fqn": schema_fqn,
                    "error": str(exc),
                },
            )
            return

        schema_entity = schema_resp.json()
        schema_ref = {
            "id": schema_entity.get("id"),
            "type": "databaseSchema",
            "name": schema_entity.get("name"),
            "fullyQualifiedName": schema_entity.get("fullyQualifiedName"),
        }

        if not schema_ref["id"]:
            self.logger.warning(
                "OpenMetadata schema response missing id",
                extra={"catalog_type": "openmetadata", "schema_fqn": schema_fqn},
            )
            return

        table_payload = {
            "name": table_name,
            "tableType": "Regular",
            "description": config.description
            or (self.asset_definition.description.purpose if self.asset_definition.description else None),
            "columns": self._build_openmetadata_columns(table_fqn),
            "databaseSchema": schema_ref,
            "tags": self._build_openmetadata_tags(config),
            "customProperties": self._build_openmetadata_custom_properties(config),
        }

        try:
            put_resp = session.put(
                f"{api_prefix}/tables/name/{table_fqn}",
                data=json.dumps(table_payload),
                timeout=config.timeout_seconds,
                verify=config.verify_ssl,
            )
            if put_resp.status_code not in (200, 201):
                self.logger.warning(
                    "OpenMetadata table sync returned non-success status",
                    extra={
                        "catalog_type": "openmetadata",
                        "status_code": put_resp.status_code,
                        "body": put_resp.text,
                    },
                )
                return

            self.logger.info(
                "Synchronized table with OpenMetadata",
                extra={
                    "catalog_type": "openmetadata",
                    "table_fqn": table_fqn,
                },
            )
        except Exception as exc:
            self.logger.warning(
                "Failed to sync table with OpenMetadata",
                extra={
                    "catalog_type": "openmetadata",
                    "table_fqn": table_fqn,
                    "error": str(exc),
                },
            )

    def _build_openmetadata_columns(self, table_fqn: str) -> List[Dict[str, Any]]:
        columns = []
        for field_def in self.asset_definition.schema:
            column_name = field_def["name"]
            data_type = self._map_openmetadata_type(field_def.get("type"))
            column = {
                "name": column_name,
                "displayName": column_name,
                "dataType": data_type,
                "dataTypeDisplay": data_type,
                "description": field_def.get("description"),
                "fullyQualifiedName": f"{table_fqn}.{column_name}",
                "tags": self._build_column_tags(field_def),
            }
            columns.append(column)
        return columns

    def _build_openmetadata_tags(
        self, config: OpenMetadataCatalogConfig
    ) -> List[Dict[str, str]]:
        tags = config.tags or self.asset_definition.tags or []
        return [{"tagFQN": tag} for tag in tags]

    def _build_column_tags(self, field_def: Dict[str, Any]) -> List[Dict[str, str]]:
        classification = field_def.get("classification")
        if not classification:
            return []

        if isinstance(classification, list):
            tags = classification
        else:
            tags = [classification]

        return [{"tagFQN": tag} for tag in tags]

    def _build_openmetadata_custom_properties(
        self, config: OpenMetadataCatalogConfig
    ) -> Dict[str, Any]:
        properties: Dict[str, Any] = {
            "source_system": self.asset_definition.source_type,
            "dativo_domain": self.asset_definition.domain or "default",
            "dativo_data_product": self.asset_definition.dataProduct or "default",
        }

        owner = config.owner or getattr(self.asset_definition.team, "owner", None)
        if owner:
            properties["owner"] = owner

        return properties

    def _map_openmetadata_type(self, field_type: Optional[str]) -> str:
        type_map = {
            "string": "STRING",
            "integer": "INT",
            "int": "INT",
            "bigint": "BIGINT",
            "float": "FLOAT",
            "double": "DOUBLE",
            "numeric": "NUMERIC",
            "boolean": "BOOLEAN",
            "timestamp": "TIMESTAMP",
            "datetime": "TIMESTAMP",
            "date": "DATE",
        }
        return type_map.get((field_type or "").lower(), "STRING")

    # ---- AWS Glue helpers -----------------------------------------------------

    def _sync_aws_glue(self, config: AwsGlueCatalogConfig) -> None:
        table_name = config.table_name or self._normalized_asset_name()
        location = config.storage_location or self.output_base_path
        location = location if location.endswith("/") else f"{location}/"

        columns = self._build_glue_columns()
        partition_keys = self._build_glue_partitions()

        storage_descriptor = {
            "Columns": columns,
            "Location": location,
            "Compressed": False,
            "NumberOfBuckets": -1,
            "SerdeInfo": {
                "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe",
                "Parameters": {"serialization.format": "1"},
            },
            "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
            "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
            "Parameters": (config.storage_parameters or {}),
        }

        table_input = {
            "Name": table_name,
            "Description": config.description
            or (self.asset_definition.description.purpose if self.asset_definition.description else None)
            or f"Dativo-ingest table for {self.asset_definition.name}",
            "TableType": "EXTERNAL_TABLE",
            "Parameters": {"classification": config.classification, **(config.table_parameters or {})},
            "PartitionKeys": partition_keys,
            "StorageDescriptor": storage_descriptor,
        }

        glue_client = self.glue_client_factory(config)
        kwargs = {"DatabaseName": config.database, "TableInput": table_input}
        if config.catalog_id:
            kwargs["CatalogId"] = config.catalog_id

        try:
            glue_client.get_table(
                DatabaseName=config.database,
                Name=table_name,
                **({"CatalogId": config.catalog_id} if config.catalog_id else {}),
            )
            glue_client.update_table(**kwargs)
            action = "updated"
        except glue_client.exceptions.EntityNotFoundException:  # type: ignore[attr-defined]
            glue_client.create_table(**kwargs)
            action = "created"
        except Exception as exc:
            self.logger.warning(
                "Failed to sync AWS Glue table",
                extra={
                    "catalog_type": "aws_glue",
                    "database": config.database,
                    "table_name": table_name,
                    "error": str(exc),
                },
            )
            return

        self.logger.info(
            "AWS Glue table synchronized",
            extra={
                "catalog_type": "aws_glue",
                "action": action,
                "database": config.database,
                "table_name": table_name,
            },
        )

    def _build_glue_columns(self) -> List[Dict[str, Any]]:
        columns = []
        for field_def in self.asset_definition.schema:
            glue_type = self._map_glue_type(field_def.get("type"))
            columns.append(
                {
                    "Name": field_def["name"],
                    "Type": glue_type,
                    "Comment": field_def.get("description"),
                }
            )
        return columns

    def _build_glue_partitions(self) -> List[Dict[str, Any]]:
        partition_columns = self.target_config.partitioning or []
        return [{"Name": col, "Type": "string"} for col in partition_columns]

    def _map_glue_type(self, field_type: Optional[str]) -> str:
        mapping = {
            "string": "string",
            "integer": "bigint",
            "int": "int",
            "bigint": "bigint",
            "float": "double",
            "double": "double",
            "numeric": "double",
            "boolean": "boolean",
            "timestamp": "timestamp",
            "datetime": "timestamp",
            "date": "date",
        }
        return mapping.get((field_type or "").lower(), "string")

    def _default_glue_client_factory(self, config: AwsGlueCatalogConfig):
        import boto3

        session = boto3.session.Session(region_name=config.region or os.getenv("AWS_REGION"))
        return session.client("glue")

    # ---- Utility helpers ------------------------------------------------------

    def _normalized_asset_name(self) -> str:
        return (
            self.asset_definition.name.lower()
            .replace(" ", "_")
            .replace("-", "_")
        )

    def _expand_env_var(self, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return os.path.expandvars(value)

