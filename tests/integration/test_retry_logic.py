"""Integration test for error handling and retry logic.

Tests Test Case 19: Error Handling and Retry Logic
- Invalid credentials (non-retryable)
- Connection timeouts (retryable)
- Partial success scenarios
- Retry policy execution
"""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from dativo_ingest.config import RetryConfig
from dativo_ingest.exceptions import AuthenticationError, ConnectionError
from dativo_ingest.retry_policy import RetryPolicy


@pytest.fixture
def test_jobs_dir(tmp_path):
    """Create job configurations for error scenarios."""
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()

    # Job with invalid credentials
    invalid_creds_job = jobs_dir / "invalid_creds.yaml"
    invalid_creds_content = """tenant_id: testcase19
source_connector: postgres
source_connector_path: connectors/postgres.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: db_employees
asset_path: tests/fixtures/assets/postgres/v1.0/db_orders.yaml
source:
  tables:
    - name: employees
      schema: public
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
"""
    with open(invalid_creds_job, "w") as f:
        f.write(invalid_creds_content)

    # Job with missing file (should fail)
    missing_file_job = jobs_dir / "missing_file.yaml"
    missing_file_content = """tenant_id: testcase19
source_connector: csv
source_connector_path: connectors/csv.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: employees
asset_path: tests/fixtures/assets/csv/v1.0/employee.yaml
source:
  files:
    - path: /nonexistent/file.csv
      object: employees
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
"""
    with open(missing_file_job, "w") as f:
        f.write(missing_file_content)

    # Job that should succeed
    success_job = jobs_dir / "success_job.yaml"
    success_content = """tenant_id: testcase19
source_connector: csv
source_connector_path: connectors/csv.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: employees
asset_path: tests/fixtures/assets/csv/v1.0/employee.yaml
source:
  files:
    - path: tests/fixtures/seeds/csv/employee.csv
      object: employees
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
"""
    with open(success_job, "w") as f:
        f.write(success_content)

    return jobs_dir


@pytest.fixture
def test_secrets_dir(tmp_path):
    """Create secrets for error scenarios."""
    secrets_dir = tmp_path / "secrets" / "testcase19"
    secrets_dir.mkdir(parents=True)

    # Invalid PostgreSQL credentials
    invalid_postgres = secrets_dir / "postgres.env"
    with open(invalid_postgres, "w") as f:
        f.write(
            """PGHOST=localhost
PGPORT=5432
PGDATABASE=postgres
PGUSER=invalid_user
PGPASSWORD=wrong_password
"""
        )

    # Valid Iceberg secrets
    iceberg_secrets = secrets_dir / "iceberg.env"
    with open(iceberg_secrets, "w") as f:
        f.write(
            """S3_ENDPOINT=http://localhost:9000
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
AWS_REGION=us-east-1
S3_BUCKET=test-bucket
NESSIE_URI=http://localhost:19120/api/v1
"""
        )

    return tmp_path / "secrets"


@pytest.mark.integration
def test_invalid_credentials_non_retryable(test_jobs_dir, test_secrets_dir):
    """Test that invalid credentials fail immediately (non-retryable)."""
    invalid_creds_job = test_jobs_dir / "invalid_creds.yaml"

    cmd = [
        "python",
        "-m",
        "dativo_ingest.cli",
        "ingest",
        "--config",
        str(invalid_creds_job),
        "--secret-manager",
        "filesystem",
        "--secrets-dir",
        str(test_secrets_dir),
        "--mode",
        "self_hosted",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent.parent.parent / "src")

    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30)

    # Should fail with exit code 2 (authentication error)
    assert result.returncode == 2, f"Expected exit code 2, got {result.returncode}"

    # Should contain authentication error message
    assert (
        "authentication" in result.stderr.lower()
        or "credential" in result.stderr.lower()
        or "password" in result.stderr.lower()
    )


