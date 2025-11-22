"""Tests for the pluggable secret manager system."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from dativo_ingest.secret_managers import (
    EnvSecretManager,
    FilesystemSecretManager,
    create_secret_manager,
)
from dativo_ingest.secret_managers.base import SecretManager


class TestSecretManagerBase:
    """Tests for the base SecretManager class."""

    def test_expand_env_vars_string(self):
        """Test environment variable expansion in strings."""
        os.environ["TEST_VAR"] = "test_value"
        result = SecretManager.expand_env_vars("prefix_${TEST_VAR}_suffix")
        assert result == "prefix_test_value_suffix"

    def test_expand_env_vars_dict(self):
        """Test environment variable expansion in dictionaries."""
        os.environ["TEST_VAR"] = "test_value"
        data = {"key": "${TEST_VAR}", "nested": {"value": "$TEST_VAR"}}
        result = SecretManager.expand_env_vars(data)
        assert result["key"] == "test_value"
        assert result["nested"]["value"] == "test_value"

    def test_expand_env_vars_list(self):
        """Test environment variable expansion in lists."""
        os.environ["TEST_VAR"] = "test_value"
        data = ["${TEST_VAR}", "plain", "$TEST_VAR"]
        result = SecretManager.expand_env_vars(data)
        assert result == ["test_value", "plain", "test_value"]


class TestEnvSecretManager:
    """Tests for the EnvSecretManager."""

    def test_load_secrets_tenant_specific(self):
        """Test loading tenant-specific secrets from environment variables."""
        os.environ["ACME_STRIPE_API_KEY"] = "sk_test_123"
        os.environ["ACME_DATABASE_URL"] = "postgres://localhost/db"
        
        manager = EnvSecretManager()
        secrets = manager.load_secrets("acme")
        
        assert "stripe_api_key" in secrets
        assert secrets["stripe_api_key"] == "sk_test_123"
        assert "database_url" in secrets
        assert secrets["database_url"] == "postgres://localhost/db"

    def test_load_secrets_generic_fallback(self):
        """Test falling back to generic secrets when tenant-specific not found."""
        os.environ["STRIPE_API_KEY"] = "sk_test_generic"
        
        manager = EnvSecretManager(config={"allow_generic": True})
        secrets = manager.load_secrets("acme")
        
        assert "stripe_api_key" in secrets
        assert secrets["stripe_api_key"] == "sk_test_generic"

    def test_load_secrets_no_generic_fallback(self):
        """Test that generic secrets are not loaded when disabled."""
        os.environ["STRIPE_API_KEY"] = "sk_test_generic"
        
        manager = EnvSecretManager(config={"allow_generic": False})
        secrets = manager.load_secrets("acme")
        
        # Should not include generic secrets
        assert "stripe_api_key" not in secrets

    def test_load_secrets_json_parsing(self):
        """Test parsing of JSON environment variables."""
        # Clear all ACME_ variables first
        for key in list(os.environ.keys()):
            if key.startswith("ACME_"):
                del os.environ[key]
        
        json_data = {"type": "service_account", "project_id": "my-project"}
        os.environ["ACME_GSHEETS_JSON"] = json.dumps(json_data)
        
        manager = EnvSecretManager(config={"allow_generic": False})
        secrets = manager.load_secrets("acme")
        
        # The _JSON suffix is stripped, so the secret is stored as "gsheets"
        assert "gsheets" in secrets
        assert isinstance(secrets["gsheets"], dict)
        assert secrets["gsheets"]["project_id"] == "my-project"

    def test_load_common_patterns_postgres(self):
        """Test loading common PostgreSQL environment variables."""
        os.environ["ACME_PGHOST"] = "localhost"
        os.environ["ACME_PGPORT"] = "5432"
        os.environ["ACME_PGDATABASE"] = "mydb"
        os.environ["ACME_PGUSER"] = "postgres"
        os.environ["ACME_PGPASSWORD"] = "secret"
        
        manager = EnvSecretManager()
        secrets = manager.load_secrets("acme")
        
        assert "postgres" in secrets
        assert secrets["postgres"]["PGHOST"] == "localhost"
        assert secrets["postgres"]["PGPASSWORD"] == "secret"

    def test_get_secret(self):
        """Test retrieving a specific secret."""
        os.environ["ACME_API_KEY"] = "test_key"
        
        manager = EnvSecretManager()
        secret = manager.get_secret("acme", "api_key")
        
        assert secret == "test_key"

    def test_has_secret(self):
        """Test checking if a secret exists."""
        os.environ["ACME_API_KEY"] = "test_key"
        
        manager = EnvSecretManager()
        
        assert manager.has_secret("acme", "api_key") is True
        assert manager.has_secret("acme", "nonexistent") is False


class TestFilesystemSecretManager:
    """Tests for the FilesystemSecretManager."""

    def test_load_secrets_json_file(self):
        """Test loading secrets from JSON files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_dir = Path(tmpdir)
            tenant_dir = secrets_dir / "acme"
            tenant_dir.mkdir()
            
            # Create JSON secret file
            secret_file = tenant_dir / "gsheets.json"
            secret_data = {"type": "service_account", "project_id": "my-project"}
            with open(secret_file, "w") as f:
                json.dump(secret_data, f)
            
            manager = FilesystemSecretManager(config={"secrets_dir": str(secrets_dir)})
            secrets = manager.load_secrets("acme")
            
            assert "gsheets" in secrets
            assert secrets["gsheets"]["project_id"] == "my-project"

    def test_load_secrets_env_file(self):
        """Test loading secrets from .env files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_dir = Path(tmpdir)
            tenant_dir = secrets_dir / "acme"
            tenant_dir.mkdir()
            
            # Create .env secret file
            env_file = tenant_dir / "postgres.env"
            with open(env_file, "w") as f:
                f.write("PGHOST=localhost\n")
                f.write("PGPORT=5432\n")
                f.write('PGPASSWORD="secret"\n')
            
            manager = FilesystemSecretManager(config={"secrets_dir": str(secrets_dir)})
            secrets = manager.load_secrets("acme")
            
            assert "postgres" in secrets
            assert secrets["postgres"]["PGHOST"] == "localhost"
            assert secrets["postgres"]["PGPASSWORD"] == "secret"

    def test_load_secrets_text_file(self):
        """Test loading secrets from plain text files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_dir = Path(tmpdir)
            tenant_dir = secrets_dir / "acme"
            tenant_dir.mkdir()
            
            # Create text secret file
            text_file = tenant_dir / "api_key.txt"
            with open(text_file, "w") as f:
                f.write("sk_test_12345")
            
            manager = FilesystemSecretManager(config={"secrets_dir": str(secrets_dir)})
            secrets = manager.load_secrets("acme")
            
            assert "api_key" in secrets
            assert secrets["api_key"] == "sk_test_12345"

    def test_load_secrets_missing_directory(self):
        """Test error handling when secrets directory doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_dir = Path(tmpdir)
            
            manager = FilesystemSecretManager(config={"secrets_dir": str(secrets_dir)})
            
            with pytest.raises(ValueError, match="Secrets directory not found"):
                manager.load_secrets("nonexistent")

    def test_resolve_secret_path(self):
        """Test resolving secret path from template."""
        manager = FilesystemSecretManager(config={"secrets_dir": "/secrets"})
        
        path = manager.resolve_secret_path("/secrets/{tenant}/gsheets.json", "acme")
        assert path == Path("/secrets/acme/gsheets.json")


class TestSecretManagerFactory:
    """Tests for the secret manager factory."""

    def test_create_env_manager(self):
        """Test creating an environment variable manager."""
        manager = create_secret_manager(manager_type="env")
        assert isinstance(manager, EnvSecretManager)

    def test_create_filesystem_manager(self):
        """Test creating a filesystem manager."""
        manager = create_secret_manager(manager_type="filesystem")
        assert isinstance(manager, FilesystemSecretManager)

    def test_create_with_config(self):
        """Test creating a manager with configuration."""
        config = {"secrets_dir": "/custom/path"}
        manager = create_secret_manager(manager_type="filesystem", config=config)
        assert isinstance(manager, FilesystemSecretManager)
        assert manager.secrets_dir == Path("/custom/path")

    def test_create_invalid_type(self):
        """Test error handling for invalid manager type."""
        with pytest.raises(ValueError, match="Unknown secret manager type"):
            create_secret_manager(manager_type="invalid")

    def test_auto_detect_env_default(self):
        """Test auto-detection defaults to env manager."""
        # Clear environment variables that might trigger other detections
        env_backup = {}
        for key in ["VAULT_ADDR", "AWS_SECRETS_MANAGER", "GOOGLE_CLOUD_PROJECT"]:
            if key in os.environ:
                env_backup[key] = os.environ[key]
                del os.environ[key]
        
        try:
            manager = create_secret_manager()
            assert isinstance(manager, EnvSecretManager)
        finally:
            # Restore environment
            os.environ.update(env_backup)

    def test_auto_detect_filesystem(self):
        """Test auto-detection of filesystem manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {"secrets_dir": tmpdir}
            manager = create_secret_manager(config=config)
            assert isinstance(manager, FilesystemSecretManager)

    @patch.dict(os.environ, {"VAULT_ADDR": "https://vault.example.com"})
    def test_auto_detect_vault(self):
        """Test auto-detection of Vault manager."""
        # This will fail because hvac is not installed, but we can test the detection
        with pytest.raises(ImportError, match="hvac"):
            create_secret_manager()

    def test_create_from_env_variable(self):
        """Test creating manager from SECRET_MANAGER_TYPE env variable."""
        with patch.dict(os.environ, {"SECRET_MANAGER_TYPE": "env"}):
            manager = create_secret_manager()
            assert isinstance(manager, EnvSecretManager)


