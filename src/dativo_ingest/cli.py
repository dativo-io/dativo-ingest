"""Command-line interface for Dativo ingestion runner."""

import argparse
import os
import sys
from pathlib import Path

from .cli_commands import (
    ConnectionChecker,
    DiscoveryService,
    format_check_output,
    format_discovery_output,
)
from .cli_connectors import (
    connectors_inspect_command,
    connectors_list_command,
    connectors_sync_command,
)
from .config import JobConfig, RunnerConfig, SourceConfig
from .job_executor import JobExecutor
from .logging import setup_logging
from .secrets import load_secret_manager_config, load_secrets_and_set_env
from .startup import startup_sequence
from .validator import ConnectorValidator


def run_command(args: argparse.Namespace) -> int:
    """Execute oneshot job run.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0=success, 1=partial, 2=failure)
    """
    try:
        manager_config = load_secret_manager_config(args.secret_manager_config)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    # Check if running from directory or single file
    if args.job_dir:
        # Run startup sequence and execute all jobs
        try:
            jobs = startup_sequence(
                job_dir=Path(args.job_dir),
                secrets_dir=Path(args.secrets_dir),
                tenant_id=args.tenant_id,
                mode=args.mode,
                secret_manager=args.secret_manager,
                secret_manager_config=manager_config,
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
            # SystemExit from JobConfig.from_yaml already prints error to stderr
            return e.code if e.code else 2
        except Exception as e:
            print(f"ERROR: Failed to load job configuration: {e}", file=sys.stderr)
            if hasattr(e, "__cause__") and e.__cause__:
                print(f"  Caused by: {e.__cause__}", file=sys.stderr)
            return 2

        # Set up logging for single job execution (no startup_sequence was called)
        log_level = job_config.logging.level if job_config.logging else "INFO"
        redact = job_config.logging.redaction if job_config.logging else False
        logger = setup_logging(
            level=log_level, redact_secrets=redact, tenant_id=job_config.tenant_id
        )

        # Load secrets for single job execution
        secrets = load_secrets_and_set_env(
            tenant_id=job_config.tenant_id,
            secrets_dir=Path(args.secrets_dir),
            manager_type=args.secret_manager,
            manager_config=manager_config,
        )
        if secrets:
            logger.info(
                f"Secrets loaded for tenant {job_config.tenant_id}",
                extra={"event_type": "secrets_loaded"},
            )
        else:
            logger.warning(
                "No secrets loaded (may be optional)",
                extra={"event_type": "secrets_warning"},
            )

        return _execute_single_job(job_config, args.mode)


def _execute_single_job(job_config: JobConfig, mode: str) -> int:
    """Execute a single job configuration.

    Args:
        job_config: Job configuration
        mode: Execution mode

    Returns:
        Exit code (0=success, 1=partial, 2=failure)
    """
    executor = JobExecutor(job_config, mode=mode)
    return executor.execute()


def check_command(args: argparse.Namespace) -> int:
    """Check connection to source/target systems.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0=success, 2=failure)
    """
    try:
        manager_config = load_secret_manager_config(args.secret_manager_config)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    # Load job configuration
    try:
        job_config = JobConfig.from_yaml(args.config)
    except SystemExit as e:
        return e.code if e.code else 2

    # Set up logging
    log_level = job_config.logging.level if job_config.logging else "INFO"
    redact = job_config.logging.redaction if job_config.logging else False
    logger = setup_logging(
        level=log_level, redact_secrets=redact, tenant_id=job_config.tenant_id
    )

    logger.info(
        "Starting connection check",
        extra={
            "event_type": "check_started",
            "job_config": args.config,
        },
    )

    # Load secrets
    secrets = load_secrets_and_set_env(
        tenant_id=job_config.tenant_id,
        secrets_dir=Path(args.secrets_dir),
        manager_type=args.secret_manager,
        manager_config=manager_config,
    )
    if secrets:
        logger.info(
            f"Secrets loaded for tenant {job_config.tenant_id}",
            extra={"event_type": "secrets_loaded"},
        )
    else:
        logger.warning(
            "No secrets loaded (may be optional)",
            extra={"event_type": "secrets_warning"},
        )

    # Validate configuration
    try:
        job_config.validate_schema_presence()
        validator = ConnectorValidator()
        validator.validate_job(job_config, mode=args.mode)
        logger.info(
            "Configuration validation passed",
            extra={"event_type": "config_validated"},
        )
    except (SystemExit, ValueError) as e:
        logger.error(
            f"Configuration validation failed: {e}",
            extra={"event_type": "config_validation_failed"},
        )
        return 2

    # Use ConnectionChecker to perform checks
    checker = ConnectionChecker(job_config, mode=args.mode, logger=logger)
    source_status = checker.check_source()
    target_status = checker.check_target()

    # Format and print output
    format_check_output(
        source_status, target_status, json_output=args.json, verbose=args.verbose
    )

    # Determine exit code
    source_ok = source_status.get("status") in ["success", "skipped"]
    target_ok = target_status.get("status") in ["success", "skipped"]

    if source_ok and target_ok:
        logger.info(
            "Connection check completed successfully",
            extra={"event_type": "check_complete", "status": "success"},
        )
        return 0
    else:
        logger.error(
            "Connection check failed",
            extra={
                "event_type": "check_failed",
                "source_status": source_status.get("status"),
                "target_status": target_status.get("status"),
            },
        )
        return 2


def discover_command(args: argparse.Namespace) -> int:
    """Discover available tables/streams from source connector.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0=success, 2=failure)
    """
    try:
        manager_config = load_secret_manager_config(args.secret_manager_config)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    # Load configuration
    source_config = None
    tenant_id = None
    job_config = None

    if args.config:
        # Load from job config
        try:
            job_config = JobConfig.from_yaml(args.config)
            source_config = job_config.get_source()
            tenant_id = job_config.tenant_id
        except SystemExit as e:
            return e.code if e.code else 2
    elif args.connector:
        # Create minimal source config from connector name
        # Check if it's a custom reader path
        if Path(args.connector).exists() and args.connector.endswith(".py"):
            source_config = SourceConfig(
                type="custom",
                custom_reader=args.connector,
                connection={},
            )
        else:
            # Built-in connector
            source_config = SourceConfig(
                type=args.connector,
                connection={},
            )
    else:
        print("ERROR: Either --connector or --config must be provided", file=sys.stderr)
        return 2

    # Set up logging
    logger = setup_logging(
        level="INFO", redact_secrets=True, tenant_id=tenant_id or "default"
    )

    logger.info(
        "Starting discovery",
        extra={
            "event_type": "discover_started",
            "connector": args.connector or args.config,
        },
    )

    # Load secrets if tenant_id is available
    if tenant_id:
        secrets = load_secrets_and_set_env(
            tenant_id=tenant_id,
            secrets_dir=Path(args.secrets_dir),
            manager_type=args.secret_manager,
            manager_config=manager_config,
        )
        if secrets:
            logger.info(
                f"Secrets loaded for tenant {tenant_id}",
                extra={"event_type": "secrets_loaded"},
            )
        else:
            logger.warning(
                "No secrets loaded (may be optional)",
                extra={"event_type": "secrets_warning"},
            )

    # Use DiscoveryService to perform discovery
    try:
        discovery_service = DiscoveryService(
            source_config=source_config,
            job_config=job_config,
            tenant_id=tenant_id,
            mode=args.mode,
            logger=logger,
        )
        discovery_result = discovery_service.discover()

        # Format and print output
        format_discovery_output(
            discovery_result, json_output=args.json, verbose=args.verbose
        )

        logger.info(
            "Discovery completed",
            extra={
                "event_type": "discover_complete",
                "stream_count": discovery_result.get("count", 0),
            },
        )

        return 0
    except Exception as e:
        logger.error(
            f"Discovery failed: {e}",
            extra={"event_type": "discover_error"},
            exc_info=True,
        )
        print(f"ERROR: Discovery failed: {e}", file=sys.stderr)
        return 2


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


def connectors_command(args: argparse.Namespace) -> int:
    """Manage connector registry and catalogs.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0=success, 2=failure)
    """
    if args.connectors_command == "list":
        return connectors_list_command(
            role=args.role,
            json_output=args.json,
            verbose=args.verbose,
        )
    elif args.connectors_command == "inspect":
        return connectors_inspect_command(
            name=args.name,
            engine=args.engine,
            json_output=args.json,
        )
    elif args.connectors_command == "sync":
        return connectors_sync_command(
            catalog_name=args.name,
            catalog_url=args.catalog_url,
            catalog_file=args.catalog_file,
            json_output=args.json,
            verbose=args.verbose,
        )
    else:
        return 2


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Dativo ingestion runner - config-driven data ingestion engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Ingest data from source to target (recommended)
  dativo ingest --config /app/configs/jobs/stripe.yaml --mode self_hosted

  # Legacy alias (backward compatibility)
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
        help="Path to secrets directory (default: /secrets, used by filesystem secret manager)",
    )
    run_parser.add_argument(
        "--tenant-id",
        help="Tenant ID override (optional; if not provided, inferred from job configurations). "
        "If provided, validates all jobs belong to this tenant.",
    )
    run_parser.add_argument(
        "--secret-manager",
        choices=["env", "filesystem", "vault", "aws", "gcp"],
        default=os.getenv("DATIVO_SECRET_MANAGER", "env"),
        help="Secret backend to use (default: env or DATIVO_SECRET_MANAGER env var).",
    )
    run_parser.add_argument(
        "--secret-manager-config",
        help="Path to YAML/JSON file or inline JSON blob with secret manager configuration. "
        "Falls back to DATIVO_SECRET_MANAGER_CONFIG when omitted.",
    )
    run_parser.add_argument(
        "--mode",
        choices=["self_hosted", "cloud"],
        default="self_hosted",
        help="Execution mode (default: self_hosted). Database connectors are only "
        "allowed in self_hosted mode.",
    )

    # Ingest command (primary, recommended)
    ingest_parser = subparsers.add_parser(
        "ingest",
        help="Ingest data from source to target (primary command, recommended)",
        description="Execute a single ingestion job and exit. This is the primary command. "
        "'run' is maintained as a backward-compatible alias. "
        "Validates configuration, schema presence, and connector restrictions before execution.",
    )
    ingest_config_group = ingest_parser.add_mutually_exclusive_group(required=True)
    ingest_config_group.add_argument(
        "--config",
        help="Path to job configuration YAML file",
    )
    ingest_config_group.add_argument(
        "--job-dir",
        help="Path to directory containing job YAML files (mutually exclusive with --config)",
    )
    ingest_parser.add_argument(
        "--secrets-dir",
        default="/secrets",
        help="Path to secrets directory (default: /secrets, used by filesystem secret manager)",
    )
    ingest_parser.add_argument(
        "--tenant-id",
        help="Tenant ID override (optional; if not provided, inferred from job configurations). "
        "If provided, validates all jobs belong to this tenant.",
    )
    ingest_parser.add_argument(
        "--secret-manager",
        choices=["env", "filesystem", "vault", "aws", "gcp"],
        default=os.getenv("DATIVO_SECRET_MANAGER", "env"),
        help="Secret backend to use (default: env or DATIVO_SECRET_MANAGER env var).",
    )
    ingest_parser.add_argument(
        "--secret-manager-config",
        help="Path to YAML/JSON file or inline JSON blob with secret manager configuration. "
        "Falls back to DATIVO_SECRET_MANAGER_CONFIG when omitted.",
    )
    ingest_parser.add_argument(
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

    # Check command
    check_parser = subparsers.add_parser(
        "check",
        help="Check connection to source/target systems",
        description="Validate connectivity and credentials for a job configuration "
        "without executing the full job. Useful for testing connections before "
        "running actual data extraction.",
    )
    check_parser.add_argument(
        "--config",
        required=True,
        help="Path to job configuration YAML file",
    )
    check_parser.add_argument(
        "--mode",
        choices=["self_hosted", "cloud"],
        default="self_hosted",
        help="Execution mode (default: self_hosted)",
    )
    check_parser.add_argument(
        "--secret-manager",
        choices=["env", "filesystem", "vault", "aws", "gcp"],
        default=os.getenv("DATIVO_SECRET_MANAGER", "env"),
        help="Secret backend to use (default: env or DATIVO_SECRET_MANAGER env var).",
    )
    check_parser.add_argument(
        "--secret-manager-config",
        help="Path to YAML/JSON file or inline JSON blob with secret manager configuration. "
        "Falls back to DATIVO_SECRET_MANAGER_CONFIG when omitted.",
    )
    check_parser.add_argument(
        "--secrets-dir",
        default="/secrets",
        help="Path to secrets directory (default: /secrets, used by filesystem secret manager)",
    )
    check_parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format",
    )
    check_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output with additional details",
    )

    # Discover command
    discover_parser = subparsers.add_parser(
        "discover",
        help="Discover available tables/streams from source connector",
        description="List available data sources (tables, streams, objects) that can be "
        "extracted from a source connector. Useful for generating asset definitions.",
    )
    discover_parser.add_argument(
        "--connector",
        help="Connector type (e.g., stripe, postgres, mysql) or path to custom reader",
    )
    discover_parser.add_argument(
        "--config",
        help="Path to job configuration YAML file (alternative to --connector)",
    )
    discover_parser.add_argument(
        "--mode",
        choices=["self_hosted", "cloud"],
        default="self_hosted",
        help="Execution mode (default: self_hosted)",
    )
    discover_parser.add_argument(
        "--secret-manager",
        choices=["env", "filesystem", "vault", "aws", "gcp"],
        default=os.getenv("DATIVO_SECRET_MANAGER", "env"),
        help="Secret backend to use (default: env or DATIVO_SECRET_MANAGER env var).",
    )
    discover_parser.add_argument(
        "--secret-manager-config",
        help="Path to YAML/JSON file or inline JSON blob with secret manager configuration.",
    )
    discover_parser.add_argument(
        "--secrets-dir",
        default="/secrets",
        help="Path to secrets directory (default: /secrets, used by filesystem secret manager)",
    )
    discover_parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format",
    )
    discover_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output with additional details",
    )

    # Connectors command
    connectors_parser = subparsers.add_parser(
        "connectors",
        help="Manage connector registry and catalogs",
        description="List, inspect, and sync connectors from the registry and external catalogs.",
    )
    connectors_subparsers = connectors_parser.add_subparsers(
        dest="connectors_command", help="Connector action"
    )

    # connectors list
    list_parser = connectors_subparsers.add_parser(
        "list", help="List all registered connectors"
    )
    list_parser.add_argument(
        "--role",
        choices=["source", "target"],
        help="Filter by role (source or target)",
    )
    list_parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format",
    )
    list_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    # connectors inspect
    inspect_parser = connectors_subparsers.add_parser(
        "inspect", help="Inspect a specific connector"
    )
    inspect_parser.add_argument(
        "name",
        help="Connector name to inspect",
    )
    inspect_parser.add_argument(
        "--engine",
        help="Engine override (e.g., airbyte, singer)",
    )
    inspect_parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format",
    )

    # connectors sync
    sync_parser = connectors_subparsers.add_parser(
        "sync", help="Sync external connector catalogs"
    )
    sync_parser.add_argument(
        "name",
        nargs="?",
        default="airbyte",
        help="Name of the catalog to sync (default: airbyte)",
    )
    sync_parser.add_argument(
        "--catalog-url",
        dest="catalog_url",
        help="URL to fetch catalog JSON from",
    )
    sync_parser.add_argument(
        "--catalog-file",
        help="Path to local catalog JSON file to ingest",
    )
    sync_parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format",
    )
    sync_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 2

    if args.command == "run" or args.command == "ingest":
        return run_command(args)
    elif args.command == "start":
        return start_command(args)
    elif args.command == "check":
        return check_command(args)
    elif args.command == "discover":
        return discover_command(args)
    elif args.command == "connectors":
        return connectors_command(args)
    else:
        parser.print_help()
        return 2


if __name__ == "__main__":
    sys.exit(main())
