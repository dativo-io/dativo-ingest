"""Runner-level notification hook utilities."""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .config import NotificationHookConfig
from .logging import get_logger
from .utils import expand_env_variable

DEFAULT_NOTIFICATION_TIMEOUT_SECONDS = 15
DEFAULT_NOTIFICATION_LOG_DIR = "/logs"
STDERR_SNIPPET_LIMIT = 500

_REDACTION_PATTERN = re.compile(
    r"(?i)(token|secret|key|webhook)(\s*[:=]\s*)([^\s,;\"']+)"
)
_SLACK_WEBHOOK_PATTERN = re.compile(
    r"hooks\.slack\.com/services/[A-Za-z0-9/_-]+"
)


def redact_notification_text(text: Optional[str]) -> Optional[str]:
    """Redact sensitive tokens from notification logs."""
    if not text:
        return text
    redacted = _REDACTION_PATTERN.sub(r"\1\2[REDACTED]", text)
    redacted = _SLACK_WEBHOOK_PATTERN.sub("[REDACTED_WEBHOOK]", redacted)
    return redacted


def format_timestamp(timestamp: Optional[datetime] = None) -> str:
    """Format timestamp as UTC ISO-8601 with Z suffix."""
    ts = timestamp or datetime.now(timezone.utc)
    return ts.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def sanitize_run_id(run_id: str) -> str:
    """Normalize run_id for filesystem paths."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", run_id)


def build_failure_summary(
    tenant_id: str,
    job_name: str,
    run_id: str,
    config_path: str,
    error_message: str,
    error_type: str,
    timestamp: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Build minimal failure summary payload."""
    return {
        "tenant_id": tenant_id,
        "job_name": job_name,
        "run_id": run_id,
        "status": "failure",
        "timestamp": format_timestamp(timestamp),
        "config_path": config_path,
        "error": {
            "message": error_message,
            "type": error_type,
        },
    }


def write_failure_summary(
    summary: Dict[str, Any],
    run_id: str,
    logger=None,
    base_dir: Optional[str] = None,
) -> str:
    """Write failure summary to deterministic path."""
    logger = logger or get_logger()
    log_dir = base_dir or DEFAULT_NOTIFICATION_LOG_DIR
    if not os.path.isabs(log_dir):
        log_dir = os.path.abspath(log_dir)

    safe_run_id = sanitize_run_id(run_id)
    summary_path = Path(log_dir) / "runs" / safe_run_id / "summary.json"

    try:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)
    except Exception as exc:
        logger.warning(
            "Failed to write notification summary",
            extra={
                "event_type": "notification_summary_error",
                "summary_path": str(summary_path),
                "error": str(exc),
            },
        )

    return str(summary_path)


def build_notification_env(
    hook_env: Optional[Dict[str, str]],
    required_env: Dict[str, str],
    base_env: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Build notification hook environment with precedence rules."""
    env = dict(base_env or os.environ)

    if hook_env:
        for key, value in hook_env.items():
            expanded = expand_env_variable(value)
            if expanded is None:
                continue
            env[str(key)] = str(expanded)

    for key, value in required_env.items():
        env[key] = "" if value is None else str(value)

    return env


def execute_notification_hook(
    hook: NotificationHookConfig,
    env: Dict[str, str],
    logger=None,
    timeout_seconds: int = DEFAULT_NOTIFICATION_TIMEOUT_SECONDS,
) -> None:
    """Execute the notification hook command safely."""
    logger = logger or get_logger()
    if not hook or not hook.command:
        logger.warning(
            "Notification hook missing command",
            extra={"event_type": "notification_hook_missing_command"},
        )
        return

    redacted_command = [redact_notification_text(str(arg)) for arg in hook.command]

    try:
        result = subprocess.run(
            hook.command,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        logger.warning(
            "Notification hook command not found",
            extra={
                "event_type": "notification_hook_not_found",
                "command": redacted_command,
            },
        )
        return
    except PermissionError:
        logger.warning(
            "Notification hook command not executable",
            extra={
                "event_type": "notification_hook_not_executable",
                "command": redacted_command,
            },
        )
        return
    except subprocess.TimeoutExpired as exc:
        stderr_snippet = redact_notification_text(
            (exc.stderr or "")[:STDERR_SNIPPET_LIMIT]
        )
        logger.warning(
            "Notification hook timed out",
            extra={
                "event_type": "notification_hook_timeout",
                "command": redacted_command,
                "timeout_seconds": timeout_seconds,
                "stderr_snippet": stderr_snippet,
            },
        )
        return
    except Exception as exc:
        logger.warning(
            "Notification hook execution failed",
            extra={
                "event_type": "notification_hook_error",
                "command": redacted_command,
                "error": str(exc),
            },
        )
        return

    if result.returncode != 0:
        stderr_snippet = redact_notification_text(
            (result.stderr or "")[:STDERR_SNIPPET_LIMIT]
        )
        logger.warning(
            "Notification hook exited non-zero",
            extra={
                "event_type": "notification_hook_failed",
                "command": redacted_command,
                "exit_code": result.returncode,
                "stderr_snippet": stderr_snippet,
            },
        )
