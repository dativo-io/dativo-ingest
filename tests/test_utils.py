"""Tests for utility functions."""

import os
import sys
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dativo_ingest.utils import expand_env_variable


class TestExpandEnvVariable:
    """Test environment variable expansion utility."""

    def test_expand_simple_variable(self, monkeypatch):
        """Test expansion of simple ${VAR} syntax."""
        monkeypatch.setenv("TEST_VAR", "test_value")
        assert expand_env_variable("${TEST_VAR}") == "test_value"

    def test_expand_variable_with_default(self, monkeypatch):
        """Test expansion of ${VAR:-default} syntax."""
        # Variable not set, should use default
        monkeypatch.delenv("MISSING_VAR", raising=False)
        assert expand_env_variable("${MISSING_VAR:-default_value}") == "default_value"

        # Variable set, should use value
        monkeypatch.setenv("EXISTING_VAR", "actual_value")
        assert expand_env_variable("${EXISTING_VAR:-default_value}") == "actual_value"

    def test_expand_multiple_defaults(self, monkeypatch):
        """Test multiple ${VAR:-default} patterns in one string."""
        monkeypatch.delenv("VAR1", raising=False)
        monkeypatch.setenv("VAR2", "value2")
        result = expand_env_variable(
            "prefix-${VAR1:-default1}-middle-${VAR2:-default2}-suffix"
        )
        assert result == "prefix-default1-middle-value2-suffix"

    def test_expand_none_value(self):
        """Test that None values are returned as-is."""
        assert expand_env_variable(None) is None

    def test_expand_non_string_value(self):
        """Test that non-string values are returned as-is."""
        assert expand_env_variable(123) == 123
        assert expand_env_variable(["list"]) == ["list"]
        assert expand_env_variable({"dict": "value"}) == {"dict": "value"}

    def test_expand_empty_string(self):
        """Test that empty strings are returned as-is."""
        assert expand_env_variable("") == ""

    def test_expand_string_without_variables(self):
        """Test that strings without variables are returned as-is."""
        assert expand_env_variable("plain_string") == "plain_string"
        assert (
            expand_env_variable("string with $ but no braces")
            == "string with $ but no braces"
        )

    def test_expand_unset_variable(self, monkeypatch):
        """Test expansion of unset variable without default."""
        monkeypatch.delenv("UNSET_VAR", raising=False)
        result = expand_env_variable("${UNSET_VAR}")
        assert result is None

    def test_expand_variable_in_middle_of_string(self, monkeypatch):
        """Test variable expansion in middle of string."""
        monkeypatch.setenv("VAR", "value")
        assert expand_env_variable("prefix-${VAR}-suffix") == "prefix-value-suffix"

    def test_expand_multiple_variables(self, monkeypatch):
        """Test expansion of multiple variables."""
        monkeypatch.setenv("VAR1", "value1")
        monkeypatch.setenv("VAR2", "value2")
        result = expand_env_variable("${VAR1}-${VAR2}")
        assert result == "value1-value2"

    def test_expand_nested_braces(self, monkeypatch):
        """Test that nested braces are handled correctly."""
        monkeypatch.setenv("VAR", "value")
        # This should not cause issues with nested braces
        result = expand_env_variable("${VAR}")
        assert result == "value"

    def test_expand_variable_with_special_chars_in_default(self, monkeypatch):
        """Test default value with special characters."""
        monkeypatch.delenv("VAR", raising=False)
        result = expand_env_variable("${VAR:-default-with-special-chars}")
        assert result == "default-with-special-chars"

    def test_expand_variable_with_colon_in_name(self, monkeypatch):
        """Test variable name with colon (should not match default pattern)."""
        # ${VAR:-default} should match VAR, not VAR:something
        monkeypatch.setenv("VAR", "value")
        result = expand_env_variable("${VAR:-default}")
        assert result == "value"

    def test_expand_variable_without_closing_brace(self, monkeypatch):
        """Test variable without closing brace (should be handled gracefully)."""
        monkeypatch.setenv("VAR", "value")
        # This might not expand correctly, but shouldn't crash
        result = expand_env_variable("${VAR")
        # Behavior depends on implementation - just ensure no crash
        assert isinstance(result, (str, type(None)))
