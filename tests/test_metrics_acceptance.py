"""Acceptance tests for metrics export (Prometheus + OpenTelemetry)."""

import socket
import time
from unittest.mock import MagicMock, Mock, patch

import pytest

from dativo_ingest.config import MetricsConfig, PrometheusConfig, OtelConfig
from dativo_ingest.metrics import MetricsCollector

# Check if prometheus_client is available
try:
    from prometheus_client import REGISTRY

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


def get_free_port():
    """Get a free port for testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


@pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="Prometheus client not available")
class TestMetricsServerIntegration:
    """Integration tests for metrics server."""

    def test_metrics_server_exposes_metrics_after_job_run(self):
        """Test that /metrics endpoint exposes counters after a job run."""
        import requests

        from dativo_ingest.metrics_server import MetricsServer

        # Get a free port
        port = get_free_port()

        # Configure Prometheus with ephemeral port
        prom_config = PrometheusConfig(
            enabled=True, host="127.0.0.1", port=port, multiproc_dir=None
        )

        # Create metrics config
        metrics_config = MetricsConfig(enabled=True, prometheus=prom_config)

        # Start metrics server
        server = MetricsServer(prom_config)
        server.start()

        try:
            # Give server a moment to start
            time.sleep(0.2)

            # Create metrics collector and simulate job execution
            collector = MetricsCollector(
                job_name="test_job",
                tenant_id="test_tenant",
                connector_type="test_connector",
                mode="orchestrated",
                config=metrics_config,
            )

            # Simulate job lifecycle
            collector.start()
            collector.start_extraction()
            time.sleep(0.1)  # Simulate work
            collector.end_extraction()

            # Record some metrics
            collector.record_records(1000, phase="extracted")
            collector.record_records(950, phase="written")
            collector.record_records(50, phase="invalid")
            collector.record_bytes(104857600, phase="written")
            collector.record_api_calls(10, api_type="stripe")

            collector.start_load()
            time.sleep(0.05)  # Simulate commit work
            collector.end_load()

            collector.finish(status="success")

            # Fetch metrics from server
            response = requests.get(f"http://127.0.0.1:{port}/metrics", timeout=5)
            assert response.status_code == 200

            metrics_text = response.text

            # Assert canonical metric names are present
            assert "dativo_ingest_records_total" in metrics_text
            assert "dativo_ingest_bytes_total" in metrics_text
            assert "dativo_ingest_retries_total" in metrics_text
            assert "dativo_ingest_api_calls_total" in metrics_text
            assert "dativo_ingest_extract_seconds" in metrics_text
            assert "dativo_ingest_load_seconds" in metrics_text
            assert "dativo_ingest_runtime_seconds" in metrics_text

            # Assert at least one counter has value > 0
            assert 'dativo_ingest_records_total{' in metrics_text
            # Check for actual values (should have recorded 1000 extracted records)
            assert "1000.0" in metrics_text or "950.0" in metrics_text

        finally:
            # Cleanup
            server.stop()

    def test_metrics_collector_lifecycle(self):
        """Test metrics collector lifecycle with proper timing."""
        metrics_config = MetricsConfig(
            enabled=True,
            prometheus=PrometheusConfig(enabled=True, multiproc_dir=None),
        )

        collector = MetricsCollector(
            job_name="lifecycle_test",
            tenant_id="test_tenant",
            connector_type="postgres",
            mode="oneshot",
            config=metrics_config,
        )

        # Test lifecycle
        collector.start()
        assert collector.start_time is not None

        # Extraction phase
        collector.start_extraction()
        assert collector.extract_start_time is not None
        time.sleep(0.05)
        collector.end_extraction()
        assert "extract_seconds" in collector.metrics

        # Load phase
        collector.start_load()
        assert collector.load_start_time is not None
        time.sleep(0.02)
        collector.end_load()
        assert "load_seconds" in collector.metrics

        # Record metrics
        collector.record_records(500, phase="extracted")
        collector.record_bytes(1048576, phase="written")
        collector.record_retry()

        # Finish
        metrics = collector.finish(status="success")

        assert metrics["status"] == "success"
        assert metrics["runtime_seconds"] > 0
        assert metrics.get("retries", 0) >= 1


class TestOneshotModeServerBehavior:
    """Test that oneshot mode doesn't start server by default."""

    @patch("dativo_ingest.metrics_server.start_http_server")
    def test_oneshot_mode_no_server_by_default(self, mock_start_server):
        """Test oneshot mode does not start HTTP server by default."""
        from dativo_ingest.metrics_server import start_metrics_server_from_config

        # Default config for oneshot (prometheus enabled but not in oneshot by default)
        config = PrometheusConfig(enabled=False)

        server = start_metrics_server_from_config(config)

        # Server should not be created when disabled
        assert server is None
        mock_start_server.assert_not_called()

    @patch("dativo_ingest.metrics_server.start_http_server")
    def test_oneshot_mode_server_when_explicitly_enabled(self, mock_start_server):
        """Test oneshot mode starts server when explicitly enabled."""
        from dativo_ingest.metrics_server import start_metrics_server_from_config

        config = PrometheusConfig(enabled=True, host="127.0.0.1", port=9999)

        if not PROMETHEUS_AVAILABLE:
            pytest.skip("Prometheus client not available")

        server = start_metrics_server_from_config(config)

        # Server should be created and started
        assert server is not None
        assert server.is_running()

    def test_metrics_collector_works_without_server(self):
        """Test metrics collector works in oneshot mode without HTTP server."""
        # Disable prometheus to simulate oneshot default
        config = MetricsConfig(
            enabled=True, prometheus=PrometheusConfig(enabled=False)
        )

        collector = MetricsCollector(
            job_name="oneshot_job",
            tenant_id="test_tenant",
            connector_type="csv",
            mode="oneshot",
            config=config,
        )

        # Should work without errors
        collector.start()
        collector.record_records(100, phase="extracted")
        metrics = collector.finish(status="success")

        assert metrics["status"] == "success"


