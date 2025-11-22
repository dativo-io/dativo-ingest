"""Integration tests for secret manager system with CLI."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from dativo_ingest.secret_managers import (
    EnvSecretManager,
    FilesystemSecretManager,
    create_secret_manager,
)


class TestSecretManagerCLIIntegration:
    """Tests for secret manager integration with CLI."""

    def test_auto_detect_with_filesystem(self):
        """Test auto-detection of filesystem manager when directory exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_dir = Path(tmpdir)
            tenant_dir = secrets_dir / "test_tenant"
            tenant_dir.mkdir()
            
            # Create a test secret file
            (tenant_dir / "api_key.txt").write_text("test_key_123")
            
            # Auto-detect should choose filesystem
            manager = create_secret_manager(config={"secrets_dir": str(secrets_dir)})
            assert isinstance(manager, FilesystemSecretManager)
            
            # Load secrets
            secrets = manager.load_secrets("test_tenant")
            assert secrets["api_key"] == "test_key_123"

    def test_explicit_env_manager(self):
        """Test explicit configuration of environment manager."""
        # Clear test environment
        for key in list(os.environ.keys()):
            if key.startswith("TESTtenant_"):
                del os.environ[key]
        
        os.environ["TESTENANT_API_KEY"] = "env_key_456"
        
        # Explicitly request env manager
        manager = create_secret_manager(manager_type="env")
        assert isinstance(manager, EnvSecretManager)
        
        # Load secrets
        secrets = manager.load_secrets("testenant")
        assert "api_key" in secrets
        assert secrets["api_key"] == "env_key_456"

    def test_manager_type_from_env_variable(self):
        """Test selecting manager type via environment variable."""
        with patch.dict(os.environ, {"SECRET_MANAGER_TYPE": "env"}):
            manager = create_secret_manager()
            assert isinstance(manager, EnvSecretManager)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"SECRET_MANAGER_TYPE": "filesystem"}):
                manager = create_secret_manager(config={"secrets_dir": tmpdir})
                assert isinstance(manager, FilesystemSecretManager)

    def test_backward_compatibility_with_existing_code(self):
        """Test that existing filesystem-based code continues to work."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_dir = Path(tmpdir)
            tenant_dir = secrets_dir / "legacy_tenant"
            tenant_dir.mkdir()
            
            # Create legacy-style secrets
            (tenant_dir / "stripe_api_key.txt").write_text("sk_test_legacy")
            (tenant_dir / "postgres.env").write_text("PGHOST=localhost\nPGPORT=5432")
            
            # Should still work with filesystem manager
            manager = FilesystemSecretManager(config={"secrets_dir": str(secrets_dir)})
            secrets = manager.load_secrets("legacy_tenant")
            
            assert secrets["stripe_api_key"] == "sk_test_legacy"
            assert secrets["postgres"]["PGHOST"] == "localhost"

    def test_environment_variable_precedence(self):
        """Test that tenant-specific variables take precedence over generic."""
        os.environ["MYTENANT_API_KEY"] = "tenant_specific"
        os.environ["API_KEY"] = "generic"
        
        manager = EnvSecretManager(config={"allow_generic": True})
        secrets = manager.load_secrets("mytenant")
        
        # Tenant-specific should win
        assert secrets["api_key"] == "tenant_specific"
        
        # Clean up
        del os.environ["MYTENANT_API_KEY"]
        del os.environ["API_KEY"]

    def test_multiple_tenants_isolation(self):
        """Test that different tenants have isolated secrets."""
        os.environ["TENANT_A_SECRET"] = "secret_a"
        os.environ["TENANT_B_SECRET"] = "secret_b"
        
        manager = EnvSecretManager(config={"allow_generic": False})
        
        secrets_a = manager.load_secrets("tenant_a")
        secrets_b = manager.load_secrets("tenant_b")
        
        # Each tenant should only see their own secrets
        assert "secret" in secrets_a
        assert secrets_a["secret"] == "secret_a"
        assert "secret" in secrets_b
        assert secrets_b["secret"] == "secret_b"
        
        # Clean up
        del os.environ["TENANT_A_SECRET"]
        del os.environ["TENANT_B_SECRET"]

    def test_json_credentials_integration(self):
        """Test loading JSON credentials like service account keys."""
        import json
        
        service_account = {
            "type": "service_account",
            "project_id": "my-project",
            "private_key": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
            "client_email": "test@my-project.iam.gserviceaccount.com"
        }
        
        os.environ["MYAPP_GSHEETS"] = json.dumps(service_account)
        
        manager = EnvSecretManager(config={"allow_generic": False})
        secrets = manager.load_secrets("myapp")
        
        assert "gsheets" in secrets
        assert isinstance(secrets["gsheets"], dict)
        assert secrets["gsheets"]["project_id"] == "my-project"
        assert secrets["gsheets"]["type"] == "service_account"
        
        # Clean up
        del os.environ["MYAPP_GSHEETS"]


# Cleanup environment after all tests
@pytest.fixture(autouse=True)
def cleanup_env():
    """Clean up environment variables after each test."""
    yield
    # Remove test environment variables (excluding pytest's own variables)
    keys_to_remove = [
        k for k in list(os.environ.keys())
        if any(prefix in k.upper() for prefix in ["TEST", "MYAPP", "MYTENANT", "TENANT_A", "TENANT_B", "LEGACY"])
        and not k.startswith("PYTEST_")
    ]
    for key in keys_to_remove:
        try:
            del os.environ[key]
        except KeyError:
            pass  # Already deleted
