"""Tests for FilesystemSecretManager - focus on our file reading and parsing logic."""

import json
from pathlib import Path

import pytest

from dativo_ingest.secrets.managers.filesystem import FilesystemSecretManager


class TestFilesystemSecretManager:
    """Test filesystem secret manager logic."""

    def test_loads_json_files(self, tmp_path):
        tenant_dir = tmp_path / "tenant_a"
        tenant_dir.mkdir()
        (tenant_dir / "config.json").write_text(
            '{"host": "localhost", "port": 5432}', encoding="utf-8"
        )

        manager = FilesystemSecretManager(secrets_dir=tmp_path)
        secrets = manager.load_secrets("tenant_a")

        assert secrets["config"] == {"host": "localhost", "port": 5432}

    def test_loads_env_files(self, tmp_path):
        tenant_dir = tmp_path / "tenant_a"
        tenant_dir.mkdir()
        (tenant_dir / "postgres.env").write_text(
            "PGHOST=localhost\nPGPORT=5432", encoding="utf-8"
        )

        manager = FilesystemSecretManager(secrets_dir=tmp_path)
        secrets = manager.load_secrets("tenant_a")

        assert secrets["postgres"]["PGHOST"] == "localhost"
        assert secrets["postgres"]["PGPORT"] == "5432"

    def test_loads_plaintext_files(self, tmp_path):
        tenant_dir = tmp_path / "tenant_a"
        tenant_dir.mkdir()
        (tenant_dir / "api_key").write_text("sk_live_123", encoding="utf-8")

        manager = FilesystemSecretManager(secrets_dir=tmp_path)
        secrets = manager.load_secrets("tenant_a")

        assert secrets["api_key"] == "sk_live_123"

    def test_expands_env_vars_in_json(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DB_HOST", "localhost")
        tenant_dir = tmp_path / "tenant_a"
        tenant_dir.mkdir()
        (tenant_dir / "config.json").write_text(
            '{"host": "${DB_HOST}"}', encoding="utf-8"
        )

        manager = FilesystemSecretManager(secrets_dir=tmp_path)
        secrets = manager.load_secrets("tenant_a")

        assert secrets["config"]["host"] == "localhost"

    def test_expands_env_vars_in_plaintext(self, tmp_path, monkeypatch):
        monkeypatch.setenv("API_KEY", "sk_secret")
        tenant_dir = tmp_path / "tenant_a"
        tenant_dir.mkdir()
        (tenant_dir / "key").write_text("${API_KEY}", encoding="utf-8")

        manager = FilesystemSecretManager(secrets_dir=tmp_path)
        secrets = manager.load_secrets("tenant_a")

        assert secrets["key"] == "sk_secret"

    def test_uses_stem_as_secret_name(self, tmp_path):
        tenant_dir = tmp_path / "tenant_a"
        tenant_dir.mkdir()
        (tenant_dir / "postgres.env").write_text("PGHOST=localhost", encoding="utf-8")

        manager = FilesystemSecretManager(secrets_dir=tmp_path)
        secrets = manager.load_secrets("tenant_a")

        assert "postgres" in secrets
        assert "postgres.env" not in secrets

    def test_skips_hidden_files(self, tmp_path):
        tenant_dir = tmp_path / "tenant_a"
        tenant_dir.mkdir()
        (tenant_dir / ".hidden").write_text("secret", encoding="utf-8")
        (tenant_dir / "visible").write_text("public", encoding="utf-8")

        manager = FilesystemSecretManager(secrets_dir=tmp_path)
        secrets = manager.load_secrets("tenant_a")

        assert ".hidden" not in secrets
        assert "visible" in secrets

    def test_skips_directories(self, tmp_path):
        tenant_dir = tmp_path / "tenant_a"
        tenant_dir.mkdir()
        (tenant_dir / "subdir").mkdir()
        (tenant_dir / "file").write_text("content", encoding="utf-8")

        manager = FilesystemSecretManager(secrets_dir=tmp_path)
        secrets = manager.load_secrets("tenant_a")

        assert "subdir" not in secrets
        assert "file" in secrets

    def test_handles_multiple_files(self, tmp_path):
        tenant_dir = tmp_path / "tenant_a"
        tenant_dir.mkdir()
        (tenant_dir / "config.json").write_text('{"key": "value"}', encoding="utf-8")
        (tenant_dir / "api_key").write_text("sk_123", encoding="utf-8")
        (tenant_dir / "db.env").write_text("HOST=localhost", encoding="utf-8")

        manager = FilesystemSecretManager(secrets_dir=tmp_path)
        secrets = manager.load_secrets("tenant_a")

        assert len(secrets) == 3
        assert secrets["config"] == {"key": "value"}
        assert secrets["api_key"] == "sk_123"
        assert secrets["db"]["HOST"] == "localhost"

    def test_raises_when_tenant_dir_missing(self, tmp_path):
        manager = FilesystemSecretManager(secrets_dir=tmp_path)

        with pytest.raises(ValueError, match="Secrets directory not found"):
            manager.load_secrets("nonexistent_tenant")

    def test_handles_invalid_json_gracefully(self, tmp_path):
        """Test that invalid JSON files don't crash the manager."""
        tenant_dir = tmp_path / "tenant_a"
        tenant_dir.mkdir()
        (tenant_dir / "good.json").write_text('{"key": "value"}', encoding="utf-8")
        (tenant_dir / "bad.json").write_text("not valid json {", encoding="utf-8")

        manager = FilesystemSecretManager(secrets_dir=tmp_path)
        # Should not raise, but log warning for bad file
        secrets = manager.load_secrets("tenant_a")

        # Good file should still be loaded
        assert "good" in secrets
        # Bad file should be skipped (error logged but not raised)
        assert "bad" not in secrets