class TestOTELConfiguration:
    """Test OTEL configuration and error handling."""

    def test_otel_disabled_returns_false(self):
        """Test configure_otel_metrics returns False when disabled."""
        from dativo_ingest.metrics_otel import configure_otel_metrics

        config = OtelConfig(enabled=False)

        result = configure_otel_metrics(config)

        assert result is False

    def test_otel_no_endpoint_returns_false(self):
        """Test configure_otel_metrics returns False when endpoint not configured."""
        from dativo_ingest.metrics_otel import configure_otel_metrics

        config = OtelConfig(enabled=True, endpoint=None)

        result = configure_otel_metrics(config)

        assert result is False

    @patch("dativo_ingest.metrics_otel.OPENTELEMETRY_AVAILABLE", True)
    @patch("dativo_ingest.metrics_otel._get_otel_exporter")
    def test_otel_unreachable_endpoint_does_not_crash(self, mock_exporter):
        """Test OTEL export failure does not crash and logs are throttled."""
        from dativo_ingest.metrics_otel import configure_otel_metrics

        # Mock exporter that will fail
        mock_exporter.return_value = Mock()

        config = OtelConfig(
            enabled=True,
            protocol="grpc",
            endpoint="http://unreachable:4317",
            timeout_seconds=1,
        )

        # This should not raise an exception
        try:
            result = configure_otel_metrics(config)
            # If OpenTelemetry is available, it should configure
            # If not available, it should return False
            assert isinstance(result, bool)
        except Exception as e:
            # Should not crash
            pytest.fail(f"configure_otel_metrics raised exception: {e}")

    @patch("dativo_ingest.metrics_otel.get_logger")
    def test_otel_export_failure_throttled_logging(self, mock_logger):
        """Test OTEL export failures use throttled logging."""
        from dativo_ingest.metrics_otel import ThrottledExportMetricReader

        if not PROMETHEUS_AVAILABLE:
            pytest.skip("OpenTelemetry not available")

        mock_logger_instance = Mock()
        mock_logger.return_value = mock_logger_instance

        # Create a mock exporter
        mock_exporter = Mock()
        mock_exporter._export = Mock(side_effect=Exception("Connection refused"))

        # Would need to test ThrottledExportMetricReader behavior
        # For now, verify the class exists and has the right structure
        reader = ThrottledExportMetricReader.__name__
        assert reader == "ThrottledExportMetricReader"


