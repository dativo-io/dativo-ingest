"""Command-line interface for Dativo ingestion runner."""

import argparse
import sys
from pathlib import Path

from .config import JobConfig, RunnerConfig
from .logging import get_logger, setup_logging
from .validator import ConnectorValidator, IncrementalStateManager


def run_command(args: argparse.Namespace) -> int:
    """Execute oneshot job run.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0=success, 1=partial, 2=failure)
    """
    # Load job configuration
    try:
        job_config = JobConfig.from_yaml(args.config)
    except SystemExit as e:
        return e.code if e.code else 2

    # Resolve source and target configs
    source_config = job_config.get_source()
    target_config = job_config.get_target()

    # Set up logging
    log_level = job_config.logging.level if job_config.logging else "INFO"
    redact = job_config.logging.redaction if job_config.logging else False
    logger = setup_logging(level=log_level, redact_secrets=redact, tenant_id=job_config.tenant_id)

    logger.info(
        "Starting job execution",
        extra={
            "connector_type": source_config.type,
            "tenant_id": job_config.tenant_id,
            "event_type": "job_started",
        },
    )

    # Validate schema presence
    try:
        job_config.validate_schema_presence()
        logger.info(
            "Schema validation passed",
            extra={
                "connector_type": source_config.type,
                "tenant_id": job_config.tenant_id,
                "event_type": "job_validated",
            },
        )
    except SystemExit as e:
        logger.error(
            "Schema validation failed",
            extra={
                "connector_type": source_config.type,
                "tenant_id": job_config.tenant_id,
                "event_type": "job_error",
            },
        )
        return e.code if e.code else 2

    # Validate connector and mode restrictions
    try:
        validator = ConnectorValidator()
        validator.validate_job(job_config, mode=args.mode)
        logger.info(
            "Connector validation passed",
            extra={
                "connector_type": source_config.type,
                "tenant_id": job_config.tenant_id,
                "event_type": "job_validated",
            },
        )
    except SystemExit as e:
        logger.error(
            "Connector validation failed",
            extra={
                "connector_type": source_config.type,
                "tenant_id": job_config.tenant_id,
                "event_type": "job_error",
            },
        )
        return e.code if e.code else 2

    # Handle incremental strategies for file/sheet sources
    if source_config.incremental:
        strategy = source_config.incremental.get("strategy")
        state_path = Path(source_config.incremental.get("state_path", ""))
        lookback_days = source_config.incremental.get("lookback_days", 0)

        if strategy == "file_modified_time" and source_config.files:
            # For file-based incremental, check if files need processing
            # In a real implementation, this would fetch modified times from API
            # For now, we'll just log that we're checking state
            logger.info(
                "Checking file incremental state",
                extra={
                    "connector_type": source_config.type,
                    "strategy": strategy,
                    "event_type": "incremental_check",
                },
            )
            # Note: Actual file modified time fetching would happen here
            # This is a placeholder for the incremental logic

        elif strategy == "spreadsheet_modified_time" and source_config.sheets:
            # For sheet-based incremental, check if sheets need processing
            logger.info(
                "Checking spreadsheet incremental state",
                extra={
                    "connector_type": source_config.type,
                    "strategy": strategy,
                    "event_type": "incremental_check",
                },
            )
            # Note: Actual spreadsheet modified time fetching would happen here

    # Execute job (placeholder - actual execution would happen here)
    logger.info(
        "Job execution completed",
        extra={
            "connector_type": source_config.type,
            "tenant_id": job_config.tenant_id,
            "event_type": "job_finished",
        },
    )

    return 0


def start_command(args: argparse.Namespace) -> int:
    """Start orchestrated mode with Dagster.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0=success, 2=failure)
    """
    # Import here to avoid dependency if not using orchestrated mode
    from .orchestrated import start_orchestrated

    # Load runner configuration
    try:
        runner_config = RunnerConfig.from_yaml(args.runner_config)
    except SystemExit as e:
        return e.code if e.code else 2

    # Set up logging
    logger = setup_logging(level="INFO", redact_secrets=False)
    logger.info(
        "Starting orchestrated mode",
        extra={"event_type": "orchestrator_starting"},
    )

    # Start orchestrated mode
    try:
        start_orchestrated(runner_config)
    except KeyboardInterrupt:
        logger.info("Orchestrator stopped by user")
        return 0
    except Exception as e:
        logger.error(
            f"Orchestrator failed: {e}",
            extra={"event_type": "orchestrator_error"},
        )
        return 2

    return 0


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Dativo ingestion runner - config-driven data ingestion engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run a single job
  dativo run --config /app/configs/jobs/stripe.yaml --mode self_hosted

  # Start orchestrated mode
  dativo start orchestrated --runner-config /app/configs/runner.yaml
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Run command
    run_parser = subparsers.add_parser(
        "run",
        help="Run a single job in oneshot mode",
        description="Execute a single ingestion job and exit. Validates configuration, "
        "schema presence, and connector restrictions before execution.",
    )
    run_parser.add_argument(
        "--config",
        required=True,
        help="Path to job configuration YAML file",
    )
    run_parser.add_argument(
        "--mode",
        choices=["self_hosted", "cloud"],
        default="self_hosted",
        help="Execution mode (default: self_hosted). Database connectors are only "
        "allowed in self_hosted mode.",
    )

    # Start command
    start_parser = subparsers.add_parser(
        "start",
        help="Start orchestrated mode with Dagster",
        description="Start the Dagster orchestrator in long-running mode. Reads schedules "
        "from runner.yaml and executes jobs according to cron expressions. "
        "Ensures tenant-level serialization to avoid conflicts.",
    )
    start_parser.add_argument(
        "mode",
        choices=["orchestrated"],
        help="Orchestration mode (currently only 'orchestrated' is supported)",
    )
    start_parser.add_argument(
        "--runner-config",
        default="/app/configs/runner.yaml",
        help="Path to runner configuration YAML file (default: /app/configs/runner.yaml)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 2

    if args.command == "run":
        return run_command(args)
    elif args.command == "start":
        return start_command(args)
    else:
        parser.print_help()
        return 2


if __name__ == "__main__":
    sys.exit(main())

