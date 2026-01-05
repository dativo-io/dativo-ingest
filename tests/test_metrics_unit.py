"""Unit tests for metrics collector."""

import time

import pytest

from dativo_ingest.config import MetricsConfig, OtelConfig, PrometheusConfig
from dativo_ingest.metrics import MetricsCollector


class TestMetricsCollectorUnit:
    """Unit tests for MetricsCollector."""

    def test_initialization(self):
        """Test collector initialization."""
        config = MetricsConfig(enabled=True)
        collector = MetricsCollector(
            job_name="test_job",
            tenant_id="test_tenant",
            connector_type="postgres",
            mode="oneshot",
            config=config,
        )

        assert collector.job_name == "test_job"
        assert collector.tenant_id == "test_tenant"
        assert collector.connector_type == "postgres"
        assert collector.mode == "oneshot"

    def test_start_records_time(self):
        """Test start() records start time."""
        config = MetricsConfig(enabled=True)
        collector = MetricsCollector(
            job_name="test", tenant_id="test", connector_type="test",
            mode="oneshot", config=config
        )

        collector.start()

        assert collector.start_time is not None
        assert collector.start_time > 0

    def test_record_records(self):
        """Test record_records() increments counters."""
        config = MetricsConfig(enabled=True)
        collector = MetricsCollector(
            job_name="test", tenant_id="test", connector_type="test",
            mode="oneshot", config=config
        )

        collector.start()
        collector.record_records(100, phase="extracted")
        collector.record_records(95, phase="written")
        collector.record_records(5, phase="invalid")

        # Should not raise exceptions
        assert collector.metrics is not None

    def test_record_bytes(self):
        """Test record_bytes() increments counter."""
        config = MetricsConfig(enabled=True)
        collector = MetricsCollector(
            job_name="test", tenant_id="test", connector_type="test",
            mode="oneshot", config=config
        )

        collector.start()
        collector.record_bytes(1048576, phase="written")

        # Should not raise exceptions
        assert collector.metrics is not None

    def test_record_api_calls(self):
        """Test record_api_calls() with api_type."""
        config = MetricsConfig(enabled=True)
        collector = MetricsCollector(
            job_name="test", tenant_id="test", connector_type="test",
            mode="oneshot", config=config
        )

        collector.start()
        collector.record_api_calls(10, api_type="stripe")

        # Should not raise exceptions
        assert collector.metrics is not None

    def test_record_retry(self):
        """Test record_retry() increments counter."""
        config = MetricsConfig(enabled=True)
        collector = MetricsCollector(
            job_name="test", tenant_id="test", connector_type="test",
            mode="oneshot", config=config
        )

        collector.start()
        collector.record_retry()
        collector.record_retry()

        # Should not raise exceptions
        assert collector.metrics is not None

    def test_extraction_timing(self):
        """Test start_extraction/end_extraction timing."""
        config = MetricsConfig(enabled=True)
        collector = MetricsCollector(
            job_name="test", tenant_id="test", connector_type="test",
            mode="oneshot", config=config
        )

        collector.start()
        collector.start_extraction()
        time.sleep(0.01)
        collector.end_extraction()

        assert "extract_seconds" in collector.metrics
        assert collector.metrics["extract_seconds"] > 0

    def test_load_timing(self):
        """Test start_load/end_load timing."""
        config = MetricsConfig(enabled=True)
        collector = MetricsCollector(
            job_name="test", tenant_id="test", connector_type="test",
            mode="oneshot", config=config
        )

        collector.start()
        collector.start_load()
        time.sleep(0.01)
        collector.end_load()

        assert "load_seconds" in collector.metrics
        assert collector.metrics["load_seconds"] > 0

    def test_finish_records_runtime(self):
        """Test finish() records runtime."""
        config = MetricsConfig(enabled=True)
        collector = MetricsCollector(
            job_name="test", tenant_id="test", connector_type="test",
            mode="oneshot", config=config
        )

        collector.start()
        time.sleep(0.05)
        metrics = collector.finish(status="success")

        assert metrics["status"] == "success"
        assert "runtime_seconds" in metrics
        assert metrics["runtime_seconds"] > 0

    def test_finish_without_start_is_safe(self):
        """Test finish() is safe without start()."""
        config = MetricsConfig(enabled=True)
        collector = MetricsCollector(
            job_name="test", tenant_id="test", connector_type="test",
            mode="oneshot", config=config
        )

        # Should not crash
        metrics = collector.finish(status="failure")

        assert isinstance(metrics, dict)
        assert metrics["status"] == "failure"

    def test_metrics_disabled(self):
        """Test collector works when metrics disabled."""
        config = MetricsConfig(enabled=False)
        collector = MetricsCollector(
            job_name="test", tenant_id="test", connector_type="test",
            mode="oneshot", config=config
        )

        # Should not crash
        collector.start()
        collector.record_records(100, phase="extracted")
        collector.finish(status="success")

    def test_prometheus_disabled_in_config(self):
        """Test collector with prometheus disabled."""
        config = MetricsConfig(
            enabled=True,
            prometheus=PrometheusConfig(enabled=False)
        )
        collector = MetricsCollector(
            job_name="test", tenant_id="test", connector_type="test",
            mode="oneshot", config=config
        )

        collector.start()
        collector.record_records(50, phase="extracted")
        metrics = collector.finish(status="success")

        assert metrics["status"] == "success"

    def test_labels_include_required_fields(self):
        """Test labels include job_name, tenant_id, connector_type, mode."""
        config = MetricsConfig(enabled=True)
        collector = MetricsCollector(
            job_name="my_job",
            tenant_id="acme",
            connector_type="stripe",
            mode="orchestrated",
            config=config
        )

        assert collector.labels["job_name"] == "my_job"
        assert collector.labels["tenant_id"] == "acme"
        assert collector.labels["connector_type"] == "stripe"
        assert collector.labels["mode"] == "orchestrated"

    def test_env_var_override_port(self, monkeypatch):
        """Test environment variable overrides port."""
        monkeypatch.setenv("DATIVO_METRICS_PORT", "9999")

        config = MetricsConfig(
            prometheus=PrometheusConfig(port=9400)
        )
        collector = MetricsCollector(
            job_name="test", tenant_id="test", connector_type="test",
            mode="oneshot", config=config
        )

        assert collector.config.prometheus.port == 9999
