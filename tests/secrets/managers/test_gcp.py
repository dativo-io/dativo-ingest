"""Tests for GCPSecretManager - focus on our logic, not GCP SDK."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dativo_ingest.secrets.managers.gcp import GCPSecretManager


class TestGCPSecretManager:
    """Test GCP Secret Manager logic."""

    def test_loads_discrete_secrets(self):
        mock_client = MagicMock()
        mock_client.access_secret_version.return_value = SimpleNamespace(
            payload=SimpleNamespace(data=b'{"url":"db"}')
        )

        manager = GCPSecretManager(
            project_id="test-project",
            secrets=[{"name": "postgres", "format": "json"}],
            client=mock_client,
        )

        secrets = manager.load_secrets("tenant1")

        assert secrets["postgres"]["url"] == "db"

    def test_resolves_secret_id_with_template(self):
        mock_client = MagicMock()
        mock_client.access_secret_version.return_value = SimpleNamespace(
            payload=SimpleNamespace(data=b"value")
        )

        manager = GCPSecretManager(
            project_id="test-project",
            secret_id_template="dativo-{tenant}-{name}",
            secrets=[{"name": "api_key"}],
            client=mock_client,
        )

        manager.load_secrets("tenant1")

        # Verify resource name was built correctly
        call_args = mock_client.access_secret_version.call_args[1]
        resource_name = call_args["name"]
        assert "projects/test-project/secrets/dativo-tenant1-api_key" in resource_name
        assert "/versions/latest" in resource_name

    def test_uses_custom_version_when_provided(self):
        mock_client = MagicMock()
        mock_client.access_secret_version.return_value = SimpleNamespace(
            payload=SimpleNamespace(data=b"value")
        )

        manager = GCPSecretManager(
            project_id="test-project",
            secrets=[{"name": "key", "version_id": "2"}],
            client=mock_client,
        )

        manager.load_secrets("tenant1")

        call_args = mock_client.access_secret_version.call_args[1]
        resource_name = call_args["name"]
        assert "/versions/2" in resource_name

    def test_loads_bundle_secret(self):
        mock_client = MagicMock()
        mock_client.access_secret_version.return_value = SimpleNamespace(
            payload=SimpleNamespace(data=b'{"postgres": {"url": "db"}}')
        )

        manager = GCPSecretManager(
            project_id="test-project",
            bundle_secret_id_template="bundle-{tenant}",
            client=mock_client,
        )

        secrets = manager.load_secrets("tenant1")

        assert secrets["postgres"]["url"] == "db"

    def test_bundle_secret_id_uses_template(self):
        mock_client = MagicMock()
        mock_client.access_secret_version.return_value = SimpleNamespace(
            payload=SimpleNamespace(data=b"{}")
        )

        manager = GCPSecretManager(
            project_id="test-project",
            bundle_secret_id_template="prod-{tenant}-secrets",
            client=mock_client,
        )

        manager.load_secrets("tenant1")

        call_args = mock_client.access_secret_version.call_args[1]
        resource_name = call_args["name"]
        assert "prod-tenant1-secrets" in resource_name

    def test_handles_bytes_payload(self):
        mock_client = MagicMock()
        mock_client.access_secret_version.return_value = SimpleNamespace(
            payload=SimpleNamespace(data=b'{"key": "value"}')
        )

        manager = GCPSecretManager(
            project_id="test-project",
            secrets=[{"name": "config", "format": "json"}],
            client=mock_client,
        )

        secrets = manager.load_secrets("tenant1")

        assert secrets["config"] == {"key": "value"}

    def test_handles_string_payload(self):
        mock_client = MagicMock()
        mock_client.access_secret_version.return_value = SimpleNamespace(
            payload=SimpleNamespace(data="string_value")
        )

        manager = GCPSecretManager(
            project_id="test-project",
            secrets=[{"name": "key"}],
            client=mock_client,
        )

        secrets = manager.load_secrets("tenant1")

        assert secrets["key"] == "string_value"

    def test_uses_default_version(self):
        mock_client = MagicMock()
        mock_client.access_secret_version.return_value = SimpleNamespace(
            payload=SimpleNamespace(data=b"value")
        )

        manager = GCPSecretManager(
            project_id="test-project",
            version="3",
            secrets=[{"name": "key"}],
            client=mock_client,
        )

        manager.load_secrets("tenant1")

        call_args = mock_client.access_secret_version.call_args[1]
        resource_name = call_args["name"]
        assert "/versions/3" in resource_name

    def test_handles_full_resource_name(self):
        mock_client = MagicMock()
        mock_client.access_secret_version.return_value = SimpleNamespace(
            payload=SimpleNamespace(data=b"value")
        )

        manager = GCPSecretManager(
            project_id="test-project",
            secrets=[{"name": "projects/other-project/secrets/key"}],
            client=mock_client,
        )

        manager.load_secrets("tenant1")

        call_args = mock_client.access_secret_version.call_args[1]
        resource_name = call_args["name"]
        # Should use the full path as-is
        assert "projects/other-project/secrets/key" in resource_name

    def test_raises_when_no_secrets_or_bundle(self):
        manager = GCPSecretManager(project_id="test-project", client=MagicMock())

        with pytest.raises(ValueError, match="requires either"):
            manager.load_secrets("tenant1")

    def test_raises_when_bundle_not_dict(self):
        mock_client = MagicMock()
        # Return valid JSON that's not a dict (e.g., a string)
        mock_client.access_secret_version.return_value = SimpleNamespace(
            payload=SimpleNamespace(data=b'"just a string"')
        )

        manager = GCPSecretManager(
            project_id="test-project",
            bundle_secret_id_template="bundle-{tenant}",
            bundle_format="json",
            client=mock_client,
        )

        with pytest.raises(ValueError, match="must deserialize into a dictionary"):
            manager.load_secrets("tenant1")

    def test_parses_secret_with_format_hint(self):
        mock_client = MagicMock()
        mock_client.access_secret_version.return_value = SimpleNamespace(
            payload=SimpleNamespace(data=b"KEY1=value1\nKEY2=value2")
        )

        manager = GCPSecretManager(
            project_id="test-project",
            secrets=[{"name": "db", "format": "env"}],
            client=mock_client,
        )

        secrets = manager.load_secrets("tenant1")

        assert secrets["db"]["KEY1"] == "value1"
        assert secrets["db"]["KEY2"] == "value2"

    def test_expands_env_vars_in_bundle(self, monkeypatch):
        monkeypatch.setenv("DB_HOST", "localhost")
        mock_client = MagicMock()
        mock_client.access_secret_version.return_value = SimpleNamespace(
            payload=SimpleNamespace(data=b'{"host": "${DB_HOST}"}')
        )

        manager = GCPSecretManager(
            project_id="test-project",
            bundle_secret_id_template="bundle-{tenant}",
            client=mock_client,
        )

        secrets = manager.load_secrets("tenant1")

        assert secrets["host"] == "localhost"
