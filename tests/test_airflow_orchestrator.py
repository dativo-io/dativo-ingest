"""Tests for Airflow orchestration support."""

import sys
import types

import pytest

from dativo_ingest.airflow_orchestrator import (
    create_airflow_dags,
    load_dags_from_runner_config,
    write_airflow_module,
)
from dativo_ingest.config import OrchestratorConfig, RunnerConfig, ScheduleConfig


class StubJobConfig:
    """Lightweight job config stub for tests."""

    tenant_id = "acme"
    retry_config = None

    def get_source(self):
        return types.SimpleNamespace(type="csv")

    def validate_schema_presence(self):
        return None


class StubValidator:
    """No-op connector validator."""

    def validate_job(self, job_config, mode):
        return None


def _install_fake_airflow(monkeypatch):
    class FakeDAG:
        def __init__(self, dag_id, **kwargs):
            self.dag_id = dag_id
            self.kwargs = kwargs
            self.schedule = kwargs.get("schedule")
            self.tags = kwargs.get("tags", [])
            self.default_args = kwargs.get("default_args", {})
            self.tasks = []

    class FakePythonOperator:
        def __init__(self, task_id, python_callable, dag):
            self.task_id = task_id
            self.python_callable = python_callable
            self.dag = dag
            dag.tasks.append(self)

    class FakeAirflowException(Exception):
        pass

    airflow_module = types.ModuleType("airflow")
    airflow_module.DAG = FakeDAG

    airflow_operators_module = types.ModuleType("airflow.operators")
    airflow_operators_python_module = types.ModuleType("airflow.operators.python")
    airflow_operators_python_module.PythonOperator = FakePythonOperator

    airflow_exceptions_module = types.ModuleType("airflow.exceptions")
    airflow_exceptions_module.AirflowException = FakeAirflowException

    monkeypatch.setitem(sys.modules, "airflow", airflow_module)
    monkeypatch.setitem(sys.modules, "airflow.operators", airflow_operators_module)
    monkeypatch.setitem(
        sys.modules, "airflow.operators.python", airflow_operators_python_module
    )
    monkeypatch.setitem(
        sys.modules, "airflow.exceptions", airflow_exceptions_module
    )


def _airflow_runner_config() -> RunnerConfig:
    schedule = ScheduleConfig(
        name="test_schedule",
        config="/app/jobs/test.yaml",
        cron="0 * * * *",
    )
    orchestrator = OrchestratorConfig(type="airflow", schedules=[schedule])
    return RunnerConfig(orchestrator=orchestrator)


def test_create_airflow_dags_with_stub_airflow(monkeypatch):
    _install_fake_airflow(monkeypatch)

    monkeypatch.setattr(
        "dativo_ingest.airflow_orchestrator.JobConfig.from_yaml",
        lambda path: StubJobConfig(),
    )
    monkeypatch.setattr(
        "dativo_ingest.airflow_orchestrator.ConnectorValidator", lambda: StubValidator()
    )
    monkeypatch.setattr(
        "dativo_ingest.airflow_orchestrator.execute_job_with_retry",
        lambda *args, **kwargs: {"status": "success"},
    )

    runner_config = _airflow_runner_config()
    dags = create_airflow_dags(runner_config)

    assert "test_schedule" in dags
    dag = dags["test_schedule"]
    assert dag.schedule == "0 * * * *"
    assert "tenant:acme" in dag.tags
    assert len(dag.tasks) == 1
    task = dag.tasks[0]
    result = task.python_callable()
    assert result["status"] == "success"
    assert dag.default_args["retries"] == 0


def test_create_airflow_dags_requires_airflow(monkeypatch):
    # Ensure no Airflow modules are preloaded
    for name in list(sys.modules):
        if name.startswith("airflow"):
            monkeypatch.delitem(sys.modules, name, raising=False)

    runner_config = _airflow_runner_config()

    with pytest.raises(RuntimeError):
        create_airflow_dags(runner_config)


def test_write_airflow_module(tmp_path):
    runner_config = _airflow_runner_config()
    output_dir = tmp_path / "dags"

    module_path = write_airflow_module(
        runner_config, output_dir, "/app/configs/runner_airflow.yaml"
    )

    assert module_path.exists()
    contents = module_path.read_text(encoding="utf-8")
    assert 'load_dags_from_runner_config("/app/configs/runner_airflow.yaml")' in contents


def test_load_dags_from_runner_config_requires_airflow_type(tmp_path):
    runner_path = tmp_path / "runner.yaml"
    runner_path.write_text(
        "runner:\n"
        "  mode: orchestrated\n"
        "  orchestrator:\n"
        "    type: dagster\n"
        "    schedules: []\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_dags_from_runner_config(runner_path)
