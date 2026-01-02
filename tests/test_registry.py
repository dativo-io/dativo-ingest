"""Tests for connector registry and catalog loading."""

import json
import tempfile
from pathlib import Path

import pytest

from src.dativo_ingest.registry import (
    CatalogLoader,
    ConnectorRegistry,
    ExternalConnector,
    RegistryLoadError,
    RegistryNotFoundError,
    ResolvedConnector,
    resolve_image_and_version,
)


class TestCatalogLoader:
    """Test external catalog loading."""

    def test_catalog_loader_no_catalogs(self, tmp_path):
        """Test catalog loader with no catalog files."""
        loader = CatalogLoader(catalogs_dir=tmp_path)
        assert loader.catalogs == {}
        assert not loader.has_catalogs()
        assert loader.get_catalog_names() == []

    def test_catalog_loader_airbyte_format(self, tmp_path):
        """Test loading Airbyte catalog format."""
        catalog_data = {
            "sources": [
                {
                    "sourceDefinitionId": "test-id-123",
                    "name": "Test Connector",
                    "dockerRepository": "airbyte/source-test",
                    "dockerImageTag": "1.0.0",
                    "documentationUrl": "https://example.com",
                    "supportLevel": "certified",
                }
            ]
        }

        catalog_file = tmp_path / "airbyte.json"
        with open(catalog_file, "w") as f:
            json.dump(catalog_data, f)

        loader = CatalogLoader(catalogs_dir=tmp_path)
        assert loader.has_catalogs()
        assert "airbyte" in loader.get_catalog_names()

        connectors = loader.list_connectors("airbyte")
        assert len(connectors) == 1
        assert connectors[0].name == "test_connector"
        assert connectors[0].external_id == "test-id-123"
        assert connectors[0].docker_image_default == "airbyte/source-test:1.0.0"
        assert connectors[0].version_default == "1.0.0"

    def test_catalog_loader_generic_format(self, tmp_path):
        """Test loading generic catalog format."""
        catalog_data = {
            "connectors": [
                {
                    "name": "test_connector",
                    "external_id": "test-123",
                    "docker_image_default": "custom/connector:1.0",
                    "version_default": "1.0",
                    "capabilities": ["incremental", "cdc"],
                }
            ]
        }

        catalog_file = tmp_path / "custom.json"
        with open(catalog_file, "w") as f:
            json.dump(catalog_data, f)

        loader = CatalogLoader(catalogs_dir=tmp_path)
        assert loader.has_catalogs()

        connector = loader.get_connector("test_connector", "custom")
        assert connector is not None
        assert connector.name == "test_connector"
        assert connector.external_id == "test-123"
        assert "incremental" in connector.capabilities

    def test_catalog_loader_invalid_json(self, tmp_path):
        """Test catalog loader with invalid JSON."""
        catalog_file = tmp_path / "invalid.json"
        with open(catalog_file, "w") as f:
            f.write("invalid json content {")

        # Should not raise, just warn
        loader = CatalogLoader(catalogs_dir=tmp_path)
        assert not loader.has_catalogs()

    def test_get_connector_by_name(self, tmp_path):
        """Test getting connector by name."""
        catalog_data = {
            "connectors": [
                {
                    "name": "stripe",
                    "external_id": "stripe-123",
                    "docker_image_default": "airbyte/source-stripe:4.0.0",
                }
            ]
        }

        catalog_file = tmp_path / "airbyte.json"
        with open(catalog_file, "w") as f:
            json.dump(catalog_data, f)

        loader = CatalogLoader(catalogs_dir=tmp_path)

        # Find in specific catalog
        connector = loader.get_connector("stripe", "airbyte")
        assert connector is not None
        assert connector.name == "stripe"

        # Find in all catalogs
        connector = loader.get_connector("stripe")
        assert connector is not None

        # Not found
        connector = loader.get_connector("nonexistent")
        assert connector is None

    def test_list_connectors_all(self, tmp_path):
        """Test listing all connectors from multiple catalogs."""
        # Create two catalog files
        catalog1 = {"connectors": [{"name": "connector1", "external_id": "id1"}]}
        catalog2 = {"connectors": [{"name": "connector2", "external_id": "id2"}]}

        with open(tmp_path / "catalog1.json", "w") as f:
            json.dump(catalog1, f)
        with open(tmp_path / "catalog2.json", "w") as f:
            json.dump(catalog2, f)

        loader = CatalogLoader(catalogs_dir=tmp_path)
        connectors = loader.list_connectors()

        assert len(connectors) == 2
        names = [c.name for c in connectors]
        assert "connector1" in names
        assert "connector2" in names


