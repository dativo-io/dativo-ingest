"""Command-line interface for Dativo ingestion runner."""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

from .config import JobConfig, RunnerConfig
from .infrastructure import validate_infrastructure
from .logging import get_logger, setup_logging
from .secrets import load_secrets
from .validator import ConnectorValidator, IncrementalStateManager


def initialize_state_directory(job_config: JobConfig) -> None:
    """Initialize state directory for incremental sync tracking.

    Args:
        job_config: Job configuration
    """
    source_config = job_config.get_source()
    if source_config.incremental:
        state_path_str = source_config.incremental.get("state_path", "")
        if state_path_str:
            state_path = Path(state_path_str)
            # Create parent directories if they don't exist
            state_path.parent.mkdir(parents=True, exist_ok=True)
            # Validate directory is writable
            if not os.access(state_path.parent, os.W_OK):
                raise PermissionError(f"State directory is not writable: {state_path.parent}")


def startup_sequence(
    job_dir: Path,
    secrets_dir: Path,
    tenant_id: Optional[str] = None,
    mode: str = "self_hosted",
) -> List[JobConfig]:
    """Complete startup sequence for E2E smoke tests.

    Args:
        job_dir: Directory containing job YAML files
        secrets_dir: Directory containing secrets
        tenant_id: Optional tenant identifier (if not provided, inferred from jobs)
        mode: Execution mode (default: self_hosted)

    Returns:
        List of validated job configurations

    Raises:
        ValueError: If startup sequence fails
    """
    # 1. Load jobs from directory first to infer tenant_id
    try:
        jobs = JobConfig.load_jobs_from_directory(job_dir)
        if not jobs:
            raise ValueError(f"No valid jobs found in {job_dir}")
    except ValueError as e:
        # Set up basic logging even if jobs fail to load
        logger = setup_logging(level="INFO", redact_secrets=True)
        logger.error(
            f"Failed to load jobs: {e}",
            extra={"event_type": "jobs_load_error"},
        )
        raise

    # 2. Infer tenant_id from jobs if not provided
    if tenant_id is None:
        # All jobs should have the same tenant_id
        tenant_ids = {job.tenant_id for job in jobs}
        if len(tenant_ids) > 1:
            raise ValueError(
                f"Jobs have conflicting tenant_ids: {tenant_ids}. "
                "All jobs in a directory must belong to the same tenant, or specify --tenant-id to override."
            )
        tenant_id = jobs[0].tenant_id
        logger = setup_logging(level="INFO", redact_secrets=True, tenant_id=tenant_id)
        logger.info(
            f"Inferred tenant_id '{tenant_id}' from job configurations",
            extra={"event_type": "tenant_inferred", "tenant_id": tenant_id},
        )
    else:
        # Validate that all jobs match the provided tenant_id
        mismatched = [job for job in jobs if job.tenant_id != tenant_id]
        if mismatched:
            raise ValueError(
                f"Tenant ID mismatch: {len(mismatched)} job(s) have tenant_id different from '{tenant_id}'. "
                f"Conflicting tenant_ids: {set(job.tenant_id for job in mismatched)}"
            )
        logger = setup_logging(level="INFO", redact_secrets=True, tenant_id=tenant_id)
        logger.info(
            f"Using tenant_id '{tenant_id}' from command line",
            extra={"event_type": "tenant_override", "tenant_id": tenant_id},
        )

    logger.info(
        f"Starting E2E smoke test startup sequence for tenant '{tenant_id}'",
        extra={"event_type": "startup_begin", "tenant_id": tenant_id, "job_count": len(jobs)},
    )

    # 3. Load secrets using inferred/validated tenant_id
    try:
        secrets = load_secrets(tenant_id, secrets_dir)
        logger.info(
            f"Secrets loaded for tenant {tenant_id}",
            extra={"event_type": "secrets_loaded", "tenant_id": tenant_id, "secret_count": len(secrets)},
        )
    except ValueError as e:
        logger.warning(
            f"Secrets loading failed (may be optional): {e}",
            extra={"event_type": "secrets_warning", "tenant_id": tenant_id},
        )

    # 4. Validate environment variables for all jobs
    for job in jobs:
        try:
            job.validate_environment_variables()
        except ValueError as e:
            logger.warning(
                f"Environment variable validation warning for job: {e}",
                extra={"event_type": "env_validation_warning", "tenant_id": job.tenant_id},
            )

    logger.info(
        "Environment variables validated",
        extra={"event_type": "env_validated", "tenant_id": tenant_id},
    )

    # 5. Validate infrastructure for all jobs
    for job in jobs:
        try:
            validate_infrastructure(job)
        except ValueError as e:
            logger.warning(
                f"Infrastructure validation warning for job: {e}",
                extra={"event_type": "infrastructure_warning", "tenant_id": job.tenant_id},
            )

    logger.info(
        "Infrastructure validated",
        extra={"event_type": "infra_validated", "tenant_id": tenant_id},
    )

    # 6. Initialize state management for all jobs
    for job in jobs:
        try:
            initialize_state_directory(job)
        except Exception as e:
            logger.warning(
                f"State directory initialization warning for job: {e}",
                extra={"event_type": "state_warning", "tenant_id": job.tenant_id},
            )

    logger.info(
        "State management initialized",
        extra={"event_type": "state_initialized", "tenant_id": tenant_id},
    )

    # 7. Validate all job configurations
    validator = ConnectorValidator()
    for job in jobs:
        try:
            job.validate_schema_presence()
            validator.validate_job(job, mode=mode)
        except (SystemExit, ValueError) as e:
            logger.error(
                f"Job validation failed: {e}",
                extra={"event_type": "job_validation_error", "tenant_id": job.tenant_id},
            )
            # Continue with other jobs

    logger.info(
        "Startup sequence completed",
        extra={"event_type": "startup_complete", "tenant_id": tenant_id, "job_count": len(jobs)},
    )

    return jobs