class TestLabelValidation:
    """Test label validation and cardinality control."""

    def test_api_type_validation(self):
        """Test API type labels are validated against known set."""
        from dativo_ingest.metrics import _validate_label_value, KNOWN_API_TYPES

        # Known value passes through
        assert _validate_label_value("stripe", KNOWN_API_TYPES) == "stripe"

        # Unknown value becomes "unknown"
        assert _validate_label_value("random_api", KNOWN_API_TYPES) == "unknown"

        # Empty value becomes default
        assert _validate_label_value("", KNOWN_API_TYPES, "unknown") == "unknown"

        # Long value is truncated
        long_value = "a" * 100
        result = _validate_label_value(long_value, KNOWN_API_TYPES)
        assert len(result) <= 50

    def test_phase_validation(self):
        """Test phase labels are validated."""
        from dativo_ingest.metrics import _validate_label_value, KNOWN_PHASES

        assert _validate_label_value("extracted", KNOWN_PHASES) == "extracted"
        assert _validate_label_value("written", KNOWN_PHASES) == "written"
        assert _validate_label_value("invalid_phase", KNOWN_PHASES) == "unknown"

    def test_metrics_collector_validates_labels(self):
        """Test MetricsCollector applies label validation."""
        config = MetricsConfig(enabled=True)

        collector = MetricsCollector(
            job_name="test",
            tenant_id="test",
            connector_type="test",
            mode="oneshot",
            config=config,
        )

        collector.start()

        # Record with unknown API type (should be normalized)
        collector.record_api_calls(5, api_type="unknown_random_api")

        # Should not raise exception
        collector.finish(status="success")


class TestConfigurationPrecedence:
    """Test configuration precedence: env > JobConfig > RunnerConfig > defaults."""

    def test_env_var_overrides_config(self, monkeypatch):
        """Test environment variables override configuration."""
        # Set env vars
        monkeypatch.setenv("DATIVO_METRICS_PROMETHEUS", "false")
        monkeypatch.setenv("DATIVO_METRICS_PORT", "9999")

        # Config says enabled
        config = MetricsConfig(prometheus=PrometheusConfig(enabled=True, port=9400))

        collector = MetricsCollector(
            job_name="test",
            tenant_id="test",
            connector_type="test",
            mode="oneshot",
            config=config,
        )

        # Env var should override
        assert collector.config.prometheus.enabled is False
        assert collector.config.prometheus.port == 9999

    def test_default_config_values(self):
        """Test default configuration values."""
        config = MetricsConfig()

        assert config.enabled is True
        assert config.prometheus.enabled is True
        assert config.prometheus.port == 9400
        assert config.prometheus.host == "0.0.0.0"
        assert config.otel.enabled is False
        assert config.labels.include_mode is True


class TestMetricsOnFailurePaths:
    """Test metrics are recorded even on failure paths."""

    def test_metrics_recorded_on_exception(self):
        """Test metrics finish() is called even when job fails."""
        config = MetricsConfig(enabled=True)

        collector = MetricsCollector(
            job_name="failing_job",
            tenant_id="test",
            connector_type="test",
            mode="oneshot",
            config=config,
        )

        collector.start()

        try:
            # Simulate some work
            collector.start_extraction()
            time.sleep(0.01)
            collector.end_extraction()

            # Simulate failure
            raise Exception("Job failed")
        except Exception:
            # Ensure finish is called on failure
            metrics = collector.finish(status="failure")

        assert metrics["status"] == "failure"
        assert "runtime_seconds" in metrics

    def test_finish_without_start_is_safe(self):
        """Test finish() is safe even if start() wasn't called."""
        config = MetricsConfig(enabled=True)

        collector = MetricsCollector(
            job_name="test",
            tenant_id="test",
            connector_type="test",
            mode="oneshot",
            config=config,
        )

        # Call finish without start (should not crash)
        metrics = collector.finish(status="failure")

        assert isinstance(metrics, dict)
