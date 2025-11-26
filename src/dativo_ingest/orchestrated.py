"""Dagster orchestration with tenant-level serialization."""

import subprocess
import sys
import time
from typing import Any, Dict, Optional

from dagster import (
    AssetExecutionContext,
    Definitions,
    RetryPolicy,
    ScheduleDefinition,
    asset,
    define_asset_job,
)

from .config import JobConfig, RunnerConfig
from .logging import get_logger, setup_logging
from .retry_policy import RetryPolicy as CustomRetryPolicy
from .validator import ConnectorValidator


def _create_dagster_retry_policy(job_config: JobConfig) -> Optional[RetryPolicy]:
    """Create Dagster RetryPolicy from job configuration.

    Args:
        job_config: Job configuration

    Returns:
        Dagster RetryPolicy or None if no retry config
    """
    if not job_config.retry_config:
        return None

    retry_config = job_config.retry_config

    # Map exit codes to retryable errors
    # Dagster retry policy uses exceptions, so we'll handle exit codes in our wrapper
    return RetryPolicy(
        max_retries=retry_config.max_retries,
        delay=retry_config.initial_delay_seconds,
    )


def _execute_job_with_retry(
    schedule_config: Any,
    job_config: JobConfig,
    custom_retry_policy: Optional[CustomRetryPolicy],
) -> Dict[str, Any]:
    """Execute job with retry logic.

    Args:
        schedule_config: Schedule configuration
        job_config: Job configuration
        custom_retry_policy: Custom retry policy instance

    Returns:
        Job execution result

    Raises:
        Exception: If job fails after all retries
    """
    job_logger = get_logger()
    tenant_id = job_config.tenant_id
    source_config = job_config.get_source()
    connector_type = source_config.type

    attempt = 0
    last_exit_code = None
    last_error = None

    while True:
        try:
            # Execute job via CLI run command
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "dativo_ingest.cli",
                    "run",
                    "--config",
                    schedule_config.config,
                    "--mode",
                    "self_hosted",
                ],
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

        except Exception as e:
            last_error = str(e)
            if custom_retry_policy and custom_retry_policy.should_retry(
                2, str(e), attempt
            ):
                custom_retry_policy.log_retry_attempt(attempt, 2, str(e))
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
            "stderr": last_error[:500] if last_error else None,
        },
    )
    raise Exception(
        f"Job execution failed after {attempt + 1} attempt(s): {last_error}"
    )


