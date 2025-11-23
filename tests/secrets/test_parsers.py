"""Tests for secret payload parsing utilities."""

import os
from unittest.mock import patch

import pytest

from dativo_ingest.secrets.parsers import (
    expand_env_vars_in_dict,
    parse_env_blob,
    parse_secret_payload,
)


class TestParseEnvBlob:
    """Test parsing .env-style blob strings."""

    def test_parses_simple_key_value_pairs(self):
        blob = "KEY1=value1\nKEY2=value2"
        result = parse_env_blob(blob)
        assert result == {"KEY1": "value1", "KEY2": "value2"}

    def test_skips_comments(self):
        blob = "KEY1=value1\n# This is a comment\nKEY2=value2"
        result = parse_env_blob(blob)
        assert result == {"KEY1": "value1", "KEY2": "value2"}

    def test_skips_empty_lines(self):
        blob = "KEY1=value1\n\nKEY2=value2"
        result = parse_env_blob(blob)
        assert result == {"KEY1": "value1", "KEY2": "value2"}

    def test_expands_environment_variables(self, monkeypatch):
        monkeypatch.setenv("DB_HOST", "localhost")
        blob = "HOST=${DB_HOST}\nPORT=5432"
        result = parse_env_blob(blob)
        assert result == {"HOST": "localhost", "PORT": "5432"}

    def test_strips_quotes(self):
        blob = "KEY1=\"value1\"\nKEY2='value2'"
        result = parse_env_blob(blob)
        assert result == {"KEY1": "value1", "KEY2": "value2"}

    def test_handles_values_with_equals(self):
        blob = "CONNECTION_STRING=postgresql://user:pass@host/db"
        result = parse_env_blob(blob)
        assert result == {"CONNECTION_STRING": "postgresql://user:pass@host/db"}

    def test_skips_lines_without_equals(self):
        blob = "KEY1=value1\nINVALID_LINE\nKEY2=value2"
        result = parse_env_blob(blob)
        assert result == {"KEY1": "value1", "KEY2": "value2"}


class TestExpandEnvVarsInDict:
    """Test environment variable expansion in data structures."""

    def test_expands_in_dict_values(self, monkeypatch):
        monkeypatch.setenv("DB_HOST", "localhost")
        data = {"host": "${DB_HOST}", "port": 5432}
        result = expand_env_vars_in_dict(data)
        assert result == {"host": "localhost", "port": 5432}

    def test_expands_in_nested_dicts(self, monkeypatch):
        monkeypatch.setenv("DB_NAME", "mydb")
        data = {"database": {"name": "${DB_NAME}", "port": 5432}}
        result = expand_env_vars_in_dict(data)
        assert result == {"database": {"name": "mydb", "port": 5432}}

    def test_expands_in_lists(self, monkeypatch):
        monkeypatch.setenv("HOST1", "host1")
        monkeypatch.setenv("HOST2", "host2")
        data = ["${HOST1}", "${HOST2}", "host3"]
        result = expand_env_vars_in_dict(data)
        assert result == ["host1", "host2", "host3"]

    def test_expands_in_nested_structures(self, monkeypatch):
        monkeypatch.setenv("DB_NAME", "mydb")
        data = {
            "databases": [
                {"name": "${DB_NAME}", "port": 5432},
                {"name": "other", "port": 3306},
            ]
        }
        result = expand_env_vars_in_dict(data)
        assert result == {
            "databases": [
                {"name": "mydb", "port": 5432},
                {"name": "other", "port": 3306},
            ]
        }

    def test_leaves_non_strings_unchanged(self):
        data = {"number": 42, "boolean": True, "null": None}
        result = expand_env_vars_in_dict(data)
        assert result == {"number": 42, "boolean": True, "null": None}


class TestParseSecretPayload:
    """Test secret payload parsing with format hints."""

    def test_parses_json_with_hint(self):
        payload = '{"key": "value"}'
        result = parse_secret_payload(payload, format_hint="json")
        assert result == {"key": "value"}

    def test_auto_detects_json(self):
        payload = '{"key": "value"}'
        result = parse_secret_payload(payload)
        assert result == {"key": "value"}

    def test_parses_env_with_hint(self):
        payload = "KEY1=value1\nKEY2=value2"
        result = parse_secret_payload(payload, format_hint="env")
        assert result == {"KEY1": "value1", "KEY2": "value2"}

    def test_auto_detects_env_format(self):
        payload = "KEY1=value1\nKEY2=value2"
        result = parse_secret_payload(payload)
        assert result == {"KEY1": "value1", "KEY2": "value2"}

    def test_parses_text_with_hint(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "secret123")
        payload = "api_key=${API_KEY}"
        result = parse_secret_payload(payload, format_hint="text")
        assert result == "api_key=secret123"

    def test_parses_raw_text(self):
        payload = "simple text value"
        result = parse_secret_payload(payload, format_hint="raw")
        assert result == "simple text value"

    def test_returns_dict_unchanged(self):
        payload = {"key": "value"}
        result = parse_secret_payload(payload)
        assert result == {"key": "value"}

    def test_returns_list_unchanged(self):
        payload = [1, 2, 3]
        result = parse_secret_payload(payload)
        assert result == [1, 2, 3]

    def test_returns_none_unchanged(self):
        result = parse_secret_payload(None)
        assert result is None

    def test_expands_env_vars_in_parsed_json(self, monkeypatch):
        monkeypatch.setenv("DB_HOST", "localhost")
        payload = '{"host": "${DB_HOST}"}'
        result = parse_secret_payload(payload, format_hint="json")
        assert result == {"host": "localhost"}

    def test_raises_on_invalid_json_with_json_hint(self):
        payload = "not json"
        with pytest.raises(Exception):  # JSONDecodeError
            parse_secret_payload(payload, format_hint="json")

    def test_falls_back_on_invalid_json_with_auto_hint(self):
        payload = "not json"
        result = parse_secret_payload(payload)  # auto mode
        # Should fall back to text parsing
        assert isinstance(result, str)
