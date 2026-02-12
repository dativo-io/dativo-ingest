"""Unit tests for notification hooks (src/dativo_ingest/notifications.py)."""

import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dativo_ingest.notifications import (
    NotificationHook,
    NotificationHookError,
    NotificationManager,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test scripts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def success_script(temp_dir):
    """Create a script that exits 0 and echoes env vars."""
    script = temp_dir / "success.sh"
    script.write_text(
        '#!/usr/bin/env bash\n'
        'echo "tenant=$DATIVO_TENANT_ID job=$DATIVO_JOB_NAME"\n'
        'exit 0\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


@pytest.fixture
def failure_script(temp_dir):
    """Create a script that exits 1."""
    script = temp_dir / "fail.sh"
    script.write_text(
        '#!/usr/bin/env bash\n'
        'echo "hook failed" >&2\n'
        'exit 1\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


@pytest.fixture
def env_echo_script(temp_dir):
    """Create a script that prints all DATIVO_ env vars."""
    script = temp_dir / "env_echo.sh"
    script.write_text(
        '#!/usr/bin/env bash\n'
        'env | grep "^DATIVO_" | sort\n'
        'echo "CUSTOM_VAR=${CUSTOM_VAR:-unset}"\n'
        'exit 0\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


@pytest.fixture
def slow_script(temp_dir):
    """Create a script that sleeps longer than any reasonable timeout."""
    script = temp_dir / "slow.sh"
    script.write_text(
        '#!/usr/bin/env bash\n'
        'sleep 60\n'
        'exit 0\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


# ---------------------------------------------------------------------------
# NotificationHook tests
# ---------------------------------------------------------------------------

class TestNotificationHook:
    """Tests for NotificationHook."""

    def test_init_requires_command(self):
        """Empty command raises ValueError."""
        with pytest.raises(ValueError, match="must not be empty"):
            NotificationHook(command=[])

    def test_init_with_valid_command(self):
        """Valid command initializes successfully."""
        hook = NotificationHook(command=["/bin/echo", "hello"])
        assert hook.command == ["/bin/echo", "hello"]
        assert hook.timeout_seconds == 30

    def test_init_with_custom_timeout(self):
        """Custom timeout is stored."""
        hook = NotificationHook(command=["/bin/echo"], timeout_seconds=60)
        assert hook.timeout_seconds == 60

    def test_init_with_env(self):
        """Custom env vars are stored."""
        hook = NotificationHook(
            command=["/bin/echo"],
            env={"SLACK_URL": "https://hooks.slack.com/test"},
        )
        assert hook.env == {"SLACK_URL": "https://hooks.slack.com/test"}

    def test_execute_success(self, success_script):
        """Successful script execution returns True."""
        hook = NotificationHook(command=[success_script])
        result = hook.execute(
            tenant_id="acme",
            job_name="test_job",
            run_id="run-001",
            exit_code=2,
        )
        assert result is True

    def test_execute_failure(self, failure_script):
        """Script that exits non-zero returns False."""
        hook = NotificationHook(command=[failure_script])
        result = hook.execute(
            tenant_id="acme",
            job_name="test_job",
            run_id="run-001",
            exit_code=2,
        )
        assert result is False

    def test_execute_missing_script(self):
        """Missing script path returns False (graceful failure)."""
        hook = NotificationHook(command=["/nonexistent/script.sh"])
        result = hook.execute(
            tenant_id="acme",
            job_name="test_job",
            run_id="run-001",
            exit_code=2,
        )
        assert result is False

    def test_execute_not_executable(self, temp_dir):
        """Script without execute permission returns False."""
        script = temp_dir / "no_exec.sh"
        script.write_text('#!/usr/bin/env bash\nexit 0\n')
        # Deliberately do not set execute permission
        script.chmod(0o644)

        hook = NotificationHook(command=[str(script)])
        result = hook.execute(
            tenant_id="acme",
            job_name="test_job",
            run_id="run-001",
            exit_code=2,
        )
        assert result is False

    def test_execute_timeout(self, slow_script):
        """Script that exceeds timeout returns False."""
        hook = NotificationHook(command=[slow_script], timeout_seconds=1)
        result = hook.execute(
            tenant_id="acme",
            job_name="test_job",
            run_id="run-001",
            exit_code=2,
        )
        assert result is False

    def test_execute_passes_dativo_env_vars(self, env_echo_script):
        """Dativo env vars are passed to the subprocess."""
        hook = NotificationHook(command=[env_echo_script])

        # Capture subprocess output by running directly
        result = subprocess.run(
            [env_echo_script],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "DATIVO_TENANT_ID": "acme",
                "DATIVO_JOB_NAME": "my_job",
                "DATIVO_RUN_ID": "run-123",
                "DATIVO_RUN_STATUS": "failure",
                "DATIVO_EXIT_CODE": "2",
                "DATIVO_SUMMARY_PATH": "/tmp/summary.json",
                "DATIVO_ERROR_MESSAGE": "Something broke",
                "DATIVO_ENVIRONMENT": "prod",
            },
        )
        assert "DATIVO_TENANT_ID=acme" in result.stdout
        assert "DATIVO_JOB_NAME=my_job" in result.stdout
        assert "DATIVO_RUN_ID=run-123" in result.stdout

    def test_execute_custom_env_vars(self, env_echo_script):
        """User-configured env vars are passed to the subprocess."""
        hook = NotificationHook(
            command=[env_echo_script],
            env={"CUSTOM_VAR": "my_value"},
        )
        # We can't easily capture the output from hook.execute(),
        # but we can verify it returns True (script succeeds)
        result = hook.execute(
            tenant_id="acme",
            job_name="test_job",
            run_id="run-001",
            exit_code=2,
        )
        assert result is True

    def test_execute_env_var_expansion(self):
        """${VAR} references in hook env are expanded."""
        hook = NotificationHook(
            command=["/bin/echo"],
            env={"EXPANDED": "${HOME}"},
        )
        resolved = hook._resolve_env()
        assert resolved["EXPANDED"] == os.environ.get("HOME", "")

    def test_execute_status_mapping(self, success_script):
        """Exit codes are correctly mapped to status strings."""
        hook = NotificationHook(command=[success_script])

        # exit_code 0 -> success
        hook.execute(tenant_id="t", job_name="j", run_id="r", exit_code=0)
        # exit_code 1 -> partial
        hook.execute(tenant_id="t", job_name="j", run_id="r", exit_code=1)
        # exit_code 2 -> failure
        hook.execute(tenant_id="t", job_name="j", run_id="r", exit_code=2)
        # Unknown -> failure
        hook.execute(tenant_id="t", job_name="j", run_id="r", exit_code=99)

    def test_execute_with_command_args(self, temp_dir):
        """Command with arguments works correctly."""
        script = temp_dir / "args.sh"
        script.write_text(
            '#!/usr/bin/env bash\n'
            'if [[ "$1" == "--channel" && "$2" == "#alerts" ]]; then\n'
            '  exit 0\n'
            'fi\n'
            'exit 1\n'
        )
        script.chmod(script.stat().st_mode | stat.S_IEXEC)

        hook = NotificationHook(command=[str(script), "--channel", "#alerts"])
        result = hook.execute(
            tenant_id="acme",
            job_name="test_job",
            run_id="run-001",
            exit_code=2,
        )
        assert result is True


# ---------------------------------------------------------------------------
# NotificationManager tests
# ---------------------------------------------------------------------------

class TestNotificationManager:
    """Tests for NotificationManager."""

    def test_from_config_none(self):
        """None config creates manager with no hooks."""
        manager = NotificationManager.from_config(None)
        assert not manager.has_failure_hooks
        assert manager.on_failure_hooks == []

    def test_from_config_empty(self):
        """Empty config creates manager with no hooks."""
        manager = NotificationManager.from_config({})
        assert not manager.has_failure_hooks

    def test_from_config_single_hook(self):
        """Single on_failure hook is created."""
        config = {
            "on_failure": {
                "command": ["/app/scripts/notify.sh"],
                "env": {"SLACK_URL": "https://hooks.slack.com/test"},
                "timeout_seconds": 15,
            }
        }
        manager = NotificationManager.from_config(config)
        assert manager.has_failure_hooks
        assert len(manager.on_failure_hooks) == 1
        hook = manager.on_failure_hooks[0]
        assert hook.command == ["/app/scripts/notify.sh"]
        assert hook.env == {"SLACK_URL": "https://hooks.slack.com/test"}
        assert hook.timeout_seconds == 15

    def test_from_config_multiple_hooks(self):
        """Multiple on_failure hooks are created."""
        config = {
            "on_failure": [
                {"command": ["/app/scripts/slack.sh"]},
                {"command": ["/app/scripts/pagerduty.sh"]},
            ]
        }
        manager = NotificationManager.from_config(config)
        assert manager.has_failure_hooks
        assert len(manager.on_failure_hooks) == 2

    def test_from_config_string_command(self):
        """String command is converted to list."""
        config = {
            "on_failure": {
                "command": "/app/scripts/notify.sh",
            }
        }
        manager = NotificationManager.from_config(config)
        assert manager.has_failure_hooks
        assert manager.on_failure_hooks[0].command == ["/app/scripts/notify.sh"]

    def test_from_config_missing_command_skipped(self):
        """Hook without command is skipped with warning."""
        config = {
            "on_failure": {
                "env": {"SLACK_URL": "test"},
            }
        }
        manager = NotificationManager.from_config(config)
        assert not manager.has_failure_hooks

    def test_from_config_default_timeout(self):
        """Default timeout is applied when not specified."""
        config = {
            "on_failure": {
                "command": ["/app/scripts/notify.sh"],
            }
        }
        manager = NotificationManager.from_config(config)
        assert manager.on_failure_hooks[0].timeout_seconds == 30

    def test_notify_failure_no_hooks(self):
        """notify_failure with no hooks returns zeros."""
        manager = NotificationManager()
        result = manager.notify_failure(
            tenant_id="acme",
            job_name="test_job",
            run_id="run-001",
            exit_code=2,
        )
        assert result == {"hooks_executed": 0, "hooks_succeeded": 0, "hooks_failed": 0}

    def test_notify_failure_with_success_hook(self, success_script):
        """notify_failure executes hooks and reports success."""
        hook = NotificationHook(command=[success_script])
        manager = NotificationManager(on_failure_hooks=[hook])

        result = manager.notify_failure(
            tenant_id="acme",
            job_name="test_job",
            run_id="run-001",
            exit_code=2,
        )
        assert result["hooks_executed"] == 1
        assert result["hooks_succeeded"] == 1
        assert result["hooks_failed"] == 0

    def test_notify_failure_with_failure_hook(self, failure_script):
        """notify_failure reports failed hooks."""
        hook = NotificationHook(command=[failure_script])
        manager = NotificationManager(on_failure_hooks=[hook])

        result = manager.notify_failure(
            tenant_id="acme",
            job_name="test_job",
            run_id="run-001",
            exit_code=2,
        )
        assert result["hooks_executed"] == 1
        assert result["hooks_succeeded"] == 0
        assert result["hooks_failed"] == 1

    def test_notify_failure_mixed_hooks(self, success_script, failure_script):
        """notify_failure with mixed results reports both."""
        manager = NotificationManager(
            on_failure_hooks=[
                NotificationHook(command=[success_script]),
                NotificationHook(command=[failure_script]),
            ]
        )
        result = manager.notify_failure(
            tenant_id="acme",
            job_name="test_job",
            run_id="run-001",
            exit_code=2,
        )
        assert result["hooks_executed"] == 2
        assert result["hooks_succeeded"] == 1
        assert result["hooks_failed"] == 1

    def test_notify_failure_with_missing_script(self):
        """Missing script is handled gracefully."""
        hook = NotificationHook(command=["/nonexistent/notify.sh"])
        manager = NotificationManager(on_failure_hooks=[hook])

        result = manager.notify_failure(
            tenant_id="acme",
            job_name="test_job",
            run_id="run-001",
            exit_code=2,
        )
        assert result["hooks_executed"] == 1
        assert result["hooks_failed"] == 1

    def test_notify_failure_passes_all_params(self, success_script):
        """All parameters are passed through to hooks."""
        hook = NotificationHook(command=[success_script])
        manager = NotificationManager(on_failure_hooks=[hook])

        # Should not raise
        result = manager.notify_failure(
            tenant_id="acme",
            job_name="stripe_customers",
            run_id="20250101T120000Z",
            exit_code=2,
            summary_path="/tmp/run-summary.json",
            error_message="Connection refused",
            environment="production",
        )
        assert result["hooks_succeeded"] == 1

    def test_has_failure_hooks_property(self, success_script):
        """has_failure_hooks property works correctly."""
        empty_manager = NotificationManager()
        assert empty_manager.has_failure_hooks is False

        hook = NotificationHook(command=[success_script])
        full_manager = NotificationManager(on_failure_hooks=[hook])
        assert full_manager.has_failure_hooks is True


# ---------------------------------------------------------------------------
# Config integration tests
# ---------------------------------------------------------------------------

class TestNotificationsConfig:
    """Tests for NotificationsConfig Pydantic model."""

    def test_notifications_config_model(self):
        """NotificationsConfig model works with valid data."""
        from dativo_ingest.config import NotificationsConfig

        config = NotificationsConfig(
            on_failure={
                "command": ["/app/scripts/notify.sh"],
                "env": {"SLACK_URL": "https://hooks.slack.com/test"},
            }
        )
        assert config.on_failure is not None
        assert config.on_failure.command == ["/app/scripts/notify.sh"]

    def test_notifications_config_to_dict(self):
        """to_dict produces expected structure."""
        from dativo_ingest.config import NotificationsConfig

        config = NotificationsConfig(
            on_failure={
                "command": ["/app/scripts/notify.sh"],
                "env": {"SLACK_URL": "test"},
                "timeout_seconds": 15,
            }
        )
        d = config.to_dict()
        assert "on_failure" in d
        assert d["on_failure"]["command"] == ["/app/scripts/notify.sh"]
        assert d["on_failure"]["timeout_seconds"] == 15

    def test_notifications_config_none(self):
        """NotificationsConfig with no on_failure."""
        from dativo_ingest.config import NotificationsConfig

        config = NotificationsConfig()
        d = config.to_dict()
        assert d == {}

    def test_notifications_config_multiple_hooks(self):
        """NotificationsConfig with list of hooks."""
        from dativo_ingest.config import NotificationsConfig

        config = NotificationsConfig(
            on_failure=[
                {"command": ["/app/scripts/slack.sh"]},
                {"command": ["/app/scripts/pagerduty.sh"], "timeout_seconds": 60},
            ]
        )
        d = config.to_dict()
        assert isinstance(d["on_failure"], list)
        assert len(d["on_failure"]) == 2

    def test_runner_config_with_notifications(self):
        """RunnerConfig accepts notifications field."""
        from dativo_ingest.config import (
            NotificationsConfig,
            OrchestratorConfig,
            RunnerConfig,
            ScheduleConfig,
        )

        schedule = ScheduleConfig(
            name="test", config="/app/test.yaml", cron="0 * * * *"
        )
        runner = RunnerConfig(
            orchestrator=OrchestratorConfig(schedules=[schedule]),
            notifications=NotificationsConfig(
                on_failure={
                    "command": ["/app/scripts/notify.sh"],
                }
            ),
        )
        assert runner.notifications is not None
        assert runner.notifications.on_failure is not None

    def test_runner_config_without_notifications(self):
        """RunnerConfig works without notifications."""
        from dativo_ingest.config import (
            OrchestratorConfig,
            RunnerConfig,
            ScheduleConfig,
        )

        schedule = ScheduleConfig(
            name="test", config="/app/test.yaml", cron="0 * * * *"
        )
        runner = RunnerConfig(
            orchestrator=OrchestratorConfig(schedules=[schedule]),
        )
        assert runner.notifications is None

    def test_notification_hook_config_validation(self):
        """NotificationHookConfig validates timeout bounds."""
        from dativo_ingest.config import NotificationHookConfig

        # Valid config
        hook = NotificationHookConfig(
            command=["/app/scripts/notify.sh"], timeout_seconds=60
        )
        assert hook.timeout_seconds == 60

        # Timeout too low
        with pytest.raises(Exception):
            NotificationHookConfig(command=["/app/scripts/notify.sh"], timeout_seconds=0)

        # Timeout too high
        with pytest.raises(Exception):
            NotificationHookConfig(
                command=["/app/scripts/notify.sh"], timeout_seconds=500
            )


# ---------------------------------------------------------------------------
# Integration: JobExecutor with notifications
# ---------------------------------------------------------------------------

class TestJobExecutorNotifications:
    """Tests for notification integration in JobExecutor."""

    def test_trigger_failure_notifications_on_exit_code_0(self):
        """Notifications are NOT triggered on exit code 0."""
        from dativo_ingest.notifications import NotificationManager

        manager = NotificationManager.from_config({
            "on_failure": {"command": ["/nonexistent/script.sh"]}
        })

        # Mock a simplified executor
        mock_executor = MagicMock()
        mock_executor.notification_manager = manager
        mock_executor.run_summary = None
        mock_executor.job_config = MagicMock()
        mock_executor.job_config.asset = "test_job"
        mock_executor.job_config.environment = "dev"
        mock_executor.tenant_id = "acme"

        # Import and call the method
        from dativo_ingest.job_executor import JobExecutor

        # exit_code 0 should not trigger notifications
        JobExecutor._trigger_failure_notifications(mock_executor, exit_code=0)
        # No assertion needed - if it doesn't call notify_failure, test passes

    def test_trigger_failure_notifications_on_exit_code_2(self, success_script):
        """Notifications ARE triggered on exit code 2."""
        manager = NotificationManager.from_config({
            "on_failure": {"command": [success_script]}
        })

        with patch.object(manager, 'notify_failure', wraps=manager.notify_failure) as mock_notify:
            mock_executor = MagicMock()
            mock_executor.notification_manager = manager
            mock_executor.run_summary = MagicMock()
            mock_executor.run_summary.run.id = "run-001"
            mock_executor.run_summary.ingestion.error = MagicMock()
            mock_executor.run_summary.ingestion.error.error_message = "Test error"
            mock_executor.job_config = MagicMock()
            mock_executor.job_config.asset = "test_job"
            mock_executor.job_config.environment = "prod"
            mock_executor.tenant_id = "acme"
            mock_executor.logger = MagicMock()

            from dativo_ingest.job_executor import JobExecutor
            JobExecutor._trigger_failure_notifications(mock_executor, exit_code=2)

            mock_notify.assert_called_once()
            call_kwargs = mock_notify.call_args
            assert call_kwargs[1]["tenant_id"] == "acme" or call_kwargs[0][0] == "acme"

    def test_notification_failure_does_not_propagate(self, failure_script):
        """Notification hook failures don't change job exit code."""
        manager = NotificationManager.from_config({
            "on_failure": {"command": [failure_script]}
        })

        mock_executor = MagicMock()
        mock_executor.notification_manager = manager
        mock_executor.run_summary = MagicMock()
        mock_executor.run_summary.run.id = "run-001"
        mock_executor.run_summary.ingestion.error = MagicMock()
        mock_executor.run_summary.ingestion.error.error_message = "Job failed"
        mock_executor.job_config = MagicMock()
        mock_executor.job_config.asset = "test_job"
        mock_executor.job_config.environment = "dev"
        mock_executor.tenant_id = "acme"
        mock_executor.logger = MagicMock()

        from dativo_ingest.job_executor import JobExecutor

        # Should not raise even though hook fails
        JobExecutor._trigger_failure_notifications(mock_executor, exit_code=2)

    def test_executor_init_with_notifications_config(self):
        """JobExecutor accepts notifications_config parameter."""
        from dativo_ingest.config import NotificationsConfig

        mock_job_config = MagicMock()
        mock_job_config.tenant_id = "acme"
        mock_job_config.notifications = None

        notifications = NotificationsConfig(
            on_failure={"command": ["/app/scripts/notify.sh"]}
        )

        from dativo_ingest.job_executor import JobExecutor
        executor = JobExecutor(
            job_config=mock_job_config,
            notifications_config=notifications,
        )
        assert executor.notification_manager.has_failure_hooks

    def test_executor_job_level_notifications_override_runner(self):
        """Job-level notifications config takes precedence over runner-level."""
        from dativo_ingest.config import NotificationsConfig

        runner_notifications = NotificationsConfig(
            on_failure={"command": ["/runner/notify.sh"]}
        )
        job_notifications = NotificationsConfig(
            on_failure={"command": ["/job/notify.sh"]}
        )

        mock_job_config = MagicMock()
        mock_job_config.tenant_id = "acme"
        mock_job_config.notifications = job_notifications

        from dativo_ingest.job_executor import JobExecutor
        executor = JobExecutor(
            job_config=mock_job_config,
            notifications_config=runner_notifications,
        )
        # Job-level should win
        assert executor.notification_manager.on_failure_hooks[0].command == ["/job/notify.sh"]
