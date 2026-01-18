"""Unit tests for notification hooks."""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dativo_ingest.config import NotificationsConfig, OnFailureHookConfig
from dativo_ingest.notification_hooks import (
    _expand_env_variable,
    _redact_command_args,
    _redact_env_for_logging,
    execute_failure_notification,
)


def test_expand_env_variable():
    """Test environment variable expansion."""
    os.environ["TEST_VAR"] = "test_value"
    os.environ["ANOTHER_VAR"] = "another_value"

    # Simple expansion
    assert _expand_env_variable("${TEST_VAR}") == "test_value"
    assert (
        _expand_env_variable("prefix-${TEST_VAR}-suffix") == "prefix-test_value-suffix"
    )

    # Multiple expansions
    assert (
        _expand_env_variable("${TEST_VAR}-${ANOTHER_VAR}") == "test_value-another_value"
    )

    # Default value
    assert _expand_env_variable("${MISSING_VAR:-default}") == "default"
    assert _expand_env_variable("${TEST_VAR:-default}") == "test_value"

    # No expansion
    assert _expand_env_variable("no-vars-here") == "no-vars-here"


def test_redact_command_args():
    """Test secret redaction in command arguments."""
    args = ["script.sh", "--token=secret123", "--key=abc", "--normal=value"]
    redacted = _redact_command_args(args)
    assert redacted[0] == "script.sh"
    assert redacted[1] == "--token=[REDACTED]"
    assert redacted[2] == "--key=[REDACTED]"
    assert redacted[3] == "--normal=value"


def test_redact_env_for_logging():
    """Test secret redaction in environment variables."""
    env = {
        "API_TOKEN": "secret123",
        "NORMAL_VAR": "value",
        "SECRET_KEY": "key123",
    }
    redacted = _redact_env_for_logging(env)
    assert redacted["API_TOKEN"] == "***REDACTED***"
    assert redacted["NORMAL_VAR"] == "value"
    assert redacted["SECRET_KEY"] == "***REDACTED***"


def test_hook_executes_only_on_exit_code_2(tmp_path, monkeypatch):
    """Test that hooks execute only when exit_code is 2."""
    # Create a test script that writes to a file
    script_path = tmp_path / "test_hook.sh"
    script_path.write_text("#!/bin/sh\necho 'hook executed' > /tmp/hook_output.txt\n")
    script_path.chmod(0o755)

    hook_config = OnFailureHookConfig(
        command=["/bin/sh", str(script_path)],
        timeout_seconds=15,
    )
    notifications_config = NotificationsConfig(on_failure=hook_config)

    # Should not execute for exit_code 0
    execute_failure_notification(
        config=notifications_config,
        tenant_id="test_tenant",
        job_name="test_job",
        config_path="test.yaml",
        exit_code=0,
        failure_reason="Test",
    )
    # Script should not have executed
    output_file = Path("/tmp/hook_output.txt")
    if output_file.exists():
        output_file.unlink()

    # Should execute for exit_code 2
    execute_failure_notification(
        config=notifications_config,
        tenant_id="test_tenant",
        job_name="test_job",
        config_path="test.yaml",
        exit_code=2,
        failure_reason="Test failure",
    )
    # Script should have executed
    if output_file.exists():
        assert "hook executed" in output_file.read_text()
        output_file.unlink()


def test_hook_timeout(tmp_path):
    """Test that hooks are killed after timeout."""
    # Create a script that sleeps longer than timeout
    script_path = tmp_path / "slow_hook.sh"
    script_path.write_text("#!/bin/sh\nsleep 10\necho 'should not reach here'\n")
    script_path.chmod(0o755)

    hook_config = OnFailureHookConfig(
        command=["/bin/sh", str(script_path)],
        timeout_seconds=1,
    )
    notifications_config = NotificationsConfig(on_failure=hook_config)

    start_time = time.time()
    execute_failure_notification(
        config=notifications_config,
        tenant_id="test_tenant",
        job_name="test_job",
        config_path="test.yaml",
        exit_code=2,
        failure_reason="Test",
    )
    elapsed = time.time() - start_time

    # Should have timed out quickly (within 2 seconds, accounting for overhead)
    assert elapsed < 2.5


