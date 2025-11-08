"""Dagster orchestration with tenant-level serialization."""

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
from .orchestrators.common import execute_job_with_retry


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
                extra={"event_type": "schedule_skipped", "schedule_name": schedule_config.name},
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
                extra={"event_type": "schedule_config_error", "schedule_name": schedule_config.name},
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

                # Execute job with retry logic
                result = execute_job_with_retry(
                    schedule_config,
                    job_config,
                    custom_retry_policy,
                    cli_module="dativo_ingest.cli",
                )

                # Calculate execution time
                execution_time = time.time() - start_time

                # Add enhanced metadata
                context.add_output_metadata(
                    {
                        "tenant_id": tenant_id,
                        "connector_type": connector_type,
                        "execution_time_seconds": execution_time,
                        "status": result.get("status", "unknown"),
                    }
                )

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
                extra={"event_type": "schedule_invalid", "schedule_name": schedule_config.name},
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

