"""Airflow orchestration support for Dativo ingestion."""

from __future__ import annotations

import textwrap
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from .config import JobConfig, RunnerConfig, ScheduleConfig
from .logging import get_logger, setup_logging
from .orchestrators.common import execute_job_with_retry
from .retry_policy import RetryPolicy as CustomRetryPolicy
from .validator import ConnectorValidator

try:  # pragma: no cover - Python <3.9
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]
    ZoneInfoNotFoundError = Exception  # type: ignore[assignment]


DEFAULT_AIRFLOW_MODULE_FILENAME = "dativo_runner_dags.py"


def _import_airflow_components():
    try:
        from airflow import DAG
        from airflow.exceptions import AirflowException
        from airflow.operators.python import PythonOperator
    except ImportError as exc:  # pragma: no cover - exercised in tests via stubs
        raise RuntimeError(
            "Airflow is not installed. Install 'apache-airflow' to use the Airflow orchestrator."
        ) from exc

    return DAG, PythonOperator, AirflowException


def _schedule_to_airflow(schedule_config: ScheduleConfig) -> Union[str, timedelta]:
    if schedule_config.cron:
        return schedule_config.cron
    if schedule_config.interval_seconds:
        return timedelta(seconds=schedule_config.interval_seconds)
    raise ValueError(
        f"Schedule '{schedule_config.name}' must define either cron or interval_seconds"
    )


def _resolve_timezone(timezone_name: str, logger) -> Optional[Any]:
    if not timezone_name:
        return None
    if ZoneInfo is None:  # pragma: no cover - compatibility branch
        logger.warning(
            "ZoneInfo module not available; timezone '%s' will be ignored",
            timezone_name,
        )
        return None
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        logger.warning(
            "Unknown timezone '%s'; falling back to Airflow default",
            timezone_name,
            extra={
                "event_type": "airflow_timezone_warning",
                "timezone": timezone_name,
            },
        )
        return None


def _build_tags(
    tenant_id: str, connector_type: str, schedule_tags: Optional[Dict[str, str]]
) -> List[str]:
    tags = [f"tenant:{tenant_id}", f"connector:{connector_type}"]
    if schedule_tags:
        tags.extend(f"{key}:{value}" for key, value in schedule_tags.items())
    return tags


def _build_python_callable(
    schedule_config: ScheduleConfig,
    cli_module: str,
    airflow_exception_cls,
) -> Callable[..., Dict[str, Any]]:
    def _run_job(**context: Any) -> Dict[str, Any]:
        job_logger = get_logger()
        job_logger.info(
            "Executing scheduled job",
            extra={
                "job_name": schedule_config.name,
                "event_type": "job_running",
                "config_path": schedule_config.config,
            },
        )

        try:
            job_config = JobConfig.from_yaml(schedule_config.config)
            tenant_id = job_config.tenant_id
            source_config = job_config.get_source()
            connector_type = source_config.type

            job_logger.info(
                "Job validated",
                extra={
                    "job_name": schedule_config.name,
                    "tenant_id": tenant_id,
                    "connector_type": connector_type,
                    "event_type": "job_validated",
                },
            )

            # Validate schema presence and connector
            job_config.validate_schema_presence()
            validator = ConnectorValidator()
            validator.validate_job(job_config, mode="self_hosted")

            custom_retry_policy = (
                CustomRetryPolicy(job_config.retry_config)
                if job_config.retry_config
                else None
            )

            return execute_job_with_retry(
                schedule_config,
                job_config,
                custom_retry_policy,
                cli_module=cli_module,
            )

        except SystemExit as exc:
            raise airflow_exception_cls(
                f"Job execution exited with status {exc.code} for schedule '{schedule_config.name}'"
            ) from None
        except Exception as exc:
            job_logger.error(
                "Job execution error: %s",
                exc,
                extra={
                    "job_name": schedule_config.name,
                    "event_type": "job_error",
                },
            )
            raise airflow_exception_cls(str(exc)) from exc

    return _run_job