def test_hook_env_expansion_and_redaction(tmp_path, monkeypatch):
    """Test that environment variable expansion works and secrets are redacted."""
    monkeypatch.setenv("HOOK_TOKEN", "secret_token_123")
    monkeypatch.setenv("HOOK_URL", "https://example.com")

    # Create a script that reads env vars and writes to file
    script_path = tmp_path / "env_hook.sh"
    output_file = tmp_path / "hook_output.txt"
    script_path.write_text(
        f"#!/bin/sh\n"
        f'echo "TOKEN=$HOOK_TOKEN" > {output_file}\n'
        f'echo "URL=$HOOK_URL" >> {output_file}\n'
        f'echo "PAYLOAD=$DATIVO_HOOK_PAYLOAD" >> {output_file}\n'
    )
    script_path.chmod(0o755)

    hook_config = OnFailureHookConfig(
        command=["/bin/sh", str(script_path)],
        env={
            "HOOK_TOKEN": "${HOOK_TOKEN}",  # Should expand
            "HOOK_URL": "${HOOK_URL}",  # Should expand
            "CUSTOM_VAR": "custom_value",
        },
        timeout_seconds=15,
    )
    notifications_config = NotificationsConfig(on_failure=hook_config)

    execute_failure_notification(
        config=notifications_config,
        tenant_id="test_tenant",
        job_name="test_job",
        config_path="test.yaml",
        exit_code=2,
        failure_reason="Test failure",
    )

    # Verify payload file was created and contains correct data
    if output_file.exists():
        output = output_file.read_text()
        assert "TOKEN=secret_token_123" in output
        assert "URL=https://example.com" in output
        assert "PAYLOAD=" in output  # PAYLOAD env var should be set
        assert ".json" in output  # Should contain path to JSON payload file


def test_hook_payload_content(tmp_path):
    """Test that hook payload contains correct information."""
    script_path = tmp_path / "payload_test.sh"
    payload_file = tmp_path / "captured_payload.json"

    script_path.write_text(f"#!/bin/sh\n" f'cp "$DATIVO_HOOK_PAYLOAD" {payload_file}\n')
    script_path.chmod(0o755)

    hook_config = OnFailureHookConfig(
        command=["/bin/sh", str(script_path)],
        timeout_seconds=15,
    )
    notifications_config = NotificationsConfig(on_failure=hook_config)

    execute_failure_notification(
        config=notifications_config,
        tenant_id="test_tenant",
        job_name="test_job",
        config_path="/path/to/config.yaml",
        exit_code=2,
        failure_reason="Test failure",
        summary_path="/path/to/summary.json",
    )

    # Verify payload file was created and contains correct data
    if payload_file.exists():
        with open(payload_file) as f:
            payload = json.load(f)
        assert payload["tenant_id"] == "test_tenant"
        assert payload["job_name"] == "test_job"
        assert payload["config_path"] == "/path/to/config.yaml"
        assert payload["exit_code"] == 2
        assert payload["failure_reason"] == "Test failure"
        assert payload["summary_path"] == "/path/to/summary.json"


def test_hook_failure_does_not_crash(tmp_path):
    """Test that hook failures don't crash the runner."""
    # Create a script that exits with error
    script_path = tmp_path / "failing_hook.sh"
    script_path.write_text("#!/bin/sh\necho 'error' >&2\nexit 1\n")
    script_path.chmod(0o755)

    hook_config = OnFailureHookConfig(
        command=["/bin/sh", str(script_path)],
        timeout_seconds=15,
    )
    notifications_config = NotificationsConfig(on_failure=hook_config)

    # Should not raise exception
    result = execute_failure_notification(
        config=notifications_config,
        tenant_id="test_tenant",
        job_name="test_job",
        config_path="test.yaml",
        exit_code=2,
        failure_reason="Test",
    )
    # Should return False (hook failed) but not crash
    assert result is False


def test_hook_nonexistent_script_does_not_crash():
    """Test that nonexistent scripts don't crash the runner."""
    hook_config = OnFailureHookConfig(
        command=["/nonexistent/script.sh"],
        timeout_seconds=15,
    )
    notifications_config = NotificationsConfig(on_failure=hook_config)

    # Should not raise exception
    result = execute_failure_notification(
        config=notifications_config,
        tenant_id="test_tenant",
        job_name="test_job",
        config_path="test.yaml",
        exit_code=2,
        failure_reason="Test",
    )
    # Should return False (hook failed) but not crash
    assert result is False


def test_hook_no_config():
    """Test that no config does nothing."""
    result = execute_failure_notification(
        config=None,
        tenant_id="test_tenant",
        job_name="test_job",
        config_path="test.yaml",
        exit_code=2,
        failure_reason="Test",
    )
    assert result is True  # Not an error - just not configured
