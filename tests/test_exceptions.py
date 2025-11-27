"""Tests for standardized error hierarchy.

Tests cover:
1. Error class hierarchy and inheritance
2. Error codes and retryable flags
3. Error serialization (to_dict)
4. Helper functions (is_retryable_error, get_error_code, wrap_exception)
"""

import pytest

from dativo_ingest.exceptions import (
    AuthenticationError,
    ConfigurationError,
    ConnectionError,
    DativoError,
    PluginError,
    PluginVersionError,
    RateLimitError,
    SandboxError,
    TransientError,
    ValidationError,
    get_error_code,
    is_retryable_error,
    wrap_exception,
)


class TestErrorHierarchy:
    """Tests for error class hierarchy."""

    def test_dativo_error_base(self):
        """Test base DativoError class."""
        error = DativoError("Test error")

        assert str(error) == "DativoError(DATIVOERROR): Test error"
        assert error.message == "Test error"
        assert error.error_code == "DATIVOERROR"  # Defaults to class name in uppercase
        assert error.retryable is False
        assert isinstance(error.details, dict)

    def test_connection_error(self):
        """Test ConnectionError class."""
        error = ConnectionError("Connection failed")

        assert isinstance(error, DativoError)
        assert error.message == "Connection failed"
        assert error.error_code == "CONNECTION_FAILED"
        assert error.retryable is True  # Connection errors are retryable by default

    def test_authentication_error(self):
        """Test AuthenticationError class."""
        error = AuthenticationError("Invalid credentials")

        assert isinstance(error, ConnectionError)  # Inherits from ConnectionError
        assert isinstance(error, DativoError)
        assert error.message == "Invalid credentials"
        assert error.error_code == "AUTHENTICATION_FAILED"
        assert error.retryable is False  # Auth errors are not retryable

    def test_validation_error(self):
        """Test ValidationError class."""
        error = ValidationError("Invalid data format", details={"field": "email"})

        assert isinstance(error, DativoError)
        assert error.message == "Invalid data format"
        assert error.error_code == "VALIDATION_FAILED"
        assert error.retryable is False
        assert error.details["field"] == "email"

    def test_configuration_error(self):
        """Test ConfigurationError class."""
        error = ConfigurationError(
            "Missing required field", details={"field": "connection"}
        )

        assert isinstance(error, DativoError)
        assert error.message == "Missing required field"
        assert error.error_code == "CONFIGURATION_ERROR"
        assert error.retryable is False
        assert error.details["field"] == "connection"

    def test_transient_error(self):
        """Test TransientError class."""
        error = TransientError("Temporary failure", retry_after=60)

        assert isinstance(error, DativoError)
        assert error.message == "Temporary failure"
        assert error.error_code == "TRANSIENT_ERROR"
        assert error.retryable is True
        assert error.retry_after == 60
        assert error.details["retry_after"] == 60

    def test_rate_limit_error(self):
        """Test RateLimitError class."""
        error = RateLimitError("Rate limit exceeded", retry_after=120)

        assert isinstance(error, TransientError)  # Inherits from TransientError
        assert isinstance(error, DativoError)
        assert error.message == "Rate limit exceeded"
        assert error.error_code == "RATE_LIMIT_EXCEEDED"
        assert error.retryable is True
        assert error.retry_after == 120

    def test_plugin_error(self):
        """Test PluginError class."""
        error = PluginError(
            "Plugin failed to load", details={"plugin_path": "/path/to/plugin.py"}
        )

        assert isinstance(error, DativoError)
        assert error.message == "Plugin failed to load"
        assert error.error_code == "PLUGIN_ERROR"
        assert error.retryable is False
        assert error.details["plugin_path"] == "/path/to/plugin.py"

    def test_plugin_version_error(self):
        """Test PluginVersionError class."""
        error = PluginVersionError(
            "Version incompatible", plugin_version="1.0.0", required_version="2.0.0"
        )

        assert isinstance(error, PluginError)  # Inherits from PluginError
        assert isinstance(error, DativoError)
        assert error.message == "Version incompatible"
        assert error.error_code == "PLUGIN_VERSION_INCOMPATIBLE"
        assert error.retryable is False
        assert error.details["plugin_version"] == "1.0.0"
        assert error.details["required_version"] == "2.0.0"

    def test_sandbox_error(self):
        """Test SandboxError class."""
        error = SandboxError(
            "Sandbox execution failed", details={"container_id": "abc123"}
        )

        assert isinstance(error, PluginError)  # Inherits from PluginError
        assert isinstance(error, DativoError)
        assert error.message == "Sandbox execution failed"
        assert error.error_code == "SANDBOX_ERROR"
        assert error.retryable is True  # Sandbox errors are retryable by default
        assert error.details["container_id"] == "abc123"


