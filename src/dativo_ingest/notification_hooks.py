"""Notification hooks for runner-level failure notifications.

Hooks execute external scripts when jobs fail (exit_code = 2).
Minimal, safe implementation that never compromises ingestion correctness.
"""

import json
import os
import re
import subprocess
import tempfile
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

    Supports ${VAR} and ${VAR:-default} syntax.

    Args:
        value: String potentially containing ${VAR} references

    Returns:
        String with environment variables expanded
    """
    pattern = re.compile(r"\$\{([^}]+)\}")

    def replace(match: re.Match) -> str:
        var_spec = match.group(1)
        if ":-" in var_spec:
            var_name, default = var_spec.split(":-", 1)
            return os.environ.get(var_name, default)
        return os.environ.get(var_spec, "")

    return pattern.sub(replace, value)


def _expand_command_args(args: List[str]) -> List[str]:
    """Expand ${VAR} references in command arguments.

    Args:
        args: Command arguments with potential ${VAR} references

    Returns:
        List with all ${VAR} references expanded
    """
    return [_expand_env_variable(arg) for arg in args]


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


def _redact_command_args(args: List[str]) -> List[str]:
    """Redact sensitive values in command arguments for logging.

    Args:
        args: Command arguments

    Returns:
        List with sensitive values redacted
    """
    redacted = []
    for arg in args:
        # Check if arg contains secret patterns (e.g., --token=secret)
        should_redact = False
        for pattern in SECRET_PATTERNS:
            if pattern.search(arg):
                should_redact = True
                break

        if should_redact:
            # Redact value after = or : separator
            if "=" in arg:
                key, _ = arg.split("=", 1)
                redacted.append(f"{key}=[REDACTED]")
            elif ":" in arg and not arg.startswith("http"):
                key, _ = arg.split(":", 1)
                redacted.append(f"{key}:[REDACTED]")
            else:
                redacted.append("[REDACTED]")
        else:
            redacted.append(arg)

    return redacted


def _create_hook_payload(
    tenant_id: str,
    job_name: str,
    config_path: str,
    exit_code: int,
    failure_reason: str,
    summary_path: Optional[str] = None,
) -> Path:
    """Create JSON payload file for hook execution.

    Args:
        tenant_id: Tenant identifier
        job_name: Job name
        config_path: Path to job configuration
        exit_code: Job exit code (should be 2 for failures)
        failure_reason: Human-readable failure reason
        summary_path: Optional path to run summary file

    Returns:
        Path to temporary payload file
    """
    payload = {
        "tenant_id": tenant_id,
        "job_name": job_name,
        "config_path": config_path,
        "exit_code": exit_code,
        "failure_reason": failure_reason,
    }
    # Only add summary_path if it's a non-empty string
    # This handles the case where summary_path might be Path("") which is truthy
    # but should not be used as a valid path
    if summary_path and isinstance(summary_path, str) and summary_path.strip():
        payload["summary_path"] = summary_path

    # Create temporary file that will be cleaned up after hook execution
    fd, payload_path = tempfile.mkstemp(suffix=".json", prefix="dativo_hook_")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, indent=2)
        return Path(payload_path)
    except Exception:
        os.close(fd)
        raise


def _execute_hook(
    command: List[str],
    payload_path: Path,
    user_env: Optional[Dict[str, str]] = None,
    timeout_seconds: int = 15,
    hook_name: str = "unknown",
) -> Tuple[bool, Optional[str]]:
    """Execute a notification hook command.

    Hook execution follows these rules:
    - Always fails gracefully (never raises exceptions)
    - Logs structured warnings/errors with redacted secrets
    - Does not affect job outcome

    Args:
        command: Command to execute as argv array (supports ${VAR} expansion)
        payload_path: Path to JSON payload file
        user_env: User-provided environment variables (supports ${VAR} expansion)
        timeout_seconds: Timeout for hook execution
        hook_name: Hook name for logging

    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    logger = get_logger()

    # Expand env vars in command arguments
    expanded_command = _expand_command_args(command)

    # Validate command exists and is executable
    if not Path(expanded_command[0]).exists():
        error_msg = f"Hook command not found: {expanded_command[0]}"
        logger.error(
            error_msg,
            extra={
                "event_type": "notification_hook_error",
                "error_type": "CommandNotFound",
                "hook_name": hook_name,
                "command": expanded_command[0],
            },
        )
        return False, error_msg

    if not os.access(expanded_command[0], os.X_OK):
        error_msg = f"Hook command not executable: {expanded_command[0]}"
        logger.error(
            error_msg,
            extra={
                "event_type": "notification_hook_error",
                "error_type": "PermissionDenied",
                "hook_name": hook_name,
                "command": expanded_command[0],
            },
        )
        return False, error_msg

    # Build environment
    env = os.environ.copy()
    expanded_user_env = expand_hook_env(user_env)
    env.update(expanded_user_env)
    env["DATIVO_HOOK_PAYLOAD"] = str(payload_path.absolute())

    # Extract summary_path from payload and set DATIVO_SUMMARY_PATH
    # Only set if summary_path exists and is a non-empty string
    # This handles the case where summary_path might be Path("") which is truthy
    # but should not be used as a valid path
    try:
        with open(payload_path, "r") as f:
            payload_data = json.load(f)
        summary_path_value = payload_data.get("summary_path")
        # Only set if summary_path is a non-empty string
        # Check explicitly for string type and non-empty to avoid Path("") issues
        if (
            summary_path_value
            and isinstance(summary_path_value, str)
            and summary_path_value.strip()
        ):
            env["DATIVO_SUMMARY_PATH"] = summary_path_value
    except Exception as e:
        # If we can't read the payload, log but don't fail
        logger.warning(
            f"Failed to read payload for DATIVO_SUMMARY_PATH: {e}",
            extra={"event_type": "notification_hook_payload_read_warning"},
        )

    # Log execution start (with redacted command and env)
    redacted_command = _redact_command_args(expanded_command)
    redacted_user_env = _redact_env_for_logging(user_env or {})
    logger.info(
        f"Executing notification hook: {hook_name}",
        extra={
            "event_type": "notification_hook_started",
            "hook_name": hook_name,
            "command": redacted_command,
            "timeout_seconds": timeout_seconds,
            "user_env": redacted_user_env,
        },
    )

    try:
        # Execute command with timeout
        result = subprocess.run(
            expanded_command,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

        if result.returncode == 0:
            logger.info(
                "Notification hook executed successfully",
                extra={
                    "event_type": "notification_hook_success",
                    "hook_name": hook_name,
                },
            )
            return True, None
        else:
            # Non-zero exit - log warning but don't fail
            stderr_snippet = result.stderr[:500] if result.stderr else "(no stderr)"
            # Redact potential secrets in stderr
            for pattern in SECRET_PATTERNS:
                stderr_snippet = pattern.sub("[REDACTED]", stderr_snippet)

            error_msg = f"Hook exited with code {result.returncode}"
            logger.warning(
                error_msg,
                extra={
                    "event_type": "notification_hook_failed",
                    "hook_name": hook_name,
                    "exit_code": result.returncode,
                    "stderr_snippet": stderr_snippet,
                },
            )
            return False, f"{error_msg}: {stderr_snippet}"

    except subprocess.TimeoutExpired:
        error_msg = f"Hook timed out after {timeout_seconds}s"
        logger.warning(
            error_msg,
            extra={
                "event_type": "notification_hook_timeout",
                "hook_name": hook_name,
                "timeout_seconds": timeout_seconds,
            },
        )
        return False, error_msg

    except Exception as e:
        error_msg = f"Hook execution error: {type(e).__name__}: {str(e)}"
        logger.error(
            error_msg,
            extra={
                "event_type": "notification_hook_error",
                "error_type": type(e).__name__,
                "hook_name": hook_name,
            },
        )
        return False, error_msg


def execute_failure_notification(
    config: "NotificationsConfig",
    tenant_id: str,
    job_name: str,
    config_path: str,
    exit_code: int,
    failure_reason: str,
    summary_path: Optional[str] = None,
) -> bool:
    """Execute failure notification hook if configured.

    This is the main entry point for triggering notification hooks.
    Hooks execute only when exit_code is 2 (hard failure).

    Args:
        config: NotificationsConfig from runner config
        tenant_id: Tenant identifier
        job_name: Job/schedule name
        config_path: Path to job configuration file
        exit_code: Job exit code (must be 2 to trigger hooks)
        failure_reason: Human-readable failure reason
        summary_path: Optional path to run summary file

    Returns:
        True if hook executed successfully or not configured, False on hook error
    """
    logger = get_logger()

    # Check if notifications are configured
    if not config or not config.on_failure:
        return True  # Not an error - just not configured

    # Only execute on exit_code 2 (hard failure)
    if exit_code != 2:
        return True

    on_failure = config.on_failure

    # Create hook payload file
    payload_path = None
    try:
        payload_path = _create_hook_payload(
            tenant_id=tenant_id,
            job_name=job_name,
            config_path=config_path,
            exit_code=exit_code,
            failure_reason=failure_reason,
            summary_path=summary_path,
        )

        # Execute hook
        success, error = _execute_hook(
            command=on_failure.command,
            payload_path=payload_path,
            user_env=on_failure.env,
            timeout_seconds=on_failure.timeout_seconds,
            hook_name="on_failure",
        )

        return success

    except Exception as e:
        logger.error(
            f"Failed to execute notification hook: {e}",
            extra={
                "event_type": "notification_hook_error",
                "error": str(e),
                "tenant_id": tenant_id,
                "job_name": job_name,
            },
        )
        return False

    finally:
        # Clean up payload file
        if payload_path and payload_path.exists():
            try:
                payload_path.unlink()
            except Exception:
                pass  # Best effort cleanup