class TestSecretManagerValidation:
    """Tests for secret validation across managers."""

    def test_validate_secrets_stripe(self):
        """Test validation for Stripe connector."""
        os.environ["ACME_STRIPE_API_KEY"] = "sk_test_123"
        
        manager = EnvSecretManager()
        
        # Should pass validation
        result = manager.validate_secrets_for_connector(
            tenant_id="acme",
            connector_type="stripe",
            credentials_config={"type": "api_key"},
        )
        assert result is True

    def test_validate_secrets_missing(self):
        """Test validation failure for missing secrets."""
        # Clear all environment variables that might contain secrets
        for key in list(os.environ.keys()):
            if any(pattern in key.upper() for pattern in ["STRIPE", "API_KEY", "ACME"]):
                del os.environ[key]
        
        manager = EnvSecretManager(config={"allow_generic": False})
        
        # Should fail validation
        with pytest.raises(ValueError, match="Missing required secrets"):
            manager.validate_secrets_for_connector(
                tenant_id="testmissingtenant",
                connector_type="stripe",
                credentials_config={"type": "api_key"},
            )

    def test_validate_secrets_no_credentials(self):
        """Test validation when no credentials are required."""
        manager = EnvSecretManager()
        
        # Should pass validation (no credentials needed)
        result = manager.validate_secrets_for_connector(
            tenant_id="acme",
            connector_type="csv",
            credentials_config={"type": "none"},
        )
        assert result is True


# Cleanup environment after tests
@pytest.fixture(autouse=True)
def cleanup_env():
    """Clean up environment variables after each test."""
    yield
    # Remove test environment variables
    keys_to_remove = [k for k in os.environ.keys() if k.startswith(("ACME_", "TEST_"))]
    for key in keys_to_remove:
        del os.environ[key]
