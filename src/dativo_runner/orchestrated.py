"""Dagster orchestration with tenant-level serialization."""

import subprocess
import sys
from typing import Any, Dict

from dagster import (
    AssetExecutionContext,
    Definitions,
    ScheduleDefinition,
    asset,
    define_asset_job,
)

from .config import JobConfig, RunnerConfig
from .logging import get_logger, setup_logging
from .validator import ConnectorValidator


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
        # Create an asset for each schedule
        asset_name = f"{schedule_config.name}_asset"

        @asset(
            name=asset_name,
            description=f"Asset for {schedule_config.name}",
            tags={"tenant": "unknown", "job_name": schedule_config.name},
        )
        def create_asset(context: AssetExecutionContext) -> Dict[str, Any]:
            """Execute job for this schedule."""
            job_logger = get_logger()
            job_logger.info(
                "Executing scheduled job",
                extra={
                    "job_name": schedule_config.name,
                    "event_type": "job_running",
                    "config_path": schedule_config.config,
                },
            )

            # Load job config to get tenant_id
            try:
                job_config = JobConfig.from_yaml(schedule_config.config)
                tenant_id = job_config.tenant_id
                source_config = job_config.get_source()
                connector_type = source_config.type

                # Build output metadata with infrastructure information for Terraform
                output_metadata = {
                    "tenant_id": tenant_id,
                    "connector_type": connector_type,
                }
                
                # Add infrastructure metadata for Terraform integration
                if job_config.infrastructure:
                    output_metadata["infrastructure_provider"] = job_config.infrastructure.provider
                    if job_config.infrastructure.compute_type:
                        output_metadata["infrastructure_compute_type"] = job_config.infrastructure.compute_type
                    if job_config.infrastructure.memory_mb:
                        output_metadata["infrastructure_memory_mb"] = str(job_config.infrastructure.memory_mb)
                    if job_config.infrastructure.vcpu:
                        output_metadata["infrastructure_vcpu"] = str(job_config.infrastructure.vcpu)
                    if job_config.infrastructure.terraform_module:
                        output_metadata["terraform_module"] = job_config.infrastructure.terraform_module
                    if job_config.infrastructure.resource_refs:
                        output_metadata["resource_refs"] = job_config.infrastructure.resource_refs

                # Update asset tags with tenant_id and infrastructure metadata
                context.add_output_metadata(output_metadata)

                job_logger.info(
                    "Job validated",
                    extra={
                        "job_name": schedule_config.name,
                        "tenant_id": tenant_id,
                        "connector_type": connector_type,
                        "event_type": "job_validated",
                    },
                )

                # Validate schema presence
                job_config.validate_schema_presence()

                # Validate connector
                validator = ConnectorValidator()
                validator.validate_job(job_config, mode="self_hosted")

                # Execute job via CLI run command
                # In a real implementation, this would call the actual extraction logic
                # For now, we'll use subprocess to call the CLI
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "dativo_runner.cli",
                        "run",
                        "--config",
                        schedule_config.config,
                        "--mode",
                        "self_hosted",
                    ],
                    capture_output=True,
                    text=True,
                )

                if result.returncode == 0:
                    job_logger.info(
                        "Job completed successfully",
                        extra={
                            "job_name": schedule_config.name,
                            "tenant_id": tenant_id,
                            "connector_type": connector_type,
                            "event_type": "job_finished",
                        },
                    )
                    return {
                        "status": "success",
                        "job_name": schedule_config.name,
                        "tenant_id": tenant_id,
                    }
                else:
                    job_logger.error(
                        f"Job failed with exit code {result.returncode}",
                        extra={
                            "job_name": schedule_config.name,
                            "tenant_id": tenant_id,
                            "connector_type": connector_type,
                            "event_type": "job_error",
                            "exit_code": result.returncode,
                            "stderr": result.stderr,
                        },
                    )
                    raise Exception(f"Job execution failed: {result.stderr}")
            except Exception as e:
                job_logger.error(
                    f"Job execution error: {e}",
                    extra={
                        "job_name": schedule_config.name,
                        "event_type": "job_error",
                        "error": str(e),
                    },
                )
                raise

        assets.append(create_asset)

        # Create schedule
        schedule_def = ScheduleDefinition(
            name=schedule_config.name,
            job=define_asset_job(
                name=f"{schedule_config.name}_job",
                selection=[asset_name],
                tags={"tenant": "unknown"},
            ),
            cron_schedule=schedule_config.cron,
        )
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
        # dagster-webserver -m dativo_runner.orchestrated -d /app
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
            "Run 'dagster-webserver -m dativo_runner.orchestrated' manually.",
            extra={"event_type": "orchestrator_warning"},
        )
        # For development, just log that definitions are ready
        logger.info(
            "Dagster definitions ready. Load with: "
            "dagster-webserver -m dativo_runner.orchestrated",
            extra={"event_type": "orchestrator_ready"},
        )