class TestResolveImageAndVersion:
    """Test unified resolution precedence helper."""

    def test_job_override_takes_precedence(self):
        """Test that job overrides have highest priority."""
        image, version = resolve_image_and_version(
            job_image="custom/image:1.0",
            job_version="1.0",
            catalog_image="catalog/image:2.0",
            catalog_version="2.0",
            registry_image_default="registry/image:3.0",
            registry_version_default="3.0",
        )
        assert image == "custom/image:1.0"
        assert version == "1.0"

    def test_catalog_takes_precedence_over_registry(self):
        """Test that catalog values override registry defaults."""
        image, version = resolve_image_and_version(
            catalog_image="catalog/image:2.0",
            catalog_version="2.0",
            registry_image_default="registry/image:3.0",
            registry_version_default="3.0",
        )
        assert image == "catalog/image:2.0"
        assert version == "2.0"

    def test_registry_defaults_used_when_no_override(self):
        """Test that registry defaults are used when nothing else set."""
        image, version = resolve_image_and_version(
            registry_image_default="registry/image:3.0",
            registry_version_default="3.0",
        )
        assert image == "registry/image:3.0"
        assert version == "3.0"

    def test_none_when_nothing_set(self):
        """Test that None is returned when no values provided."""
        image, version = resolve_image_and_version()
        assert image is None
        assert version is None

    def test_partial_resolution(self):
        """Test that image and version can be resolved independently."""
        image, version = resolve_image_and_version(
            job_image="custom/image:1.0",
            registry_version_default="3.0",
        )
        assert image == "custom/image:1.0"
        assert version == "3.0"


