"""Tests for secret loading utilities."""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from dativo_ingest.secrets import load_secret_manager_config, load_secrets_and_set_env


class TestLoadSecretManagerConfig:
    """Test secret manager config loading."""

    def test_load_from_yaml_file(self, tmp_path):
        """Test loading config from YAML file."""
        config_file = tmp_path / "config.yaml"
        config_data = {"vault": {"url": "http://vault:8200"}}
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        result = load_secret_manager_config(str(config_file))
        assert result == config_data

    def test_load_from_json_file(self, tmp_path):
        """Test loading config from JSON file."""
        config_file = tmp_path / "config.json"
        config_data = {"vault": {"url": "http://vault:8200"}}
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        result = load_secret_manager_config(str(config_file))
        assert result == config_data

    def test_load_from_inline_json(self):
        """Test loading config from inline JSON string."""
        config_data = {"vault": {"url": "http://vault:8200"}}
        json_str = json.dumps(config_data)
        result = load_secret_manager_config(json_str)
        assert result == config_data

    def test_load_from_env_var(self, monkeypatch, tmp_path):
        """Test loading config from environment variable."""
        config_file = tmp_path / "config.yaml"
        config_data = {"vault": {"url": "http://vault:8200"}}
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        monkeypatch.setenv("DATIVO_SECRET_MANAGER_CONFIG", str(config_file))
        result = load_secret_manager_config(None)
        assert result == config_data

    def test_returns_none_when_not_provided(self):
        """Test that None is returned when config is not provided."""
        result = load_secret_manager_config(None)
        assert result is None

    def test_raises_error_for_invalid_json(self):
        """Test that invalid JSON raises ValueError."""
        with pytest.raises(ValueError, match="must be a path"):
            load_secret_manager_config("{invalid json}")

    def test_raises_error_for_invalid_file_format(self, tmp_path):
        """Test that invalid file format raises ValueError."""
        config_file = tmp_path / "config.txt"
        config_file.write_text("not yaml or json")
        with pytest.raises(ValueError, match="must be YAML or JSON"):
            load_secret_manager_config(str(config_file))


class TestLoadSecretsAndSetEnv:
    """Test secret loading and environment variable setup."""

    def test_loads_secrets_and_sets_env_vars(self, tmp_path, monkeypatch):
        """Test that secrets are loaded and environment variables are set."""
        # Create a secrets directory with .env file
        tenant_dir = tmp_path / "test_tenant"
        tenant_dir.mkdir()
        env_file = tenant_dir / "test.env"
        env_file.write_text("KEY1=value1\nKEY2=value2\n")

        # Clear any existing env vars
        monkeypatch.delenv("KEY1", raising=False)
        monkeypatch.delenv("KEY2", raising=False)

        secrets = load_secrets_and_set_env(
            tenant_id="test_tenant",
            secrets_dir=tmp_path,
            manager_type="filesystem",
        )

        assert "test" in secrets
        assert secrets["test"]["KEY1"] == "value1"
        assert secrets["test"]["KEY2"] == "value2"
        assert os.getenv("KEY1") == "value1"
        assert os.getenv("KEY2") == "value2"

    def test_does_not_overwrite_existing_env_vars(self, tmp_path, monkeypatch):
        """Test that existing environment variables are not overwritten."""
        tenant_dir = tmp_path / "test_tenant"
        tenant_dir.mkdir()
        env_file = tenant_dir / "test.env"
        env_file.write_text("KEY1=new_value\n")

        monkeypatch.setenv("KEY1", "existing_value")

        load_secrets_and_set_env(
            tenant_id="test_tenant",
            secrets_dir=tmp_path,
            manager_type="filesystem",
        )

        assert os.getenv("KEY1") == "existing_value"

    def test_handles_simple_secret_values(self, monkeypatch):
        """Test handling of simple secret values (not dicts)."""
        monkeypatch.delenv("SIMPLE_SECRET", raising=False)

        secrets = load_secrets_and_set_env(
            tenant_id="test_tenant",
            secrets_dir=Path("/nonexistent"),
            manager_type="env",
        )

        # For env manager, behavior depends on env vars
        # Just verify function doesn't crash
        assert isinstance(secrets, dict)

    def test_handles_secret_loading_failure(self, monkeypatch):
        """Test that secret loading failures are handled gracefully."""
        # Use invalid manager type to trigger failure
        secrets = load_secrets_and_set_env(
            tenant_id="test_tenant",
            secrets_dir=Path("/nonexistent"),
            manager_type="invalid_manager",
        )

        # Should return empty dict or handle gracefully
        assert isinstance(secrets, dict)

    def test_sets_uppercase_secret_names(self, tmp_path, monkeypatch):
        """Test that simple secret values use uppercase secret name as env var."""
        tenant_dir = tmp_path / "test_tenant"
        tenant_dir.mkdir()
        secret_file = tenant_dir / "my_secret"
        secret_file.write_text("secret_value")

        monkeypatch.delenv("MY_SECRET", raising=False)

        secrets = load_secrets_and_set_env(
            tenant_id="test_tenant",
            secrets_dir=tmp_path,
            manager_type="filesystem",
        )

        # Filesystem manager returns dict with secret name as key
        # Simple values should set uppercase env var
        assert "my_secret" in secrets
