import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from dativo_ingest.config import ConnectorRecipe, SourceConfig
from dativo_ingest.connectors.engine_config import EngineConfigParser
from dativo_ingest.registry.catalog_loader import ExternalConnector
from dativo_ingest.registry.connector_registry import (
    ConnectorRegistry,
    ResolvedConnector,
)


class TestConnectorResolution(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.registry_data = {
            "connectors": {
                "stripe": {
                    "roles": ["source"],
                    "default_engine": "airbyte",
                    "docker_image_default": "airbyte/source-stripe:1.0.0",
                }
            }
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("dativo_ingest.registry.connector_registry.ConnectorRegistry._load_registry")
    @patch(
        "dativo_ingest.registry.connector_registry.ConnectorRegistry._find_registry_path"
    )
    def test_resolve_priorities(self, mock_find_path, mock_load_registry):
        # Create a dummy registry file so exists() returns True
        dummy_registry = Path(self.temp_dir.name) / "registry.yaml"
        dummy_registry.touch()

        mock_find_path.return_value = dummy_registry
        mock_load_registry.return_value = self.registry_data

        # Mock catalog loader
        mock_catalog_loader = MagicMock()
        mock_catalog_loader.get_connector.return_value = ExternalConnector(
            name="stripe",
            external_id="stripe-id",
            docker_image_default="airbyte/source-stripe:2.0.0",  # Catalog has newer version
            version_default="2.0.0",
            source_of_truth="airbyte",
        )

        registry = ConnectorRegistry(
            registry_path=dummy_registry, catalog_loader=mock_catalog_loader
        )

        # Case 1: Registry only (catalog mocked above, so we get catalog value if engine matches)
        # Note: resolve_connector calls get_connector if engine is airbyte.
        resolved = registry.resolve_connector("stripe", engine="airbyte")
        self.assertEqual(
            resolved.docker_image, "airbyte/source-stripe:2.0.0"
        )  # Catalog wins over registry

        # Case 2: Job override
        job_overrides = {"docker_image": "custom/stripe:latest"}
        resolved = registry.resolve_connector(
            "stripe", engine="airbyte", job_overrides=job_overrides
        )
        self.assertEqual(
            resolved.docker_image, "custom/stripe:latest"
        )  # Job override wins

    @patch("dativo_ingest.connectors.engine_config.ConnectorRegistry")
    def test_engine_config_get_docker_image(self, MockRegistry):
        # Setup mocks
        mock_registry_instance = MagicMock()
        MockRegistry.from_default_paths.return_value = mock_registry_instance

        # Mock resolved connector
        mock_resolved = MagicMock()
        mock_resolved.docker_image = "resolved:latest"
        mock_registry_instance.resolve_connector.return_value = mock_resolved

        # Setup configs - CORRECTION: nested airbyte options
        source_config = SourceConfig(
            type="stripe",
            engine={"options": {"airbyte": {"docker_image": "job-override:1.0"}}},
        )
        connector_recipe = ConnectorRecipe(
            name="stripe",
            type="stripe",
            roles=["source"],
            default_engine={"type": "airbyte"},
        )

        parser = EngineConfigParser(source_config, connector_recipe)

        # Test get_docker_image
        image = parser.get_docker_image()

        # Verify it called resolve_connector with correct overrides
        mock_registry_instance.resolve_connector.assert_called_with(
            "stripe",
            engine="airbyte",
            job_overrides={"docker_image": "job-override:1.0"},
            strict_mode=True,
        )
        self.assertEqual(image, "resolved:latest")

    @patch("dativo_ingest.registry.connector_registry.ConnectorRegistry._load_registry")
    @patch(
        "dativo_ingest.registry.connector_registry.ConnectorRegistry._find_registry_path"
    )
    def test_strict_mode_failure(self, mock_find_path, mock_load_registry):
        dummy_registry = Path(self.temp_dir.name) / "registry.yaml"
        dummy_registry.touch()
        mock_find_path.return_value = dummy_registry

        # Registry missing docker_image_default
        bad_registry_data = {
            "connectors": {
                "stripe": {
                    "roles": ["source"],
                    "default_engine": "airbyte",
                    # No docker_image_default
                }
            }
        }
        mock_load_registry.return_value = bad_registry_data

        # Mock catalog loader returning nothing
        mock_catalog_loader = MagicMock()
        mock_catalog_loader.get_connector.return_value = None

        registry = ConnectorRegistry(
            registry_path=dummy_registry, catalog_loader=mock_catalog_loader
        )

        # Should fail in strict mode
        with self.assertRaises(ValueError) as cm:
            registry.resolve_connector("stripe", engine="airbyte", strict_mode=True)
        self.assertIn("Failed to resolve docker image", str(cm.exception))

        # Should NOT fail in fallback mode (strict_mode=False)
        resolved = registry.resolve_connector(
            "stripe", engine="airbyte", strict_mode=False
        )
        self.assertIsNone(resolved.docker_image)
