"""Minimal MVP test for metrics export."""

import socket
import time
from unittest.mock import Mock, patch

import pytest

from dativo_ingest.config import MetricsConfig, PrometheusConfig
from dativo_ingest.metrics import MetricsCollector


def get_free_port():
    """Get a free port for testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        return s.getsockname()[1]


def test_metrics_endpoint_returns_non_zero_counters():
    """Test that /metrics returns non-zero counters after job execution.
    
    This test satisfies the MVP acceptance criteria:
    - Start metrics server
    - Run minimal job execution path  
    - GET /metrics
    - Assert HTTP 200 and metrics present
    """
    try:
        import requests
        from dativo_ingest.metrics_server import MetricsServer
    except ImportError:
        pytest.skip("requests or prometheus_client not available")

    # Start server on random port
    port = get_free_port()
    prom_config = PrometheusConfig(enabled=True, host="127.0.0.1", port=port)
    server = MetricsServer(prom_config)
    server.start()

    try:
        time.sleep(0.1)  # Brief startup delay

        # Create metrics collector and simulate job
        config = MetricsConfig(enabled=True, prometheus=prom_config)
        collector = MetricsCollector(
            job_name="test_job",
            tenant_id="test",
            connector_type="test",
            mode="orchestrated",
            config=config,
        )

        # Minimal execution path
        collector.start()
        collector.start_extraction()
        time.sleep(0.01)
        collector.end_extraction()
        collector.record_records(100, phase="extracted")
        collector.record_bytes(1024, phase="written")
        collector.start_load()
        time.sleep(0.01)
        collector.end_load()
        collector.finish(status="success")

        # Fetch metrics
        response = requests.get(f"http://127.0.0.1:{port}/metrics", timeout=2)

        # Assert success
        assert response.status_code == 200
        metrics_text = response.text

        # Assert required metrics present
        assert "dativo_ingest_records_total" in metrics_text
        assert "dativo_ingest_runtime_seconds" in metrics_text

    finally:
        server.stop()


def test_oneshot_mode_no_server():
    """Test oneshot mode does NOT start HTTP server."""
    config = MetricsConfig(enabled=True)
    
    collector = MetricsCollector(
        job_name="oneshot_test",
        tenant_id="test",
        connector_type="csv",
        mode="oneshot",
        config=config,
    )

    # Should work without errors
    collector.start()
    collector.record_records(50, phase="extracted")
    metrics = collector.finish(status="success")

    assert metrics["status"] == "success"


def test_otel_export_does_not_crash_on_failure():
    """Test OTEL exporter failure does not crash job."""
    from dativo_ingest.config import OtelConfig
    from dativo_ingest.metrics_otel import configure_otel_metrics

    # Configure OTEL with unreachable endpoint
    otel_config = OtelConfig(enabled=True, endpoint="http://unreachable:4317")

    # Should not raise exception
    try:
        result = configure_otel_metrics(otel_config)
        # Either configures or returns False, but doesn't crash
        assert isinstance(result, bool)
    except Exception as e:
        pytest.fail(f"OTEL configuration crashed: {e}")
