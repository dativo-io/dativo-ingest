"""Shared orchestration helpers."""

from __future__ import annotations

import subprocess
import sys
from typing import Any, Dict, List, Optional

from dativo_ingest.logging import get_logger
from dativo_ingest.retry_policy import RetryPolicy as CustomRetryPolicy


def execute_job_with_retry(
    schedule_config: Any,
    job_config: Any,
    custom_retry_policy: Optional[CustomRetryPolicy],
    cli_module: str,
    extra_cli_args: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Execute a job via the CLI entrypoint with retry logic.

    Args:
        schedule_config: Schedule configuration object with metadata
        job_config: Loaded job configuration
        custom_retry_policy: Optional retry policy for exit codes/messages
        cli_module: Python module path for the CLI entrypoint
        extra_cli_args: Additional CLI arguments to append after mode

    Returns:
        Execution metadata dictionary

    Raises:
        Exception: If execution ultimately fails
    """
    job_logger = get_logger()
    tenant_id = getattr(job_config, "tenant_id", "unknown")
    source_config = job_config.get_source()
    connector_type = getattr(source_config, "type", "unknown")

    attempt = 0
    last_exit_code = None
    last_error = None

    while True:
        try:
            cli_args = [
                sys.executable,
                "-m",
                cli_module,
                "run",
                "--config",
                schedule_config.config,
                "--mode",
                "self_hosted",
            ]
            if extra_cli_args:
                cli_args.extend(extra_cli_args)

            result = subprocess.run(
                cli_args,
                capture_output=True,
                text=True,
            )

            last_exit_code = result.returncode

            if result.returncode == 0:
                job_logger.info(
                    "Job completed successfully",
                    extra={
                        "job_name": schedule_config.name,
                        "tenant_id": tenant_id,
                        "connector_type": connector_type,
                        "event_type": "job_finished",
                        "attempt": attempt + 1,
                    },
                )
                return {
                    "status": "success",
                    "job_name": schedule_config.name,
                    "tenant_id": tenant_id,
                    "attempt": attempt + 1,
                }

            # Check if we should retry
            if custom_retry_policy and custom_retry_policy.should_retry(
                result.returncode, result.stderr, attempt
            ):
                custom_retry_policy.log_retry_attempt(
                    attempt, result.returncode, result.stderr
                )
                custom_retry_policy.wait_for_retry(attempt)
                attempt += 1
                continue

            # No retry or retries exhausted
            last_error = result.stderr
            break

        except Exception as exc:  # pragma: no cover - defensive
            last_error = str(exc)
            if custom_retry_policy and custom_retry_policy.should_retry(
                2, str(exc), attempt
            ):
                custom_retry_policy.log_retry_attempt(attempt, 2, str(exc))
                custom_retry_policy.wait_for_retry(attempt)
                attempt += 1
                continue
            raise

    # All retries exhausted or non-retryable error
    job_logger.error(
        f"Job failed after {attempt + 1} attempt(s)",
        extra={
            "job_name": schedule_config.name,
            "tenant_id": tenant_id,
            "connector_type": connector_type,
            "event_type": "job_error",
            "exit_code": last_exit_code,
            "attempts": attempt + 1,
            "stderr": last_error[:500] if isinstance(last_error, str) else last_error,
        },
    )
    raise Exception(
        f"Job execution failed after {attempt + 1} attempt(s): {last_error}"
    )
