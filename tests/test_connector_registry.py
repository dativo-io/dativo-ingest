"""Unit tests for ConnectorRegistryService."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from dativo_ingest.registry.connector_registry import ConnectorRegistryService


@pytest.fixture()
def registry_file(tmp_path: Path) -> Path:
    """Create a temporary registry file."""
    registry_path = tmp_path / "connectors.yaml"
    data = {
        "version": 3,
        "connectors": {
            "test_airbyte": {
                "roles": ["source"],
                "category": "api",
                "default_engine": "airbyte",
                "engines_supported": ["airbyte"],
                "source_of_truth": "airbyte",
                "external_id": "source-test",
                "docker_image_default": "airbyte/source-test",
                "version_default": "0.1.0",
                "allowed_in_cloud": True,
                "supports_incremental": True,
            }
        },
    }
    registry_path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return registry_path


@pytest.fixture()
def catalog_dir(tmp_path: Path) -> Path:
    """Create a temporary catalog directory."""
    directory = tmp_path / "catalogs"
    directory.mkdir()
    catalog_data = {
        "sources": [
            {
                "name": "Test Airbyte",
                "dockerRepository": "airbyte/source-test",
                "dockerImageTag": "1.2.3",
                "supportLevel": "certified",
                "releaseStage": "generally_available",
            }
        ]
    }
    (directory / "airbyte.json").write_text(json.dumps(catalog_data), encoding="utf-8")
    return directory


def test_resolve_engine_defaults_uses_catalog(registry_file: Path, catalog_dir: Path):
    """Ensure catalog metadata overrides registry defaults when available."""
    service = ConnectorRegistryService(registry_path=registry_file, catalog_dir=catalog_dir)
    engine = {"type": "airbyte", "options": {}}
    resolved = service.resolve_engine_defaults("test_airbyte", engine)
    assert resolved is not None
    airbyte_opts = resolved["options"]["airbyte"]
    assert airbyte_opts["docker_image"] == "airbyte/source-test:1.2.3"
    assert airbyte_opts["version"] == "1.2.3"
    assert airbyte_opts["docker_repository"] == "airbyte/source-test"


def test_resolve_engine_defaults_registry_fallback(registry_file: Path, tmp_path: Path):
    """When catalog missing, fall back to registry-defined defaults."""
    catalog_dir = tmp_path / "empty"
    catalog_dir.mkdir()
    service = ConnectorRegistryService(registry_path=registry_file, catalog_dir=catalog_dir)
    resolved = service.resolve_engine_defaults("test_airbyte", {"type": "airbyte", "options": {}})
    airbyte_opts = resolved["options"]["airbyte"]
    assert airbyte_opts["docker_image"] == "airbyte/source-test:0.1.0"
    assert airbyte_opts["version"] == "0.1.0"


def test_job_override_preserved(registry_file: Path, catalog_dir: Path):
    """Job-level overrides should win over catalog defaults."""
    service = ConnectorRegistryService(registry_path=registry_file, catalog_dir=catalog_dir)
    job_override = {
        "type": "airbyte",
        "options": {"airbyte": {"docker_image": "custom/image:dev"}},
    }
    resolved = service.resolve_engine_defaults(
        "test_airbyte", {"type": "airbyte", "options": {}}, job_engine_override=job_override
    )
    airbyte_opts = resolved["options"]["airbyte"]
    assert airbyte_opts["docker_image"] == "custom/image:dev"
    # version still comes from catalog even though image overridden
    assert airbyte_opts["version"] == "1.2.3"
