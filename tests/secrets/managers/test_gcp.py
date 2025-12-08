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

    def test_smoke_test_load_secret_successfully(self):
        """Smoke test: Validate that GCP manager can successfully load a secret at runtime."""
        mock_client = MagicMock()
        mock_client.access_secret_version.return_value = SimpleNamespace(
            payload=SimpleNamespace(
                data=b'{"api_key": "test-api-key-123", "database_url": "postgres://localhost/db"}'
            )
        )

        manager = GCPSecretManager(
            project_id="test-project",
            secrets=[{"name": "config", "format": "json"}],
            client=mock_client,
        )

        secrets = manager.load_secrets("tenant1")

        assert "config" in secrets
        assert secrets["config"]["api_key"] == "test-api-key-123"
        assert secrets["config"]["database_url"] == "postgres://localhost/db"
        mock_client.access_secret_version.assert_called_once()

    def test_raises_import_error_when_google_cloud_secret_manager_missing(self):
        """Test that ImportError is raised when google-cloud-secret-manager is not installed."""
        import sys
        from unittest.mock import patch

        # Temporarily remove google.cloud.secretmanager from sys.modules if present
        gcp_backup = sys.modules.pop("google.cloud.secretmanager", None)
        try:
            with patch.dict("sys.modules", {"google.cloud.secretmanager": None}):
                manager = GCPSecretManager(project_id="test-project")
                with pytest.raises(
                    ImportError, match="google-cloud-secret-manager is required"
                ):
                    manager._build_client()
        finally:
            if gcp_backup:
                sys.modules["google.cloud.secretmanager"] = gcp_backup

    def test_raises_not_found_when_secret_not_found(self):
        """Test that NotFound exception is raised when secret is not found in GCP."""
        from google.api_core import exceptions as gcp_exceptions

        mock_client = MagicMock()
        mock_client.access_secret_version.side_effect = gcp_exceptions.NotFound(
            "Secret version projects/test-project/secrets/missing_secret/versions/latest not found"
        )

        manager = GCPSecretManager(
            project_id="test-project",
            secrets=[{"name": "missing_secret"}],
            client=mock_client,
        )

        with pytest.raises(gcp_exceptions.NotFound):
            manager.load_secrets("tenant1")

    def test_raises_value_error_when_project_id_missing(self):
        """Test that ValueError is raised when project_id is missing."""
        with pytest.raises(ValueError, match="project_id is required"):
            GCPSecretManager(project_id=None)

    def test_raises_value_error_when_no_secrets_or_bundle_configured(self):
        """Test that ValueError is raised when neither secrets nor bundle is configured."""
        manager = GCPSecretManager(project_id="test-project", client=MagicMock())

        with pytest.raises(ValueError, match="requires either"):
            manager.load_secrets("tenant1")
