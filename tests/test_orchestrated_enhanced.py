"""Tests for enhanced orchestration features (v1.3.0)."""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from dativo_ingest.config import (
    OrchestratorConfig,
    RetryConfig,
    RunnerConfig,
    ScheduleConfig,
)
from dativo_ingest.metrics import MetricsCollector
from dativo_ingest.retry_policy import RetryPolicy
from dativo_ingest.tracing import get_tracer, trace_job_execution


class TestRetryConfig:
    """Tests for RetryConfig model."""

    def test_retry_config_defaults(self):
        """Test RetryConfig with default values."""
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.initial_delay_seconds == 5
        assert config.max_delay_seconds == 300
        assert config.backoff_multiplier == 2.0
        assert config.retryable_exit_codes == [1, 2]

    def test_retry_config_custom(self):
        """Test RetryConfig with custom values."""
        config = RetryConfig(
            max_retries=5,
            initial_delay_seconds=10,
            max_delay_seconds=600,
            backoff_multiplier=1.5,
            retryable_exit_codes=[2],
        )
        assert config.max_retries == 5
        assert config.initial_delay_seconds == 10
        assert config.max_delay_seconds == 600
        assert config.backoff_multiplier == 1.5
        assert config.retryable_exit_codes == [2]

    def test_retry_config_backward_compat(self):
        """Test RetryConfig backward compatibility with retry_delay_seconds."""
        config = RetryConfig(retry_delay_seconds=15)
        assert config.initial_delay_seconds == 15

    def test_retry_config_error_patterns(self):
        """Test RetryConfig with error patterns."""
        config = RetryConfig(
            retryable_error_patterns=["ConnectionError", "TimeoutError"]
        )
        assert config.retryable_error_patterns == ["ConnectionError", "TimeoutError"]


class TestRetryPolicy:
    """Tests for RetryPolicy class."""

    def test_should_retry_exit_code(self):
        """Test should_retry with exit codes."""
        config = RetryConfig(retryable_exit_codes=[1, 2])
        policy = RetryPolicy(config)

        # Should retry for exit code 1
        assert policy.should_retry(1, attempt=0) is True
        # Should retry for exit code 2
        assert policy.should_retry(2, attempt=0) is True
        # Should not retry for exit code 0
        assert policy.should_retry(0, attempt=0) is False
        # Should not retry after max retries
        assert policy.should_retry(1, attempt=3) is False

    def test_should_retry_error_patterns(self):
        """Test should_retry with error patterns."""
        config = RetryConfig(
            retryable_exit_codes=[2],
            retryable_error_patterns=["ConnectionError", "Timeout"],
        )
        policy = RetryPolicy(config)

        # Should retry if error matches pattern
        assert policy.should_retry(2, "ConnectionError occurred", attempt=0) is True
        assert policy.should_retry(2, "Timeout happened", attempt=0) is True
        # Should not retry if error doesn't match
        assert policy.should_retry(2, "Unknown error", attempt=0) is False

    def test_calculate_delay(self):
        """Test delay calculation with exponential backoff."""
        config = RetryConfig(
            initial_delay_seconds=5, backoff_multiplier=2.0, max_delay_seconds=300
        )
        policy = RetryPolicy(config)

        # Attempt 0: 5 seconds
        assert policy.calculate_delay(0) == 5
        # Attempt 1: 10 seconds (5 * 2)
        assert policy.calculate_delay(1) == 10
        # Attempt 2: 20 seconds (5 * 2^2)
        assert policy.calculate_delay(2) == 20
        # Attempt 10: capped at 300 seconds
        assert policy.calculate_delay(10) == 300

    def test_get_retry_metadata(self):
        """Test retry metadata generation."""
        config = RetryConfig(
            max_retries=3, initial_delay_seconds=5, backoff_multiplier=2.0
        )
        policy = RetryPolicy(config)

        metadata = policy.get_retry_metadata(0)
        assert metadata["retry_attempt"] == 1
        assert metadata["max_retries"] == 3
        assert metadata["delay_seconds"] == 5
        assert metadata["backoff_multiplier"] == 2.0