def create_airflow_dags(
    runner_config: RunnerConfig,
    cli_module: str = "dativo_ingest.cli",
) -> Dict[str, Any]:
    """Create Airflow DAG objects from the runner configuration.

    Args:
        runner_config: Runner configuration with schedules and metadata
        cli_module: Python module path used to execute jobs

    Returns:
        Dictionary mapping DAG IDs to Airflow DAG objects
    """
    DAG, PythonOperator, AirflowException = _import_airflow_components()
    logger = setup_logging(level="INFO", redact_secrets=False)

    dags: Dict[str, Any] = {}

    for schedule_config in runner_config.orchestrator.schedules:
        if not schedule_config.enabled:
            logger.info(
                "Schedule '%s' is disabled; skipping Airflow DAG creation",
                schedule_config.name,
                extra={
                    "event_type": "schedule_skipped",
                    "schedule_name": schedule_config.name,
                },
            )
            continue

        try:
            job_config = JobConfig.from_yaml(schedule_config.config)
            tenant_id = job_config.tenant_id
            connector_type = job_config.get_source().type
        except SystemExit as exc:
            logger.error(
                "Job configuration for schedule '%s' exited with status %s",
                schedule_config.name,
                exc.code,
                extra={
                    "event_type": "schedule_config_error",
                    "schedule_name": schedule_config.name,
                    "exit_code": exc.code,
                },
            )
            continue
        except Exception as exc:
            logger.error(
                "Failed to load job configuration for schedule '%s': %s",
                schedule_config.name,
                exc,
                extra={
                    "event_type": "schedule_config_error",
                    "schedule_name": schedule_config.name,
                },
            )
            continue

        airflow_schedule = _schedule_to_airflow(schedule_config)
        tzinfo = _resolve_timezone(schedule_config.timezone, logger)
        dag_tags = _build_tags(tenant_id, connector_type, schedule_config.tags)

        dag = DAG(
            dag_id=schedule_config.name,
            description=f"Dativo ingestion job for {schedule_config.name}",
            schedule=airflow_schedule,
            catchup=False,
            tags=dag_tags,
            max_active_runs=schedule_config.max_concurrent_runs,
            timezone=tzinfo,
            default_args={
                "owner": "dativo",
                "depends_on_past": False,
                "retries": 0,
            },
        )

        PythonOperator(
            task_id="run_job",
            python_callable=_build_python_callable(
                schedule_config, cli_module, AirflowException
            ),
            dag=dag,
        )

        dags[dag.dag_id] = dag
        logger.info(
            "Registered Airflow DAG '%s'",
            dag.dag_id,
            extra={
                "event_type": "airflow_dag_registered",
                "dag_id": dag.dag_id,
                "schedule_name": schedule_config.name,
                "tenant_id": tenant_id,
                "connector_type": connector_type,
                "schedule": str(airflow_schedule),
            },
        )

    return dags


def load_dags_from_runner_config(
    config_path: Union[str, Path],
    cli_module: str = "dativo_ingest.cli",
) -> Dict[str, Any]:
    """Convenience loader for Airflow DAG discovery code."""
    runner_config = RunnerConfig.from_yaml(config_path)
    if runner_config.orchestrator.type != "airflow":
        raise ValueError(
            f"Runner config at '{config_path}' is not configured for Airflow orchestrator"
        )
    return create_airflow_dags(runner_config, cli_module=cli_module)


def write_airflow_module(
    runner_config: RunnerConfig,
    output_dir: Union[str, Path],
    runner_config_path: Union[str, Path],
    module_filename: str = DEFAULT_AIRFLOW_MODULE_FILENAME,
) -> Path:
    """Generate a lightweight Airflow DAG module that loads DAGs from the runner config."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    module_path = output_path / module_filename
    config_path_str = Path(runner_config_path).as_posix()

    module_source = textwrap.dedent(
        f'''\
        """Auto-generated Airflow DAG bootstrap for Dativo ingestion."""

        from dativo_ingest.airflow_orchestrator import load_dags_from_runner_config

        DAGS = load_dags_from_runner_config("{config_path_str}")
        globals().update(DAGS)
        '''
    ).strip() + "\n"

    module_path.write_text(module_source, encoding="utf-8")
    return module_path