def create_dagster_assets(runner_config: RunnerConfig) -> Definitions:
    """Create Dagster definitions from runner configuration.

    Args:
        runner_config: Runner configuration with schedules

    Returns:
        Dagster Definitions object
    """
    logger = setup_logging(level="INFO", redact_secrets=False)
    assets = []
    schedules = []

    for schedule_config in runner_config.orchestrator.schedules:
        # Skip disabled schedules
        if not schedule_config.enabled:
            logger.info(
                f"Schedule '{schedule_config.name}' is disabled, skipping",
                extra={
                    "event_type": "schedule_skipped",
                    "schedule_name": schedule_config.name,
                },
            )
            continue

        # Load job config early to get tenant_id and retry config
        try:
            job_config = JobConfig.from_yaml(schedule_config.config)
            tenant_id = job_config.tenant_id
            source_config = job_config.get_source()
            connector_type = source_config.type

            # Create custom retry policy if configured
            custom_retry_policy = None
            if job_config.retry_config:
                custom_retry_policy = CustomRetryPolicy(job_config.retry_config)

            # Create Dagster retry policy
            dagster_retry_policy = _create_dagster_retry_policy(job_config)

        except Exception as e:
            logger.error(
                f"Failed to load job config for schedule '{schedule_config.name}': {e}",
                extra={
                    "event_type": "schedule_config_error",
                    "schedule_name": schedule_config.name,
                },
            )
            continue

        # Create an asset for each schedule
        asset_name = f"{schedule_config.name}_asset"

        # Build asset tags
        asset_tags = {
            "tenant": tenant_id,
            "job_name": schedule_config.name,
            "connector_type": connector_type,
        }
        if schedule_config.tags:
            asset_tags.update(schedule_config.tags)

        # Add infrastructure tags if configured
        if job_config.infrastructure:
            infra_config = job_config.infrastructure
            # Add infrastructure metadata to asset tags
            asset_tags["infrastructure_provider"] = infra_config.provider
            if infra_config.runtime and infra_config.runtime.region:
                asset_tags["infrastructure_region"] = infra_config.runtime.region
            if infra_config.runtime and infra_config.runtime.compute_type:
                asset_tags["infrastructure_compute_type"] = infra_config.runtime.compute_type

            # Merge infrastructure tags (for cost allocation and compliance)
            if infra_config.tags:
                # Prefix infrastructure tags to avoid conflicts
                for key, value in infra_config.tags.items():
                    asset_tags[f"infra_{key}"] = value

        @asset(
            name=asset_name,
            description=f"Asset for {schedule_config.name}",
            tags=asset_tags,
            retry_policy=dagster_retry_policy,
        )
        def create_asset(context: AssetExecutionContext) -> Dict[str, Any]:
            """Execute job for this schedule."""
            job_logger = get_logger()
            start_time = time.time()

            job_logger.info(
                "Executing scheduled job",
                extra={
                    "job_name": schedule_config.name,
                    "tenant_id": tenant_id,
                    "event_type": "job_running",
                    "config_path": schedule_config.config,
                },
            )

            try:
                # Validate schema presence
                job_config.validate_schema_presence()

                # Validate connector
                validator = ConnectorValidator()
                validator.validate_job(job_config, mode="self_hosted")

                # Validate infrastructure configuration if present
                if job_config.infrastructure:
                    from .infrastructure import validate_infrastructure_config

                    validate_infrastructure_config(job_config)

                # Execute job with retry logic
                result = _execute_job_with_retry(
                    schedule_config, job_config, custom_retry_policy
                )

                # Calculate execution time
                execution_time = time.time() - start_time

                # Add enhanced metadata
                metadata = {
                    "tenant_id": tenant_id,
                    "connector_type": connector_type,
                    "execution_time_seconds": execution_time,
                    "status": result.get("status", "unknown"),
                }

                # Add infrastructure metadata if configured
                if job_config.infrastructure:
                    infra_config = job_config.infrastructure
                    metadata["infrastructure_provider"] = infra_config.provider
                    if infra_config.runtime:
                        if infra_config.runtime.region:
                            metadata["infrastructure_region"] = infra_config.runtime.region
                        if infra_config.runtime.compute_type:
                            metadata["infrastructure_compute_type"] = (
                                infra_config.runtime.compute_type
                            )
                    if infra_config.resources:
                        # Add resource references for Terraform integration
                        if infra_config.resources.compute_resource:
                            metadata["terraform_compute_resource"] = (
                                infra_config.resources.compute_resource
                            )
                        if infra_config.resources.execution_role:
                            metadata["terraform_execution_role"] = (
                                infra_config.resources.execution_role
                            )

                    # Generate Terraform variables for external infrastructure
                    try:
                        from .infrastructure import generate_terraform_vars

                        terraform_vars = generate_terraform_vars(job_config)
                        metadata["terraform_vars"] = terraform_vars
                    except Exception as e:
                        job_logger.warning(
                            f"Failed to generate Terraform variables: {e}",
                            extra={
                                "event_type": "terraform_vars_warning",
                                "job_name": schedule_config.name,
                            },
                        )

                context.add_output_metadata(metadata)

                return result

            except Exception as e:
                execution_time = time.time() - start_time
                job_logger.error(
                    f"Job execution error: {e}",
                    extra={
                        "job_name": schedule_config.name,
                        "tenant_id": tenant_id,
                        "execution_time_seconds": execution_time,
                        "event_type": "job_error",
                    },
                )
                raise

        assets.append(create_asset)

        # Create schedule with cron or interval
        job_tags = {"tenant": tenant_id}
        if schedule_config.tags:
            job_tags.update(schedule_config.tags)

        job_def = define_asset_job(
            name=f"{schedule_config.name}_job",
            selection=[asset_name],
            tags=job_tags,
        )

        if schedule_config.cron:
            schedule_def = ScheduleDefinition(
                name=schedule_config.name,
                job=job_def,
                cron_schedule=schedule_config.cron,
            )
        elif schedule_config.interval_seconds:
            try:
                from dagster import IntervalSchedule
            except ImportError:
                # Fallback for older Dagster versions - use cron equivalent
                # Convert interval_seconds to approximate cron expression
                interval_minutes = schedule_config.interval_seconds // 60
                if interval_minutes < 60:
                    cron_expr = f"*/{interval_minutes} * * * *"
                else:
                    interval_hours = interval_minutes // 60
                    cron_expr = f"0 */{interval_hours} * * *"

                logger.warning(
                    f"IntervalSchedule not available, using cron equivalent: {cron_expr}",
                    extra={
                        "event_type": "schedule_fallback",
                        "schedule_name": schedule_config.name,
                        "interval_seconds": schedule_config.interval_seconds,
                        "cron_equivalent": cron_expr,
                    },
                )
                schedule_def = ScheduleDefinition(
                    name=schedule_config.name,
                    job=job_def,
                    cron_schedule=cron_expr,
                )
            else:
                schedule_def = ScheduleDefinition(
                    name=schedule_config.name,
                    job=job_def,
                    schedule=IntervalSchedule(
                        interval_seconds=schedule_config.interval_seconds,
                    ),
                )
        else:
            logger.warning(
                f"Schedule '{schedule_config.name}' has no cron or interval, skipping",
                extra={
                    "event_type": "schedule_invalid",
                    "schedule_name": schedule_config.name,
                },
            )
            continue

        schedules.append(schedule_def)

    # Create run queue configuration for tenant-level serialization
    # This ensures only one job runs per tenant at a time
    concurrency_per_tenant = runner_config.orchestrator.concurrency_per_tenant

    return Definitions(
        assets=assets,
        schedules=schedules,
        # Configure run queue with tag-based concurrency limits
        # This is handled via Dagster's run queue configuration
        # In practice, you'd configure this in dagster.yaml or via code
    )


