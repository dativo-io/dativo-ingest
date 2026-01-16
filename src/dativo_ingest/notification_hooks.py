"""Notification hooks for job execution outcomes."""

import json
import os
import re
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

from .config import NotificationHookConfig
from .logging import get_logger

_SECRET_PATTERNS = ["token", "key", "secret", "password", "credential", "auth"]


def _expand_env_vars(value: str) -> str:
    """Expand ${VAR} or ${VAR:-default} patterns."""

    def replace(m: re.Match) -> str:
        return os.getenv(m.group(1), m.group(2) or "")

    return re.sub(r"\$\{([^}:]+)(?::-([^}]*))?\}", replace, value)


def _redact_secrets_in_args(args: List[str]) -> List[str]:
    """Redact secret patterns in command arguments."""
    redacted = []
    for arg in args:
        if any(p in arg.lower() for p in _SECRET_PATTERNS):
            redacted.append(
                f"{arg.split('=')[0]}=[REDACTED]" if "=" in arg else "[REDACTED]"
            )
        else:
            redacted.append(arg)
    return redacted


def _redact_secrets_in_env(env: Dict[str, str]) -> Dict[str, str]:
    """Redact secret patterns in environment variables."""
    return {
        k: "[REDACTED]" if any(p in k.lower() for p in _SECRET_PATTERNS) else v
        for k, v in env.items()
    }


def execute_hook(
    hook: NotificationHookConfig,
    tenant_id: str,
    job_name: str,
    config_path: str,
    exit_code: int,
    failure_reason: Optional[str] = None,
    summary_path: Optional[str] = None,
) -> None:
    """Execute a notification hook script. Hook failures are logged but never raise exceptions."""
    logger = get_logger()

    if exit_code not in hook.trigger_on_exit_codes:
        return

    expanded_args = [_expand_env_vars(arg) for arg in hook.command]
    hook_env = os.environ.copy()
    if hook.env:
        hook_env.update({k: _expand_env_vars(v) for k, v in hook.env.items()})

    payload = {
        "tenant_id": tenant_id,
        "job_name": job_name,
        "config_path": config_path,
        "exit_code": exit_code,
        "failure_reason": failure_reason,
        "summary_path": summary_path,
    }

    payload_file = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            json.dump(payload, f)
            payload_file = f.name

        hook_env["DATIVO_HOOK_PAYLOAD"] = payload_file

        logger.info(
            f"Executing notification hook '{hook.name}'",
            extra={
                "event_type": "hook_executing",
                "hook_name": hook.name,
                "command": _redact_secrets_in_args(expanded_args),
                "timeout_seconds": hook.timeout_seconds,
            },
        )

        try:
            result = subprocess.run(
                expanded_args,
                env=hook_env,
                capture_output=True,
                text=True,
                timeout=hook.timeout_seconds,
            )

            if result.returncode == 0:
                logger.info(
                    f"Hook '{hook.name}' completed successfully",
                    extra={"event_type": "hook_success", "hook_name": hook.name},
                )
            else:
                logger.warning(
                    f"Hook '{hook.name}' failed with exit code {result.returncode}",
                    extra={
                        "event_type": "hook_failure",
                        "hook_name": hook.name,
                        "exit_code": result.returncode,
                        "stderr_tail": (result.stderr[-500:] if result.stderr else ""),
                    },
                )
        except subprocess.TimeoutExpired:
            logger.warning(
                f"Hook '{hook.name}' timed out after {hook.timeout_seconds} seconds",
                extra={"event_type": "hook_timeout", "hook_name": hook.name},
            )
        except Exception as e:
            logger.error(
                f"Hook '{hook.name}' execution error: {e}",
                extra={
                    "event_type": "hook_error",
                    "hook_name": hook.name,
                    "error": str(e),
                },
                exc_info=True,
            )
    finally:
        if payload_file and os.path.exists(payload_file):
            try:
                os.unlink(payload_file)
            except Exception:
                pass


def execute_notification_hooks(
    hooks: Optional[List[NotificationHookConfig]],
    tenant_id: str,
    job_name: str,
    config_path: str,
    exit_code: int,
    failure_reason: Optional[str] = None,
    summary_path: Optional[str] = None,
) -> None:
    """Execute all configured notification hooks. All failures are logged but never raise exceptions."""
    if not hooks:
        return

    logger = get_logger()
    for hook in hooks:
        try:
            execute_hook(
                hook,
                tenant_id,
                job_name,
                config_path,
                exit_code,
                failure_reason,
                summary_path,
            )
        except Exception as e:
            logger.error(
                f"Unexpected error executing hook '{hook.name}': {e}",
                extra={
                    "event_type": "hook_unexpected_error",
                    "hook_name": hook.name,
                    "error": str(e),
                },
                exc_info=True,
            )