class TestConnectorRegistry:
    """Test connector registry with catalog integration."""

    def test_registry_loading(self):
        """Test loading the actual registry file."""
        registry = ConnectorRegistry.from_default_paths()
        assert registry.registry_data is not None
        assert "version" in registry.registry_data

    def test_from_default_paths(self):
        """Test from_default_paths class method."""
        registry = ConnectorRegistry.from_default_paths()
        assert registry.registry_path.exists()
        assert registry.registry_data is not None

    def test_registry_not_found_error(self, tmp_path):
        """Test that RegistryNotFoundError is raised when registry not found."""
        # Create a non-existent path
        non_existent = tmp_path / "nonexistent.yaml"
        with pytest.raises(RegistryNotFoundError) as exc_info:
            ConnectorRegistry(registry_path=non_existent)
        error_msg = str(exc_info.value).lower()
        assert "does not exist" in error_msg or "not found" in error_msg
        assert "mount" in error_msg or "docker" in error_msg or "env var" in error_msg

    def test_registry_load_error(self, tmp_path):
        """Test that RegistryLoadError is raised for invalid YAML."""
        invalid_yaml = tmp_path / "invalid.yaml"
        invalid_yaml.write_text("invalid: yaml: content: [")
        with pytest.raises(RegistryLoadError):
            ConnectorRegistry(registry_path=invalid_yaml)

    def test_get_connector_entry(self):
        """Test getting connector entry from registry."""
        registry = ConnectorRegistry.from_default_paths()

        # Test unified format
        entry = registry.get_connector_entry("hubspot", role="source")
        assert entry is not None
        assert "roles" in entry or "category" in entry

        # Test non-existent
        entry = registry.get_connector_entry("nonexistent")
        assert entry is None

    def test_list_connectors(self):
        """Test listing connectors."""
        registry = ConnectorRegistry.from_default_paths()

        # List all
        all_connectors = registry.list_connectors()
        assert len(all_connectors) > 0

        # List sources
        sources = registry.list_connectors(role="source")
        assert len(sources) > 0
        assert "hubspot" in sources or "stripe" in sources

        # List targets
        targets = registry.list_connectors(role="target")
        assert len(targets) > 0

    def test_resolve_connector_basic(self):
        """Test basic connector resolution without catalog."""
        registry = ConnectorRegistry.from_default_paths()

        resolved = registry.resolve_connector("hubspot")
        assert resolved is not None
        assert resolved.name == "hubspot"
        assert "source" in resolved.roles
        assert resolved.default_engine in ["airbyte", "native", "singer", "meltano"]

    def test_resolve_connector_with_catalog(self, tmp_path):
        """Test connector resolution with catalog integration."""
        # Create a minimal registry file
        registry_data = {
            "version": "1.0",
            "connectors": {
                "hubspot": {
                    "roles": ["source"],
                    "default_engine": "airbyte",
                    "engines_supported": ["airbyte"],
                }
            },
        }
        registry_file = tmp_path / "connectors.yaml"
        import yaml

        with open(registry_file, "w") as f:
            yaml.dump(registry_data, f)

        # Create a test catalog
        catalog_data = {
            "connectors": [
                {
                    "name": "hubspot",
                    "external_id": "airbyte/source-hubspot",
                    "docker_image_default": "airbyte/source-hubspot:2.5.0",
                    "version_default": "2.5.0",
                }
            ]
        }

        catalog_file = tmp_path / "airbyte.json"
        with open(catalog_file, "w") as f:
            json.dump(catalog_data, f)

        # Create registry with test catalog
        loader = CatalogLoader(catalogs_dir=tmp_path)
        registry = ConnectorRegistry(registry_path=registry_file, catalog_loader=loader)

        # Resolve with airbyte engine - should use catalog
        # Use strict_mode=True since we have complete catalog data (docker_image and version)
        resolved = registry.resolve_connector(
            "hubspot", engine="airbyte", strict_mode=True
        )
        assert resolved is not None
        assert resolved.docker_image == "airbyte/source-hubspot:2.5.0"
        assert resolved.version == "2.5.0"
        assert resolved.catalog_entry is not None

    def test_resolve_connector_with_overrides(self, tmp_path):
        """Test connector resolution with job-level overrides."""
        # Create a minimal registry file
        registry_data = {
            "version": "1.0",
            "connectors": {
                "stripe": {
                    "roles": ["source"],
                    "default_engine": "airbyte",
                    "engines_supported": ["airbyte"],
                }
            },
        }
        registry_file = tmp_path / "connectors.yaml"
        import yaml

        with open(registry_file, "w") as f:
            yaml.dump(registry_data, f)

        catalog_data = {
            "connectors": [
                {
                    "name": "stripe",
                    "external_id": "airbyte/source-stripe",
                    "docker_image_default": "airbyte/source-stripe:4.0.0",
                }
            ]
        }

        catalog_file = tmp_path / "airbyte.json"
        with open(catalog_file, "w") as f:
            json.dump(catalog_data, f)

        loader = CatalogLoader(catalogs_dir=tmp_path)
        registry = ConnectorRegistry(registry_path=registry_file, catalog_loader=loader)

        # Job override should take precedence
        # Use strict_mode=True since we have complete data (overrides provide docker_image/version)
        overrides = {"docker_image": "custom/stripe:5.0.0", "version": "5.0.0"}
        resolved = registry.resolve_connector(
            "stripe", engine="airbyte", job_overrides=overrides, strict_mode=True
        )

        assert resolved.docker_image == "custom/stripe:5.0.0"
        assert resolved.version == "5.0.0"

    def test_resolve_connector_does_not_mutate_job_overrides(self, tmp_path):
        """Test that resolve_connector does not mutate the caller's job_overrides dict."""
        # Create a minimal registry file
        registry_data = {
            "version": "1.0",
            "connectors": {
                "stripe": {
                    "roles": ["source"],
                    "default_engine": "airbyte",
                    "engines_supported": ["airbyte"],
                }
            },
        }
        registry_file = tmp_path / "connectors.yaml"
        import yaml

        with open(registry_file, "w") as f:
            yaml.dump(registry_data, f)

        registry = ConnectorRegistry(registry_path=registry_file)

        # Create job_overrides dict that should NOT be mutated
        original_overrides = {"docker_image": "custom/stripe:5.0.0"}
        original_overrides_id = id(original_overrides)
        original_overrides_keys = set(original_overrides.keys())

        # Call resolve_connector with engine parameter
        # Use strict_mode=False since this test is about mutation, not validation
        # and we don't have complete catalog data for singer engine
        resolved = registry.resolve_connector(
            "stripe",
            engine="singer",
            job_overrides=original_overrides,
            strict_mode=False,
        )

        # Verify the original dict was NOT mutated
        assert id(original_overrides) == original_overrides_id
        assert set(original_overrides.keys()) == original_overrides_keys
        assert "engine" not in original_overrides
        assert original_overrides["docker_image"] == "custom/stripe:5.0.0"

        # Verify the resolved connector has the engine set correctly
        assert resolved.default_engine == "singer"

    def test_validate_connector(self):
        """Test connector validation."""
        registry = ConnectorRegistry.from_default_paths()

        # Valid connector
        entry = registry.validate_connector("hubspot", "source", "self_hosted")
        assert entry is not None

        # Invalid connector - should exit
        with pytest.raises(SystemExit):
            registry.validate_connector("nonexistent", "source", "self_hosted")


