"""Notification hooks for runner-level failure notifications.

This module implements the notification hook system that executes external
commands when jobs fail. It follows Dativo's philosophy:
- Headless, config-only
- No embedded services
- No opinionated integrations in core logic

Hooks are triggered only on job failure (exit_code = 2).
"""

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .logging import get_logger


# Patterns for redacting sensitive values in logs
SECRET_PATTERNS = [
    re.compile(r"(TOKEN|KEY|SECRET|WEBHOOK|PASSWORD|CREDENTIAL)", re.IGNORECASE),
]


def _should_redact_key(key: str) -> bool:
    """Check if an environment variable key should be redacted in logs.

    Args:
        key: Environment variable key name

    Returns:
        True if the key contains sensitive patterns
    """
    for pattern in SECRET_PATTERNS:
        if pattern.search(key):
            return True
    return False


def _redact_env_for_logging(env: Dict[str, str]) -> Dict[str, str]:
    """Redact sensitive values from environment dict for logging.

    Args:
        env: Environment variables dict

    Returns:
        Dict with sensitive values redacted
    """
    redacted = {}
    for key, value in env.items():
        if _should_redact_key(key):
            redacted[key] = "***REDACTED***"
        else:
            redacted[key] = value
    return redacted


def _expand_env_variable(value: str) -> str:
    """Expand ${VAR} style environment variable references.

    Args:
        value: String potentially containing ${VAR} references

    Returns:
        String with environment variables expanded
    """
    pattern = re.compile(r"\$\{([^}]+)\}")

    def replace(match: re.Match) -> str:
        var_name = match.group(1)
        return os.environ.get(var_name, "")

    return pattern.sub(replace, value)


def expand_hook_env(
    user_env: Optional[Dict[str, str]],
) -> Dict[str, str]:
    """Expand environment variables in hook env configuration.

    Performs ${VAR} expansion for all values in the user-provided env dict.

    Args:
        user_env: User-provided environment variables with ${VAR} syntax

    Returns:
        Dict with all ${VAR} references expanded
    """
    if not user_env:
        return {}

    expanded = {}
    for key, value in user_env.items():
        expanded[key] = _expand_env_variable(value)

    return expanded


class FailureSummary:
    """Generates failure summary JSON for notification hooks.

    The summary file contains minimal, stable information about the failed run.
    It never includes secrets and follows a stable schema contract.
    """

    def __init__(
        self,
        tenant_id: str,
        job_name: str,
        run_id: str,
        config_path: str,
        error_message: str,
        error_type: str = "UnknownError",
        timestamp: Optional[datetime] = None,
    ):
        """Initialize failure summary.

        Args:
            tenant_id: Tenant identifier
            job_name: Job/schedule name
            run_id: Unique run identifier (timestamp-based)
            config_path: Path to job configuration file
            error_message: Human-readable error message
            error_type: Error type classification
            timestamp: Failure timestamp (defaults to now)
        """
        self.tenant_id = tenant_id
        self.job_name = job_name
        self.run_id = run_id
        self.config_path = config_path
        self.error_message = error_message
        self.error_type = error_type
        self.timestamp = timestamp or datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dict with summary fields
        """
        return {
            "tenant_id": self.tenant_id,
            "job_name": self.job_name,
            "run_id": self.run_id,
            "status": "failure",
            "timestamp": self.timestamp.isoformat(),
            "config_path": self.config_path,
            "error": {
                "message": self.error_message,
                "type": self.error_type,
            },
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string.

        Args:
            indent: JSON indentation level

        Returns:
            JSON string representation
        """
        return json.dumps(self.to_dict(), indent=indent)

    def write_to_file(self, base_dir: str = "/logs/runs") -> Path:
        """Write summary to a deterministic file path.

        Creates directory structure if needed:
        {base_dir}/{run_id}/summary.json

        Args:
            base_dir: Base directory for run logs

        Returns:
            Path to written summary file
        """
        # Use run_id for directory name (sanitize for filesystem)
        run_dir_name = self.run_id.replace(":", "-").replace("/", "-")
        summary_dir = Path(base_dir) / run_dir_name
        summary_dir.mkdir(parents=True, exist_ok=True)

        summary_path = summary_dir / "summary.json"
        with open(summary_path, "w") as f:
            f.write(self.to_json())

        return summary_path


