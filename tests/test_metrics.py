"""Tests for metrics collection and export."""

import time

import pytest

from dativo_ingest.metrics import PROMETHEUS_AVAILABLE, MetricsCollector


class TestMetricsCollector:
    """Test MetricsCollector functionality."""

    def test_metrics_collector_initialization(self):
        """Test metrics collector can be initialized."""
        collector = MetricsCollector(
            job_name="test_job",
            tenant_id="test_tenant",
            connector_type="test_connector",
        )

        assert collector.job_name == "test_job"
        assert collector.tenant_id == "test_tenant"
        assert collector.connector_type == "test_connector"

    def test_metrics_collector_lifecycle(self):
        """Test complete metrics collection lifecycle."""
        collector = MetricsCollector(
            job_name="test_job",
            tenant_id="test_tenant",
            connector_type="test_connector",
        )

        # Start collection
        collector.start()
        assert collector.start_time is not None

        # Record extraction
        collector.record_extraction(records_count=1000, files_count=5)
        assert collector.metrics["records_extracted"] == 1000
        assert collector.metrics["files_processed"] == 5

        # Record validation
        collector.record_validation(
            valid_records=950, invalid_records=50, total_records=1000
        )
        assert collector.metrics["records_valid"] == 950
        assert collector.metrics["records_invalid"] == 50

        # Record writing
        collector.record_writing(files_written=5, total_bytes=1048576)
        assert collector.metrics["files_written"] == 5
        assert collector.metrics["bytes_written"] == 1048576

        # Record API calls
        collector.record_api_calls(api_calls=10, api_type="stripe")
        assert collector.metrics["api_calls"]["stripe"] == 10

        # Record errors
        collector.record_error(error_type="validation_error", error_count=2)
        assert collector.metrics["errors"]["validation_error"] == 2

        # Record retries
        collector.record_retry(attempt=1, exit_code=1)
        assert collector.metrics["retries"]["count"] == 1

        # Finish collection
        time.sleep(0.1)  # Ensure some time passes
        final_metrics = collector.finish(status="success")

        assert final_metrics["status"] == "success"
        assert final_metrics["execution_time_seconds"] > 0
        assert "records_per_second" in final_metrics

    def test_metrics_extraction_timing(self):
        """Test extraction timing metrics."""
        collector = MetricsCollector(
            job_name="test_job",
            tenant_id="test_tenant",
            connector_type="test_connector",
        )

        collector.start_extraction()
        time.sleep(0.1)
        collector.end_extraction()

        assert "extraction_duration_seconds" in collector.metrics
        assert collector.metrics["extraction_duration_seconds"] > 0

    def test_metrics_batch_recording(self):
        """Test batch metrics recording."""
        collector = MetricsCollector(
            job_name="test_job",
            tenant_id="test_tenant",
            connector_type="test_connector",
        )

        collector.record_batch(batch_size=100, processing_time=0.5)
        # Should not raise any exceptions

    def test_metrics_prometheus_disabled(self):
        """Test metrics work when Prometheus is disabled."""
        collector = MetricsCollector(
            job_name="test_job",
            tenant_id="test_tenant",
            connector_type="test_connector",
            enable_prometheus=False,
        )

        collector.start()
        collector.record_extraction(records_count=100)
        collector.finish(status="success")

        # Should complete without errors even if Prometheus is disabled
        assert collector.metrics["records_extracted"] == 100

    def test_metrics_finish_without_start(self):
        """Test finish is safe when start was not called."""
        collector = MetricsCollector(
            job_name="test_job",
            tenant_id="test_tenant",
            connector_type="test_connector",
        )

        # Finish without calling start
        metrics = collector.finish(status="failure")

        # Should return empty metrics without crashing
        assert isinstance(metrics, dict)


@pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="Prometheus client not available")
class TestPrometheusIntegration:
    """Test Prometheus integration."""

    def test_prometheus_metrics_initialized(self):
        """Test Prometheus metrics are initialized."""
        from dativo_ingest.metrics import _initialize_prometheus_metrics, _prom_metrics

        _initialize_prometheus_metrics()

        # Check key metrics exist
        assert "records_extracted_total" in _prom_metrics
        assert "job_runs_total" in _prom_metrics
        assert "job_duration_seconds" in _prom_metrics

    def test_prometheus_metrics_recorded(self):
        """Test metrics are recorded to Prometheus."""
        collector = MetricsCollector(
            job_name="test_job",
            tenant_id="test_tenant",
            connector_type="test_connector",
            enable_prometheus=True,
        )

        collector.start()
        collector.record_extraction(records_count=100)
        collector.finish(status="success")

        # Should complete without errors
        assert collector.metrics["records_extracted"] == 100


class TestMetricsServer:
    """Test metrics HTTP server."""

    def test_metrics_server_initialization(self):
        """Test metrics server can be initialized."""
        from dativo_ingest.metrics_server import MetricsServer

        server = MetricsServer(port=9999)
        assert server.port == 9999
        assert not server.is_running()

    @pytest.mark.skipif(
        not PROMETHEUS_AVAILABLE, reason="Prometheus client not available"
    )
    def test_get_metrics_text(self):
        """Test getting metrics in text format."""
        from dativo_ingest.metrics_server import get_metrics_text

        metrics_text = get_metrics_text()
        assert isinstance(metrics_text, str)


class TestOTELIntegration:
    """Test OpenTelemetry integration."""

    def test_otel_helper_initialization(self):
        """Test OTEL helper can be initialized."""
        from dativo_ingest.metrics_otel import OTELMetricsHelper

        helper = OTELMetricsHelper()
        # Should initialize without errors even if OTEL not available

    def test_otel_configure_disabled(self):
        """Test OTEL configuration when disabled."""
        import os

        from dativo_ingest.metrics_otel import configure_otel_metrics

        # Ensure OTEL is disabled
        os.environ["DATIVO_METRICS_OTEL"] = "false"

        result = configure_otel_metrics()
        assert result is False
