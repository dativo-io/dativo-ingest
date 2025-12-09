"""Structured logging with secret redaction and tenant tagging."""

import json
import logging
import re
from typing import Any, Dict, List, Optional


def _redact_list_values(data: List[Any]) -> List[Any]:
    """Recursively redact secret values in a list.

    Args:
        data: List that may contain secrets

    Returns:
        List with secret values redacted
    """
    redacted = []
    for item in data:
        if isinstance(item, dict):
            redacted.append(_redact_dict_values(item))
        elif isinstance(item, list):
            redacted.append(_redact_list_values(item))
        elif isinstance(item, str) and len(item) >= 20:
            # Redact long strings that look like secrets (base64-like)
            if re.match(r"^[A-Za-z0-9+/=]{20,}$", item):
                redacted.append("[REDACTED]")
            else:
                redacted.append(item)
        else:
            redacted.append(item)
    return redacted


def _redact_dict_values(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively redact secret values in a dictionary.

    This function processes dictionaries recursively, handling:
    - Nested dictionaries (recursively processed)
    - List values (delegated to _redact_list_values for recursive processing)
    - String values (redacted if they match secret key patterns or look like secrets)

    Args:
        data: Dictionary that may contain secrets

    Returns:
        Dictionary with secret values redacted
    """
    redacted = {}
    secret_key_patterns = [
        "password",
        "token",
        "api_key",
        "secret",
        "credential",
        "access_key",
        "secret_key",
        "secret_access_key",
        "private_key",
        "auth_token",
        "bearer",
    ]

    for key, value in data.items():
        key_lower = key.lower()
        # Check if key matches any secret pattern
        is_secret_key = any(pattern in key_lower for pattern in secret_key_patterns)

        if isinstance(value, dict):
            redacted[key] = _redact_dict_values(value)
        elif isinstance(value, list):
            redacted[key] = _redact_list_values(value)
        elif isinstance(value, str) and is_secret_key:
            # Redact string values in secret keys
            redacted[key] = "[REDACTED]"
        elif isinstance(value, str) and len(value) >= 20:
            # Redact long strings that look like secrets (base64-like)
            if re.match(r"^[A-Za-z0-9+/=]{20,}$", value):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = value
        else:
            redacted[key] = value

    return redacted


class StructuredJSONFormatter(logging.Formatter):
    """JSON formatter for structured logging with secret redaction."""

    def __init__(self, redact_secrets: bool = False):
        super().__init__()
        self.redact_secrets = redact_secrets
        # Patterns for common secret fields - these match the field name and value
        # Format: field_name (with optional spaces/underscores) followed by colon/equals and the value
        # Handles: "password: value", "api_key: value", "API key: value", etc.
        self.secret_patterns = [
            r'(\bpassword\s*["\']?\s*[:=]\s*["\']?)([^"\'\s,}]+)',
            r'(\btoken\s*["\']?\s*[:=]\s*["\']?)([^"\'\s,}]+)',
            r'(\bapi[_\s]?key\s*["\']?\s*[:=]\s*["\']?)([^"\'\s,}]+)',
            r'(\bsecret\s*["\']?\s*[:=]\s*["\']?)([^"\'\s,}]+)',
            r'(\bcredential\s*["\']?\s*[:=]\s*["\']?)([^"\'\s,}]+)',
            r'(\baccess[_\s]?key\s*["\']?\s*[:=]\s*["\']?)([^"\'\s,}]+)',
            r'(\bsecret[_\s]?key\s*["\']?\s*[:=]\s*["\']?)([^"\'\s,}]+)',
            r'(\bsecret[_\s]?access[_\s]?key\s*["\']?\s*[:=]\s*["\']?)([^"\'\s,}]+)',
            r'(\bprivate[_\s]?key\s*["\']?\s*[:=]\s*["\']?)([^"\'\s,}]+)',
            r'(\bauth[_\s]?token\s*["\']?\s*[:=]\s*["\']?)([^"\'\s,}]+)',
            r'(\bbearer\s*["\']?\s*[:=]\s*["\']?)([^"\'\s,}]+)',
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

        # Collect all extra fields from record attributes
        extra_fields = {}
        if hasattr(record, "extra_data"):
            if isinstance(record.extra_data, dict):
                extra_fields.update(record.extra_data)

        # Also check for extra dict items (from logger.info(..., extra={...}))
        # These are stored as attributes on the record
        for key, value in record.__dict__.items():
            # Skip standard LogRecord attributes and already processed fields
            if key not in [
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "thread",
                "threadName",
                "exc_info",
                "exc_text",
                "stack_info",
                "tenant_id",
                "job_name",
                "event_type",
                "connector_type",
                "extra_data",
            ]:
                extra_fields[key] = value

        # Redact secrets in extra fields before adding to log_data
        if self.redact_secrets and extra_fields:
            redacted_extra = _redact_dict_values(extra_fields)
            log_data.update(redacted_extra)
        elif extra_fields:
            log_data.update(extra_fields)

        # Redact secrets if enabled - redact in the data structure before JSON encoding
        if self.redact_secrets:
            # Redact secrets in the message string
            if "message" in log_data and isinstance(log_data["message"], str):
                message = log_data["message"]
                # Redact known secret patterns in message
                for pattern in self.secret_patterns:
                    message = re.sub(
                        pattern, r"\1[REDACTED]", message, flags=re.IGNORECASE
                    )
                # Redact long base64-like strings
                message = re.sub(
                    r'(["\']?)([A-Za-z0-9+/=]{20,})(["\']?)',
                    lambda m: (
                        m.group(1) + "[REDACTED]" + m.group(3)
                        if not m.group(2).startswith("[REDACTED]")
                        and "[REDACTED]" not in m.group(2)
                        else m.group(0)
                    ),
                    message,
                )
                log_data["message"] = message

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
