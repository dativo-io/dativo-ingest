"""Notification hooks for job failure events.

Supports executing external commands (shell scripts, binaries) when a job
fails, enabling integration with Slack, PagerDuty, email, or any custom
alerting system.

Environment variables injected into hook processes:
    DATIVO_TENANT_ID      - Tenant identifier
    DATIVO_JOB_NAME       - Job/asset name
    DATIVO_RUN_ID         - Unique run identifier
    DATIVO_RUN_STATUS     - Run status (failure, partial, success)
    DATIVO_EXIT_CODE      - Numeric exit code (0, 1, 2)
    DATIVO_SUMMARY_PATH   - Path to the run summary JSON file (if available)
    DATIVO_ERROR_MESSAGE  - Short error description (if available)
    DATIVO_ENVIRONMENT    - Environment name (dev, staging, prod)
"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class NotificationHookError(Exception):
    """Raised when a notification hook fails to execute."""

    pass


class NotificationHook:
    """Executes notification commands on job lifecycle events.

    Designed to fail gracefully: hook failures are logged but never
    cause the parent job to fail or change its exit code.
    """

    # Timeout for hook execution (seconds)
    DEFAULT_TIMEOUT_SECONDS = 30

    def __init__(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ):
        """Initialize notification hook.

        Args:
            command: Command and arguments to execute (e.g. ["/app/scripts/notify.sh"])
            env: Additional environment variables to pass to the command.
                 Values may contain ${VAR} references that will be expanded
                 from the current process environment.
            timeout_seconds: Maximum time to wait for hook to complete.
        """
        if not command:
            raise ValueError("Notification hook command must not be empty")

        self.command = command
        self.env = env or {}
        self.timeout_seconds = timeout_seconds

    def _resolve_env(self, extra_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Build the environment for the hook subprocess.

        Starts with the current process environment, layers in user-configured
        env vars (with ${VAR} expansion), then adds the Dativo-specific vars
        provided by the caller.

        Args:
            extra_env: Dativo runtime env vars (DATIVO_TENANT_ID, etc.)

        Returns:
            Merged environment dictionary.
        """
        # Start with current process env
        resolved = dict(os.environ)

        # Apply user-configured env vars with expansion
        for key, value in self.env.items():
            resolved[key] = os.path.expandvars(value)

        # Apply Dativo runtime vars (these take precedence)
        if extra_env:
            resolved.update(extra_env)

        return resolved

    def execute(
        self,
        tenant_id: str,
        job_name: str,
        run_id: str,
        exit_code: int,
        summary_path: Optional[str] = None,
        error_message: Optional[str] = None,
        environment: Optional[str] = None,
    ) -> bool:
        """Execute the notification hook command.

        Args:
            tenant_id: Tenant identifier.
            job_name: Job/asset name.
            run_id: Unique run identifier.
            exit_code: Job exit code (0=success, 1=partial, 2=failure).
            summary_path: Path to run summary JSON file, if written.
            error_message: Short error description.
            environment: Environment name (dev, staging, prod).

        Returns:
            True if the hook executed successfully (exit code 0), False otherwise.
        """
        status_map = {0: "success", 1: "partial", 2: "failure"}
        run_status = status_map.get(exit_code, "failure")

        # Build Dativo runtime env vars
        dativo_env: Dict[str, str] = {
            "DATIVO_TENANT_ID": tenant_id,
            "DATIVO_JOB_NAME": job_name,
            "DATIVO_RUN_ID": run_id,
            "DATIVO_RUN_STATUS": run_status,
            "DATIVO_EXIT_CODE": str(exit_code),
            "DATIVO_SUMMARY_PATH": summary_path or "",
            "DATIVO_ERROR_MESSAGE": error_message or "",
            "DATIVO_ENVIRONMENT": environment or "",
        }

        hook_env = self._resolve_env(dativo_env)

        logger.info(
            "Executing notification hook",
            extra={
                "event_type": "notification_hook_started",
                "command": self.command,
                "tenant_id": tenant_id,
                "job_name": job_name,
                "run_status": run_status,
            },
        )

        try:
            # Validate that the command exists before execution
            cmd_path = Path(self.command[0])
            if not cmd_path.is_absolute():
                # Relative path or bare command -- let subprocess handle PATH lookup
                pass
            elif not cmd_path.exists():
                logger.warning(
                    f"Notification hook script not found: {self.command[0]}. "
                    "Skipping notification. Check that the script path is correct "
                    "and the file exists.",
                    extra={
                        "event_type": "notification_hook_missing",
                        "command": self.command,
                    },
                )
                return False

            result = subprocess.run(
                self.command,
                env=hook_env,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )

            if result.returncode == 0:
                logger.info(
                    "Notification hook completed successfully",
                    extra={
                        "event_type": "notification_hook_success",
                        "command": self.command,
                        "stdout_preview": (result.stdout[:200] if result.stdout else ""),
                    },
                )
                return True
            else:
                logger.warning(
                    f"Notification hook exited with code {result.returncode}",
                    extra={
                        "event_type": "notification_hook_failed",
                        "command": self.command,
                        "exit_code": result.returncode,
                        "stderr_preview": (result.stderr[:500] if result.stderr else ""),
                    },
                )
                return False

        except FileNotFoundError:
            logger.warning(
                f"Notification hook command not found: {self.command[0]}. "
                "Skipping notification. Ensure the script exists and is executable.",
                extra={
                    "event_type": "notification_hook_not_found",
                    "command": self.command,
                },
            )
            return False

        except subprocess.TimeoutExpired:
            logger.warning(
                f"Notification hook timed out after {self.timeout_seconds}s",
                extra={
                    "event_type": "notification_hook_timeout",
                    "command": self.command,
                    "timeout_seconds": self.timeout_seconds,
                },
            )
            return False

        except PermissionError:
            logger.warning(
                f"Notification hook permission denied: {self.command[0]}. "
                "Ensure the script has execute permissions (chmod +x).",
                extra={
                    "event_type": "notification_hook_permission_error",
                    "command": self.command,
                },
            )
            return False

        except Exception as e:
            logger.warning(
                f"Notification hook failed unexpectedly: {e}",
                extra={
                    "event_type": "notification_hook_error",
                    "command": self.command,
                    "error": str(e),
                },
            )
            return False


