"""Utilities for exporting ODCS and dbt metadata from Specs-as-Code contracts."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .config import AssetDefinition


@dataclass(frozen=True)
class MetadataPaths:
    """Metadata file locations generated for a contract."""

    odcs: Path
    dbt: Path


def _slugify(value: str) -> str:
    """Normalize a string for safe filesystem usage."""
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value.strip().lower())
    return slug.strip("_") or "contract"


def _unique(values: List[str]) -> List[str]:
    """Return a list with duplicates removed while preserving order."""
    seen = set()
    unique_values: List[str] = []
    for value in values:
        if value is None:
            continue
        key = value.lower()
        if key not in seen:
            seen.add(key)
            unique_values.append(value)
    return unique_values


class MetadataExporter:
    """Generate ODCS JSON and dbt YAML metadata from an AssetDefinition."""

    def __init__(
        self,
        asset: AssetDefinition,
        base_dir: Optional[Path | str] = None,
    ) -> None:
        self.asset = asset
        base = Path(base_dir) if base_dir else Path(os.getenv("DATIVO_METADATA_DIR", "metadata"))
        self.base_dir = base.resolve()

        self._slug = _slugify(self.asset.name)
        major, minor, patch = self.asset.version.split(".")
        self._major = major
        self._minor = minor
        self._patch = patch

    # ------------------------------------------------------------------ Builders
    def build_odcs_payload(self) -> Dict[str, Any]:
        """Return ODCS-compliant JSON payload for the contract."""
        payload = self.asset.model_dump(mode="json", exclude_none=True)
        payload["$schema"] = payload.pop(
            "schema_ref",
            "schemas/odcs/dativo-odcs-3.0.2-extended.schema.json",
        )
        return payload

    def build_dbt_payload(self) -> Dict[str, Any]:
        """Return dbt YAML payload capturing sources, models, and exposures."""
        classification = self.asset.compliance.classification if self.asset.compliance else []
        tags = _unique(list(self.asset.tags or []) + list(classification or []))

        source_name = self.asset.name
        table_name = self.asset.name
        description = ""
        if self.asset.description:
            description = (
                self.asset.description.purpose
                or self.asset.description.usage
                or ""
            )

        # Source metadata
        source_meta: Dict[str, Any] = {
            "owner": self.asset.team.owner,
            "classification": classification,
            "retention_days": self.asset.compliance.retention_days if self.asset.compliance else None,
            "cost_center": self.asset.finops.cost_center,
            "contract_version": self.asset.version,
            "governance_status": self.asset.governance_status,
        }
        source_meta = {k: v for k, v in source_meta.items() if v is not None}

        database = None
        schema = None
        if self.asset.target:
            database = self.asset.target.get("catalog") or self.asset.target.get("warehouse")
            schema = self.asset.target.get("schema") or self.asset.target.get("database")
        if not database:
            database = self.asset.tenant or "dativo"
        if not schema:
            schema = self.asset.domain or self.asset.dataProduct or "public"

        source_columns: List[Dict[str, Any]] = []
        for field in self.asset.schema:
            column_meta = {
                "type": field.get("type"),
                "required": field.get("required", False),
            }
            if "classification" in field:
                column_meta["classification"] = field["classification"]
            column_tests: List[Any] = []
            if field.get("required"):
                column_tests.append("not_null")
            column_entry = {
                "name": field["name"],
                "description": field.get("description") or "",
                "meta": column_meta,
            }
            if column_tests:
                column_entry["tests"] = column_tests
            source_columns.append(column_entry)

        source_entry = {
            "name": source_name,
            "description": description,
            "database": database,
            "schema": schema,
            "tags": tags,
            "meta": source_meta,
            "tables": [
                {
                    "name": table_name,
                    "identifier": table_name,
                    "description": self.asset.description.usage if self.asset.description else "",
                    "columns": source_columns,
                }
            ],
        }

        # Model metadata (staging representation)
        model_meta = {
            "source_type": self.asset.source_type,
            "contract_version": self.asset.version,
            "classification": classification,
            "cost_center": self.asset.finops.cost_center,
        }

        model_columns = [
            {
                "name": field["name"],
                "description": field.get("description") or "",
                "meta": {
                    "type": field.get("type"),
                    "required": field.get("required", False),
                },
            }
            for field in self.asset.schema
        ]

        model_entry = {
            "name": f"{self.asset.name}_staging",
            "description": self.asset.description.usage if self.asset.description else "",
            "tags": tags,
            "meta": {k: v for k, v in model_meta.items() if v is not None},
            "columns": model_columns,
        }

        # Exposure metadata for catalog & AI usage
        exposure_meta = {
            "classification": classification,
            "retention_days": self.asset.compliance.retention_days if self.asset.compliance else None,
            "cost_center": self.asset.finops.cost_center,
            "contract_version": self.asset.version,
            "governance_status": self.asset.governance_status,
            "lineage": [edge.model_dump(mode="json") for edge in self.asset.lineage],
        }
        exposure_meta = {k: v for k, v in exposure_meta.items() if v is not None}

        exposure_entry = {
            "name": f"{self.asset.name}_contract",
            "type": "analysis",
            "owner": {
                "name": self.asset.team.owner,
                "email": self.asset.team.owner,
            },
            "maturity": "medium",
            "depends_on": [
                f"source('{source_name}', '{table_name}')",
            ],
            "description": description,
            "tags": tags,
            "meta": exposure_meta,
        }

        return {
            "version": 2,
            "sources": [source_entry],
            "models": [model_entry],
            "exposures": [exposure_entry],
        }

    # ------------------------------------------------------------------ Writers
    def write(self) -> MetadataPaths:
        """Write ODCS JSON and dbt YAML metadata to disk."""
        odcs_payload = self.build_odcs_payload()
        dbt_payload = self.build_dbt_payload()

        odcs_path = self._build_output_path(
            category="odcs",
            extension=".json",
        )
        dbt_path = self._build_output_path(
            category="dbt",
            extension=".yml",
        )

        self._atomic_write_json(odcs_path, odcs_payload)
        self._atomic_write_yaml(dbt_path, dbt_payload)
        self._update_manifest(odcs_path, dbt_path)
        return MetadataPaths(odcs=odcs_path, dbt=dbt_path)

    # ------------------------------------------------------------------ Helpers
    def _build_output_path(self, category: str, extension: str) -> Path:
        """Construct an output path factoring source type and version."""
        version_dir = f"v{self._major}.{self._minor}"
        filename = f"{self._slug}_v{self._major}_{self._minor}_{self._patch}{extension}"
        return (
            self.base_dir
            / category
            / self.asset.source_type
            / version_dir
            / filename
        ).resolve()

    def _atomic_write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        """Write JSON atomically."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        tmp_path.replace(path)

    def _atomic_write_yaml(self, path: Path, payload: Dict[str, Any]) -> None:
        """Write YAML atomically."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(payload, handle, sort_keys=False)
        tmp_path.replace(path)

    def _update_manifest(self, odcs_path: Path, dbt_path: Path) -> None:
        """Update metadata manifest with latest contract information."""
        manifest_path = self.base_dir / "manifest.json"
        contracts: Dict[str, Any] = {}

        if manifest_path.exists():
            try:
                with manifest_path.open("r", encoding="utf-8") as handle:
                    existing = json.load(handle)
                    contracts = existing.get("contracts", {})
            except json.JSONDecodeError:
                contracts = {}

        relative_odcs = os.path.relpath(odcs_path, self.base_dir)
        relative_dbt = os.path.relpath(dbt_path, self.base_dir)

        contracts[self.asset.id] = {
            "name": self.asset.name,
            "source_type": self.asset.source_type,
            "version": self.asset.version,
            "paths": {
                "odcs": relative_odcs,
                "dbt": relative_dbt,
            },
            "classification": self.asset.compliance.classification if self.asset.compliance else [],
            "owner": self.asset.team.owner,
            "governance_status": self.asset.governance_status,
            "cost_center": self.asset.finops.cost_center,
        }

        manifest_payload = {
            "version": 1,
            "updated_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            "contracts": contracts,
        }
        self._atomic_write_json(manifest_path, manifest_payload)


__all__ = ["MetadataExporter", "MetadataPaths"]
