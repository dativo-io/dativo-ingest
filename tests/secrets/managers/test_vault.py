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
