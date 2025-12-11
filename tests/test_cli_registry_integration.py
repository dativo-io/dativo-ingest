"""Integration tests for CLI commands with ConnectorRegistry."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

from src.dativo_ingest.cli_connectors import (
    connectors_inspect_command,
    connectors_list_command,
    connectors_sync_command,
)
from src.dativo_ingest.registry import RegistryNotFoundError


class TestCLIRegistryIntegration:
    """Test CLI commands integration with ConnectorRegistry."""

    def test_connectors_list_success(self):
        """connectors list should succeed with valid registry."""
        exit_code = connectors_list_command()
        assert exit_code == 0

    def test_connectors_list_json_output(self, capsys):
        """connectors list --json should output valid JSON."""
        exit_code = connectors_list_command(json_output=True)
        assert exit_code == 0

        captured = capsys.readouterr()
        output = captured.out

        # Should be valid JSON
        data = json.loads(output)
        assert "connectors" in data or "error" in data

    def test_connectors_list_with_missing_registry(self, tmp_path, monkeypatch):
        """connectors list should fail with clear error when registry missing."""
        # Point to non-existent registry
        non_existent = tmp_path / "nonexistent.yaml"

        # Mock the default paths to point to non-existent file
        from unittest.mock import patch

        from src.dativo_ingest.registry.connector_registry import ConnectorRegistry

        with patch.object(ConnectorRegistry, "_find_registry_path", return_value=None):
            with patch.object(
                ConnectorRegistry,
                "_get_default_registry_paths",
                return_value=[non_existent],
            ):
                exit_code = connectors_list_command()
                assert exit_code == 2

    def test_connectors_inspect_success(self):
        """connectors inspect should succeed with known connector."""
        exit_code = connectors_inspect_command("stripe")
        assert exit_code == 0

    def test_connectors_inspect_json_output(self, capsys):
        """connectors inspect --json should output valid JSON."""
        exit_code = connectors_inspect_command("stripe", json_output=True)
        assert exit_code == 0

        captured = capsys.readouterr()
        output = captured.out

        # Should be valid JSON
        data = json.loads(output)
        assert "name" in data or "error" in data

    def test_connectors_inspect_unknown_connector(self):
        """connectors inspect should fail with unknown connector."""
        with pytest.raises(SystemExit) as exc_info:
            connectors_inspect_command("nonexistent_connector_xyz")
        assert exc_info.value.code == 2

    def test_connectors_inspect_unknown_connector_json(self, capsys):
        """connectors inspect --json should output error JSON for unknown connector."""
        with pytest.raises(SystemExit) as exc_info:
            connectors_inspect_command("nonexistent_connector_xyz", json_output=True)
        assert exc_info.value.code == 2

        captured = capsys.readouterr()
        output = captured.out

        # Should be valid JSON with error
        data = json.loads(output)
        assert "error" in data

    def test_connectors_sync_no_args_shows_catalogs(self):
        """connectors sync without args should show current catalogs."""
        exit_code = connectors_sync_command()
        # Should succeed (shows current catalogs or empty message)
        assert exit_code == 0

    def test_connectors_sync_with_valid_file(self, tmp_path):
        """connectors sync --catalog-file should succeed with valid file."""
        # Create a valid catalog file
        catalog_data = {
            "connectors": [
                {
                    "name": "test_connector",
                    "external_id": "test-id",
                    "docker_image_default": "test/image:1.0",
                }
            ]
        }
        catalog_file = tmp_path / "test_catalog.json"
        with open(catalog_file, "w") as f:
            json.dump(catalog_data, f)

        exit_code = connectors_sync_command(catalog_file=str(catalog_file))
        assert exit_code == 0

    def test_connectors_sync_with_missing_file(self):
        """connectors sync --catalog-file should fail with missing file."""
        exit_code = connectors_sync_command(catalog_file="/nonexistent/file.json")
        assert exit_code == 2

    def test_connectors_sync_with_missing_file_json(self, capsys):
        """connectors sync --catalog-file --json should output error JSON."""
        exit_code = connectors_sync_command(
            catalog_file="/nonexistent/file.json", json_output=True
        )
        assert exit_code == 2

        captured = capsys.readouterr()
        output = captured.out

        # Should be valid JSON with error
        data = json.loads(output)
        assert "error" in data

    def test_connectors_sync_url_not_implemented(self):
        """connectors sync --catalog-url should fail with clear error."""
        exit_code = connectors_sync_command(
            catalog_url="https://example.com/catalog.json"
        )
        assert exit_code == 2

    def test_connectors_sync_url_not_implemented_json(self, capsys):
        """connectors sync --catalog-url --json should output error JSON."""
        exit_code = connectors_sync_command(
            catalog_url="https://example.com/catalog.json", json_output=True
        )
        assert exit_code == 2

        captured = capsys.readouterr()
        output = captured.out

        # Should be valid JSON with error
        data = json.loads(output)
        assert "error" in data
        assert (
            "not implemented" in data["error"].lower() or "url" in data["error"].lower()
        )