@pytest.mark.integration
def test_missing_file_error(test_jobs_dir, test_secrets_dir):
    """Test that missing file errors are handled correctly."""
    missing_file_job = test_jobs_dir / "missing_file.yaml"

    cmd = [
        "python",
        "-m",
        "dativo_ingest.cli",
        "ingest",
        "--config",
        str(missing_file_job),
        "--secret-manager",
        "filesystem",
        "--secrets-dir",
        str(test_secrets_dir),
        "--mode",
        "self_hosted",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent.parent.parent / "src")

    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30)

    # Should fail (non-zero exit code)
    assert result.returncode != 0, "Expected job to fail with missing file"

    # Should contain file not found error
    assert (
        "not found" in result.stderr.lower()
        or "no such file" in result.stderr.lower()
        or "file" in result.stderr.lower()
    )


@pytest.mark.integration
def test_partial_success_scenario(test_jobs_dir, test_secrets_dir):
    """Test partial success scenario (some jobs succeed, some fail)."""
    # Skip if infrastructure not available
    try:
        result = subprocess.run(
            ["docker", "ps", "-q", "-f", "name=minio"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if not result.stdout.strip():
            pytest.skip("MinIO not available for integration tests")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pytest.skip("Docker not available for integration tests")

    # Create job directory with both success and failure jobs
    multi_job_dir = test_jobs_dir / "multi"
    multi_job_dir.mkdir()

    # Copy success job
    success_job = test_jobs_dir / "success_job.yaml"
    import shutil

    shutil.copy(success_job, multi_job_dir / "success_job.yaml")

    # Copy missing file job
    missing_file_job = test_jobs_dir / "missing_file.yaml"
    shutil.copy(missing_file_job, multi_job_dir / "missing_file.yaml")

    # Run jobs from directory
    cmd = [
        "python",
        "-m",
        "dativo_ingest.cli",
        "ingest",
        "--job-dir",
        str(multi_job_dir),
        "--secret-manager",
        "filesystem",
        "--secrets-dir",
        str(test_secrets_dir),
        "--mode",
        "self_hosted",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent.parent.parent / "src")

    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)

    # Should return exit code 1 (partial success)
    # Exit code 1 indicates some jobs succeeded but others failed
    assert result.returncode in [
        1,
        2,
    ], f"Expected exit code 1 or 2 for partial success, got {result.returncode}"


@pytest.mark.integration
def test_retry_policy_unit():
    """Test retry policy logic (unit test within integration suite)."""
    # Test retryable vs non-retryable errors
    config = RetryConfig(
        max_retries=3,
        retryable_exit_codes=[1, 2],
        retryable_error_patterns=["ConnectionError", "Timeout"],
    )
    policy = RetryPolicy(config)

    # Connection errors should be retryable
    assert policy.should_retry(2, "ConnectionError occurred", attempt=0) is True

    # Authentication errors should not be retryable (not in patterns)
    assert policy.should_retry(2, "Authentication failed", attempt=0) is False

    # Should not retry after max retries
    assert policy.should_retry(1, "", attempt=3) is False

    # Should retry for retryable exit codes
    assert policy.should_retry(1, "", attempt=0) is True
    assert policy.should_retry(2, "", attempt=0) is True

    # Should not retry for non-retryable exit codes
    assert policy.should_retry(0, "", attempt=0) is False


@pytest.mark.integration
def test_error_classification():
    """Test error classification (retryable vs non-retryable)."""
    from dativo_ingest.exceptions import (
        AuthenticationError,
        ConnectionError,
        is_retryable_error,
    )

    # Connection errors should be retryable
    conn_error = ConnectionError("Connection failed")
    assert is_retryable_error(conn_error) is True

    # Authentication errors should not be retryable
    auth_error = AuthenticationError("Invalid credentials")
    assert is_retryable_error(auth_error) is False


@pytest.mark.integration
def test_retry_delay_calculation():
    """Test retry delay calculation with exponential backoff."""
    config = RetryConfig(
        initial_delay_seconds=5,
        backoff_multiplier=2.0,
        max_delay_seconds=300,
    )
    policy = RetryPolicy(config)

    # Attempt 0: initial delay
    assert policy.calculate_delay(0) == 5

    # Attempt 1: 5 * 2 = 10
    assert policy.calculate_delay(1) == 10

    # Attempt 2: 5 * 2^2 = 20
    assert policy.calculate_delay(2) == 20

    # Attempt 10: capped at max_delay_seconds
    assert policy.calculate_delay(10) == 300


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