class TestErrorSerialization:
    """Tests for error serialization."""

    def test_error_to_dict(self):
        """Test error to_dict method."""
        error = ConnectionError(
            "Connection failed", details={"host": "localhost", "port": 5432}
        )

        error_dict = error.to_dict()

        assert error_dict["error_type"] == "ConnectionError"
        assert error_dict["error_code"] == "CONNECTION_FAILED"
        assert error_dict["message"] == "Connection failed"
        assert error_dict["retryable"] is True
        assert error_dict["details"]["host"] == "localhost"
        assert error_dict["details"]["port"] == 5432

    def test_transient_error_to_dict_with_retry_after(self):
        """Test TransientError to_dict includes retry_after."""
        error = TransientError("Temporary failure", retry_after=60)

        error_dict = error.to_dict()

        assert error_dict["error_type"] == "TransientError"
        assert error_dict["retryable"] is True
        assert error_dict["retry_after"] == 60
        assert error_dict["details"]["retry_after"] == 60


class TestErrorHelperFunctions:
    """Tests for error helper functions."""

    def test_is_retryable_error_connection(self):
        """Test is_retryable_error with ConnectionError."""
        error = ConnectionError("Connection failed")
        assert is_retryable_error(error) is True

    def test_is_retryable_error_authentication(self):
        """Test is_retryable_error with AuthenticationError."""
        error = AuthenticationError("Invalid credentials")
        assert is_retryable_error(error) is False

    def test_is_retryable_error_transient(self):
        """Test is_retryable_error with TransientError."""
        error = TransientError("Temporary failure")
        assert is_retryable_error(error) is True

    def test_is_retryable_error_rate_limit(self):
        """Test is_retryable_error with RateLimitError."""
        error = RateLimitError("Rate limit exceeded", retry_after=60)
        assert is_retryable_error(error) is True

    def test_is_retryable_error_validation(self):
        """Test is_retryable_error with ValidationError."""
        error = ValidationError("Invalid data")
        assert is_retryable_error(error) is False

    def test_is_retryable_error_unknown(self):
        """Test is_retryable_error with unknown exception."""
        error = ValueError("Unknown error")
        assert is_retryable_error(error) is False  # Unknown errors are not retryable

    def test_get_error_code_connection(self):
        """Test get_error_code with ConnectionError."""
        error = ConnectionError("Connection failed")
        assert get_error_code(error) == "CONNECTION_FAILED"

    def test_get_error_code_authentication(self):
        """Test get_error_code with AuthenticationError."""
        error = AuthenticationError("Invalid credentials")
        assert get_error_code(error) == "AUTHENTICATION_FAILED"

    def test_get_error_code_transient(self):
        """Test get_error_code with TransientError."""
        error = TransientError("Temporary failure")
        assert get_error_code(error) == "TRANSIENT_ERROR"

    def test_get_error_code_unknown(self):
        """Test get_error_code with unknown exception."""
        error = ValueError("Unknown error")
        assert get_error_code(error) == "UNKNOWN_ERROR"

    def test_wrap_exception_dativo_error(self):
        """Test wrap_exception with existing DativoError."""
        original_error = ConnectionError("Connection failed")
        wrapped = wrap_exception(original_error)

        assert wrapped is original_error  # Should return same object

    def test_wrap_exception_standard_error(self):
        """Test wrap_exception with standard exception."""
        original_error = ValueError("Some error")
        wrapped = wrap_exception(original_error, ConnectionError)

        assert isinstance(wrapped, ConnectionError)
        assert isinstance(wrapped, DativoError)
        assert "Some error" in wrapped.message
        assert wrapped.details["original_error"] == "ValueError"
        assert wrapped.details["original_message"] == "Some error"

    def test_wrap_exception_with_custom_message(self):
        """Test wrap_exception with custom message."""
        original_error = IOError("File not found")
        wrapped = wrap_exception(
            original_error, ConnectionError, message="Failed to connect to file system"
        )

        assert isinstance(wrapped, ConnectionError)
        assert wrapped.message == "Failed to connect to file system"
        # IOError is an alias for OSError in Python 3.9+
        assert wrapped.details["original_error"] in ("IOError", "OSError")
        assert wrapped.details["original_message"] == "File not found"

    def test_wrap_exception_default_class(self):
        """Test wrap_exception with default error class."""
        original_error = KeyError("Missing key")
        wrapped = wrap_exception(original_error)

        assert isinstance(wrapped, DativoError)
        assert str(original_error) in wrapped.message
        assert wrapped.details["original_error"] == "KeyError"