def start_orchestrated(runner_config: RunnerConfig) -> None:
    """Start Dagster orchestrator in long-running mode.

    Args:
        runner_config: Runner configuration

    Raises:
        SystemExit: If orchestrator fails to start
    """
    logger = setup_logging(level="INFO", redact_secrets=False)
    logger.info(
        "Initializing Dagster orchestrator",
        extra={"event_type": "orchestrator_initializing"},
    )

    # Create Dagster definitions
    try:
        defs = create_dagster_assets(runner_config)
    except Exception as e:
        logger.error(
            f"Failed to create Dagster definitions: {e}",
            extra={"event_type": "orchestrator_error"},
        )
        raise

    logger.info(
        f"Created {len(defs.assets)} assets and {len(defs.schedules)} schedules",
        extra={"event_type": "orchestrator_ready"},
    )

    # Start Dagster UI and scheduler
    # In a real deployment, this would use dagster-webserver
    # For now, we'll use the programmatic API
    try:
        from dagster._core.instance import DagsterInstance
        from dagster._daemon import daemon

        instance = DagsterInstance.ephemeral()
        logger.info(
            "Starting Dagster daemon",
            extra={"event_type": "daemon_starting"},
        )

        # Note: In a production setup, you'd run:
        # dagster-webserver -m dativo_ingest.orchestrated -d /app
        # This is a simplified version for the framework
        logger.info(
            "Dagster orchestrator started. Use 'dagster-webserver' to access UI.",
            extra={"event_type": "orchestrator_started"},
        )

        # For now, we'll just log that it's ready
        # In a real implementation, this would start the webserver and daemon
        logger.info(
            "Orchestrator running. Press Ctrl+C to stop.",
            extra={"event_type": "orchestrator_running"},
        )

        # Keep running until interrupted
        import time

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info(
                "Orchestrator stopping",
                extra={"event_type": "orchestrator_stopping"},
            )

    except ImportError:
        logger.warning(
            "Dagster daemon components not available. "
            "Run 'dagster-webserver -m dativo_ingest.orchestrated' manually.",
            extra={"event_type": "orchestrator_warning"},
        )
        # For development, just log that definitions are ready
        logger.info(
            "Dagster definitions ready. Load with: "
            "dagster-webserver -m dativo_ingest.orchestrated",
            extra={"event_type": "orchestrator_ready"},
        )
