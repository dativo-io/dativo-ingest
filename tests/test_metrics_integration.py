"""Integration tests for metrics with HTTP server and OTEL."""

import socket
import time
from unittest.mock import Mock, patch

import pytest

from dativo_ingest.config import MetricsConfig, OtelConfig, PrometheusConfig
from dativo_ingest.metrics import MetricsCollector


def get_free_port():
    """Get a free port for testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        return s.getsockname()[1]


class TestMetricsServerIntegration:
    """Integration tests for metrics HTTP server."""

    def test_server_starts_and_exposes_metrics(self):
        """Test metrics server starts and /metrics endpoint works."""
        try:
            import requests
            from dativo_ingest.metrics_server import MetricsServer
        except ImportError:
            pytest.skip("requests or prometheus_client not available")

        port = get_free_port()
        prom_config = PrometheusConfig(enabled=True, host="127.0.0.1", port=port)
        server = MetricsServer(prom_config)

        try:
            server.start()
            time.sleep(0.2)

            # Create collector and record metrics
            config = MetricsConfig(enabled=True, prometheus=prom_config)
            collector = MetricsCollector(
                job_name="integration_test",
                tenant_id="test",
                connector_type="postgres",
                mode="orchestrated",
                config=config,
            )

            collector.start()
            collector.start_extraction()
            time.sleep(0.01)
            collector.end_extraction()
            collector.record_records(500, phase="extracted")
            collector.record_records(480, phase="written")
            collector.record_records(20, phase="invalid")
            collector.record_bytes(524288, phase="written")
            collector.start_load()
            time.sleep(0.01)
            collector.end_load()
            collector.finish(status="success")

            # Fetch metrics
            response = requests.get(f"http://127.0.0.1:{port}/metrics", timeout=2)

            assert response.status_code == 200
            metrics_text = response.text

            # Verify required metrics present
            assert "dativo_ingest_records_total" in metrics_text
            assert "dativo_ingest_bytes_total" in metrics_text
            assert "dativo_ingest_extract_seconds" in metrics_text
            assert "dativo_ingest_load_seconds" in metrics_text
            assert "dativo_ingest_runtime_seconds" in metrics_text

            # Verify labels present
            assert "job_name=" in metrics_text
            assert "tenant_id=" in metrics_text
            assert "connector_type=" in metrics_text
            assert "mode=" in metrics_text

        finally:
            server.stop()

    def test_server_not_started_when_disabled(self):
        """Test server is not started when prometheus disabled."""
        from dativo_ingest.metrics_server import start_metrics_server_from_config

        config = PrometheusConfig(enabled=False)
        server = start_metrics_server_from_config(config)

        assert server is None

    def test_get_metrics_text_returns_string(self):
        """Test get_metrics_text() returns valid string."""
        try:
            from dativo_ingest.metrics_server import get_metrics_text
        except ImportError:
            pytest.skip("prometheus_client not available")

        metrics_text = get_metrics_text()

        assert isinstance(metrics_text, str)
        assert len(metrics_text) > 0


class TestOTELIntegration:
    """Integration tests for OpenTelemetry."""

    def test_otel_configuration_disabled(self):
        """Test OTEL returns False when disabled."""
        from dativo_ingest.metrics_otel import configure_otel_metrics

        config = OtelConfig(enabled=False)
        result = configure_otel_metrics(config)

        assert result is False

    def test_otel_configuration_no_endpoint(self):
        """Test OTEL returns False when endpoint not configured."""
        from dativo_ingest.metrics_otel import configure_otel_metrics

        config = OtelConfig(enabled=True, endpoint=None)
        result = configure_otel_metrics(config)

        assert result is False

    def test_otel_unreachable_endpoint_does_not_crash(self):
        """Test OTEL with unreachable endpoint does not crash."""
        from dativo_ingest.metrics_otel import configure_otel_metrics

        config = OtelConfig(enabled=True, endpoint="http://unreachable:4317")

        # Should not raise exception
        try:
            result = configure_otel_metrics(config)
            assert isinstance(result, bool)
        except Exception as e:
            pytest.fail(f"OTEL configuration should not crash: {e}")

    def test_collector_with_otel_enabled(self):
        """Test collector works with OTEL enabled but unreachable."""
        config = MetricsConfig(
            enabled=True,
            otel=OtelConfig(enabled=True, endpoint="http://fake:4317")
        )

        collector = MetricsCollector(
            job_name="otel_test",
            tenant_id="test",
            connector_type="stripe",
            mode="oneshot",
            config=config,
        )

        # Should work even if OTEL fails
        collector.start()
        collector.record_records(100, phase="extracted")
        metrics = collector.finish(status="success")

        assert metrics["status"] == "success"


class TestFullJobLifecycle:
    """Integration test for full job lifecycle with metrics."""

    def test_complete_job_execution_with_metrics(self):
        """Test complete job execution records all required metrics."""
        config = MetricsConfig(
            enabled=True,
            prometheus=PrometheusConfig(enabled=False),  # No server for unit test
        )

        collector = MetricsCollector(
            job_name="full_job_test",
            tenant_id="acme",
            connector_type="postgres",
            mode="oneshot",
            config=config,
        )

        # Simulate full job lifecycle
        collector.start()

        # Extraction phase
        collector.start_extraction()
        time.sleep(0.02)
        collector.end_extraction()
        collector.record_records(1000, phase="extracted")

        # Validation
        collector.record_records(950, phase="written")
        collector.record_records(50, phase="invalid")

        # Writing
        collector.record_bytes(2097152, phase="written")

        # API calls
        collector.record_api_calls(25, api_type="postgres")

        # Load phase
        collector.start_load()
        time.sleep(0.01)
        collector.end_load()

        # Finish
        time.sleep(0.01)
        metrics = collector.finish(status="success")

        # Verify all metrics recorded
        assert metrics["status"] == "success"
        assert "runtime_seconds" in metrics
        assert metrics["runtime_seconds"] > 0
        assert "extract_seconds" in metrics
        assert metrics["extract_seconds"] > 0
        assert "load_seconds" in metrics
        assert metrics["load_seconds"] > 0

    def test_job_failure_path_records_metrics(self):
        """Test metrics recorded even on failure path."""
        config = MetricsConfig(enabled=True)

        collector = MetricsCollector(
            job_name="failing_job",
            tenant_id="test",
            connector_type="stripe",
            mode="oneshot",
            config=config,
        )

        collector.start()
        collector.start_extraction()
        time.sleep(0.01)
        collector.end_extraction()
        collector.record_records(100, phase="extracted")

        # Simulate failure
        collector.record_retry()
        metrics = collector.finish(status="failure")

        assert metrics["status"] == "failure"
        assert "runtime_seconds" in metrics
        assert metrics["runtime_seconds"] > 0

    def test_partial_success_records_metrics(self):
        """Test metrics for partial success."""
        config = MetricsConfig(enabled=True)

        collector = MetricsCollector(
            job_name="partial_job",
            tenant_id="test",
            connector_type="csv",
            mode="oneshot",
            config=config,
        )

        collector.start()
        collector.start_extraction()
        time.sleep(0.01)
        collector.end_extraction()
        collector.record_records(1000, phase="extracted")
        collector.record_records(500, phase="written")
        collector.record_records(500, phase="invalid")
        collector.start_load()
        time.sleep(0.01)
        collector.end_load()
        metrics = collector.finish(status="partial")

        assert metrics["status"] == "partial"
        assert "runtime_seconds" in metrics


class TestConfigPrecedence:
    """Test configuration precedence rules."""

    def test_job_config_takes_precedence(self):
        """Test job config overrides are used."""
        # In real usage, job config would override runner config
        # For this test, we just verify collector uses provided config
        job_config = MetricsConfig(
            enabled=True,
            prometheus=PrometheusConfig(enabled=True, port=9999)
        )

        collector = MetricsCollector(
            job_name="test",
            tenant_id="test",
            connector_type="test",
            mode="oneshot",
            config=job_config,
        )

        assert collector.config.prometheus.port == 9999

    def test_env_var_overrides_config(self, monkeypatch):
        """Test environment variable overrides config."""
        monkeypatch.setenv("DATIVO_METRICS_PORT", "8888")

        config = MetricsConfig(
            prometheus=PrometheusConfig(port=9400)
        )

        collector = MetricsCollector(
            job_name="test",
            tenant_id="test",
            connector_type="test",
            mode="oneshot",
            config=config,
        )

        # Env var should override
        assert collector.config.prometheus.port == 8888
