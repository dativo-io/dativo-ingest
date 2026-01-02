import unittest
import ssl
from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile

from dativo_ingest.registry.connector_catalog import CatalogSyncer

class TestCatalogSecurity(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.catalogs_dir = Path(self.temp_dir.name)
        self.syncer = CatalogSyncer(catalogs_dir=self.catalogs_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("ssl.create_default_context")
    @patch("urllib.request.urlopen")
    def test_sync_secure_by_default(self, mock_urlopen, mock_create_context):
        # Mock successful response
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"sources": []}'
        mock_response.info.return_value = {}
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response
        
        # Mock SSL context
        mock_context = MagicMock()
        mock_create_context.return_value = mock_context
        
        # Run sync (default insecure=False)
        self.syncer.sync_from_url("https://example.com/catalog.json")
        
        # Verify ssl.create_default_context was called (implies secure default)
        mock_create_context.assert_called_once()
        # Verify we didn't disable verification
        # (mock_context.check_hostname and verify_mode shouldn't be touched by us in secure mode
        # or at least not set to False/CERT_NONE)
        
        # Verify urlopen called with context
        mock_urlopen.assert_called_with(
            unittest.mock.ANY, 
            context=mock_context, 
            timeout=30
        )

    @patch("ssl.create_default_context")
    @patch("urllib.request.urlopen")
    def test_sync_insecure_explicit(self, mock_urlopen, mock_create_context):
        # Mock successful response
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"sources": []}'
        mock_response.info.return_value = {}
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response
        
        # Mock SSL context
        mock_context = MagicMock()
        mock_create_context.return_value = mock_context
        
        # Run sync with insecure=True
        self.syncer.sync_from_url("https://example.com/catalog.json", insecure=True)
        
        # Verify context settings were changed
        self.assertEqual(mock_context.check_hostname, False)
        self.assertEqual(mock_context.verify_mode, ssl.CERT_NONE)