def run_command(args: argparse.Namespace) -> int:
    """Execute oneshot job run.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0=success, 1=partial, 2=failure)
    """
    # Check if running from directory or single file
    if args.job_dir:
        # Run startup sequence and execute all jobs
        try:
            jobs = startup_sequence(
                job_dir=Path(args.job_dir),
                secrets_dir=Path(args.secrets_dir),
                tenant_id=args.tenant_id,
                mode=args.mode,
            )
        except ValueError as e:
            print(f"ERROR: Startup sequence failed: {e}", file=sys.stderr)
            return 2

        # Execute all jobs sequentially
        results = []
        for job_config in jobs:
            result = _execute_single_job(job_config, args.mode)
            results.append(result)

        # Return 0 if all succeeded, 2 if any failed
        return 0 if all(r == 0 for r in results) else 2
    else:
        # Single job execution (original behavior)
        try:
            job_config = JobConfig.from_yaml(args.config)
        except SystemExit as e:
            return e.code if e.code else 2

        return _execute_single_job(job_config, args.mode)


def _execute_single_job(job_config: JobConfig, mode: str) -> int:
    """Execute a single job configuration.

    Args:
        job_config: Job configuration
        mode: Execution mode

    Returns:
        Exit code (0=success, 1=partial, 2=failure)
    """

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
        validator.validate_job(job_config, mode=mode)
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
    config_group = run_parser.add_mutually_exclusive_group(required=True)
    config_group.add_argument(
        "--config",
        help="Path to job configuration YAML file",
    )
    config_group.add_argument(
        "--job-dir",
        help="Path to directory containing job YAML files (mutually exclusive with --config)",
    )
    run_parser.add_argument(
        "--secrets-dir",
        default="/secrets",
        help="Path to secrets directory (default: /secrets, required with --job-dir)",
    )
    run_parser.add_argument(
        "--tenant-id",
        help="Tenant ID override (optional; if not provided, inferred from job configurations). "
        "If provided, validates all jobs belong to this tenant.",
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