class TestScheduleConfig:
    """Tests for ScheduleConfig model."""

    def test_schedule_config_cron(self):
        """Test ScheduleConfig with cron expression."""
        schedule = ScheduleConfig(
            name="test_schedule", config="/app/jobs/test.yaml", cron="0 * * * *"
        )
        assert schedule.name == "test_schedule"
        assert schedule.cron == "0 * * * *"
        assert schedule.enabled is True
        assert schedule.timezone == "UTC"

    def test_schedule_config_interval(self):
        """Test ScheduleConfig with interval."""
        schedule = ScheduleConfig(
            name="test_schedule", config="/app/jobs/test.yaml", interval_seconds=3600
        )
        assert schedule.interval_seconds == 3600
        assert schedule.cron is None

    def test_schedule_config_enabled(self):
        """Test ScheduleConfig enabled flag."""
        schedule = ScheduleConfig(
            name="test_schedule",
            config="/app/jobs/test.yaml",
            cron="0 * * * *",
            enabled=False,
        )
        assert schedule.enabled is False

    def test_schedule_config_timezone(self):
        """Test ScheduleConfig timezone."""
        schedule = ScheduleConfig(
            name="test_schedule",
            config="/app/jobs/test.yaml",
            cron="0 * * * *",
            timezone="America/New_York",
        )
        assert schedule.timezone == "America/New_York"

    def test_schedule_config_tags(self):
        """Test ScheduleConfig custom tags."""
        schedule = ScheduleConfig(
            name="test_schedule",
            config="/app/jobs/test.yaml",
            cron="0 * * * *",
            tags={"environment": "production", "priority": "high"},
        )
        assert schedule.tags == {"environment": "production", "priority": "high"}

    def test_schedule_config_validation_error_both(self):
        """Test ScheduleConfig validation when both cron and interval are provided."""
        with pytest.raises(ValueError, match="Cannot specify both"):
            ScheduleConfig(
                name="test_schedule",
                config="/app/jobs/test.yaml",
                cron="0 * * * *",
                interval_seconds=3600,
            )

    def test_schedule_config_validation_error_neither(self):
        """Test ScheduleConfig validation when neither cron nor interval is provided."""
        with pytest.raises(
            ValueError, match="Either 'cron' or 'interval_seconds' must be provided"
        ):
            ScheduleConfig(name="test_schedule", config="/app/jobs/test.yaml")


class TestMetricsCollector:
    """Tests for MetricsCollector class."""

    def test_metrics_collector_start(self):
        """Test metrics collector initialization."""
        collector = MetricsCollector("test_job", "acme")
        collector.start()
        assert collector.start_time is not None
        assert collector.metrics["job_name"] == "test_job"
        assert collector.metrics["tenant_id"] == "acme"

    def test_metrics_collector_extraction(self):
        """Test extraction metrics recording."""
        collector = MetricsCollector("test_job", "acme")
        collector.start()
        collector.record_extraction(1000, 5)
        assert collector.metrics["records_extracted"] == 1000
        assert collector.metrics["files_processed"] == 5

    def test_metrics_collector_validation(self):
        """Test validation metrics recording."""
        collector = MetricsCollector("test_job", "acme")
        collector.start()
        collector.record_validation(950, 50, 1000)
        assert collector.metrics["records_valid"] == 950
        assert collector.metrics["records_invalid"] == 50
        assert collector.metrics["records_total"] == 1000

    def test_metrics_collector_writing(self):
        """Test writing metrics recording."""
        collector = MetricsCollector("test_job", "acme")
        collector.start()
        collector.record_writing(2, 1048576)  # 2 files, 1 MB
        assert collector.metrics["files_written"] == 2
        assert collector.metrics["bytes_written"] == 1048576

    def test_metrics_collector_finish(self):
        """Test metrics collector finish."""
        collector = MetricsCollector("test_job", "acme")
        collector.start()
        collector.record_extraction(1000, 5)
        metrics = collector.finish("success")
        assert metrics["status"] == "success"
        assert "execution_time_seconds" in metrics
        assert metrics["records_extracted"] == 1000


