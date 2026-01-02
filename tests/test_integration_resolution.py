import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from dativo_ingest.config import ConnectorRecipe, SourceConfig
from dativo_ingest.connectors.engine_config import EngineConfigParser
from dativo_ingest.registry.connector_registry import ConnectorRegistry


class TestIntegrationResolution(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        # Setup registry directory
        self.registry_dir = self.root / "registry"
        self.registry_dir.mkdir()
        self.catalogs_dir = self.registry_dir / "catalogs"
        self.catalogs_dir.mkdir()

        # Create connectors.yaml
        self.connectors_yaml = self.registry_dir / "connectors.yaml"
        with open(self.connectors_yaml, "w") as f:
            f.write(
                """
version: 3
connectors:
  stripe:
    roles: [source]
    default_engine: airbyte
    engines_supported: [airbyte]
    external_id: "airbyte/source-stripe"
            """
            )

        # Create airbyte.json catalog (normalized)
        self.airbyte_json = self.catalogs_dir / "airbyte.json"
        with open(self.airbyte_json, "w") as f:
            json.dump(
                {
                    "catalog": "airbyte",
                    "schema_version": 1,
                    "generated_at": "2023-01-01T00:00:00Z",
                    "meta": {"fetched_at": "2023-01-01T00:00:00Z", "sha256": "abc"},
                    "connectors": [
                        {
                            "name": "stripe",
                            "external_id": "airbyte/source-stripe",
                            "docker_image": "airbyte/source-stripe:4.0.0",
                            "version": "4.0.0",
                            "capabilities": {},
                        }
                    ],
                },
                f,
            )

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch(
        "dativo_ingest.registry.connector_registry.ConnectorRegistry._find_registry_path"
    )
    @patch("dativo_ingest.registry.catalog_loader.CatalogLoader.__init__")
    def test_full_resolution_flow(self, mock_loader_init, mock_find_path):
        # Point registry to our temp connectors.yaml
        mock_find_path.return_value = self.connectors_yaml

        # Point catalog loader to our temp catalogs dir
        # CatalogLoader.__init__ returns None, but we need to intercept the path argument or self assignment
        # Actually easier to rely on default path logic if we can mock the paths list
        # But here we are mocking __init__.
        # Let's instead patch where CatalogLoader looks for files.

        # Better approach: Instantiate EngineConfigParser, but we need it to use a registry instance
        # that uses our temp dir.
        # EngineConfigParser uses ConnectorRegistry.from_default_paths().

        # We can mock ConnectorRegistry.from_default_paths to return an instance pointing to our dir
        pass

    @patch("dativo_ingest.connectors.engine_config.ConnectorRegistry")
    def test_integration_resolution(self, MockRegistry):
        # Create a real registry instance pointing to our temp files
        # We need to ensure CatalogLoader also points to our temp files
        from dativo_ingest.registry.catalog_loader import CatalogLoader

        loader = CatalogLoader(catalogs_dir=self.catalogs_dir)
        registry = ConnectorRegistry(
            registry_path=self.connectors_yaml, catalog_loader=loader
        )

        # Configure the mock to return our real registry instance
        MockRegistry.from_default_paths.return_value = registry

        # 1. Test resolution from Catalog
        source_config = SourceConfig(type="stripe", engine={"type": "airbyte"})
        recipe = ConnectorRecipe(
            name="stripe",
            type="stripe",
            roles=["source"],
            default_engine={"type": "airbyte"},
        )

        parser = EngineConfigParser(source_config, recipe)
        image = parser.get_docker_image()

        self.assertEqual(image, "airbyte/source-stripe:4.0.0")  # From catalog

        # 2. Test Job Override
        source_config_override = SourceConfig(
            type="stripe",
            engine={
                "type": "airbyte",
                "options": {"airbyte": {"docker_image": "custom/stripe:5.0.0"}},
            },
        )

        parser_override = EngineConfigParser(source_config_override, recipe)
        image_override = parser_override.get_docker_image()

        self.assertEqual(image_override, "custom/stripe:5.0.0")  # From job