class NotificationHookExecutor:
    """Executes notification hooks for job failures.

    This class handles:
    - Command execution (argv-based, no shell)
    - Environment variable injection
    - Timeout handling
    - Graceful failure (never crashes the runner)
    - Secret redaction in logs
    """

    # Required DATIVO_* environment variables injected by runner
    REQUIRED_ENV_VARS = [
        "DATIVO_TENANT_ID",
        "DATIVO_JOB_NAME",
        "DATIVO_RUN_ID",
        "DATIVO_SUMMARY_PATH",
    ]

    def __init__(
        self,
        command: List[str],
        user_env: Optional[Dict[str, str]] = None,
        timeout_seconds: int = 15,
    ):
        """Initialize hook executor.

        Args:
            command: Command to execute as argv array
            user_env: User-provided environment variables (supports ${VAR} expansion)
            timeout_seconds: Timeout for hook execution
        """
        self.command = command
        self.user_env = user_env or {}
        self.timeout_seconds = timeout_seconds
        self.logger = get_logger()

    def _build_environment(
        self,
        tenant_id: str,
        job_name: str,
        run_id: str,
        summary_path: str,
    ) -> Dict[str, str]:
        """Build environment for hook execution.

        Environment precedence (highest to lowest):
        1. Required DATIVO_* variables (always set, override user values)
        2. User-provided env (after ${VAR} expansion)
        3. Existing process environment

        Args:
            tenant_id: Tenant identifier
            job_name: Job name
            run_id: Run identifier
            summary_path: Absolute path to summary JSON file

        Returns:
            Complete environment dict for subprocess
        """
        # Start with existing process environment
        env = os.environ.copy()

        # Apply user-provided env (after expansion)
        expanded_user_env = expand_hook_env(self.user_env)
        env.update(expanded_user_env)

        # Apply required DATIVO_* variables (highest precedence)
        env["DATIVO_TENANT_ID"] = tenant_id
        env["DATIVO_JOB_NAME"] = job_name
        env["DATIVO_RUN_ID"] = run_id
        env["DATIVO_SUMMARY_PATH"] = summary_path

        return env

    def execute(
        self,
        tenant_id: str,
        job_name: str,
        run_id: str,
        summary_path: str,
    ) -> Tuple[bool, Optional[str]]:
        """Execute the notification hook.

        Hook execution follows these rules:
        - Always fails gracefully (never raises exceptions)
        - Logs structured warnings/errors with redacted secrets
        - Does not affect job outcome

        Args:
            tenant_id: Tenant identifier
            job_name: Job name
            run_id: Run identifier
            summary_path: Absolute path to summary JSON file

        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        # Validate command exists and is executable
        command_path = Path(self.command[0])
        if not command_path.exists():
            error_msg = f"Hook command not found: {self.command[0]}"
            self.logger.error(
                error_msg,
                extra={
                    "event_type": "notification_hook_error",
                    "error_type": "CommandNotFound",
                    "command": self.command[0],
                    "tenant_id": tenant_id,
                    "job_name": job_name,
                },
            )
            return False, error_msg

        if not os.access(self.command[0], os.X_OK):
            error_msg = f"Hook command not executable: {self.command[0]}"
            self.logger.error(
                error_msg,
                extra={
                    "event_type": "notification_hook_error",
                    "error_type": "PermissionDenied",
                    "command": self.command[0],
                    "tenant_id": tenant_id,
                    "job_name": job_name,
                },
            )
            return False, error_msg

        # Build environment
        env = self._build_environment(tenant_id, job_name, run_id, summary_path)

        # Log execution start (with redacted env)
        redacted_user_env = _redact_env_for_logging(self.user_env)
        self.logger.info(
            f"Executing notification hook: {self.command[0]}",
            extra={
                "event_type": "notification_hook_started",
                "command": self.command,
                "timeout_seconds": self.timeout_seconds,
                "user_env": redacted_user_env,
                "tenant_id": tenant_id,
                "job_name": job_name,
                "run_id": run_id,
            },
        )

        try:
            # Execute command with timeout
            result = subprocess.run(
                self.command,
                env=env,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )

            if result.returncode == 0:
                self.logger.info(
                    "Notification hook executed successfully",
                    extra={
                        "event_type": "notification_hook_success",
                        "command": self.command[0],
                        "tenant_id": tenant_id,
                        "job_name": job_name,
                        "run_id": run_id,
                    },
                )
                return True, None
            else:
                # Non-zero exit - log warning but don't fail
                stderr_snippet = (
                    result.stderr[:500] if result.stderr else "(no stderr)"
                )
                # Redact potential secrets in stderr
                for pattern in SECRET_PATTERNS:
                    stderr_snippet = pattern.sub("[REDACTED]", stderr_snippet)

                error_msg = f"Hook exited with code {result.returncode}"
                self.logger.warning(
                    error_msg,
                    extra={
                        "event_type": "notification_hook_failed",
                        "command": self.command[0],
                        "exit_code": result.returncode,
                        "stderr_snippet": stderr_snippet,
                        "tenant_id": tenant_id,
                        "job_name": job_name,
                        "run_id": run_id,
                    },
                )
                return False, f"{error_msg}: {stderr_snippet}"

        except subprocess.TimeoutExpired:
            error_msg = f"Hook timed out after {self.timeout_seconds}s"
            self.logger.warning(
                error_msg,
                extra={
                    "event_type": "notification_hook_timeout",
                    "command": self.command[0],
                    "timeout_seconds": self.timeout_seconds,
                    "tenant_id": tenant_id,
                    "job_name": job_name,
                    "run_id": run_id,
                },
            )
            return False, error_msg

        except Exception as e:
            error_msg = f"Hook execution error: {type(e).__name__}: {str(e)}"
            self.logger.error(
                error_msg,
                extra={
                    "event_type": "notification_hook_error",
                    "error_type": type(e).__name__,
                    "command": self.command[0],
                    "tenant_id": tenant_id,
                    "job_name": job_name,
                    "run_id": run_id,
                },
            )
            return False, error_msg


def execute_failure_notification(
    config: "NotificationsConfig",
    tenant_id: str,
    job_name: str,
    run_id: str,
    config_path: str,
    error_message: str,
    error_type: str = "UnknownError",
    summary_base_dir: str = "/logs/runs",
) -> bool:
    """Execute failure notification hook if configured.

    This is the main entry point for triggering notification hooks.
    It handles the complete flow:
    1. Writes failure summary to file
    2. Executes the configured hook command
    3. Returns success/failure status

    Args:
        config: NotificationsConfig from runner config
        tenant_id: Tenant identifier
        job_name: Job/schedule name
        run_id: Unique run identifier
        config_path: Path to job configuration file
        error_message: Human-readable error message
        error_type: Error type classification
        summary_base_dir: Base directory for summary files

    Returns:
        True if hook executed successfully, False otherwise
    """
    # Import here to avoid circular imports
    from .config import NotificationsConfig

    logger = get_logger()

    # Check if notifications are configured
    if not config or not config.on_failure:
        logger.debug(
            "No failure notification hook configured",
            extra={
                "event_type": "notification_hook_skipped",
                "reason": "not_configured",
                "tenant_id": tenant_id,
                "job_name": job_name,
            },
        )
        return True  # Not an error - just not configured

    on_failure = config.on_failure

    # Generate failure summary
    summary = FailureSummary(
        tenant_id=tenant_id,
        job_name=job_name,
        run_id=run_id,
        config_path=config_path,
        error_message=error_message,
        error_type=error_type,
    )

    # Write summary to file
    try:
        summary_path = summary.write_to_file(base_dir=summary_base_dir)
        logger.info(
            f"Failure summary written to {summary_path}",
            extra={
                "event_type": "failure_summary_written",
                "summary_path": str(summary_path),
                "tenant_id": tenant_id,
                "job_name": job_name,
                "run_id": run_id,
            },
        )
    except Exception as e:
        logger.error(
            f"Failed to write failure summary: {e}",
            extra={
                "event_type": "failure_summary_error",
                "error": str(e),
                "tenant_id": tenant_id,
                "job_name": job_name,
            },
        )
        # Continue anyway - try to execute hook with empty summary path
        summary_path = Path("")

    # Execute notification hook
    executor = NotificationHookExecutor(
        command=on_failure.command,
        user_env=on_failure.env,
        timeout_seconds=on_failure.timeout_seconds,
    )

    success, error = executor.execute(
        tenant_id=tenant_id,
        job_name=job_name,
        run_id=run_id,
        summary_path=str(summary_path.absolute()) if summary_path else "",
    )

    return success