class TestResolvedConnector:
    """Test resolved connector object."""

    def test_resolved_connector_basic(self):
        """Test basic resolved connector properties."""
        registry_entry = {
            "roles": ["source"],
            "default_engine": "native",
            "engines_supported": ["native", "airbyte"],
            "category": "files",
            "allowed_in_cloud": True,
            "supports_incremental": True,
            "incremental_strategy_default": "updated_after",
        }

        resolved = ResolvedConnector(
            name="test_connector",
            connector_type="test",
            registry_entry=registry_entry,
        )

        assert resolved.name == "test_connector"
        assert resolved.roles == ["source"]
        assert resolved.default_engine == "native"
        assert resolved.category == "files"
        assert resolved.allowed_in_cloud is True
        assert resolved.supports_incremental is True
        assert "incremental" in resolved.capabilities

    def test_resolved_connector_with_catalog(self):
        """Test resolved connector with catalog entry."""
        registry_entry = {
            "roles": ["source"],
            "default_engine": "airbyte",
            "engines_supported": ["airbyte"],
        }

        catalog_entry = ExternalConnector(
            name="test",
            external_id="airbyte/source-test",
            docker_image_default="airbyte/source-test:1.0.0",
            version_default="1.0.0",
            capabilities=["certified"],
            source_of_truth="airbyte",
        )

        resolved = ResolvedConnector(
            name="test",
            connector_type="test",
            registry_entry=registry_entry,
            catalog_entry=catalog_entry,
        )

        # Catalog values should be used
        assert resolved.docker_image == "airbyte/source-test:1.0.0"
        assert resolved.version == "1.0.0"
        assert resolved.external_id == "airbyte/source-test"
        assert "certified" in resolved.capabilities

    def test_resolved_connector_override_priority(self):
        """Test that job overrides take precedence."""
        registry_entry = {
            "roles": ["source"],
            "default_engine": "airbyte",
            "engines_supported": ["airbyte"],
            "docker_image_default": "airbyte/source-test:1.0.0",
        }

        catalog_entry = ExternalConnector(
            name="test",
            external_id="airbyte/source-test",
            docker_image_default="airbyte/source-test:2.0.0",
            version_default="2.0.0",
        )

        job_overrides = {
            "docker_image": "custom/test:3.0.0",
            "version": "3.0.0",
            "engine": "native",
        }

        resolved = ResolvedConnector(
            name="test",
            connector_type="test",
            registry_entry=registry_entry,
            catalog_entry=catalog_entry,
            job_overrides=job_overrides,
        )

        # Job overrides should win
        assert resolved.docker_image == "custom/test:3.0.0"
        assert resolved.version == "3.0.0"
        assert resolved.default_engine == "native"

    def test_resolved_connector_to_dict(self):
        """Test converting resolved connector to dict."""
        registry_entry = {
            "roles": ["source"],
            "default_engine": "native",
            "engines_supported": ["native"],
            "category": "files",
        }

        resolved = ResolvedConnector(
            name="test",
            connector_type="test",
            registry_entry=registry_entry,
        )

        result = resolved.to_dict()
        assert result["name"] == "test"
        assert result["type"] == "test"
        assert result["roles"] == ["source"]
        assert result["default_engine"] == "native"
        assert result["category"] == "files"


class TestConnectorResolutionIntegration:
    """Integration tests for connector resolution with real registry."""

    def test_stripe_connector_resolution(self):
        """Test Stripe connector resolution."""
        registry = ConnectorRegistry.from_default_paths()
        resolved = registry.resolve_connector("stripe")

        assert resolved is not None
        assert "source" in resolved.roles
        assert resolved.default_engine in ["airbyte", "singer", "native"]
        assert resolved.supports_incremental is True

    def test_postgres_connector_resolution(self):
        """Test Postgres connector resolution."""
        registry = ConnectorRegistry.from_default_paths()
        resolved = registry.resolve_connector("postgres")

        assert resolved is not None
        assert "source" in resolved.roles or "target" in resolved.roles
        assert (
            resolved.allowed_in_cloud is False
        )  # Database connectors blocked in cloud

    def test_csv_connector_resolution(self):
        """Test CSV connector (native) resolution."""
        registry = ConnectorRegistry.from_default_paths()
        resolved = registry.resolve_connector("csv")

        assert resolved is not None
        assert resolved.default_engine == "native"
        assert "source" in resolved.roles
        assert "target" in resolved.roles

    def test_mimesis_connector_resolution(self):
        """Test Mimesis connector resolution."""
        registry = ConnectorRegistry.from_default_paths()
        resolved = registry.resolve_connector("mimesis")

        assert resolved is not None
        assert resolved.default_engine == "native"
        assert "source" in resolved.roles
        assert resolved.supports_incremental is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
