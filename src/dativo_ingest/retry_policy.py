"""Retry policy implementation with exponential backoff and error classification."""

import re
import time
from typing import Any, Dict, List, Optional

from .config import RetryConfig
from .logging import get_logger


class RetryPolicy:
    """Retry policy with exponential backoff and error classification."""

    def __init__(self, config: Optional[RetryConfig] = None):
        """Initialize retry policy.

        Args:
            config: Retry configuration (if None, uses defaults)
        """
        self.config = config or RetryConfig()
        self.logger = get_logger()

    def should_retry(
        self,
        exit_code: int,
        error_message: Optional[str] = None,
        attempt: int = 0,
    ) -> bool:
        """Determine if a retry should be attempted.

        Args:
            exit_code: Exit code from job execution
            error_message: Error message (optional)
            attempt: Current attempt number (0-indexed)

        Returns:
            True if retry should be attempted
        """
        # Check if we've exceeded max retries
        if attempt >= self.config.max_retries:
            self.logger.debug(
                f"Max retries ({self.config.max_retries}) exceeded",
                extra={"attempt": attempt, "exit_code": exit_code},
            )
            return False

        # Check if exit code is retryable
        if exit_code not in self.config.retryable_exit_codes:
            self.logger.debug(
                f"Exit code {exit_code} not in retryable list",
                extra={
                    "exit_code": exit_code,
                    "retryable_codes": self.config.retryable_exit_codes,
                },
            )
            return False

        # Check error message patterns if provided
        if error_message and self.config.retryable_error_patterns:
            if not self._matches_error_patterns(error_message):
                self.logger.debug(
                    "Error message does not match retryable patterns",
                    extra={"error_message": error_message[:100]},
                )
                return False

        return True

    def _matches_error_patterns(self, error_message: str) -> bool:
        """Check if error message matches any retryable pattern.

        Args:
            error_message: Error message to check

        Returns:
            True if message matches any pattern
        """
        if not self.config.retryable_error_patterns:
            return True  # No patterns means all errors are retryable

        for pattern in self.config.retryable_error_patterns:
            try:
                if re.search(pattern, error_message, re.IGNORECASE):
                    return True
            except re.error:
                self.logger.warning(
                    f"Invalid regex pattern in retryable_error_patterns: {pattern}",
                    extra={"pattern": pattern},
                )

        return False

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay before next retry using exponential backoff.

        Args:
            attempt: Current attempt number (0-indexed)

        Returns:
            Delay in seconds (capped at max_delay_seconds)
        """
        delay = self.config.initial_delay_seconds * (
            self.config.backoff_multiplier**attempt
        )
        return min(delay, self.config.max_delay_seconds)

    def get_retry_metadata(self, attempt: int) -> Dict[str, Any]:
        """Get metadata for retry attempt.

        Args:
            attempt: Current attempt number (0-indexed)

        Returns:
            Metadata dictionary
        """
        delay = self.calculate_delay(attempt)
        return {
            "retry_attempt": attempt + 1,
            "max_retries": self.config.max_retries,
            "delay_seconds": delay,
            "backoff_multiplier": self.config.backoff_multiplier,
        }

    def log_retry_attempt(
        self,
        attempt: int,
        exit_code: int,
        error_message: Optional[str] = None,
    ) -> None:
        """Log retry attempt with structured logging.

        Args:
            attempt: Current attempt number (0-indexed)
            exit_code: Exit code from job execution
            error_message: Error message (optional)
        """
        delay = self.calculate_delay(attempt)
        metadata = self.get_retry_metadata(attempt)

        self.logger.warning(
            f"Retrying job (attempt {attempt + 1}/{self.config.max_retries})",
            extra={
                "event_type": "retry_attempt",
                "exit_code": exit_code,
                "error_message": error_message[:200] if error_message else None,
                **metadata,
            },
        )

        if delay > 0:
            self.logger.info(
                f"Waiting {delay:.2f} seconds before retry",
                extra={"event_type": "retry_delay", "delay_seconds": delay},
            )

    def wait_for_retry(self, attempt: int) -> None:
        """Wait for calculated delay before retry.

        Args:
            attempt: Current attempt number (0-indexed)
        """
        delay = self.calculate_delay(attempt)
        if delay > 0:
            time.sleep(delay)
