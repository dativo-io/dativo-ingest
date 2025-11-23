"""Tests for secret validation utilities."""

import os

import pytest

from dativo_ingest.secrets.validation import validate_secrets_for_connector


class TestValidateSecretsForConnector:
    """Test connector secret validation logic."""

    def test_passes_when_no_credentials_needed(self):
        secrets = {}
        credentials_config = {"type": "none"}
        # Should not raise
        assert (
            validate_secrets_for_connector(secrets, "any", credentials_config) is True
        )

    def test_validates_file_template_secret(self):
        secrets = {"gsheets": {"key": "value"}}
        credentials_config = {
            "type": "file",
            "file_template": "/secrets/{tenant}/gsheets.json",
        }
        # Should not raise
        assert (
            validate_secrets_for_connector(secrets, "gsheets", credentials_config)
            is True
        )

    def test_raises_when_file_template_secret_missing(self):
        secrets = {}
        credentials_config = {
            "type": "file",
            "file_template": "/secrets/{tenant}/gsheets.json",
        }
        with pytest.raises(ValueError, match="Missing required secrets"):
            validate_secrets_for_connector(secrets, "gsheets", credentials_config)

    def test_validates_stripe_api_key(self):
        secrets = {"stripe_api_key": "sk_test_123"}
        credentials_config = {"type": "api_key"}
        # Should not raise
        assert (
            validate_secrets_for_connector(secrets, "stripe", credentials_config)
            is True
        )

    def test_validates_stripe_with_generic_api_key(self):
        secrets = {"api_key": "sk_test_123"}
        credentials_config = {"type": "api_key"}
        # Should not raise
        assert (
            validate_secrets_for_connector(secrets, "stripe", credentials_config)
            is True
        )

    def test_raises_when_stripe_api_key_missing(self):
        secrets = {}
        credentials_config = {"type": "api_key"}
        with pytest.raises(ValueError, match="stripe_api_key"):
            validate_secrets_for_connector(secrets, "stripe", credentials_config)

    def test_validates_hubspot_api_key(self):
        secrets = {"hubspot_api_key": "key123"}
        credentials_config = {"type": "api_key"}
        # Should not raise
        assert (
            validate_secrets_for_connector(secrets, "hubspot", credentials_config)
            is True
        )

    def test_raises_when_hubspot_api_key_missing(self):
        secrets = {}
        credentials_config = {"type": "api_key"}
        with pytest.raises(ValueError, match="hubspot_api_key"):
            validate_secrets_for_connector(secrets, "hubspot", credentials_config)

    def test_validates_postgres_secret(self):
        secrets = {"postgres": {"PGHOST": "localhost"}}
        credentials_config = {"type": "connection_string"}
        # Should not raise
        assert (
            validate_secrets_for_connector(secrets, "postgres", credentials_config)
            is True
        )

    def test_raises_when_postgres_secret_missing(self):
        secrets = {}
        credentials_config = {"type": "connection_string"}
        with pytest.raises(ValueError, match="postgres"):
            validate_secrets_for_connector(secrets, "postgres", credentials_config)

    def test_validates_mysql_secret(self):
        secrets = {"mysql": {"host": "localhost"}}
        credentials_config = {"type": "connection_string"}
        # Should not raise
        assert (
            validate_secrets_for_connector(secrets, "mysql", credentials_config) is True
        )

    def test_raises_when_mysql_secret_missing(self):
        secrets = {}
        credentials_config = {"type": "connection_string"}
        with pytest.raises(ValueError, match="mysql"):
            validate_secrets_for_connector(secrets, "mysql", credentials_config)

    def test_validates_iceberg_with_secret(self):
        secrets = {"iceberg": {"uri": "s3://bucket"}}
        credentials_config = {"type": "connection_string"}
        # Should not raise
        assert (
            validate_secrets_for_connector(secrets, "iceberg", credentials_config)
            is True
        )

    def test_validates_iceberg_with_nessie_secret(self):
        secrets = {"nessie": {"uri": "s3://bucket"}}
        credentials_config = {"type": "connection_string"}
        # Should not raise
        assert (
            validate_secrets_for_connector(secrets, "iceberg", credentials_config)
            is True
        )

    def test_validates_iceberg_with_env_var(self, monkeypatch):
        monkeypatch.setenv("NESSIE_URI", "s3://bucket")
        secrets = {}
        credentials_config = {"type": "connection_string"}
        # Should not raise
        assert (
            validate_secrets_for_connector(secrets, "iceberg", credentials_config)
            is True
        )

    def test_raises_when_iceberg_secret_and_env_missing(self):
        secrets = {}
        credentials_config = {"type": "connection_string"}
        with pytest.raises(ValueError, match="iceberg"):
            validate_secrets_for_connector(secrets, "iceberg", credentials_config)

    def test_matches_partial_secret_names(self):
        secrets = {"postgres.env": {"PGHOST": "localhost"}}
        credentials_config = {"type": "connection_string"}
        # Should not raise - matches "postgres" prefix
        assert (
            validate_secrets_for_connector(secrets, "postgres", credentials_config)
            is True
        )
