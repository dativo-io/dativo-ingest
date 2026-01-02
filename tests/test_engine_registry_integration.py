"""Integration tests for EngineConfigParser with ConnectorRegistry."""

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from src.dativo_ingest.config import ConnectorRecipe, SourceConfig
from src.dativo_ingest.connectors.engine_config import EngineConfigParser
from src.dativo_ingest.registry import CatalogLoader, ConnectorRegistry


class TestEngineConfigParserRegistryIntegration:
    """Test EngineConfigParser integration with ConnectorRegistry."""

    def test_job_explicit_docker_image_unchanged(self, tmp_path):
        """Job with explicit docker_image should not be overridden by registry/catalog."""
        # Create registry with a default image and version
        registry_data = {
            "version": "1.0",
            "connectors": {
                "stripe": {
                    "roles": ["source"],
                    "default_engine": "airbyte",
                    "engines_supported": ["airbyte"],
                    "docker_image_default": "airbyte/source-stripe:4.0.0",
                    "version_default": "4.0.0",
                }
            },
        }
        registry_file = tmp_path / "connectors.yaml"
        with open(registry_file, "w") as f:
            yaml.dump(registry_data, f)

        # Create catalog with different image
        catalog_data = {
            "connectors": [
                {
                    "name": "stripe",
                    "docker_image_default": "airbyte/source-stripe:5.0.0",
                }
            ]
        }
        catalog_file = tmp_path / "airbyte.json"
        with open(catalog_file, "w") as f:
            json.dump(catalog_data, f)

        loader = CatalogLoader(catalogs_dir=tmp_path)
        registry = ConnectorRegistry(registry_path=registry_file, catalog_loader=loader)

        # Create job config with explicit docker_image
        source_config = SourceConfig(
            type="stripe",
            object="charges",
        )
        connector_recipe = ConnectorRecipe(
            name="stripe",
            type="stripe",
            default_engine={
                "type": "airbyte",
                "options": {
                    "airbyte": {
                        "docker_image": "custom/stripe:6.0.0",  # Explicit job override
                    }
                },
            },
        )

        parser = EngineConfigParser(source_config, connector_recipe)
        docker_image = parser.get_docker_image()

        # Job override must win
        assert docker_image == "custom/stripe:6.0.0"

    def test_catalog_overrides_registry_defaults(self, tmp_path):
        """Catalog should override registry defaults when no job override."""
        # Create registry with default image and version
        registry_data = {
            "version": "1.0",
            "connectors": {
                "stripe": {
                    "roles": ["source"],
                    "default_engine": "airbyte",
                    "engines_supported": ["airbyte"],
                    "docker_image_default": "airbyte/source-stripe:4.0.0",
                    "version_default": "4.0.0",
                }
            },
        }
        registry_file = tmp_path / "connectors.yaml"
        with open(registry_file, "w") as f:
            yaml.dump(registry_data, f)

        # Create catalog with different image
        # Note: Catalog format uses "docker_image" and "version", which get mapped to
        # "docker_image_default" and "version_default" in ExternalConnector
        catalog_data = {
            "connectors": [
                {
                    "name": "stripe",
                    "external_id": "stripe-id",
                    "docker_image": "airbyte/source-stripe:5.0.0",
                    "version": "5.0.0",
                    "capabilities": {},
                }
            ]
        }
        catalog_file = tmp_path / "airbyte.json"
        with open(catalog_file, "w") as f:
            json.dump(catalog_data, f)

        loader = CatalogLoader(catalogs_dir=tmp_path)
        registry = ConnectorRegistry(registry_path=registry_file, catalog_loader=loader)

        # Create job config WITHOUT explicit docker_image
        source_config = SourceConfig(
            type="stripe",
            object="charges",
        )
        connector_recipe = ConnectorRecipe(
            name="stripe",
            type="stripe",
            default_engine={
                "type": "airbyte",
                "options": {
                    "airbyte": {
                        # No docker_image - should use catalog
                    }
                },
            },
        )

        # Mock the registry resolution in EngineConfigParser
        # We need to patch ConnectorRegistry.from_default_paths to return our test registry
        from unittest.mock import patch

        with patch(
            "src.dativo_ingest.connectors.engine_config.ConnectorRegistry.from_default_paths"
        ) as mock_registry:
            mock_registry.return_value = registry

            parser = EngineConfigParser(source_config, connector_recipe)
            docker_image = parser.get_docker_image()

            # Catalog should win over registry default
            assert docker_image == "airbyte/source-stripe:5.0.0"

    def test_registry_defaults_used_when_catalog_missing(self, tmp_path):
        """Registry defaults should be used when catalog is missing."""
        # Create registry with default image and version (required for strict mode)
        registry_data = {
            "version": "1.0",
            "connectors": {
                "stripe": {
                    "roles": ["source"],
                    "default_engine": "airbyte",
                    "engines_supported": ["airbyte"],
                    "docker_image_default": "airbyte/source-stripe:4.0.0",
                    "version_default": "4.0.0",
                }
            },
        }
        registry_file = tmp_path / "connectors.yaml"
        with open(registry_file, "w") as f:
            yaml.dump(registry_data, f)

        # No catalog file

        loader = CatalogLoader(catalogs_dir=tmp_path)
        registry = ConnectorRegistry(registry_path=registry_file, catalog_loader=loader)

        # Create job config WITHOUT explicit docker_image
        source_config = SourceConfig(
            type="stripe",
            object="charges",
        )
        connector_recipe = ConnectorRecipe(
            name="stripe",
            type="stripe",
            default_engine={
                "type": "airbyte",
                "options": {
                    "airbyte": {
                        # No docker_image - should use registry default
                    }
                },
            },
        )

        from unittest.mock import patch

        with patch(
            "src.dativo_ingest.connectors.engine_config.ConnectorRegistry.from_default_paths"
        ) as mock_registry:
            mock_registry.return_value = registry

            parser = EngineConfigParser(source_config, connector_recipe)
            docker_image = parser.get_docker_image()

            # Registry default should be used
            assert docker_image == "airbyte/source-stripe:4.0.0"

    def test_missing_registry_graceful_fallback(self, tmp_path, caplog):
        """Missing registry should raise ValueError in strict mode (default)."""
        # No registry file

        # Create job config
        source_config = SourceConfig(
            type="stripe",
            object="charges",
        )
        connector_recipe = ConnectorRecipe(
            name="stripe",
            type="stripe",
            default_engine={
                "type": "airbyte",
                "options": {
                    "airbyte": {
                        # No docker_image
                    }
                },
            },
        )

        from unittest.mock import patch

        from src.dativo_ingest.registry import RegistryNotFoundError

        with patch(
            "src.dativo_ingest.connectors.engine_config.ConnectorRegistry.from_default_paths"
        ) as mock_registry:
            mock_registry.side_effect = RegistryNotFoundError("Registry not found")

            parser = EngineConfigParser(source_config, connector_recipe)

            # With strict_mode=True (default), missing registry should raise ValueError
            # This is expected behavior - strict mode requires registry for Airbyte connectors
            with pytest.raises(ValueError, match="Registry required"):
                parser.get_docker_image()
