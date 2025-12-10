"""Connector registry loader with optional external catalog enrichment."""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


@dataclass
class CatalogEntry:
    """Normalized external catalog entry."""

    name: str
    source: str
    external_id: Optional[str] = None
    docker_image_default: Optional[str] = None
    version_default: Optional[str] = None
    capabilities: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def slug(self) -> Optional[str]:
        """Return canonical slug (typically final segment of docker repo)."""
        if self.external_id:
            return self.external_id
        if self.docker_image_default:
            return self.docker_image_default.split("/")[-1]
        return None


class ConnectorRegistryService:
    """Loads connector registry metadata and merges external catalog data."""

    def __init__(
        self,
        registry_path: Optional[Path] = None,
        catalog_dir: Optional[Path] = None,
    ):
        self.registry_path = self._resolve_registry_path(registry_path)
        self.catalog_dir = self._resolve_catalog_dir(catalog_dir)
        self._registry_cache: Optional[Dict[str, Any]] = None
        self._catalog_entries: Optional[List[CatalogEntry]] = None
        self._catalog_index: Optional[Dict[str, Dict[str, CatalogEntry]]] = None

    # ------------------------------------------------------------------ #
    # Path resolution helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _resolve_registry_path(override: Optional[Path]) -> Optional[Path]:
        candidates: List[Path] = []
        if override:
            candidates.append(Path(override))
        env_path = os.getenv("DATIVO_CONNECTOR_REGISTRY_PATH")
        if env_path:
            candidates.append(Path(env_path))
        candidates.extend(
            [
                Path("/app/registry/connectors.yaml"),
                Path("registry/connectors.yaml"),
            ]
        )
        for candidate in candidates:
            if candidate and candidate.exists():
                return candidate
        return candidates[-1] if candidates else None

    @staticmethod
    def _resolve_catalog_dir(override: Optional[Path]) -> Path:
        candidates: List[Path] = []
        if override:
            candidates.append(Path(override))
        env_path = os.getenv("DATIVO_CONNECTOR_CATALOG_DIR")
        if env_path:
            candidates.append(Path(env_path))
        candidates.extend(
            [
                Path("/app/registry/catalogs"),
                Path("registry/catalogs"),
            ]
        )
        for candidate in candidates:
            if candidate and candidate.exists():
                return candidate
        # Default to last candidate even if it doesn't exist yet
        return candidates[-1] if candidates else Path("registry/catalogs")

    # ------------------------------------------------------------------ #
    # Registry + catalog loaders
    # ------------------------------------------------------------------ #
    def _load_registry(self) -> Dict[str, Any]:
        if self._registry_cache is None:
            if not self.registry_path or not self.registry_path.exists():
                self._registry_cache = {}
            else:
                with open(self.registry_path, "r", encoding="utf-8") as handle:
                    self._registry_cache = yaml.safe_load(handle) or {}
        return self._registry_cache

    def _load_catalog_entries(self) -> List[CatalogEntry]:
        if self._catalog_entries is not None:
            return self._catalog_entries

        entries: List[CatalogEntry] = []
        if self.catalog_dir and self.catalog_dir.exists():
            for catalog_file in sorted(self.catalog_dir.glob("*.json")):
                entries.extend(self._parse_catalog_file(catalog_file))
        self._catalog_entries = entries
        return entries

    def _build_catalog_index(self) -> Dict[str, Dict[str, CatalogEntry]]:
        if self._catalog_index is not None:
            return self._catalog_index

        index: Dict[str, Dict[str, CatalogEntry]] = {
            "by_slug": {},
            "by_repo": {},
            "by_name": {},
        }
        for entry in self._load_catalog_entries():
            if entry.slug:
                index["by_slug"][entry.slug.lower()] = entry
            if entry.docker_image_default:
                repo_key = entry.docker_image_default.lower()
                index["by_repo"][repo_key] = entry
            if entry.name:
                index["by_name"][entry.name.lower()] = entry
        self._catalog_index = index
        return index

    # ------------------------------------------------------------------ #
    # External catalog parsing
    # ------------------------------------------------------------------ #
    def _parse_catalog_file(self, path: Path) -> List[CatalogEntry]:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, OSError):
            return []

        if "sources" in data:  # Airbyte registry
            return self._normalize_airbyte_catalog(data)

        return []

    @staticmethod
    def _normalize_airbyte_catalog(data: Dict[str, Any]) -> List[CatalogEntry]:
        entries: List[CatalogEntry] = []
        for item in data.get("sources", []):
            repo = item.get("dockerRepository")
            version = item.get("dockerImageTag")
            slug = None
            if repo:
                slug = repo.split("/")[-1]

            capabilities: List[str] = []
            for key in ("releaseStage", "supportLevel", "sourceType"):
                value = item.get(key)
                if value:
                    capabilities.append(f"{key}:{value}")
            if item.get("tags"):
                capabilities.extend(item["tags"])
            ab_internal = item.get("ab_internal") or {}
            for meta_key in ("connectorSubtype", "connectorType"):
                value = ab_internal.get(meta_key)
                if value:
                    capabilities.append(f"{meta_key}:{value}")

            entries.append(
                CatalogEntry(
                    name=item.get("name") or slug or "unknown",
                    source="airbyte",
                    external_id=slug,
                    docker_image_default=repo,
                    version_default=version,
                    capabilities=capabilities,
                    raw=item,
                )
            )
        return entries

    # ------------------------------------------------------------------ #
    # Public helpers
    # ------------------------------------------------------------------ #
    def list_connectors(self) -> Dict[str, Any]:
        """Return raw connectors dictionary (new registry format)."""
        registry = self._load_registry()
        return registry.get("connectors") or registry.get("sources") or {}

    def get_connector_definition(self, name: str) -> Optional[Dict[str, Any]]:
        """Get connector definition by name."""
        connectors = self.list_connectors()
        return connectors.get(name)

    def get_connector_metadata(self, name: str) -> Optional[Dict[str, Any]]:
        """Return summarized metadata for CLI inspection."""
        connector_def = self.get_connector_definition(name)
        if not connector_def:
            return None

        engine_dict = self._normalize_engine_config(connector_def.get("default_engine"))
        resolved_engine, catalog_entry = self._apply_engine_defaults(
            name, engine_dict, job_engine_override=None
        )
        airbyte_opts = (
            (resolved_engine or {}).get("options", {}).get("airbyte", {}) if resolved_engine else {}
        )

        docker_image = airbyte_opts.get("docker_image")
        docker_repo = airbyte_opts.get("docker_repository") or connector_def.get(
            "docker_image_default"
        )
        version = airbyte_opts.get("version") or connector_def.get("version_default")

        metadata = {
            "name": name,
            "category": connector_def.get("category"),
            "roles": connector_def.get("roles"),
            "default_engine": connector_def.get("default_engine"),
            "source_of_truth": connector_def.get("source_of_truth", "native"),
            "external_id": connector_def.get("external_id"),
            "docker_repository": docker_repo,
            "docker_image": docker_image,
            "version": version,
            "catalog_source": catalog_entry.source if catalog_entry else "registry",
            "capabilities": (
                catalog_entry.capabilities if catalog_entry else connector_def.get("objects_supported", [])
            ),
            "allows_cloud": connector_def.get("allowed_in_cloud", True),
            "supports_incremental": connector_def.get("supports_incremental"),
        }
        return metadata

    def resolve_engine_defaults(
        self,
        connector_type: str,
        current_engine: Optional[Dict[str, Any]],
        job_engine_override: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Resolve engine defaults with catalog + registry fallback."""
        resolved_engine, _ = self._apply_engine_defaults(
            connector_type, current_engine, job_engine_override
        )
        return resolved_engine

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _normalize_engine_config(engine_value: Any) -> Optional[Dict[str, Any]]:
        if engine_value is None:
            return None
        if isinstance(engine_value, dict):
            engine_dict = copy.deepcopy(engine_value)
            engine_dict.setdefault("options", {})
            return engine_dict
        return {"type": engine_value, "options": {}}

    @staticmethod
    def _get_engine_type(engine_dict: Optional[Dict[str, Any]]) -> Optional[str]:
        if not engine_dict:
            return None
        engine_type = engine_dict.get("type")
        if engine_type:
            return str(engine_type)
        return None

    def _apply_engine_defaults(
        self,
        connector_type: str,
        engine_dict: Optional[Dict[str, Any]],
        job_engine_override: Optional[Dict[str, Any]],
    ) -> Tuple[Optional[Dict[str, Any]], Optional[CatalogEntry]]:
        if engine_dict is None or not isinstance(engine_dict, dict):
            return engine_dict, None

        working_engine = copy.deepcopy(engine_dict)
        options = working_engine.setdefault("options", {})
        engine_type = self._get_engine_type(working_engine)
        catalog_entry: Optional[CatalogEntry] = None

        if engine_type == "airbyte":
            connector_def = self.get_connector_definition(connector_type) or {}
            catalog_entry = self._match_catalog_entry(connector_type, connector_def)
            self._merge_airbyte_defaults(
                working_engine,
                connector_def,
                catalog_entry,
                job_engine_override,
            )

        return working_engine, catalog_entry

    def _match_catalog_entry(
        self, connector_name: str, connector_def: Dict[str, Any]
    ) -> Optional[CatalogEntry]:
        index = self._build_catalog_index()
        search_keys: List[str] = []

        external_id = connector_def.get("external_id")
        docker_repo = connector_def.get("docker_image_default")

        if external_id:
            search_keys.append(external_id.lower())
        if docker_repo:
            repo_key = docker_repo.lower()
            search_keys.append(repo_key)
            search_keys.append(repo_key.split("/")[-1])

        for key in search_keys:
            if key in index["by_slug"]:
                return index["by_slug"][key]
            if key in index["by_repo"]:
                return index["by_repo"][key]

        name_key = connector_name.lower()
        return index["by_name"].get(name_key)

    def _merge_airbyte_defaults(
        self,
        engine_dict: Dict[str, Any],
        connector_def: Dict[str, Any],
        catalog_entry: Optional[CatalogEntry],
        job_engine_override: Optional[Dict[str, Any]],
    ) -> None:
        options = engine_dict.setdefault("options", {})
        airbyte_opts = options.setdefault("airbyte", {})
        override_opts = self._extract_airbyte_override(job_engine_override)

        repo = (
            airbyte_opts.get("docker_repository")
            or connector_def.get("docker_image_default")
            or (catalog_entry.docker_image_default if catalog_entry else None)
        )
        version = (
            airbyte_opts.get("version")
            or override_opts.get("version")
            or (catalog_entry.version_default if catalog_entry else None)
            or connector_def.get("version_default")
        )

        if self._has_value(override_opts, "docker_repository"):
            repo = override_opts["docker_repository"]
            airbyte_opts["docker_repository"] = repo

        if self._has_value(override_opts, "version"):
            version = override_opts["version"]
            airbyte_opts["version"] = version

        if self._has_value(override_opts, "docker_image"):
            airbyte_opts["docker_image"] = override_opts["docker_image"]

        if not self._has_value(airbyte_opts, "docker_repository") and repo:
            airbyte_opts["docker_repository"] = repo

        if not self._has_value(airbyte_opts, "docker_image"):
            docker_image = self._compose_docker_image(repo, version)
            if docker_image:
                airbyte_opts["docker_image"] = docker_image

        if version and not self._has_value(airbyte_opts, "version"):
            airbyte_opts["version"] = version

        if catalog_entry and catalog_entry.capabilities:
            airbyte_opts.setdefault("capabilities", catalog_entry.capabilities)

    @staticmethod
    def _compose_docker_image(
        repository: Optional[str], version: Optional[str]
    ) -> Optional[str]:
        if not repository:
            return None
        if version:
            return f"{repository}:{version}"
        return repository

    @staticmethod
    def _extract_airbyte_override(
        job_engine_override: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if (
            isinstance(job_engine_override, dict)
            and isinstance(job_engine_override.get("options"), dict)
        ):
            airbyte_override = job_engine_override["options"].get("airbyte")
            if isinstance(airbyte_override, dict):
                return airbyte_override
        return {}

    @staticmethod
    def _has_value(options: Dict[str, Any], key: str) -> bool:
        value = options.get(key)
        return value is not None and value != ""


# ---------------------------------------------------------------------- #
# Module-level helpers / caching
# ---------------------------------------------------------------------- #
_REGISTRY_SINGLETON: Optional[ConnectorRegistryService] = None


def get_connector_registry(
    registry_path: Optional[Path] = None,
    catalog_dir: Optional[Path] = None,
) -> ConnectorRegistryService:
    """Return cached registry service (or new instance when overrides provided)."""
    global _REGISTRY_SINGLETON
    if registry_path or catalog_dir:
        return ConnectorRegistryService(registry_path=registry_path, catalog_dir=catalog_dir)

    if _REGISTRY_SINGLETON is None:
        _REGISTRY_SINGLETON = ConnectorRegistryService()
    return _REGISTRY_SINGLETON


def reset_connector_registry_cache() -> None:
    """Reset cached registry service (useful for tests)."""
    global _REGISTRY_SINGLETON
    _REGISTRY_SINGLETON = None
