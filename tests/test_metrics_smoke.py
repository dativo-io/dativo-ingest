"""Smoke tests for metrics - basic functionality checks."""

import pytest

from dativo_ingest.config import MetricsConfig, OtelConfig, PrometheusConfig


class TestMetricsSmoke:
    """Smoke tests for metrics functionality."""

    def test_metrics_config_can_be_created(self):
        """Smoke test: MetricsConfig can be instantiated."""
        config = MetricsConfig(
            enabled=True,
            prometheus=PrometheusConfig(enabled=True, port=9400),
            otel=OtelConfig(enabled=False),
        )

        assert config.enabled is True
        assert config.prometheus.enabled is True
        assert config.prometheus.port == 9400
        assert config.otel.enabled is False

    def test_metrics_collector_can_be_imported(self):
        """Smoke test: MetricsCollector can be imported."""
        from dativo_ingest.metrics import MetricsCollector

        assert MetricsCollector is not None

    def test_metrics_server_can_be_imported(self):
        """Smoke test: MetricsServer can be imported."""
        from dativo_ingest.metrics_server import MetricsServer

        assert MetricsServer is not None

    def test_metrics_otel_can_be_imported(self):
        """Smoke test: OTEL module can be imported."""
        from dativo_ingest.metrics_otel import configure_otel_metrics

        assert configure_otel_metrics is not None

    def test_basic_metrics_collection_works(self):
        """Smoke test: Basic metrics collection works end-to-end."""
        from dativo_ingest.metrics import MetricsCollector

        config = MetricsConfig(enabled=True)
        collector = MetricsCollector(
            job_name="smoke_test",
            tenant_id="test",
            connector_type="test",
            mode="oneshot",
            config=config,
        )

        # Basic workflow
        collector.start()
        collector.record_records(10, phase="extracted")
        metrics = collector.finish(status="success")

        assert metrics["status"] == "success"

    def test_prometheus_metrics_available_check(self):
        """Smoke test: Check if Prometheus is available."""
        from dativo_ingest.metrics import PROMETHEUS_AVAILABLE

        # Just verify the flag exists
        assert isinstance(PROMETHEUS_AVAILABLE, bool)

    def test_metrics_collector_doesnt_crash_without_prometheus(self):
        """Smoke test: Collector works even if Prometheus not installed."""
        from dativo_ingest.metrics import MetricsCollector

        config = MetricsConfig(
            enabled=True,
            prometheus=PrometheusConfig(enabled=False)
        )
        collector = MetricsCollector(
            job_name="test",
            tenant_id="test",
            connector_type="test",
            mode="oneshot",
            config=config,
        )

        # Should not crash
        collector.start()
        collector.finish(status="success")

    def test_otel_disabled_by_default(self):
        """Smoke test: OTEL is disabled by default."""
        config = MetricsConfig()

        assert config.otel.enabled is False

    def test_prometheus_enabled_by_default(self):
        """Smoke test: Prometheus is enabled by default."""
        config = MetricsConfig()

        assert config.prometheus.enabled is True

    def test_default_port_is_9400(self):
        """Smoke test: Default Prometheus port is 9400."""
        config = MetricsConfig()

        assert config.prometheus.port == 9400

    def test_metrics_can_be_disabled(self):
        """Smoke test: Metrics can be disabled."""
        from dativo_ingest.metrics import MetricsCollector

        config = MetricsConfig(enabled=False)
        collector = MetricsCollector(
            job_name="test",
            tenant_id="test",
            connector_type="test",
            mode="oneshot",
            config=config,
        )

        # Should work without errors
        collector.start()
        collector.record_records(100, phase="extracted")
        collector.finish(status="success")

    def test_orchestrated_mode_label(self):
        """Smoke test: Orchestrated mode sets correct label."""
        from dativo_ingest.metrics import MetricsCollector

        config = MetricsConfig(enabled=True)
        collector = MetricsCollector(
            job_name="test",
            tenant_id="test",
            connector_type="test",
            mode="orchestrated",
            config=config,
        )

        assert collector.mode == "orchestrated"
        assert collector.labels["mode"] == "orchestrated"

    def test_oneshot_mode_label(self):
        """Smoke test: Oneshot mode sets correct label."""
        from dativo_ingest.metrics import MetricsCollector

        config = MetricsConfig(enabled=True)
        collector = MetricsCollector(
            job_name="test",
            tenant_id="test",
            connector_type="test",
            mode="oneshot",
            config=config,
        )

        assert collector.mode == "oneshot"
        assert collector.labels["mode"] == "oneshot"

    def test_all_metric_record_methods_exist(self):
        """Smoke test: All record methods exist and don't crash."""
        from dativo_ingest.metrics import MetricsCollector

        config = MetricsConfig(enabled=True)
        collector = MetricsCollector(
            job_name="test",
            tenant_id="test",
            connector_type="test",
            mode="oneshot",
            config=config,
        )

        collector.start()

        # All these should exist and not crash
        collector.record_records(100, phase="extracted")
        collector.record_bytes(1024, phase="written")
        collector.record_api_calls(5, api_type="test")
        collector.record_retry()
        collector.start_extraction()
        collector.end_extraction()
        collector.start_load()
        collector.end_load()
        collector.finish(status="success")

        # If we got here, all methods exist and work
        assert True
