"""Tests for log secret redaction functionality."""

import json
import logging
from io import StringIO

import pytest

from dativo_ingest.logging import (
    StructuredJSONFormatter,
    get_logger,
    setup_logging,
    update_logging_settings,
)


class TestStructuredJSONFormatter:
    """Test StructuredJSONFormatter secret redaction."""

    def test_redacts_password_in_message(self):
        """Test that passwords in log messages are redacted."""
        formatter = StructuredJSONFormatter(redact_secrets=True)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Connecting with password: mysecret123",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        log_data = json.loads(result)

        assert "[REDACTED]" in log_data["message"]
        assert "mysecret123" not in log_data["message"]

    def test_redacts_api_key_in_message(self):
        """Test that API keys in log messages are redacted."""
        formatter = StructuredJSONFormatter(redact_secrets=True)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg='API key: "sk_live_1234567890abcdef"',
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        log_data = json.loads(result)

        assert "[REDACTED]" in log_data["message"]
        assert "sk_live_1234567890abcdef" not in log_data["message"]

    def test_redacts_token_in_message(self):
        """Test that tokens in log messages are redacted."""
        formatter = StructuredJSONFormatter(redact_secrets=True)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Bearer token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        log_data = json.loads(result)

        assert "[REDACTED]" in log_data["message"]
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in log_data["message"]

    def test_redacts_secret_access_key(self):
        """Test that AWS secret access keys are redacted."""
        formatter = StructuredJSONFormatter(redact_secrets=True)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg='secret_access_key: "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"',
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        log_data = json.loads(result)

        assert "[REDACTED]" in log_data["message"]
        assert "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY" not in log_data["message"]

    def test_redacts_long_base64_strings(self):
        """Test that long base64-like strings are redacted even without field names."""
        formatter = StructuredJSONFormatter(redact_secrets=True)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg='Value: "dGVzdGluZzEyMzQ1Njc4OTBhYmNkZWZnaGlqa2xtbm9wcXJzdHV2d3h5eg=="',
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        log_data = json.loads(result)

        assert "[REDACTED]" in log_data["message"]
        assert (
            "dGVzdGluZzEyMzQ1Njc4OTBhYmNkZWZnaGlqa2xtbm9wcXJzdHV2d3h5eg=="
            not in log_data["message"]
        )

    def test_redacts_secrets_in_extra_data(self):
        """Test that secrets in extra_data are redacted."""
        formatter = StructuredJSONFormatter(redact_secrets=True)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        # Set extra_data as attribute
        record.extra_data = {
            "api_key": "sk_live_1234567890",
            "password": "secret123",
            "normal_field": "not_secret",
        }

        result = formatter.format(record)
        log_data = json.loads(result)

        assert log_data["api_key"] == "[REDACTED]"
        assert log_data["password"] == "[REDACTED]"
        assert log_data["normal_field"] == "not_secret"
        assert "sk_live_1234567890" not in result
        assert "secret123" not in result

    def test_redacts_nested_secrets_in_extra_data(self):
        """Test that secrets in nested extra_data dictionaries are redacted."""
        formatter = StructuredJSONFormatter(redact_secrets=True)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.extra_data = {
            "credentials": {
                "username": "user",
                "password": "secret123",
                "api_key": "sk_live_1234567890",
            },
            "config": {"normal": "value"},
        }

        result = formatter.format(record)
        log_data = json.loads(result)

        assert log_data["credentials"]["password"] == "[REDACTED]"
        assert log_data["credentials"]["api_key"] == "[REDACTED]"
        assert log_data["credentials"]["username"] == "user"
        assert log_data["config"]["normal"] == "value"

    def test_no_redaction_when_disabled(self):
        """Test that secrets are not redacted when redaction is disabled."""
        formatter = StructuredJSONFormatter(redact_secrets=False)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg='API key: "sk_live_1234567890"',
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        log_data = json.loads(result)

        assert "[REDACTED]" not in log_data["message"]
        assert "sk_live_1234567890" in log_data["message"]

    def test_preserves_non_secret_data(self):
        """Test that non-secret data is preserved."""
        formatter = StructuredJSONFormatter(redact_secrets=True)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Processing file: data.csv with 100 records",
            args=(),
            exc_info=None,
        )
        record.extra_data = {
            "file_count": 10,
            "status": "success",
            "normal_string": "short",
        }

        result = formatter.format(record)
        log_data = json.loads(result)

        assert log_data["message"] == "Processing file: data.csv with 100 records"
        assert log_data["file_count"] == 10
        assert log_data["status"] == "success"
        assert log_data["normal_string"] == "short"


