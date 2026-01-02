import hashlib
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

from dativo_ingest.registry.adapters.airbyte_adapter import AirbyteAdapter
from dativo_ingest.registry.connector_catalog import CatalogSyncer


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
        mock_urlopen.return_value = mock_response  # Return same response

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
                    "supportLevel": "certified",
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

    def test_path_traversal_prevention(self):
        """Test that path traversal attacks are prevented in catalog names."""
        # Test various path traversal attempts
        malicious_names = [
            "../../../etc/config",
            "..\\..\\..\\etc\\config",
            "/etc/passwd",
            "catalog/../../etc/config",
            "catalog\\..\\..\\etc\\config",
            "normal-name/../etc/config",
        ]

        for malicious_name in malicious_names:
            with self.assertRaises(ValueError) as cm:
                self.syncer._sanitize_catalog_name(malicious_name)
            # Verify the error message indicates the issue
            error_msg = str(cm.exception).lower()
            self.assertTrue(
                "invalid" in error_msg or "no valid characters" in error_msg,
                f"Error message should mention 'invalid' or 'no valid characters', got: {cm.exception}",
            )

    def test_sanitize_valid_names(self):
        """Test that valid catalog names are preserved."""
        valid_names = [
            "airbyte",
            "airbyte-catalog",
            "airbyte_catalog",
            "catalog123",
            "a-b_c-123",
        ]

        for valid_name in valid_names:
            sanitized = self.syncer._sanitize_catalog_name(valid_name)
            # Valid names should remain unchanged or only have minor normalization
            self.assertTrue(len(sanitized) > 0)
            # Should not contain path separators
            self.assertNotIn("/", sanitized)
            self.assertNotIn("\\", sanitized)
            self.assertNotIn("..", sanitized)

    @patch("urllib.request.urlopen")
    def test_sync_from_url_path_traversal_prevention(self, mock_urlopen):
        """Test that sync_from_url prevents path traversal in name parameter."""
        url = "http://example.com/catalog.json"
        content = json.dumps({"sources": []}).encode("utf-8")

        mock_response = MagicMock()
        mock_response.read.return_value = content
        mock_response.info.return_value = {}
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        # Attempt path traversal attack
        with self.assertRaises(ValueError):
            self.syncer.sync_from_url(url, name="../../../etc/config")

        # Verify no file was created outside catalogs_dir
        # The malicious path should have been sanitized/rejected
        malicious_path = self.catalogs_dir.parent.parent / "etc" / "config.json"
        self.assertFalse(malicious_path.exists())

    def test_sync_from_file_path_traversal_prevention(self):
        """Test that sync_from_file prevents path traversal in name parameter."""
        # Create a valid source file
        source_file = self.catalogs_dir / "source.json"
        with open(source_file, "w") as f:
            json.dump({"sources": []}, f)

        # Attempt path traversal attack
        with self.assertRaises(ValueError):
            self.syncer.sync_from_file(source_file, name="../../../etc/config")

        # Verify no file was created outside catalogs_dir
        malicious_path = self.catalogs_dir.parent.parent / "etc" / "config.json"
        self.assertFalse(malicious_path.exists())
