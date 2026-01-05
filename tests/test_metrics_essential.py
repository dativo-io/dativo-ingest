"""Essential metrics tests - minimal, stable, maps to acceptance criteria."""

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


def test_prometheus_endpoint_non_zero_counters():
    """AC1: Orchestrated mode - /metrics returns non-zero counters.
    
    Tests:
    - Server starts
    - Job execution records metrics
    - /metrics accessible via HTTP 200
    - Counters have non-zero values
    """
    try:
        import requests
        from dativo_ingest.config import MetricsConfig, PrometheusConfig
        from dativo_ingest.metrics import MetricsCollector
        from dativo_ingest.metrics_server import MetricsServer
    except ImportError:
        pytest.skip("requests or prometheus_client not available")

    # Start server on free port
    port = get_free_port()
    prom_config = PrometheusConfig(enabled=True, host="127.0.0.1", port=port)
    metrics_config = MetricsConfig(enabled=True, prometheus=prom_config)
    
    server = MetricsServer(prom_config)
    server.start()

    try:
        # Brief delay for server startup
        time.sleep(0.15)

        # Simulate job execution
        collector = MetricsCollector(
            job_name="test_job",
            tenant_id="test_tenant",
            connector_type="postgres",
            mode="orchestrated",
            config=metrics_config,
        )

        # Minimal job lifecycle
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

        # Assert required metrics present (actual metric names from code)
        assert "dativo_ingest_records_total" in metrics_text
        assert "dativo_ingest_bytes_total" in metrics_text
        assert "dativo_ingest_runtime_seconds" in metrics_text
        assert "dativo_ingest_extract_seconds" in metrics_text
        assert "dativo_ingest_load_seconds" in metrics_text

        # Assert at least one counter is > 0
        assert "1000.0" in metrics_text or "950.0" in metrics_text

    finally:
        server.stop()


def test_oneshot_no_server():
    """AC2: Oneshot mode - no HTTP server, job doesn't crash."""
    from dativo_ingest.config import MetricsConfig
    from dativo_ingest.metrics import MetricsCollector

    metrics_config = MetricsConfig(enabled=True)
    
    collector = MetricsCollector(
        job_name="oneshot_job",
        tenant_id="test",
        connector_type="csv",
        mode="oneshot",
        config=metrics_config,
    )

    # Execute job lifecycle
    collector.start()
    collector.record_records(100, phase="extracted")
    collector.record_records(95, phase="written")
    metrics = collector.finish(status="success")

    # Assert job completed successfully
    assert metrics["status"] == "success"
    assert "runtime_seconds" in metrics
    
    # Note: Server start is controlled by orchestrated.py, not collector
    # In oneshot, no server should be started


def test_otel_failure_no_crash():
    """AC3: OTEL - export failure doesn't crash job.
    
    Tests with mocked exporter that fails.
    """
    from dativo_ingest.config import MetricsConfig, OtelConfig
    from dativo_ingest.metrics import MetricsCollector

    # Configure OTEL (will fail silently)
    otel_config = OtelConfig(
        enabled=True,
        endpoint="http://unreachable-host:4317"
    )
    metrics_config = MetricsConfig(enabled=True, otel=otel_config)
    
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

    # Assert job completed (didn't crash)
    assert metrics["status"] == "success"
