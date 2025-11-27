"""Standardized error handling with error code hierarchy.

This module defines a hierarchy of exceptions for the Dativo platform,
enabling orchestrators to distinguish between retryable and permanent failures.
"""

from typing import Any, Dict, Optional


class DativoError(Exception):
    """Base exception for all Dativo errors.
    
    All errors include:
    - error_code: Machine-readable error code
    - message: Human-readable error message
    - details: Optional additional context
    - retryable: Whether the error is retryable
    """

    error_code: str = "DATIVO_ERROR"
    retryable: bool = False

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        retryable: Optional[bool] = None,
    ):
        """Initialize Dativo error.

        Args:
            message: Human-readable error message
            error_code: Optional error code override
            details: Optional additional context
            retryable: Optional retryable flag override
        """
        super().__init__(message)
        self.message = message
        if error_code:
            self.error_code = error_code
        self.details = details or {}
        if retryable is not None:
            self.retryable = retryable

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary.

        Returns:
            Dictionary with error information
        """
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
            "retryable": self.retryable,
            "type": self.__class__.__name__,
        }


# Connection Errors (Retryable)
class ConnectionError(DativoError):
    """Base class for connection-related errors."""

    error_code = "CONNECTION_ERROR"
    retryable = True


class NetworkError(ConnectionError):
    """Network connectivity errors (DNS, timeout, etc.)."""

    error_code = "NETWORK_ERROR"
    retryable = True


class TimeoutError(ConnectionError):
    """Request timeout errors."""

    error_code = "TIMEOUT_ERROR"
    retryable = True


class RateLimitError(ConnectionError):
    """Rate limit exceeded errors."""

    error_code = "RATE_LIMIT_ERROR"
    retryable = True


# Authentication Errors (Permanent)
class AuthenticationError(DativoError):
    """Base class for authentication errors."""

    error_code = "AUTH_ERROR"
    retryable = False


class InvalidCredentialsError(AuthenticationError):
    """Invalid credentials (wrong API key, password, etc.)."""

    error_code = "INVALID_CREDENTIALS"
    retryable = False


class TokenExpiredError(AuthenticationError):
    """Expired authentication token (may be retryable after refresh)."""

    error_code = "TOKEN_EXPIRED"
    retryable = True  # Can retry after token refresh


class InsufficientPermissionsError(AuthenticationError):
    """Insufficient permissions to access resource."""

    error_code = "INSUFFICIENT_PERMISSIONS"
    retryable = False


# Configuration Errors (Permanent)
class ConfigurationError(DativoError):
    """Base class for configuration errors."""

    error_code = "CONFIG_ERROR"
    retryable = False


class InvalidConfigError(ConfigurationError):
    """Invalid configuration format or values."""

    error_code = "INVALID_CONFIG"
    retryable = False


class MissingConfigError(ConfigurationError):
    """Required configuration is missing."""

    error_code = "MISSING_CONFIG"
    retryable = False


class SchemaValidationError(ConfigurationError):
    """Schema validation failed."""

    error_code = "SCHEMA_VALIDATION_ERROR"
    retryable = False


# Data Errors (Context-dependent)
class DataError(DativoError):
    """Base class for data-related errors."""

    error_code = "DATA_ERROR"
    retryable = False


class DataNotFoundError(DataError):
    """Requested data not found."""

    error_code = "DATA_NOT_FOUND"
    retryable = False


class DataFormatError(DataError):
    """Data format is invalid or unexpected."""

    error_code = "DATA_FORMAT_ERROR"
    retryable = False


class DataValidationError(DataError):
    """Data validation failed."""

    error_code = "DATA_VALIDATION_ERROR"
    retryable = False


# Resource Errors (Mixed)
class ResourceError(DativoError):
    """Base class for resource-related errors."""

    error_code = "RESOURCE_ERROR"
    retryable = False


class ResourceNotFoundError(ResourceError):
    """Resource not found (table, file, endpoint, etc.)."""

    error_code = "RESOURCE_NOT_FOUND"
    retryable = False


class ResourceUnavailableError(ResourceError):
    """Resource temporarily unavailable."""

    error_code = "RESOURCE_UNAVAILABLE"
    retryable = True


class DiskFullError(ResourceError):
    """Disk or storage full."""

    error_code = "DISK_FULL"
    retryable = False


# Plugin Errors (Permanent)
class PluginError(DativoError):
    """Base class for plugin-related errors."""

    error_code = "PLUGIN_ERROR"
    retryable = False


class PluginLoadError(PluginError):
    """Failed to load plugin."""

    error_code = "PLUGIN_LOAD_ERROR"
    retryable = False


class PluginVersionError(PluginError):
    """Plugin version incompatibility."""

    error_code = "PLUGIN_VERSION_ERROR"
    retryable = False


class PluginExecutionError(PluginError):
    """Plugin execution failed."""

    error_code = "PLUGIN_EXECUTION_ERROR"
    retryable = False


# Transient Errors (Retryable)
class TransientError(DativoError):
    """Base class for transient errors that should be retried."""

    error_code = "TRANSIENT_ERROR"
    retryable = True


class ServiceUnavailableError(TransientError):
    """External service temporarily unavailable."""

    error_code = "SERVICE_UNAVAILABLE"
    retryable = True


class DatabaseLockError(TransientError):
    """Database lock or deadlock."""

    error_code = "DATABASE_LOCK"
    retryable = True


class ConcurrencyError(TransientError):
    """Concurrent modification conflict."""

    error_code = "CONCURRENCY_ERROR"
    retryable = True


# Helper functions
def is_retryable_error(error: Exception) -> bool:
    """Check if an error is retryable.

    Args:
        error: Exception to check

    Returns:
        True if error is retryable, False otherwise
    """
    if isinstance(error, DativoError):
        return error.retryable
    # Unknown errors are not retryable by default
    return False


def get_error_code(error: Exception) -> str:
    """Get error code from exception.

    Args:
        error: Exception to extract code from

    Returns:
        Error code string
    """
    if isinstance(error, DativoError):
        return error.error_code
    # Return generic error code for unknown exceptions
    return "UNKNOWN_ERROR"


def wrap_exception(
    error: Exception,
    error_class: type = DativoError,
    message: Optional[str] = None,
) -> DativoError:
    """Wrap an exception in a Dativo error.

    Args:
        error: Original exception
        error_class: Dativo error class to wrap with
        message: Optional custom message

    Returns:
        Wrapped Dativo error
    """
    if isinstance(error, DativoError):
        return error

    error_message = message or str(error)
    return error_class(
        message=error_message,
        details={"original_error": type(error).__name__, "original_message": str(error)},
    )
