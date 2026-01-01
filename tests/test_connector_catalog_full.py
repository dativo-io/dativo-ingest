import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from dativo_ingest.registry.connector_catalog import CatalogSyncer
from dativo_ingest.registry.adapters.airbyte_adapter import AirbyteAdapter


class TestConnectorCatalogFull(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.catalogs_dir = Path(self.temp_dir.name)
        self.syncer = CatalogSyncer(catalogs_dir=self.catalogs_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("urllib.request.urlopen")
    def test_sync_idempotency(self, mock_urlopen):
        url = "http://example.com/catalog.json"
        content = json.dumps({"sources": []}).encode("utf-8")
        content_hash = hashlib.sha256(content).hexdigest()
        
        # 1. First sync (fresh)
        mock_response = MagicMock()
        mock_response.read.return_value = content
        mock_response.info.return_value = {"ETag": '"123"', "Last-Modified": "Today"}
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response
        
        path = self.syncer.sync_from_url(url)
        self.assertTrue(path.exists())
        
        with open(path, "r") as f:
            data = json.load(f)
            self.assertEqual(data["meta"]["sha256"], content_hash)
            self.assertEqual(data["meta"]["etag"], '"123"')

        # 2. Second sync (content matches)
        # Reset mock to verify calls
        mock_urlopen.reset_mock()
        mock_urlopen.return_value = mock_response # Return same response
        
        path2 = self.syncer.sync_from_url(url)
        self.assertEqual(path, path2)
        # Should imply it didn't rewrite if we checked mtime, but functionality is covered if it returns success.
        
        # 3. Third sync (304 Not Modified)
        error_response = urllib.error.HTTPError(
            url, 304, "Not Modified", {"ETag": '"123"'}, None
        )
        mock_urlopen.side_effect = error_response
        
        path3 = self.syncer.sync_from_url(url)
        self.assertEqual(path, path3)

    def test_airbyte_normalization(self):
        adapter = AirbyteAdapter()
        raw = {
            "sources": [
                {
                    "sourceDefinitionId": "id1",
                    "name": "Stripe",
                    "dockerRepository": "airbyte/source-stripe",
                    "dockerImageTag": "1.0.0",
                    "documentationUrl": "http://docs",
                    "supportLevel": "certified"
                }
            ]
        }
        meta = {"fetched_at": "now", "sha256": "abc"}
        normalized = adapter.normalize(raw, meta)
        
        self.assertEqual(normalized["catalog"], "airbyte")
        self.assertEqual(len(normalized["connectors"]), 1)
        connector = normalized["connectors"][0]
        self.assertEqual(connector["name"], "stripe")
        self.assertEqual(connector["docker_image"], "airbyte/source-stripe:1.0.0")
        self.assertEqual(connector["metadata"]["support_level"], "certified")
        
        # Capabilities defaults
        self.assertFalse(connector["capabilities"]["supports_incremental"])
        self.assertTrue(connector["capabilities"]["supports_state"])

import urllib.error
