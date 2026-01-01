import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from dativo_ingest.registry.connector_catalog import CatalogSyncer


class TestConnectorCatalog(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.catalogs_dir = Path(self.temp_dir.name)
        self.syncer = CatalogSyncer(catalogs_dir=self.catalogs_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("urllib.request.urlopen")
    def test_sync_from_url_success(self, mock_urlopen):
        # Mock response
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps(
            {
                "sources": [
                    {
                        "name": "Stripe",
                        "sourceDefinitionId": "123",
                        "dockerRepository": "airbyte/source-stripe",
                        "dockerImageTag": "5.0.0",
                    }
                ]
            }
        ).encode("utf-8")
        mock_response.__enter__.return_value = mock_response

        mock_urlopen.return_value = mock_response

        # Sync
        path = self.syncer.sync_from_url("http://example.com/catalog.json", "airbyte")

        # Verify file exists
        self.assertTrue(path.exists())
        self.assertEqual(path.name, "airbyte.json")

        # Verify content
        with open(path, "r") as f:
            data = json.load(f)
            self.assertEqual(len(data["sources"]), 1)
            self.assertEqual(data["sources"][0]["name"], "Stripe")

    @patch("urllib.request.urlopen")
    def test_sync_from_url_invalid_json(self, mock_urlopen):
        # Mock response
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b"invalid json"
        mock_response.__enter__.return_value = mock_response

        mock_urlopen.return_value = mock_response

        # Sync should fail
        with self.assertRaises(ValueError):
            self.syncer.sync_from_url("http://example.com/catalog.json")

    @patch("urllib.request.urlopen")
    def test_sync_from_url_http_error(self, mock_urlopen):
        # Mock response
        mock_response = MagicMock()
        mock_response.status = 404
        mock_response.reason = "Not Found"
        mock_response.__enter__.return_value = mock_response

        mock_urlopen.return_value = mock_response

        # Sync should fail
        with self.assertRaises(ValueError):
            self.syncer.sync_from_url("http://example.com/catalog.json")
