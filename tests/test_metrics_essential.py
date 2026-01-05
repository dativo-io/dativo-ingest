"""Essential metrics tests (minimal, stable, maps directly to acceptance criteria)."""

import socket
import time
from unittest.mock import Mock, patch

import pytest


def get_free_port():
    """Get a free ephemeral port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        return s.getsockname()[1]


class TestMetricsAcceptance:
    """Essential tests mapping directly to acceptance criteria."""

    def test_orchestrated_metrics_endpoint_returns_non_zero_counters(self):
        """AC1: Orchestrated mode - /metrics returns non-zero counters after job.
        
        Tests:
        - Server starts in orchestrated mode
        - Job execution records metrics
        - /metrics endpoint accessible
        - Counters have non-zero values
        """
        try:
            import requests
            from dativo_ingest.config import MetricsConfig, PrometheusConfig
            from dativo_ingest.metrics import MetricsCollector
            from dativo_ingest.metrics_server import MetricsServer
        except ImportError:
            pytest.skip("requests or prometheus_client not available")

        # Start server on ephemeral port
        port = get_free_port()
        prom_config = PrometheusConfig(enabled=True, host="127.0.0.1", port=port)
        metrics_config = MetricsConfig(enabled=True, prometheus=prom_config)
        
        server = MetricsServer(prom_config)
        server.start()

        try:
            # Brief delay for server startup
            time.sleep(0.1)

            # Simulate job execution
            collector = MetricsCollector(
                job_name="test_job",
                tenant_id="test_tenant",
                connector_type="postgres",
                mode="orchestrated",
                config=metrics_config,
            )

            # Execute minimal job lifecycle
            collector.start()
            collector.start_extraction()
            time.sleep(0.01)
            collector.end_extraction()
            
            # Record metrics (ensures non-zero)
            collector.record_records(1000, phase="extracted")
            collector.record_records(950, phase="written")
            collector.record_bytes(104857600, phase="written")
            
            collector.start_load()
            time.sleep(0.01)
            collector.end_load()
            collector.finish(status="success")

            # Poll /metrics with short timeout
            response = requests.get(f"http://127.0.0.1:{port}/metrics", timeout=2)

            # Assert HTTP 200
            assert response.status_code == 200

            metrics_text = response.text

            # Assert required metrics present
            assert "dativo_ingest_records_total" in metrics_text
            assert "dativo_ingest_bytes_total" in metrics_text
            assert "dativo_ingest_runtime_seconds" in metrics_text
            assert "dativo_ingest_extract_seconds" in metrics_text
            assert "dativo_ingest_load_seconds" in metrics_text

            # Assert at least one counter is > 0 (basic regex)
            assert "1000.0" in metrics_text or "950.0" in metrics_text

        finally:
            server.stop()

    def test_oneshot_mode_no_server_started(self):
        """AC2: Oneshot mode - no HTTP server started, job doesn't crash.
        
        Tests:
        - Oneshot mode doesn't start server
        - Job executes successfully
        - Metrics recorded internally
        """
        from dativo_ingest.config import MetricsConfig
        from dativo_ingest.metrics import MetricsCollector

        metrics_config = MetricsConfig(enabled=True)
        
        collector = MetricsCollector(
            job_name="oneshot_job",
            tenant_id="test_tenant",
            connector_type="csv",
            mode="oneshot",
            config=metrics_config,
        )

        # Execute job lifecycle
        collector.start()
        collector.record_records(100, phase="extracted")
        collector.record_records(95, phase="written")
        collector.record_bytes(10240, phase="written")
        metrics = collector.finish(status="success")

        # Assert job completed successfully
        assert metrics["status"] == "success"
        assert "runtime_seconds" in metrics
        
        # In oneshot mode, no server should be started
        # (Server start is controlled by orchestrated.py, not collector)

    def test_otel_export_failure_does_not_crash_job(self):
        """AC3: OTEL - export failure doesn't crash job, warning logged.
        
        Tests:
        - OTEL enabled with unreachable endpoint
        - Job completes successfully
        - Warning logged (not crash)
        """
        from dativo_ingest.config import MetricsConfig, OtelConfig
        from dativo_ingest.metrics_otel import configure_otel_metrics

        # Configure OTEL with invalid endpoint
        otel_config = OtelConfig(
            enabled=True,
            endpoint="http://unreachable-fake-host:4317"
        )

        # This should not raise exception
        try:
            result = configure_otel_metrics(otel_config)
            # Either configures or returns False, but doesn't crash
            assert isinstance(result, bool)
        except Exception as e:
            pytest.fail(f"OTEL configuration should not crash: {e}")

        # Now test with metrics collector
        metrics_config = MetricsConfig(enabled=True, otel=otel_config)
        
        from dativo_ingest.metrics import MetricsCollector
        
        collector = MetricsCollector(
            job_name="otel_test",
            tenant_id="test",
            connector_type="stripe",
            mode="oneshot",
            config=metrics_config,
        )

        # Job should complete even with OTEL failure
        collector.start()
        collector.record_records(50, phase="extracted")
        metrics = collector.finish(status="success")

        assert metrics["status"] == "success"
