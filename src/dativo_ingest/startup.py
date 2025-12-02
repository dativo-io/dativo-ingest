"""Startup sequence for batch job execution."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import JobConfig
from .infrastructure import validate_infrastructure
from .logging import setup_logging
from .secrets import load_secrets_and_set_env
from .validator import ConnectorValidator, initialize_state_directory


def startup_sequence(
    job_dir: Path,
    secrets_dir: Path,
    tenant_id: Optional[str] = None,
    mode: str = "self_hosted",
    secret_manager: str = "env",
    secret_manager_config: Optional[Dict[str, Any]] = None,
) -> List[JobConfig]:
    """Complete startup sequence for batch job execution.

    Loads and validates job configurations from a directory, sets up
    infrastructure, and prepares jobs for execution.

    Args:
        job_dir: Directory containing job YAML files
        secrets_dir: Directory containing secrets (filesystem manager only)
        tenant_id: Optional tenant identifier (if not provided, inferred from jobs)
        mode: Execution mode (default: self_hosted)
        secret_manager: Secret backend to use (env, filesystem, vault, aws, gcp)
        secret_manager_config: Optional manager-specific configuration dictionary

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
        # Include None values to detect mixed tenant_id scenarios
        tenant_ids = {job.tenant_id for job in jobs}
        if len(tenant_ids) > 1:
            raise ValueError(
                f"Multiple tenant IDs found in jobs: {tenant_ids}. "
                "All jobs must belong to the same tenant, or provide --tenant-id."
            )
        tenant_id = jobs[0].tenant_id if jobs else None
        tenant_source = "inferred from job configurations"
    else:
        # Validate all jobs belong to the provided tenant
        # Check all jobs, including those with None tenant_id
        for job in jobs:
            if job.tenant_id != tenant_id:
                raise ValueError(
                    f"Job '{job.asset}' belongs to tenant '{job.tenant_id}', "
                    f"but --tenant-id '{tenant_id}' was provided. "
                    "All jobs must belong to the same tenant."
                )
        tenant_source = "provided via --tenant-id"

    # Set up logging with inferred/validated tenant_id
    logger = setup_logging(level="INFO", redact_secrets=True, tenant_id=tenant_id)
    logger.info(
        f"Tenant ID '{tenant_id}' {tenant_source}",
        extra={
            "event_type": (
                "tenant_inferred"
                if tenant_source == "inferred from job configurations"
                else "tenant_override"
            )
        },
    )

    logger.info(
        f"Starting startup sequence for tenant '{tenant_id}'",
        extra={"event_type": "startup_begin", "job_count": len(jobs)},
    )

    # 3. Load secrets using inferred/validated tenant_id
    secrets = load_secrets_and_set_env(
        tenant_id=tenant_id,
        secrets_dir=secrets_dir,
        manager_type=secret_manager,
        manager_config=secret_manager_config,
    )
    if secrets:
        logger.info(
            f"Secrets loaded for tenant {tenant_id}",
            extra={"event_type": "secrets_loaded", "secret_count": len(secrets)},
        )
    else:
        logger.warning(
            "No secrets loaded (may be optional)",
            extra={"event_type": "secrets_warning"},
        )

    # 4. Validate environment variables for all jobs
    for job in jobs:
        try:
            job.validate_environment_variables()
        except ValueError as e:
            logger.warning(
                f"Environment variable validation warning for job: {e}",
                extra={"event_type": "env_validation_warning"},
            )

    logger.info(
        "Environment variables validated",
        extra={"event_type": "env_validated"},
    )

    # 5. Validate infrastructure for all jobs
    for job in jobs:
        try:
            validate_infrastructure(job)
        except ValueError as e:
            logger.warning(
                f"Infrastructure validation warning for job: {e}",
                extra={"event_type": "infrastructure_warning"},
            )

    logger.info(
        "Infrastructure validated",
        extra={"event_type": "infra_validated"},
    )

    # 6. Initialize state management for all jobs
    for job in jobs:
        try:
            initialize_state_directory(job)
        except Exception as e:
            logger.warning(
                f"State directory initialization warning for job: {e}",
                extra={"event_type": "state_warning"},
            )

    logger.info(
        "State management initialized",
        extra={"event_type": "state_initialized"},
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
                extra={"event_type": "job_validation_error"},
            )
            # Continue with other jobs

    logger.info(
        "Startup sequence completed",
        extra={"event_type": "startup_complete", "job_count": len(jobs)},
    )

    return jobs
