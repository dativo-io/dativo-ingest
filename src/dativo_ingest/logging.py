"""Structured logging with secret redaction and tenant tagging."""

import json
import logging
import re
from typing import Any, Dict, Optional


class StructuredJSONFormatter(logging.Formatter):
    """JSON formatter for structured logging with secret redaction."""

    def __init__(self, redact_secrets: bool = False):
        super().__init__()
        self.redact_secrets = redact_secrets
        # Patterns for common secret fields
        self.secret_patterns = [
            r'password["\']?\s*[:=]\s*["\']?([^"\']+)',
            r'token["\']?\s*[:=]\s*["\']?([^"\']+)',
            r'api_key["\']?\s*[:=]\s*["\']?([^"\']+)',
            r'secret["\']?\s*[:=]\s*["\']?([^"\']+)',
            r'credential["\']?\s*[:=]\s*["\']?([^"\']+)',
        ]

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON with optional secret redaction."""
        log_data: Dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add tenant_id if present in extra
        if hasattr(record, "tenant_id"):
            log_data["tenant_id"] = record.tenant_id

        # Add job_name if present
        if hasattr(record, "job_name"):
            log_data["job_name"] = record.job_name

        # Add event_type if present
        if hasattr(record, "event_type"):
            log_data["event_type"] = record.event_type

        # Add connector context if present
        if hasattr(record, "connector_type"):
            log_data["connector_type"] = record.connector_type

        # Add any other extra fields
        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)

        # Redact secrets if enabled
        if self.redact_secrets:
            log_str = json.dumps(log_data)
            for pattern in self.secret_patterns:
                log_str = re.sub(pattern, r"\1", log_str, flags=re.IGNORECASE)
                # Replace matched secrets with [REDACTED]
                log_str = re.sub(
                    r'(["\']?)([A-Za-z0-9+/=]{20,})(["\']?)', r"\1[REDACTED]\3", log_str
                )
            return log_str

        return json.dumps(log_data)


def setup_logging(
    level: str = "INFO",
    redact_secrets: bool = False,
    tenant_id: Optional[str] = None,
) -> logging.Logger:
    """Set up structured JSON logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        redact_secrets: Whether to redact secrets in logs
        tenant_id: Optional tenant ID to include in all logs

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("dativo_ingest")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    logger.handlers.clear()

    # Create console handler with JSON formatter
    handler = logging.StreamHandler()
    formatter = StructuredJSONFormatter(redact_secrets=redact_secrets)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Add tenant_id to all log records if provided
    if tenant_id:
        old_factory = logging.getLogRecordFactory()

        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            record.tenant_id = tenant_id
            return record

        logging.setLogRecordFactory(record_factory)

    return logger


def update_logging_settings(
    level: Optional[str] = None,
    redact_secrets: Optional[bool] = None,
    tenant_id: Optional[str] = None,
) -> logging.Logger:
    """Update existing logger settings without clearing handlers.

    This is useful when you want to update logging configuration (e.g., log level
    or redaction settings) without losing existing handlers or reinitializing.

    Args:
        level: Log level to set (DEBUG, INFO, WARNING, ERROR). If None, keeps current.
        redact_secrets: Whether to redact secrets. If None, keeps current.
        tenant_id: Tenant ID to include in logs. If None, keeps current.

    Returns:
        Updated logger instance
    """
    logger = logging.getLogger("dativo_ingest")

    # Update log level if provided
    if level is not None:
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Update formatter on existing handlers if redact_secrets is provided
    if redact_secrets is not None:
        for handler in logger.handlers:
            if isinstance(handler.formatter, StructuredJSONFormatter):
                handler.formatter.redact_secrets = redact_secrets
            else:
                # Replace formatter if it's not the right type
                handler.setFormatter(
                    StructuredJSONFormatter(redact_secrets=redact_secrets)
                )

    # Update tenant_id in log record factory if provided
    if tenant_id is not None:
        old_factory = logging.getLogRecordFactory()

        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            record.tenant_id = tenant_id
            return record

        logging.setLogRecordFactory(record_factory)

    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Get a logger instance.

    Args:
        name: Optional logger name (defaults to 'dativo_ingest')

    Returns:
        Logger instance
    """
    return logging.getLogger(name or "dativo_ingest")
