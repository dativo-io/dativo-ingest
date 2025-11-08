"""Tests for Airflow DAG generation."""

from pathlib import Path

from dativo_ingest.airflow_runner import generate_airflow_dags
from dativo_ingest.config import (
    AirflowOrchestratorConfig,
    OrchestratorConfig,
    RunnerConfig,
    ScheduleConfig,
)


def _build_runner_config(tmp_path: Path) -> RunnerConfig:
    schedule = ScheduleConfig(
        name="example_schedule",
        config="/app/jobs/example.yaml",
        cron="0 * * * *",
        enabled=True,
        timezone="UTC",
        tags={"environment": "test"},
    )
    airflow_cfg = AirflowOrchestratorConfig(
        dag_output_dir=str(tmp_path),
        dag_file_prefix="dativo_",
        python_interpreter="python",
        dag_tags=["dativo"],
        catchup=False,
        start_date="2024-01-01T00:00:00Z",
        default_args={"email_on_failure": True},
    )
    orchestrator = OrchestratorConfig(
        type="airflow",
        schedules=[schedule],
        concurrency_per_tenant=1,
        airflow=airflow_cfg,
    )
    return RunnerConfig(orchestrator=orchestrator)


def test_generate_airflow_dag_creates_file(tmp_path):
    """Generated DAG files should exist with expected content."""
    runner_config = _build_runner_config(tmp_path)

    generated = list(generate_airflow_dags(runner_config))

    assert len(generated) == 1
    dag_meta = generated[0]
    dag_path = tmp_path / f"{dag_meta.dag_id}.py"
    assert dag_path.exists()

    content = dag_path.read_text()
    assert "BashOperator" in content
    assert "--config /app/jobs/example.yaml" in content
    assert "schedule=\"0 * * * *\"" in content
    assert "max_active_runs=1" in content
    assert '"dativo", "environment:test"' in content


def test_generate_airflow_dag_skips_disabled(tmp_path):
    """Disabled schedules should not produce DAG files."""
    schedule_enabled = ScheduleConfig(
        name="enabled_schedule",
        config="/app/jobs/enabled.yaml",
        cron="0 0 * * *",
        enabled=True,
    )
    schedule_disabled = ScheduleConfig(
        name="disabled_schedule",
        config="/app/jobs/disabled.yaml",
        cron="0 1 * * *",
        enabled=False,
    )
    airflow_cfg = AirflowOrchestratorConfig(dag_output_dir=str(tmp_path))
    orchestrator = OrchestratorConfig(
        type="airflow",
        schedules=[schedule_enabled, schedule_disabled],
        concurrency_per_tenant=1,
        airflow=airflow_cfg,
    )
    runner_config = RunnerConfig(orchestrator=orchestrator)

    generated = list(generate_airflow_dags(runner_config))

    assert len(generated) == 1
    dag_ids = [dag.dag_id for dag in generated]
    assert "dativo_enabled_schedule" in dag_ids
    disabled_path = tmp_path / "dativo_disabled_schedule.py"
    assert not disabled_path.exists()
