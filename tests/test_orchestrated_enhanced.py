"""Tests for enhanced orchestration features (v1.3.0)."""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from dativo_ingest.config import (
    FailureNotificationConfig,
    NotificationsConfig,
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
        collector = MetricsCollector("test_job", "acme", "postgres")
        collector.start()
        assert collector.start_time is not None
        assert collector.metrics["job_name"] == "test_job"
        assert collector.metrics["tenant_id"] == "acme"

    def test_metrics_collector_extraction(self):
        """Test extraction metrics recording."""
        collector = MetricsCollector("test_job", "acme", "postgres")
        collector.start()
        collector.start_extraction()
        collector.record_records(1000, phase="extracted")
        collector.end_extraction()
        assert collector.metrics["records_extracted"] == 1000
        assert "extract_seconds" in collector.metrics

    def test_metrics_collector_validation(self):
        """Test validation metrics recording."""
        collector = MetricsCollector("test_job", "acme", "postgres")
        collector.start()
        collector.record_records(1000, phase="extracted")
        collector.record_records(950, phase="written")
        collector.record_records(50, phase="invalid")
        assert collector.metrics["records_extracted"] == 1000
        assert collector.metrics["records_written"] == 950
        assert collector.metrics["records_invalid"] == 50

    def test_metrics_collector_writing(self):
        """Test writing metrics recording."""
        collector = MetricsCollector("test_job", "acme", "postgres")
        collector.start()
        collector.record_bytes(1048576, phase="written")  # 1 MB
        assert collector.metrics["bytes_written"] == 1048576

    def test_metrics_collector_finish(self):
        """Test metrics collector finish."""
        collector = MetricsCollector("test_job", "acme", "postgres")
        collector.start()
        collector.record_records(1000, phase="extracted")
        metrics = collector.finish("success")
        assert metrics["status"] == "success"
        assert "runtime_seconds" in metrics
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


class TestFailureNotificationHooks:
    """Tests for runner-level failure notification hooks."""

    def test_runner_config_loads_notifications_with_env_expansion(
        self, tmp_path, monkeypatch
    ):
        """Test RunnerConfig supports notifications and expands env variables."""
        monkeypatch.setenv(
            "SLACK_WEBHOOK_URL", "https://hooks.slack.example/services/test"
        )

        runner_path = tmp_path / "runner.yaml"
        runner_path.write_text(
            """
runner:
  mode: orchestrated
  orchestrator:
    type: dagster
    schedules:
      - name: orders_hourly
        config: /app/jobs/orders.yaml
        cron: "0 * * * *"
  notifications:
    on_failure:
      command: ["/app/scripts/notify.sh"]
      env:
        SLACK_WEBHOOK_URL: ${SLACK_WEBHOOK_URL}
"""
        )

        runner_config = RunnerConfig.from_yaml(runner_path)

        assert runner_config.notifications is not None
        assert runner_config.notifications.on_failure is not None
        assert runner_config.notifications.on_failure.command == [
            "/app/scripts/notify.sh"
        ]
        assert runner_config.notifications.on_failure.env["SLACK_WEBHOOK_URL"] == (
            "https://hooks.slack.example/services/test"
        )

    @patch("dativo_ingest.orchestrated.subprocess.run")
    def test_failure_notification_hook_receives_required_env(self, mock_subprocess):
        """Test failure hook command receives required dativo context variables."""
        from dativo_ingest.orchestrated import _run_failure_notification_hook

        schedule = ScheduleConfig(
            name="orders_hourly", config="/app/jobs/orders.yaml", cron="0 * * * *"
        )
        runner_config = RunnerConfig(
            orchestrator=OrchestratorConfig(schedules=[schedule]),
            notifications=NotificationsConfig(
                on_failure=FailureNotificationConfig(
                    command=["/app/scripts/notify.sh"],
                    env={"SLACK_WEBHOOK_URL": "${SLACK_WEBHOOK_URL}"},
                )
            ),
        )

        mock_subprocess.return_value = Mock(returncode=0, stderr="", stdout="ok")
        summary_path = Path("/tmp/state/acme/orders/runs/run-20260212T120000Z.json")

        with patch.dict(
            "os.environ",
            {"SLACK_WEBHOOK_URL": "https://hooks.slack.example/services/test"},
            clear=False,
        ):
            _run_failure_notification_hook(
                runner_config=runner_config,
                tenant_id="acme",
                schedule_name="orders_hourly",
                job_name="orders",
                run_id="20260212T120000Z",
                summary_path=summary_path,
                exit_code=2,
                error_message="Job failed",
            )

        assert mock_subprocess.call_count == 1
        command = mock_subprocess.call_args.args[0]
        hook_env = mock_subprocess.call_args.kwargs["env"]
        assert command == ["/app/scripts/notify.sh"]
        assert hook_env["SLACK_WEBHOOK_URL"] == (
            "https://hooks.slack.example/services/test"
        )
        assert hook_env["DATIVO_TENANT_ID"] == "acme"
        assert hook_env["DATIVO_JOB_NAME"] == "orders"
        assert hook_env["DATIVO_RUN_ID"] == "20260212T120000Z"
        assert hook_env["DATIVO_SUMMARY_PATH"].endswith("run-20260212T120000Z.json")

    @patch("dativo_ingest.orchestrated.get_logger")
    @patch("dativo_ingest.orchestrated.subprocess.run")
    def test_missing_failure_notification_script_is_graceful(
        self, mock_subprocess, mock_get_logger
    ):
        """Test missing notification command logs warning and does not raise."""
        from dativo_ingest.orchestrated import _run_failure_notification_hook

        schedule = ScheduleConfig(
            name="orders_hourly", config="/app/jobs/orders.yaml", cron="0 * * * *"
        )
        runner_config = RunnerConfig(
            orchestrator=OrchestratorConfig(schedules=[schedule]),
            notifications=NotificationsConfig(
                on_failure=FailureNotificationConfig(command=["/missing/notify.sh"])
            ),
        )

        mock_subprocess.side_effect = FileNotFoundError("script not found")
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        _run_failure_notification_hook(
            runner_config=runner_config,
            tenant_id="acme",
            schedule_name="orders_hourly",
            job_name="orders",
            run_id=None,
            summary_path=None,
            exit_code=2,
            error_message="Job failed",
        )

        assert mock_logger.warning.called

    @patch("dativo_ingest.orchestrated.subprocess.run")
    def test_execute_job_with_retry_tracks_run_summary_on_failure(
        self, mock_subprocess, tmp_path
    ):
        """Test failed execution captures run_id and summary path metadata."""
        from dativo_ingest.orchestrated import JobExecutionFailure, _execute_job_with_retry

        schedule = Mock()
        schedule.name = "orders_hourly"
        schedule.config = "/app/jobs/orders.yaml"

        source_config = Mock()
        source_config.type = "csv"
        source_config.object = "orders"

        job_config = Mock()
        job_config.tenant_id = "acme"
        job_config.get_source.return_value = source_config

        def _failed_run(*args, **kwargs):
            summary_dir = tmp_path / "acme" / "orders" / "runs"
            summary_dir.mkdir(parents=True, exist_ok=True)
            (summary_dir / "run-20260212T130000Z.json").write_text("{}")
            return Mock(returncode=2, stderr="boom")

        mock_subprocess.side_effect = _failed_run

        with patch.dict("os.environ", {"STATE_DIR": str(tmp_path)}, clear=False):
            with pytest.raises(JobExecutionFailure) as exc:
                _execute_job_with_retry(
                    schedule_config=schedule,
                    job_config=job_config,
                    custom_retry_policy=None,
                    summary_job_name="orders",
                )

        assert exc.value.exit_code == 2
        assert exc.value.run_id == "20260212T130000Z"
        assert exc.value.summary_path is not None
        assert str(exc.value.summary_path).endswith("run-20260212T130000Z.json")
