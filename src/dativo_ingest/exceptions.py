"""Standardized error hierarchy for Dativo platform.

This module defines a comprehensive error hierarchy that enables:
- Distinguishing retryable vs. permanent failures
- Proper error categorization for observability
- Version compatibility checks
- Better error handling in orchestrators
"""

from typing import Any, Dict, Optional


class DativoError(Exception):
    """Base exception for all Dativo errors.

    All Dativo-specific exceptions should inherit from this class.
    """

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        retryable: bool = False,
    ):
        """Initialize Dativo error.

        Args:
            message: Human-readable error message
            error_code: Machine-readable error code (e.g., "CONNECTION_FAILED")
            details: Additional error details for debugging
            retryable: Whether this error is retryable (default: False)
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__.upper()
        self.details = details or {}
        self.retryable = retryable

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for serialization.

        Returns:
            Dictionary representation of the error
        """
        return {
            "error_type": self.__class__.__name__,
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
            "retryable": self.retryable,
        }

    def __str__(self) -> str:
        """String representation of error."""
        return f"{self.__class__.__name__}({self.error_code}): {self.message}"


class ConnectionError(DativoError):
    """Connection-related errors.

    These errors occur when connecting to external systems (databases, APIs, etc.).
    Most connection errors are retryable (network issues, temporary unavailability).
    """

    def __init__(
        self,
        message: str,
        error_code: str = "CONNECTION_FAILED",
        details: Optional[Dict[str, Any]] = None,
        retryable: bool = True,
    ):
        """Initialize connection error.

        Args:
            message: Error message
            error_code: Error code (default: "CONNECTION_FAILED")
            details: Additional details
            retryable: Whether retryable (default: True for connection errors)
        """
        super().__init__(message, error_code, details, retryable)


class AuthenticationError(ConnectionError):
    """Authentication/authorization errors.

    These errors occur when credentials are invalid or insufficient.
    Generally NOT retryable (unless credentials are rotated).
    """

    def __init__(
        self,
        message: str,
        error_code: str = "AUTHENTICATION_FAILED",
        details: Optional[Dict[str, Any]] = None,
        retryable: bool = False,
    ):
        """Initialize authentication error.

        Args:
            message: Error message
            error_code: Error code (default: "AUTHENTICATION_FAILED")
            details: Additional details
            retryable: Whether retryable (default: False for auth errors)
        """
        super().__init__(message, error_code, details, retryable)


class ValidationError(DativoError):
    """Data validation errors.

    These errors occur when data doesn't match expected schemas or formats.
    NOT retryable - indicates data quality issues.
    """

    def __init__(
        self,
        message: str,
        error_code: str = "VALIDATION_FAILED",
        details: Optional[Dict[str, Any]] = None,
        retryable: bool = False,
    ):
        """Initialize validation error.

        Args:
            message: Error message
            error_code: Error code (default: "VALIDATION_FAILED")
            details: Additional details (e.g., field names, expected types)
            retryable: Whether retryable (default: False for validation errors)
        """
        super().__init__(message, error_code, details, retryable)


class ConfigurationError(DativoError):
    """Configuration errors.

    These errors occur when job/connector configuration is invalid.
    NOT retryable - indicates misconfiguration.
    """

    def __init__(
        self,
        message: str,
        error_code: str = "CONFIGURATION_ERROR",
        details: Optional[Dict[str, Any]] = None,
        retryable: bool = False,
    ):
        """Initialize configuration error.

        Args:
            message: Error message
            error_code: Error code (default: "CONFIGURATION_ERROR")
            details: Additional details (e.g., config path, missing fields)
            retryable: Whether retryable (default: False for config errors)
        """
        super().__init__(message, error_code, details, retryable)


class TransientError(DativoError):
    """Transient/temporary errors.

    These errors are expected to be temporary and should be retried.
    Examples: rate limits, temporary service unavailability, timeouts.
    """

    def __init__(
        self,
        message: str,
        error_code: str = "TRANSIENT_ERROR",
        details: Optional[Dict[str, Any]] = None,
        retryable: bool = True,
        retry_after: Optional[int] = None,
    ):
        """Initialize transient error.

        Args:
            message: Error message
            error_code: Error code (default: "TRANSIENT_ERROR")
            details: Additional details
            retryable: Whether retryable (default: True)
            retry_after: Seconds to wait before retry (optional)
        """
        super().__init__(message, error_code, details, retryable)
        self.retry_after = retry_after
        if retry_after:
            self.details["retry_after"] = retry_after

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary including retry_after."""
        result = super().to_dict()
        if self.retry_after:
            result["retry_after"] = self.retry_after
        return result


class RateLimitError(TransientError):
    """Rate limit errors.

    These errors occur when API rate limits are exceeded.
    Retryable after the specified retry_after period.
    """

    def __init__(
        self,
        message: str,
        error_code: str = "RATE_LIMIT_EXCEEDED",
        details: Optional[Dict[str, Any]] = None,
        retry_after: Optional[int] = None,
    ):
        """Initialize rate limit error.

        Args:
            message: Error message
            error_code: Error code (default: "RATE_LIMIT_EXCEEDED")
            details: Additional details
            retry_after: Seconds to wait before retry (required for rate limits)
        """
        super().__init__(
            message, error_code, details, retryable=True, retry_after=retry_after
        )


class PluginError(DativoError):
    """Plugin-related errors.

    These errors occur when loading or executing plugins.
    May be retryable depending on the specific error.
    """

    def __init__(
        self,
        message: str,
        error_code: str = "PLUGIN_ERROR",
        details: Optional[Dict[str, Any]] = None,
        retryable: bool = False,
    ):
        """Initialize plugin error.

        Args:
            message: Error message
            error_code: Error code (default: "PLUGIN_ERROR")
            details: Additional details (e.g., plugin path, class name)
            retryable: Whether retryable (default: False)
        """
        super().__init__(message, error_code, details, retryable)


class PluginVersionError(PluginError):
    """Plugin version compatibility errors.

    These errors occur when plugin version is incompatible with the platform.
    NOT retryable - requires plugin update.
    """

    def __init__(
        self,
        message: str,
        plugin_version: Optional[str] = None,
        required_version: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Initialize plugin version error.

        Args:
            message: Error message
            plugin_version: Version of the plugin
            required_version: Required version
            details: Additional details
        """
        if details is None:
            details = {}
        if plugin_version:
            details["plugin_version"] = plugin_version
        if required_version:
            details["required_version"] = required_version

        super().__init__(
            message,
            error_code="PLUGIN_VERSION_INCOMPATIBLE",
            details=details,
            retryable=False,
        )


class SandboxError(PluginError):
    """Plugin sandbox execution errors.

    These errors occur when executing plugins in sandboxed environments.
    May be retryable depending on the specific error.
    """

    def __init__(
        self,
        message: str,
        error_code: str = "SANDBOX_ERROR",
        details: Optional[Dict[str, Any]] = None,
        retryable: bool = True,
    ):
        """Initialize sandbox error.

        Args:
            message: Error message
            error_code: Error code (default: "SANDBOX_ERROR")
            details: Additional details
            retryable: Whether retryable (default: True for sandbox errors)
        """
        super().__init__(message, error_code, details, retryable)


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
        details={
            "original_error": type(error).__name__,
            "original_message": str(error),
        },
    )
