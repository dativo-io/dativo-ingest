"""Tests for secret manager factory and registry."""

from pathlib import Path

import pytest

from dativo_ingest.secrets import (
    AWSSecretsManager,
    EnvironmentSecretManager,
    FilesystemSecretManager,
    GCPSecretManager,
    HashicorpVaultSecretManager,
    create_secret_manager,
    load_secrets,
)


class TestCreateSecretManager:
    """Test secret manager factory function."""

    def test_creates_environment_manager_by_default(self):
        manager = create_secret_manager(None)
        assert isinstance(manager, EnvironmentSecretManager)

    def test_creates_environment_manager_explicitly(self):
        manager = create_secret_manager("env")
        assert isinstance(manager, EnvironmentSecretManager)

    def test_creates_environment_manager_with_alias(self):
        manager = create_secret_manager("environment")
        assert isinstance(manager, EnvironmentSecretManager)

    def test_creates_filesystem_manager(self):
        manager = create_secret_manager("filesystem", secrets_dir=Path("/tmp"))
        assert isinstance(manager, FilesystemSecretManager)
        assert manager.secrets_dir == Path("/tmp")

    def test_creates_filesystem_manager_with_alias(self):
        manager = create_secret_manager("fs", secrets_dir=Path("/tmp"))
        assert isinstance(manager, FilesystemSecretManager)

    def test_creates_vault_manager(self):
        manager = create_secret_manager(
            "vault", config={"address": "http://localhost", "token": "test"}
        )
        assert isinstance(manager, HashicorpVaultSecretManager)

    def test_creates_vault_manager_with_alias(self):
        manager = create_secret_manager(
            "hashicorp", config={"address": "http://localhost", "token": "test"}
        )
        assert isinstance(manager, HashicorpVaultSecretManager)

    def test_creates_aws_manager(self):
        manager = create_secret_manager("aws", config={"region_name": "us-east-1"})
        assert isinstance(manager, AWSSecretsManager)

    def test_creates_aws_manager_with_alias(self):
        manager = create_secret_manager(
            "aws_secrets_manager", config={"region_name": "us-east-1"}
        )
        assert isinstance(manager, AWSSecretsManager)

    def test_creates_gcp_manager(self):
        manager = create_secret_manager("gcp", config={"project_id": "test-project"})
        assert isinstance(manager, GCPSecretManager)

    def test_creates_gcp_manager_with_alias(self):
        manager = create_secret_manager(
            "gcp_secret_manager", config={"project_id": "test-project"}
        )
        assert isinstance(manager, GCPSecretManager)

    def test_passes_config_to_manager(self):
        manager = create_secret_manager(
            "env", config={"prefix": "CUSTOM", "delimiter": "::"}
        )
        assert manager.prefix == "CUSTOM"
        assert manager.delimiter == "::"

    def test_raises_on_unsupported_manager(self):
        with pytest.raises(ValueError, match="Unsupported secret manager"):
            create_secret_manager("invalid_manager")

    def test_case_insensitive_manager_type(self):
        manager = create_secret_manager("ENV")
        assert isinstance(manager, EnvironmentSecretManager)


class TestLoadSecrets:
    """Test high-level load_secrets function."""

    def test_loads_from_environment_by_default(self, monkeypatch):
        monkeypatch.setenv("DATIVO_SECRET__TENANT_X__api_key__text", "abc123")
        secrets = load_secrets("tenant_x")
        assert secrets["api_key"] == "abc123"

    def test_loads_from_filesystem_manager(self, tmp_path):
        tenant_dir = tmp_path / "tenant_a"
        tenant_dir.mkdir()
        (tenant_dir / "api_key").write_text("secret123", encoding="utf-8")

        secrets = load_secrets(
            "tenant_a",
            secrets_dir=tmp_path,
            manager_type="filesystem",
        )
        assert secrets["api_key"] == "secret123"

    def test_passes_manager_config(self, monkeypatch):
        monkeypatch.setenv("DATIVO_SECRET__TENANT_X__key__text", "value1")
        monkeypatch.setenv("CUSTOM_SECRET__TENANT_X__key__text", "value2")

        # Default prefix won't find CUSTOM_SECRET
        secrets1 = load_secrets("tenant_x")
        assert "key" not in secrets1 or secrets1.get("key") != "value2"

        # Custom prefix will find CUSTOM_SECRET
        secrets2 = load_secrets(
            "tenant_x",
            manager_type="env",
            manager_config={"prefix": "CUSTOM_SECRET"},
        )
        assert secrets2["key"] == "value2"
