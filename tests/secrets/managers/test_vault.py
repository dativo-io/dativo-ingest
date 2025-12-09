"""Tests for HashicorpVaultSecretManager - focus on our path merging and auth logic."""

from unittest.mock import MagicMock

import pytest

from dativo_ingest.secrets.managers.vault import HashicorpVaultSecretManager


class TestHashiCorpVaultSecretManager:
    """Test HashiCorp Vault secret manager logic."""

    def test_loads_secrets_from_single_path(self):
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"token": "abc", "key": "value"}}
        }

        manager = HashicorpVaultSecretManager(
            address="http://vault.local",
            token="root",
            path_template="tenants/{tenant}",
            client_factory=lambda: mock_client,
        )

        secrets = manager.load_secrets("tenant1")

        assert secrets["token"] == "abc"
        assert secrets["key"] == "value"

    def test_merges_secrets_from_multiple_paths(self):
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.side_effect = [
            {"data": {"data": {"token": "abc"}}},
            {"data": {"data": {"nested": {"secret": "xyz"}}}},
        ]

        manager = HashicorpVaultSecretManager(
            address="http://vault.local",
            token="root",
            path_template="tenants/{tenant}",
            paths=["tenants/{tenant}", "shared/{tenant}"],
            client_factory=lambda: mock_client,
        )

        secrets = manager.load_secrets("tenant1")

        assert secrets["token"] == "abc"
        assert secrets["nested"]["secret"] == "xyz"

    def test_renders_path_template_with_tenant(self):
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {}}
        }

        manager = HashicorpVaultSecretManager(
            address="http://vault.local",
            token="root",
            path_template="dativo/{tenant}/secrets",
            client_factory=lambda: mock_client,
        )

        manager.load_secrets("tenant1")

        call_args = mock_client.secrets.kv.v2.read_secret_version.call_args[1]
        assert call_args["path"] == "dativo/tenant1/secrets"

    def test_uses_kv_v1_when_specified(self):
        mock_client = MagicMock()
        mock_client.secrets.kv.v1.read_secret.return_value = {"data": {"token": "abc"}}

        manager = HashicorpVaultSecretManager(
            address="http://vault.local",
            token="root",
            kv_version=1,
            client_factory=lambda: mock_client,
        )

        secrets = manager.load_secrets("tenant1")

        assert secrets["token"] == "abc"
        mock_client.secrets.kv.v1.read_secret.assert_called_once()

    def test_uses_custom_mount_point(self):
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {}}
        }

        manager = HashicorpVaultSecretManager(
            address="http://vault.local",
            token="root",
            mount_point="custom-mount",
            client_factory=lambda: mock_client,
        )

        manager.load_secrets("tenant1")

        call_args = mock_client.secrets.kv.v2.read_secret_version.call_args[1]
        assert call_args["mount_point"] == "custom-mount"

    def test_paths_can_override_mount_point(self):
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {}}
        }

        manager = HashicorpVaultSecretManager(
            address="http://vault.local",
            token="root",
            mount_point="default-mount",
            paths=[{"path": "secrets/{tenant}", "mount_point": "custom-mount"}],
            client_factory=lambda: mock_client,
        )

        manager.load_secrets("tenant1")

        call_args = mock_client.secrets.kv.v2.read_secret_version.call_args[1]
        assert call_args["mount_point"] == "custom-mount"

    def test_paths_can_override_kv_version(self):
        mock_client = MagicMock()
        mock_client.secrets.kv.v1.read_secret.return_value = {"data": {}}

        manager = HashicorpVaultSecretManager(
            address="http://vault.local",
            token="root",
            kv_version=2,
            paths=[{"path": "secrets/{tenant}", "kv_version": 1}],
            client_factory=lambda: mock_client,
        )

        manager.load_secrets("tenant1")

        mock_client.secrets.kv.v1.read_secret.assert_called_once()

    def test_normalizes_string_paths(self):
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {}}
        }

        manager = HashicorpVaultSecretManager(
            address="http://vault.local",
            token="root",
            paths=["path1/{tenant}", "path2/{tenant}"],
            client_factory=lambda: mock_client,
        )

        manager.load_secrets("tenant1")

        assert mock_client.secrets.kv.v2.read_secret_version.call_count == 2

    def test_normalizes_dict_paths(self):
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {}}
        }

        manager = HashicorpVaultSecretManager(
            address="http://vault.local",
            token="root",
            paths=[
                {"path": "path1/{tenant}"},
                {"path": "path2/{tenant}", "mount_point": "custom"},
            ],
            client_factory=lambda: mock_client,
        )

        manager.load_secrets("tenant1")

        assert mock_client.secrets.kv.v2.read_secret_version.call_count == 2

    def test_raises_on_invalid_path_format(self):
        with pytest.raises(ValueError, match="must be a string or dict"):
            HashicorpVaultSecretManager(
                address="http://vault.local",
                token="root",
                paths=[123],  # Invalid type
            )

    def test_raises_when_address_missing(self):
        with pytest.raises(ValueError, match="Vault address is required"):
            HashicorpVaultSecretManager(address=None)

    def test_uses_env_var_for_address(self, monkeypatch):
        monkeypatch.setenv("VAULT_ADDR", "http://vault.from.env")
        manager = HashicorpVaultSecretManager(token="root")
        assert manager.address == "http://vault.from.env"

    def test_uses_env_var_for_namespace(self, monkeypatch):
        monkeypatch.setenv("VAULT_NAMESPACE", "ns1")
        manager = HashicorpVaultSecretManager(
            address="http://vault.local", token="root"
        )
        assert manager.namespace == "ns1"

    def test_handles_empty_path_responses(self):
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = None

        manager = HashicorpVaultSecretManager(
            address="http://vault.local",
            token="root",
            client_factory=lambda: mock_client,
        )

        secrets = manager.load_secrets("tenant1")

        assert secrets == {}

    def test_expands_env_vars_in_secrets(self, monkeypatch):
        monkeypatch.setenv("DB_HOST", "localhost")
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"host": "${DB_HOST}"}}
        }

        manager = HashicorpVaultSecretManager(
            address="http://vault.local",
            token="root",
            client_factory=lambda: mock_client,
        )

        secrets = manager.load_secrets("tenant1")

        assert secrets["host"] == "localhost"

    def test_smoke_test_load_secret_successfully(self):
        """Smoke test: Validate that Vault manager can successfully load a secret at runtime."""
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {
                "data": {
                    "api_key": "test-api-key-123",
                    "database_url": "postgres://localhost/db",
                }
            }
        }

        manager = HashicorpVaultSecretManager(
            address="http://vault.local",
            token="test-token",
            client_factory=lambda: mock_client,
        )

        secrets = manager.load_secrets("tenant1")

        assert "api_key" in secrets
        assert secrets["api_key"] == "test-api-key-123"
        assert "database_url" in secrets
        assert secrets["database_url"] == "postgres://localhost/db"
        # Note: is_authenticated is not called when using client_factory
        # because _build_client is bypassed
        mock_client.secrets.kv.v2.read_secret_version.assert_called_once()

    def test_raises_import_error_when_hvac_missing(self):
        """Test that ImportError is raised when hvac is not installed."""
        import sys
        from unittest.mock import patch

        # Temporarily remove hvac from sys.modules if present
        hvac_backup = sys.modules.pop("hvac", None)
        try:
            with patch.dict("sys.modules", {"hvac": None}):
                manager = HashicorpVaultSecretManager(
                    address="http://vault.local",
                    token="test-token",
                )
                with pytest.raises(ImportError, match="hvac is required"):
                    manager._build_client()
        finally:
            if hvac_backup:
                sys.modules["hvac"] = hvac_backup

    def test_raises_value_error_when_token_missing(self):
        """Test that ValueError is raised when token is missing for token auth."""
        from unittest.mock import patch, MagicMock

        # Mock hvac to avoid ImportError
        mock_hvac = MagicMock()
        mock_client = MagicMock()
        mock_hvac.Client.return_value = mock_client

        with patch("dativo_ingest.secrets.managers.vault.hvac", mock_hvac):
            with pytest.raises(ValueError, match="Vault token is required"):
                HashicorpVaultSecretManager(
                    address="http://vault.local",
                    auth_method="token",
                    token=None,
                )._build_client()

    def test_raises_value_error_when_approle_credentials_missing(self):
        """Test that ValueError is raised when role_id or secret_id is missing for approle auth."""
        from unittest.mock import patch, MagicMock

        # Mock hvac to avoid ImportError
        mock_hvac = MagicMock()
        mock_client = MagicMock()
        mock_hvac.Client.return_value = mock_client

        with patch("dativo_ingest.secrets.managers.vault.hvac", mock_hvac):
            with pytest.raises(ValueError, match="role_id and secret_id are required"):
                HashicorpVaultSecretManager(
                    address="http://vault.local",
                    auth_method="approle",
                    role_id=None,
                    secret_id="test-secret-id",
                )._build_client()

            with pytest.raises(ValueError, match="role_id and secret_id are required"):
                HashicorpVaultSecretManager(
                    address="http://vault.local",
                    auth_method="approle",
                    role_id="test-role-id",
                    secret_id=None,
                )._build_client()

    def test_raises_value_error_when_authentication_fails(self):
        """Test that ValueError is raised when Vault authentication fails."""
        from unittest.mock import patch, MagicMock

        # Mock hvac module and client that fails authentication
        mock_hvac_module = MagicMock()
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = False
        mock_hvac_module.Client.return_value = mock_client

        # Patch the hvac import inside the vault module
        with patch("dativo_ingest.secrets.managers.vault.hvac", mock_hvac_module):
            manager = HashicorpVaultSecretManager(
                address="http://vault.local",
                token="invalid-token",
            )

            with pytest.raises(ValueError, match="Vault authentication failed"):
                manager._build_client()

    def test_handles_missing_secret_path_gracefully(self):
        """Test that missing secret paths return empty dict rather than raising exception."""
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        # Simulate path not found - Vault returns None or empty response
        mock_client.secrets.kv.v2.read_secret_version.return_value = None

        manager = HashicorpVaultSecretManager(
            address="http://vault.local",
            token="test-token",
            client_factory=lambda: mock_client,
        )

        secrets = manager.load_secrets("tenant1")

        assert secrets == {}
