"""E2E test for environment variable secret manager.

Tests Test Case 15: Environment Variable Secret Manager
- Secrets loaded from environment variables
- Namespace format (DATIVO_SECRET__{TENANT}__{SECRET_NAME})
- Global secrets support
- Full E2E job execution with env secrets
"""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def test_data_dir(tmp_path):
    """Create temporary directory for test data."""
    data_dir = tmp_path / "data" / "test_env_secrets"
    data_dir.mkdir(parents=True)

    # Create test CSV
    csv_file = data_dir / "employees.csv"
    with open(csv_file, "w") as f:
        f.write("id,name,email,department,salary\n")
        f.write("1,John Doe,john@example.com,Engineering,120000\n")
        f.write("2,Jane Smith,jane@example.com,Marketing,95000\n")

    return data_dir


@pytest.fixture
def test_job_config(tmp_path, test_data_dir):
    """Create a job configuration file."""
    job_file = tmp_path / "env_secrets_job.yaml"
    job_content = f"""tenant_id: testcase15
source_connector: csv
source_connector_path: connectors/csv.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: employees
asset_path: tests/fixtures/assets/csv/v1.0/employee.yaml
source:
  files:
    - path: {test_data_dir / "employees.csv"}
      object: employees
target:
  connection:
    s3:
      bucket: "${{S3_BUCKET}}"
"""
    with open(job_file, "w") as f:
        f.write(job_content)
    return job_file


@pytest.mark.integration
def test_env_secrets_namespace_format(test_job_config):
    """Test environment variable secret namespace format."""
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

    # Set environment variables with dativo format
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent.parent.parent / "src")

    # Set secrets in namespace format
    env["DATIVO_SECRET__TESTCASE15__iceberg__env"] = (
        "S3_ENDPOINT=http://localhost:9000\n"
        "AWS_ACCESS_KEY_ID=minioadmin\n"
        "AWS_SECRET_ACCESS_KEY=minioadmin\n"
        "AWS_REGION=us-east-1\n"
        "S3_BUCKET=test-bucket\n"
        "NESSIE_URI=http://localhost:19120/api/v1"
    )

    # Run job with env secret manager
    cmd = [
        "python",
        "-m",
        "dativo_ingest.cli",
        "ingest",
        "--config",
        str(test_job_config),
        "--secret-manager",
        "env",
        "--mode",
        "self_hosted",
    ]

    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)

    # Job should succeed
    assert result.returncode == 0, f"Job failed: {result.stderr}"


@pytest.mark.integration
def test_env_secrets_global_secrets(test_job_config):
    """Test global secrets accessible to all tenants."""
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

    # Set environment variables
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent.parent.parent / "src")

    # Set global secrets
    env["DATIVO_SECRET__GLOBAL__aws_access_key__text"] = "minioadmin"
    env["DATIVO_SECRET__GLOBAL__aws_secret_key__text"] = "minioadmin"

    # Set tenant-specific secrets (can reference global secrets)
    env["DATIVO_SECRET__TESTCASE15__iceberg__env"] = (
        "S3_ENDPOINT=http://localhost:9000\n"
        "AWS_ACCESS_KEY_ID=${DATIVO_SECRET__GLOBAL__aws_access_key__text}\n"
        "AWS_SECRET_ACCESS_KEY=${DATIVO_SECRET__GLOBAL__aws_secret_key__text}\n"
        "AWS_REGION=us-east-1\n"
        "S3_BUCKET=test-bucket\n"
        "NESSIE_URI=http://localhost:19120/api/v1"
    )

    # Run job
    cmd = [
        "python",
        "-m",
        "dativo_ingest.cli",
        "ingest",
        "--config",
        str(test_job_config),
        "--secret-manager",
        "env",
        "--mode",
        "self_hosted",
    ]

    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)

    # Job should succeed
    assert result.returncode == 0, f"Job failed: {result.stderr}"


@pytest.mark.integration
def test_env_secrets_json_format(test_job_config):
    """Test environment variable secrets with JSON format."""
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

    # Set environment variables
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent.parent.parent / "src")

    # Set secrets in JSON format
    env["DATIVO_SECRET__TESTCASE15__iceberg__json"] = (
        '{"S3_ENDPOINT": "http://localhost:9000", '
        '"AWS_ACCESS_KEY_ID": "minioadmin", '
        '"AWS_SECRET_ACCESS_KEY": "minioadmin", '
        '"AWS_REGION": "us-east-1", '
        '"S3_BUCKET": "test-bucket", '
        '"NESSIE_URI": "http://localhost:19120/api/v1"}'
    )

    # Run job
    cmd = [
        "python",
        "-m",
        "dativo_ingest.cli",
        "ingest",
        "--config",
        str(test_job_config),
        "--secret-manager",
        "env",
        "--mode",
        "self_hosted",
    ]

    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)

    # Job should succeed
    assert result.returncode == 0, f"Job failed: {result.stderr}"


@pytest.mark.integration
def test_env_secrets_default_manager(test_job_config):
    """Test that env is the default secret manager."""
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

    # Set environment variables
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent.parent.parent / "src")

    # Set secrets
    env["DATIVO_SECRET__TESTCASE15__iceberg__env"] = (
        "S3_ENDPOINT=http://localhost:9000\n"
        "AWS_ACCESS_KEY_ID=minioadmin\n"
        "AWS_SECRET_ACCESS_KEY=minioadmin\n"
        "AWS_REGION=us-east-1\n"
        "S3_BUCKET=test-bucket\n"
        "NESSIE_URI=http://localhost:19120/api/v1"
    )

    # Run job without specifying --secret-manager (should default to env)
    cmd = [
        "python",
        "-m",
        "dativo_ingest.cli",
        "ingest",
        "--config",
        str(test_job_config),
        "--mode",
        "self_hosted",
    ]

    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)

    # Job should succeed
    assert result.returncode == 0, f"Job failed: {result.stderr}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
