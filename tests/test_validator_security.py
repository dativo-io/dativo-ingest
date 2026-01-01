import unittest
import os
from unittest.mock import MagicMock, patch

from dativo_ingest.validator import ConnectorValidator
from dativo_ingest.config import JobConfig, SourceConfig

class TestValidatorSecurity(unittest.TestCase):
    def setUp(self):
        self.mock_registry = MagicMock()
        self.validator = ConnectorValidator()
        self.validator.registry = self.mock_registry
        
    @patch.dict(os.environ, {"DATIVO_ALLOW_CUSTOM_IMAGES": "false"})
    def test_image_security_blocked(self):
        # Mock resolution
        mock_resolved = MagicMock()
        mock_resolved.docker_image = "custom/image:latest"
        self.mock_registry.resolve_connector.return_value = mock_resolved
        
        # Should exit with code 2
        with self.assertRaises(SystemExit) as cm:
            self.validator.validate_image_security("stripe", "airbyte", "custom/image:latest")
        self.assertEqual(cm.exception.code, 2)

    @patch.dict(os.environ, {"DATIVO_ALLOW_CUSTOM_IMAGES": "false"})
    def test_image_security_allowed(self):
        # Allow airbyte/ prefix
        self.validator.validate_image_security("stripe", "airbyte", "airbyte/source-stripe:latest")
        
    @patch.dict(os.environ, {"DATIVO_ALLOW_CUSTOM_IMAGES": "true"})
    def test_image_security_override(self):
        # Allow custom if env var set
        self.validator.validate_image_security("stripe", "airbyte", "custom/image:latest")
