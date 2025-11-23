"""Tests for AWSSecretsManager - focus on our logic, not boto3."""

from unittest.mock import MagicMock

import pytest

from dativo_ingest.secrets.managers.aws import AWSSecretsManager


class TestAWSSecretsManager:
    """Test AWS Secrets Manager logic."""

    def test_loads_discrete_secrets(self):
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {"SecretString": '{"url":"db"}'}

        manager = AWSSecretsManager(
            region_name="us-east-1",
            secrets=[{"name": "postgres", "format": "json"}],
            client=mock_client,
        )

        secrets = manager.load_secrets("tenant1")

        assert secrets["postgres"]["url"] == "db"
        mock_client.get_secret_value.assert_called_once()

    def test_resolves_secret_id_with_template(self):
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {"SecretString": "value"}

        manager = AWSSecretsManager(
            region_name="us-east-1",
            secret_id_template="prod/{tenant}/{name}",
            secrets=[{"name": "api_key"}],
            client=mock_client,
        )

        manager.load_secrets("tenant1")

        # Verify template was used
        call_args = mock_client.get_secret_value.call_args[1]
        assert call_args["SecretId"] == "prod/tenant1/api_key"

    def test_uses_custom_secret_id_when_provided(self):
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {"SecretString": "value"}

        manager = AWSSecretsManager(
            region_name="us-east-1",
            secret_id_template="default/{tenant}/{name}",
            secrets=[{"name": "api_key", "id": "custom/path"}],
            client=mock_client,
        )

        manager.load_secrets("tenant1")

        call_args = mock_client.get_secret_value.call_args[1]
        assert call_args["SecretId"] == "custom/path"

    def test_loads_bundle_secret(self):
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": '{"postgres": {"url": "db"}, "api_key": "sk_123"}'
        }

        manager = AWSSecretsManager(
            region_name="us-east-1",
            bundle_secret_id_template="bundle/{tenant}",
            client=mock_client,
        )

        secrets = manager.load_secrets("tenant1")

        assert secrets["postgres"]["url"] == "db"
        assert secrets["api_key"] == "sk_123"

    def test_bundle_secret_id_uses_template(self):
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {"SecretString": "{}"}

        manager = AWSSecretsManager(
            region_name="us-east-1",
            bundle_secret_id_template="prod/{tenant}/secrets",
            client=mock_client,
        )

        manager.load_secrets("tenant1")

        call_args = mock_client.get_secret_value.call_args[1]
        assert call_args["SecretId"] == "prod/tenant1/secrets"

    def test_handles_secret_binary_correctly(self):
        """Test that SecretBinary is decoded without double base64 decoding."""
        mock_client = MagicMock()
        # boto3 returns SecretBinary as raw bytes (already base64-decoded)
        mock_client.get_secret_value.return_value = {
            "SecretBinary": b'{"api_key": "sk_test_123"}'
        }

        manager = AWSSecretsManager(
            region_name="us-east-1",
            secrets=[{"name": "api_key", "format": "json"}],
            client=mock_client,
        )

        secrets = manager.load_secrets("tenant1")

        assert secrets["api_key"]["api_key"] == "sk_test_123"

    def test_handles_secret_string(self):
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {"SecretString": '{"key": "value"}'}

        manager = AWSSecretsManager(
            region_name="us-east-1",
            secrets=[{"name": "config", "format": "json"}],
            client=mock_client,
        )

        secrets = manager.load_secrets("tenant1")

        assert secrets["config"] == {"key": "value"}

    def test_uses_version_id_when_provided(self):
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {"SecretString": "value"}

        manager = AWSSecretsManager(
            region_name="us-east-1",
            secrets=[{"name": "key", "version_id": "v123"}],
            client=mock_client,
        )

        manager.load_secrets("tenant1")

        call_args = mock_client.get_secret_value.call_args[1]
        assert call_args["VersionId"] == "v123"

    def test_uses_version_stage_when_provided(self):
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {"SecretString": "value"}

        manager = AWSSecretsManager(
            region_name="us-east-1",
            secrets=[{"name": "key", "version_stage": "AWSCURRENT"}],
            client=mock_client,
        )

        manager.load_secrets("tenant1")

        call_args = mock_client.get_secret_value.call_args[1]
        assert call_args["VersionStage"] == "AWSCURRENT"

    def test_raises_when_no_secrets_or_bundle(self):
        manager = AWSSecretsManager(region_name="us-east-1", client=MagicMock())

        with pytest.raises(ValueError, match="requires either"):
            manager.load_secrets("tenant1")

    def test_raises_when_bundle_not_dict(self):
        mock_client = MagicMock()
        # Return valid JSON that's not a dict (e.g., a string or array)
        mock_client.get_secret_value.return_value = {"SecretString": '"just a string"'}

        manager = AWSSecretsManager(
            region_name="us-east-1",
            bundle_secret_id_template="bundle/{tenant}",
            client=mock_client,
        )

        with pytest.raises(ValueError, match="must deserialize into a dictionary"):
            manager.load_secrets("tenant1")

    def test_parses_secret_with_format_hint(self):
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": "KEY1=value1\nKEY2=value2"
        }

        manager = AWSSecretsManager(
            region_name="us-east-1",
            secrets=[{"name": "db", "format": "env"}],
            client=mock_client,
        )

        secrets = manager.load_secrets("tenant1")

        assert secrets["db"]["KEY1"] == "value1"
        assert secrets["db"]["KEY2"] == "value2"

    def test_expands_env_vars_in_bundle(self, monkeypatch):
        monkeypatch.setenv("DB_HOST", "localhost")
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": '{"host": "${DB_HOST}"}'
        }

        manager = AWSSecretsManager(
            region_name="us-east-1",
            bundle_secret_id_template="bundle/{tenant}",
            client=mock_client,
        )

        secrets = manager.load_secrets("tenant1")

        assert secrets["host"] == "localhost"
