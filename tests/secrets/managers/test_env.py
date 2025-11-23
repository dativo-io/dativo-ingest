"""Tests for EnvironmentSecretManager - focus on our parsing and filtering logic."""

import pytest

from dativo_ingest.secrets.managers.env import EnvironmentSecretManager


class TestEnvironmentSecretManager:
    """Test environment variable secret manager logic."""

    def test_loads_tenant_specific_secrets(self, monkeypatch):
        monkeypatch.setenv("DATIVO_SECRET__TENANT_A__postgres__env", "PGHOST=db")
        manager = EnvironmentSecretManager()

        secrets = manager.load_secrets("tenant_a")

        assert "postgres" in secrets
        assert secrets["postgres"]["PGHOST"] == "db"

    def test_loads_global_secrets(self, monkeypatch):
        monkeypatch.setenv("DATIVO_SECRET__GLOBAL__api_key__text", "sk_live_123")
        manager = EnvironmentSecretManager()

        secrets = manager.load_secrets("tenant_a")

        assert secrets["api_key"] == "sk_live_123"

    def test_ignores_other_tenant_secrets(self, monkeypatch):
        monkeypatch.setenv("DATIVO_SECRET__TENANT_A__key1__text", "value1")
        monkeypatch.setenv("DATIVO_SECRET__TENANT_B__key2__text", "value2")
        manager = EnvironmentSecretManager()

        secrets = manager.load_secrets("tenant_a")

        assert "key1" in secrets
        assert "key2" not in secrets

    def test_parses_json_format(self, monkeypatch):
        monkeypatch.setenv(
            "DATIVO_SECRET__TENANT_A__config__json", '{"host": "localhost"}'
        )
        manager = EnvironmentSecretManager()

        secrets = manager.load_secrets("tenant_a")

        assert secrets["config"] == {"host": "localhost"}

    def test_parses_env_format(self, monkeypatch):
        monkeypatch.setenv(
            "DATIVO_SECRET__TENANT_A__db__env", "PGHOST=localhost\nPGPORT=5432"
        )
        manager = EnvironmentSecretManager()

        secrets = manager.load_secrets("tenant_a")

        assert secrets["db"]["PGHOST"] == "localhost"
        assert secrets["db"]["PGPORT"] == "5432"

    def test_parses_text_format(self, monkeypatch):
        monkeypatch.setenv("DATIVO_SECRET__TENANT_A__api_key__text", "sk_live_123")
        manager = EnvironmentSecretManager()

        secrets = manager.load_secrets("tenant_a")

        assert secrets["api_key"] == "sk_live_123"

    def test_auto_detects_json_format(self, monkeypatch):
        monkeypatch.setenv("DATIVO_SECRET__TENANT_A__config", '{"key": "value"}')
        manager = EnvironmentSecretManager()

        secrets = manager.load_secrets("tenant_a")

        assert secrets["config"] == {"key": "value"}

    def test_auto_detects_env_format(self, monkeypatch):
        monkeypatch.setenv("DATIVO_SECRET__TENANT_A__db", "KEY1=value1\nKEY2=value2")
        manager = EnvironmentSecretManager()

        secrets = manager.load_secrets("tenant_a")

        assert isinstance(secrets["db"], dict)
        assert secrets["db"]["KEY1"] == "value1"

    def test_expands_environment_variables(self, monkeypatch):
        monkeypatch.setenv("DB_PASSWORD", "secret123")
        monkeypatch.setenv(
            "DATIVO_SECRET__TENANT_A__db__env",
            "PGHOST=localhost\nPGPASSWORD=${DB_PASSWORD}",
        )
        manager = EnvironmentSecretManager()

        secrets = manager.load_secrets("tenant_a")

        assert secrets["db"]["PGPASSWORD"] == "secret123"

    def test_sanitizes_secret_names(self, monkeypatch):
        monkeypatch.setenv("DATIVO_SECRET__TENANT_A__MY__SECRET__KEY__text", "value")
        manager = EnvironmentSecretManager()

        secrets = manager.load_secrets("tenant_a")

        assert "my_secret_key" in secrets

    def test_case_insensitive_tenant_matching(self, monkeypatch):
        monkeypatch.setenv("DATIVO_SECRET__TENANT_A__key__text", "value1")
        monkeypatch.setenv("DATIVO_SECRET__tenant_a__key2__text", "value2")
        manager = EnvironmentSecretManager()

        secrets = manager.load_secrets("TENANT_A")

        assert secrets["key"] == "value1"
        assert secrets["key2"] == "value2"

    def test_custom_prefix(self, monkeypatch):
        monkeypatch.setenv("CUSTOM__TENANT_A__key__text", "value")
        manager = EnvironmentSecretManager(prefix="CUSTOM", delimiter="__")

        secrets = manager.load_secrets("tenant_a")

        assert secrets["key"] == "value"

    def test_custom_delimiter(self, monkeypatch):
        monkeypatch.setenv("DATIVO_SECRET::TENANT_A::key::text", "value")
        manager = EnvironmentSecretManager(delimiter="::")

        secrets = manager.load_secrets("tenant_a")

        assert secrets["key"] == "value"

    def test_disables_global_scope(self, monkeypatch):
        monkeypatch.setenv("DATIVO_SECRET__GLOBAL__key__text", "value")
        manager = EnvironmentSecretManager(allow_global_scope=False)

        secrets = manager.load_secrets("tenant_a")

        assert "key" not in secrets

    def test_ignores_invalid_format(self, monkeypatch):
        monkeypatch.setenv("DATIVO_SECRET__TENANT_A__key__invalid", "value")
        manager = EnvironmentSecretManager()

        secrets = manager.load_secrets("tenant_a")

        # Invalid format hint is treated as part of the name
        assert "key_invalid" in secrets

    def test_handles_multi_part_secret_names(self, monkeypatch):
        monkeypatch.setenv("DATIVO_SECRET__TENANT_A__stripe__api__key__text", "sk_123")
        manager = EnvironmentSecretManager()

        secrets = manager.load_secrets("tenant_a")

        assert secrets["stripe_api_key"] == "sk_123"