class NotificationManager:
    """Manages notification hooks for job lifecycle events.

    Reads notification configuration and dispatches hooks when appropriate
    events occur (currently: on_failure).
    """

    def __init__(
        self,
        on_failure_hooks: Optional[List[NotificationHook]] = None,
    ):
        """Initialize notification manager.

        Args:
            on_failure_hooks: Hooks to execute when a job fails.
        """
        self.on_failure_hooks = on_failure_hooks or []

    @classmethod
    def from_config(cls, notifications_config: Optional[Dict[str, Any]]) -> "NotificationManager":
        """Create a NotificationManager from a notifications config dict.

        Expected structure:
            notifications:
              on_failure:
                command: ["/app/scripts/notify.sh"]
                timeout_seconds: 30      # optional
                env:
                  SLACK_WEBHOOK_URL: ${SLACK_WEBHOOK_URL}

        Args:
            notifications_config: The 'notifications' section from runner.yaml
                or job config. May be None if notifications are not configured.

        Returns:
            NotificationManager instance (with empty hooks if config is None).
        """
        if not notifications_config:
            return cls()

        on_failure_hooks: List[NotificationHook] = []

        on_failure_config = notifications_config.get("on_failure")
        if on_failure_config:
            # Support a single hook or a list of hooks
            hook_configs = (
                on_failure_config
                if isinstance(on_failure_config, list)
                else [on_failure_config]
            )

            for hook_cfg in hook_configs:
                command = hook_cfg.get("command")
                if not command:
                    logger.warning(
                        "Notification on_failure hook missing 'command' field, skipping",
                        extra={"event_type": "notification_config_warning"},
                    )
                    continue

                # Ensure command is a list
                if isinstance(command, str):
                    command = [command]

                env = hook_cfg.get("env", {})
                timeout = hook_cfg.get("timeout_seconds", NotificationHook.DEFAULT_TIMEOUT_SECONDS)

                on_failure_hooks.append(
                    NotificationHook(command=command, env=env, timeout_seconds=timeout)
                )

        return cls(on_failure_hooks=on_failure_hooks)

    def notify_failure(
        self,
        tenant_id: str,
        job_name: str,
        run_id: str,
        exit_code: int,
        summary_path: Optional[str] = None,
        error_message: Optional[str] = None,
        environment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute all on_failure hooks.

        Hook failures are logged but never propagated -- the job's exit code
        is never changed by a notification failure.

        Args:
            tenant_id: Tenant identifier.
            job_name: Job/asset name.
            run_id: Unique run identifier.
            exit_code: Job exit code.
            summary_path: Path to run summary JSON, if available.
            error_message: Short error description.
            environment: Environment name.

        Returns:
            Dict with execution results:
                hooks_executed: number of hooks attempted
                hooks_succeeded: number of hooks that returned True
                hooks_failed: number of hooks that returned False
        """
        if not self.on_failure_hooks:
            return {"hooks_executed": 0, "hooks_succeeded": 0, "hooks_failed": 0}

        logger.info(
            f"Triggering {len(self.on_failure_hooks)} on_failure notification hook(s)",
            extra={
                "event_type": "notification_hooks_triggered",
                "hook_count": len(self.on_failure_hooks),
                "tenant_id": tenant_id,
                "job_name": job_name,
            },
        )

        succeeded = 0
        failed = 0

        for hook in self.on_failure_hooks:
            result = hook.execute(
                tenant_id=tenant_id,
                job_name=job_name,
                run_id=run_id,
                exit_code=exit_code,
                summary_path=summary_path,
                error_message=error_message,
                environment=environment,
            )
            if result:
                succeeded += 1
            else:
                failed += 1

        summary = {
            "hooks_executed": len(self.on_failure_hooks),
            "hooks_succeeded": succeeded,
            "hooks_failed": failed,
        }

        logger.info(
            f"Notification hooks completed: {succeeded} succeeded, {failed} failed",
            extra={
                "event_type": "notification_hooks_completed",
                **summary,
            },
        )

        return summary

    @property
    def has_failure_hooks(self) -> bool:
        """Return True if any on_failure hooks are configured."""
        return len(self.on_failure_hooks) > 0