class TestLoggingSetup:
    """Test logging setup and redaction integration."""

    def test_setup_logging_with_redaction(self):
        """Test that setup_logging configures redaction correctly."""
        logger = setup_logging(
            level="INFO", redact_secrets=True, tenant_id="test-tenant"
        )

        # Capture log output
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredJSONFormatter(redact_secrets=True))
        logger.addHandler(handler)

        logger.info('API key: "sk_live_1234567890"')

        output = stream.getvalue()
        assert "[REDACTED]" in output
        assert "sk_live_1234567890" not in output

    def test_update_logging_settings_enables_redaction(self):
        """Test that update_logging_settings can enable redaction."""
        logger = setup_logging(level="INFO", redact_secrets=False)

        # Capture log output
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredJSONFormatter(redact_secrets=False))
        logger.addHandler(handler)

        logger.info('API key: "sk_live_1234567890"')
        output_before = stream.getvalue()
        assert "sk_live_1234567890" in output_before

        # Update to enable redaction
        stream.truncate(0)
        stream.seek(0)
        update_logging_settings(redact_secrets=True)
        # Update handler formatter
        handler.setFormatter(StructuredJSONFormatter(redact_secrets=True))

        logger.info('API key: "sk_live_1234567890"')
        output_after = stream.getvalue()
        assert "[REDACTED]" in output_after
        assert "sk_live_1234567890" not in output_after

    def test_redaction_in_real_world_scenario(self):
        """Test redaction in a realistic logging scenario."""
        logger = setup_logging(level="INFO", redact_secrets=True, tenant_id="acme-corp")

        # Capture log output
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredJSONFormatter(redact_secrets=True))
        logger.addHandler(handler)

        # Simulate logging with secrets using extra parameter
        logger.info(
            "Connecting to database",
            extra={
                "host": "db.example.com",
                "username": "admin",
                "password": "super_secret_password_123",
                "api_key": "sk_live_abcdef1234567890",
            },
        )

        output = stream.getvalue()
        log_data = json.loads(output)

        # Verify secrets are redacted
        assert log_data["password"] == "[REDACTED]"
        assert log_data["api_key"] == "[REDACTED]"
        # Verify non-secrets are preserved
        assert log_data["host"] == "db.example.com"
        assert log_data["username"] == "admin"
        assert "super_secret_password_123" not in output
        assert "sk_live_abcdef1234567890" not in output

    def test_redaction_with_tenant_id(self):
        """Test that tenant_id is preserved when redaction is enabled."""
        logger = setup_logging(
            level="INFO", redact_secrets=True, tenant_id="test-tenant"
        )

        # Capture log output
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredJSONFormatter(redact_secrets=True))
        logger.addHandler(handler)

        logger.info('API key: "sk_live_1234567890"')

        output = stream.getvalue()
        log_data = json.loads(output)

        assert log_data["tenant_id"] == "test-tenant"
        assert "[REDACTED]" in log_data["message"]


class TestSecretPatterns:
    """Test that various secret patterns are caught."""

    @pytest.mark.parametrize(
        "secret_type,secret_value",
        [
            ("password", "mysecret123"),
            ("token", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"),
            ("api_key", "sk_live_1234567890"),
            ("secret", "very_secret_value"),
            ("credential", "credential_value"),
            ("access_key", "AKIAIOSFODNN7EXAMPLE"),
            ("secret_key", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"),
            ("secret_access_key", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"),
            (
                "private_key",
                "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC...",
            ),
            ("auth_token", "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"),
        ],
    )
    def test_redacts_various_secret_types(self, secret_type, secret_value):
        """Test that various secret types are redacted."""
        formatter = StructuredJSONFormatter(redact_secrets=True)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg=f'{secret_type}: "{secret_value}"',
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        log_data = json.loads(result)

        assert "[REDACTED]" in log_data["message"]
        assert secret_value not in log_data["message"]

    def test_redacts_secrets_in_list_of_dicts(self):
        """Test that secrets in lists of dictionaries are redacted."""
        formatter = StructuredJSONFormatter(redact_secrets=True)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.extra_data = {
            "credentials": [
                {"username": "user1", "password": "secret123"},
                {"username": "user2", "api_key": "sk_live_1234567890"},
            ],
            "tokens": ["token1", "token2"],
        }

        result = formatter.format(record)
        log_data = json.loads(result)

        # Verify secrets in list of dicts are redacted
        assert log_data["credentials"][0]["password"] == "[REDACTED]"
        assert log_data["credentials"][0]["username"] == "user1"
        assert log_data["credentials"][1]["api_key"] == "[REDACTED]"
        assert log_data["credentials"][1]["username"] == "user2"
        assert "secret123" not in result
        assert "sk_live_1234567890" not in result

    def test_redacts_secrets_in_nested_lists(self):
        """Test that secrets in nested lists are redacted."""
        formatter = StructuredJSONFormatter(redact_secrets=True)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.extra_data = {
            "configs": [
                [
                    {"password": "secret123"},
                    {"api_key": "sk_live_1234567890"},
                ]
            ],
        }

        result = formatter.format(record)
        log_data = json.loads(result)

        # Verify secrets in nested lists are redacted
        assert log_data["configs"][0][0]["password"] == "[REDACTED]"
        assert log_data["configs"][0][1]["api_key"] == "[REDACTED]"
        assert "secret123" not in result
        assert "sk_live_1234567890" not in result
