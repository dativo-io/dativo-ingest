"""Airflow orchestration with tenant-level serialization."""

import subprocess
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
from airflow.utils.task_group import TaskGroup

from .config import JobConfig, RunnerConfig
from .logging import get_logger, setup_logging
from .retry_policy import RetryPolicy as CustomRetryPolicy
from .validator import ConnectorValidator


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
            if custom_retry_policy and custom_retry_policy.should_retry(2, str(e), attempt):
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
    raise Exception(f"Job execution failed after {attempt + 1} attempt(s): {last_error}")


def create_task_function(schedule_config: Any, job_config: JobConfig, custom_retry_policy: Optional[CustomRetryPolicy]):
    """Create a task function for Airflow operator.

    Args:
        schedule_config: Schedule configuration
        job_config: Job configuration
        custom_retry_policy: Custom retry policy instance

    Returns:
        Callable task function
    """
    def task_function(**context):
        """Execute job for this schedule."""
        job_logger = get_logger()
        start_time = time.time()
        
        tenant_id = job_config.tenant_id
        source_config = job_config.get_source()
        connector_type = source_config.type

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
            result = _execute_job_with_retry(
                schedule_config, job_config, custom_retry_policy
            )

            # Calculate execution time
            execution_time = time.time() - start_time

            job_logger.info(
                "Job execution completed",
                extra={
                    "job_name": schedule_config.name,
                    "tenant_id": tenant_id,
                    "connector_type": connector_type,
                    "execution_time_seconds": execution_time,
                    "status": result.get("status", "unknown"),
                    "event_type": "job_completed",
                },
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

    return task_function


def create_airflow_dags(runner_config: RunnerConfig) -> Dict[str, DAG]:
    """Create Airflow DAGs from runner configuration.

    Args:
        runner_config: Runner configuration with schedules

    Returns:
        Dictionary of DAG ID to DAG objects
    """
    logger = setup_logging(level="INFO", redact_secrets=False)
    dags = {}

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

        except Exception as e:
            logger.error(
                f"Failed to load job config for schedule '{schedule_config.name}': {e}",
                extra={"event_type": "schedule_config_error", "schedule_name": schedule_config.name},
            )
            continue

        # Build default args for DAG
        default_args = {
            'owner': 'dativo',
            'depends_on_past': False,
            'email_on_failure': False,
            'email_on_retry': False,
            'retries': job_config.retry_config.max_retries if job_config.retry_config else 0,
            'retry_delay': timedelta(seconds=job_config.retry_config.initial_delay_seconds if job_config.retry_config else 5),
        }

        # Add tags
        dag_tags = ['dativo', f'tenant:{tenant_id}', f'connector:{connector_type}']
        if schedule_config.tags:
            dag_tags.extend([f'{k}:{v}' for k, v in schedule_config.tags.items()])

        # Determine schedule interval
        schedule_interval = None
        if schedule_config.cron:
            schedule_interval = schedule_config.cron
        elif schedule_config.interval_seconds:
            schedule_interval = timedelta(seconds=schedule_config.interval_seconds)

        # Create DAG
        dag = DAG(
            dag_id=schedule_config.name,
            default_args=default_args,
            description=f'Dativo ingestion job: {schedule_config.name}',
            schedule_interval=schedule_interval,
            start_date=datetime(2024, 1, 1),
            catchup=False,
            max_active_runs=schedule_config.max_concurrent_runs,
            tags=dag_tags,
        )

        # Create task
        task_func = create_task_function(schedule_config, job_config, custom_retry_policy)
        
        task = PythonOperator(
            task_id=f'run_{schedule_config.name}',
            python_callable=task_func,
            dag=dag,
            provide_context=True,
        )

        dags[schedule_config.name] = dag
        
        logger.info(
            f"Created Airflow DAG for schedule '{schedule_config.name}'",
            extra={
                "event_type": "dag_created",
                "schedule_name": schedule_config.name,
                "tenant_id": tenant_id,
                "connector_type": connector_type,
            },
        )

    return dags


def start_orchestrated(runner_config: RunnerConfig) -> None:
    """Start Airflow orchestrator in long-running mode.

    Args:
        runner_config: Runner configuration

    Raises:
        SystemExit: If orchestrator fails to start
    """
    logger = setup_logging(level="INFO", redact_secrets=False)
    logger.info(
        "Initializing Airflow orchestrator",
        extra={"event_type": "orchestrator_initializing"},
    )

    # Create Airflow DAGs
    try:
        dags = create_airflow_dags(runner_config)
    except Exception as e:
        logger.error(
            f"Failed to create Airflow DAGs: {e}",
            extra={"event_type": "orchestrator_error"},
        )
        raise

    logger.info(
        f"Created {len(dags)} DAGs",
        extra={"event_type": "orchestrator_ready"},
    )

    # In production, Airflow runs as a separate service with scheduler and webserver
    # This function is mainly for validation and DAG generation
    logger.info(
        "Airflow DAGs created successfully. To run Airflow:",
        extra={"event_type": "orchestrator_instructions"},
    )
    logger.info(
        "1. Set AIRFLOW_HOME environment variable",
        extra={"event_type": "orchestrator_instructions"},
    )
    logger.info(
        "2. Initialize database: airflow db init",
        extra={"event_type": "orchestrator_instructions"},
    )
    logger.info(
        "3. Start webserver: airflow webserver --port 8080",
        extra={"event_type": "orchestrator_instructions"},
    )
    logger.info(
        "4. Start scheduler: airflow scheduler",
        extra={"event_type": "orchestrator_instructions"},
    )

    logger.info(
        "Airflow orchestrator configured. Start Airflow services manually.",
        extra={"event_type": "orchestrator_configured"},
    )


# Export DAGs for Airflow to discover
# This is typically loaded by setting AIRFLOW__CORE__DAGS_FOLDER to this module's directory
def get_dags_from_config(config_path: str) -> Dict[str, DAG]:
    """Load DAGs from runner configuration file.

    This function is called by Airflow when scanning for DAGs.

    Args:
        config_path: Path to runner.yaml configuration file

    Returns:
        Dictionary of DAG ID to DAG objects
    """
    from pathlib import Path
    
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Runner config not found: {config_path}")

    runner_config = RunnerConfig.from_yaml(config_path)
    return create_airflow_dags(runner_config)
