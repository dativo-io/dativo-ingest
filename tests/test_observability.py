import logging
import sys
import types

import pytest

from dativo_ingest.config import (
    AWSObservabilityConfig,
    JobConfig,
    ObservabilityConfig,
)
from dativo_ingest.observability import ObservabilityManager


def _base_job_kwargs(**overrides):
    """Helper for constructing minimal JobConfig payloads."""
    base = {
        "tenant_id": "tenant_a",
        "source_connector_path": "connectors/csv.yaml",
        "target_connector_path": "connectors/iceberg.yaml",
        "asset_path": "assets/csv/v1.0/test_job.yaml",
    }
    base.update(overrides)
    return base


def test_observability_config_requires_provider():
    with pytest.raises(ValueError):
        ObservabilityConfig()


def test_job_config_parses_observability_block():
    job = JobConfig(
        **_base_job_kwargs(
            observability={
                "aws": {
                    "region": "us-east-1",
                    "log_group": "/dativo/test",
                    "metrics_namespace": "Dativo/Test",
                },
                "gcp": {
                    "project_id": "demo-project",
                    "log_name": "demo-log",
                },
            }
        )
    )

    assert job.observability is not None
    assert job.observability.aws is not None
    assert job.observability.aws.log_group == "/dativo/test"
    assert job.observability.gcp is not None
    assert job.observability.gcp.project_id == "demo-project"


def test_observability_manager_noop_without_config():
    job = JobConfig(**_base_job_kwargs())
    manager = ObservabilityManager(job, logger=logging.getLogger("test/noop"))

    manager.start()
    manager.notify_completion(exit_code=0, status="success")
    manager.close()

    assert manager.handlers == []


def test_observability_manager_configures_aws_logging(monkeypatch):
    import boto3

    dummy_calls = []

    class DummyClient:
        def put_metric_data(self, Namespace, MetricData):
            dummy_calls.append((Namespace, MetricData))

    dummy_client = DummyClient()

    class DummySession:
        def __init__(self, region_name=None):
            self.region_name = region_name

        def client(self, name):
            assert name == "cloudwatch"
            return dummy_client

    monkeypatch.setattr(boto3.session, "Session", DummySession)

    class DummyHandler(logging.Handler):
        instances = []

        def __init__(self, **kwargs):
            super().__init__()
            self.kwargs = kwargs
            DummyHandler.instances.append(self)

        def emit(self, record):
            return

    fake_watchtower = types.SimpleNamespace(CloudWatchLogHandler=DummyHandler)
    monkeypatch.setitem(sys.modules, "watchtower", fake_watchtower)

    job = JobConfig(
        **_base_job_kwargs(
            observability=ObservabilityConfig(
                aws=AWSObservabilityConfig(
                    region="us-east-1",
                    log_group="/dativo/tests",
                    metrics_namespace="Dativo/Tests",
                )
            )
        )
    )

    logger = logging.getLogger("test/aws")
    manager = ObservabilityManager(job, logger=logger)
    manager.start()

    assert DummyHandler.instances, "CloudWatch handler should be attached"
    handler_kwargs = DummyHandler.instances[0].kwargs
    assert handler_kwargs["log_group"] == "/dativo/tests"

    manager.notify_completion(
        exit_code=0,
        status="success",
        metadata={"total_records": 5, "files_written": 1},
    )
    manager.close()

    assert dummy_calls, "CloudWatch metrics should be emitted when namespace is set"
