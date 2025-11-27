"""Tests for cloud observability integrations."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dativo_ingest.config import (
    AWSObservabilityConfig,
    GCPObservabilityConfig,
    ObservabilityConfig,
)
from dativo_ingest.observability import ObservabilityAdapter


def test_observability_adapter_no_config():
    """Adapter should safely no-op when not configured."""
    adapter = ObservabilityAdapter(None, {"job_name": "job", "tenant_id": "tenant"})
    adapter.emit_job_summary(
        status="success",
        metrics={"records_extracted": 10},
        mode="cloud",
        validation_mode="strict",
        extra={"exit_code": 0},
    )


@patch("dativo_ingest.observability.boto3")
def test_aws_metrics_emission(mock_boto):
    """AWS backend emits metrics via CloudWatch."""
    cloudwatch_client = MagicMock()
    mock_boto.client.return_value = cloudwatch_client

    config = ObservabilityConfig(
        provider="aws",
        metrics_enabled=True,
        logs_enabled=False,
        aws=AWSObservabilityConfig(region="us-east-1", cloudwatch_namespace="Test/Jobs"),
    )
    adapter = ObservabilityAdapter(
        config, {"job_name": "job", "tenant_id": "tenant", "source_connector": "csv"}
    )

    adapter.emit_job_summary(
        status="success",
        metrics={"records_extracted": 5, "execution_time_seconds": 1.2},
        mode="cloud",
        validation_mode="strict",
        extra={"exit_code": 0},
    )

    cloudwatch_client.put_metric_data.assert_called()


@patch("dativo_ingest.observability.monitoring_v3")
@patch("dativo_ingest.observability.logging_v2")
def test_gcp_observability_emit(mock_logging_v2, mock_monitoring_v3):
    """GCP backend pushes both metrics and logs."""
    metric_client = MagicMock()
    mock_monitoring_v3.MetricServiceClient.return_value = metric_client

    logging_client = MagicMock()
    logger_instance = MagicMock()
    logging_client.logger.return_value = logger_instance
    mock_logging_v2.Client.return_value = logging_client

    config = ObservabilityConfig(
        provider="gcp",
        metrics_enabled=True,
        logs_enabled=True,
        gcp=GCPObservabilityConfig(project_id="proj-123", log_name="custom-log"),
    )
    adapter = ObservabilityAdapter(
        config, {"job_name": "job", "tenant_id": "tenant", "source_connector": "csv"}
    )

    adapter.emit_job_summary(
        status="success",
        metrics={"records_extracted": 5, "execution_time_seconds": 1.2},
        mode="cloud",
        validation_mode="strict",
        extra={"exit_code": 0},
    )

    metric_client.create_time_series.assert_called_once()
    logging_client.logger.assert_called_with("custom-log")
    logger_instance.log_struct.assert_called_once()