class TestTracing:
    """Tests for tracing functionality."""

    def test_get_tracer_optional(self):
        """Test that tracer is optional (works without OpenTelemetry)."""
        tracer = get_tracer()
        # Should not raise even if OpenTelemetry is not installed
        assert tracer is None or hasattr(tracer, "start_span")

    def test_trace_job_execution(self):
        """Test trace_job_execution context manager."""
        # Should not raise even if OpenTelemetry is not installed
        with trace_job_execution("test_job", "acme", "csv"):
            pass  # Context manager should work


class TestOrchestratedIntegration:
    """Integration tests for orchestrated features."""

    @patch("dativo_ingest.orchestrated.JobConfig.from_yaml")
    @patch("dativo_ingest.orchestrated.ConnectorValidator")
    def test_create_dagster_assets_with_retry(self, mock_validator, mock_job_config):
        """Test Dagster asset creation with retry policy."""
        from dativo_ingest.orchestrated import create_dagster_assets

        # Mock job config
        mock_config = Mock()
        mock_config.tenant_id = "acme"
        mock_config.retry_config = RetryConfig(max_retries=3)
        mock_config.get_source.return_value.type = "csv"
        mock_config.validate_schema_presence = Mock()
        mock_job_config.return_value = mock_config

        # Mock validator
        mock_validator_instance = Mock()
        mock_validator.return_value = mock_validator_instance

        # Create runner config
        schedule = ScheduleConfig(
            name="test_schedule", config="/app/jobs/test.yaml", cron="0 * * * *"
        )
        orchestrator = OrchestratorConfig(schedules=[schedule])
        runner_config = RunnerConfig(orchestrator=orchestrator)

        # Should not raise
        defs = create_dagster_assets(runner_config)
        assert defs is not None

    @patch("dativo_ingest.orchestrated.JobConfig.from_yaml")
    def test_create_dagster_assets_disabled_schedule(self, mock_job_config):
        """Test that disabled schedules are skipped."""
        from dativo_ingest.orchestrated import create_dagster_assets

        # Create runner config with disabled schedule
        schedule = ScheduleConfig(
            name="disabled_schedule",
            config="/app/jobs/test.yaml",
            cron="0 * * * *",
            enabled=False,
        )
        orchestrator = OrchestratorConfig(schedules=[schedule])
        runner_config = RunnerConfig(orchestrator=orchestrator)

        # Should not load job config for disabled schedule
        defs = create_dagster_assets(runner_config)
        assert len(defs.schedules) == 0
        mock_job_config.assert_not_called()

    @patch("dativo_ingest.orchestrated.JobConfig.from_yaml")
    def test_create_dagster_assets_interval_schedule(self, mock_job_config):
        """Test interval-based schedule creation."""
        from dativo_ingest.orchestrated import create_dagster_assets

        # Mock job config
        mock_config = Mock()
        mock_config.tenant_id = "acme"
        mock_config.retry_config = None
        mock_config.get_source.return_value.type = "csv"
        mock_config.validate_schema_presence = Mock()
        mock_job_config.return_value = mock_config

        # Create runner config with interval schedule
        schedule = ScheduleConfig(
            name="interval_schedule",
            config="/app/jobs/test.yaml",
            interval_seconds=3600,
        )
        orchestrator = OrchestratorConfig(schedules=[schedule])
        runner_config = RunnerConfig(orchestrator=orchestrator)

        # Should create schedule with interval
        defs = create_dagster_assets(runner_config)
        assert len(defs.schedules) == 1
