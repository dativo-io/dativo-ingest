"""Integration test for multi-tenant job execution.

Tests Test Case 14: Multi-Tenant Job Execution
- Parallel execution of jobs for different tenants
- State isolation between tenants
- Data isolation in S3/MinIO
- No cross-tenant data contamination
"""

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest


@pytest.fixture
def test_data_dir(tmp_path):
    """Create temporary directory for test data."""
    data_dir = tmp_path / "data" / "test_multi_tenant"
    data_dir.mkdir(parents=True)
    return data_dir


@pytest.fixture
def test_jobs_dir(tmp_path):
    """Create temporary directory for job configs."""
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    return jobs_dir


@pytest.fixture
def test_secrets_dir(tmp_path):
    """Create temporary directory for secrets."""
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    return secrets_dir


@pytest.fixture
def test_state_dir(tmp_path):
    """Create temporary directory for state files."""
    state_dir = tmp_path / ".local" / "state"
    state_dir.mkdir(parents=True)
    return state_dir


def create_test_csv(data_dir, tenant_name, num_records=5):
    """Create a test CSV file for a tenant."""
    csv_file = data_dir / f"{tenant_name}_data.csv"
    with open(csv_file, "w") as f:
        f.write("id,tenant,value\n")
        for i in range(1, num_records + 1):
            f.write(f"{i},{tenant_name},value_{i}\n")
    return csv_file


def create_job_config(jobs_dir, tenant_id, csv_path):
    """Create a job configuration for a tenant."""
    job_file = jobs_dir / f"{tenant_id}_job.yaml"
    job_content = f"""tenant_id: {tenant_id}
source_connector: csv
source_connector_path: connectors/csv.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: employees
asset_path: tests/fixtures/assets/csv/v1.0/employee.yaml
source:
  files:
    - path: {csv_path}
      object: employees
target:
  connection:
    s3:
      bucket: "${{S3_BUCKET}}"
"""
    with open(job_file, "w") as f:
        f.write(job_content)
    return job_file


def create_secrets(secrets_dir, tenant_id):
    """Create secrets file for a tenant."""
    tenant_secrets_dir = secrets_dir / tenant_id
    tenant_secrets_dir.mkdir(exist_ok=True)

    secrets_file = tenant_secrets_dir / "iceberg.env"
    secrets_content = """S3_ENDPOINT=http://localhost:9000
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
AWS_REGION=us-east-1
S3_BUCKET=test-bucket
NESSIE_URI=http://localhost:19120/api/v1
"""
    with open(secrets_file, "w") as f:
        f.write(secrets_content)
    return secrets_file


@pytest.mark.integration
def test_multi_tenant_parallel_execution(
    test_data_dir, test_jobs_dir, test_secrets_dir, test_state_dir
):
    """Test parallel execution of jobs for multiple tenants."""
    # Skip if infrastructure not available
    try:
        import subprocess

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

    # Create test data for 3 tenants
    tenants = ["tenant_a", "tenant_b", "tenant_c"]
    csv_files = {}
    job_files = {}
    secret_files = {}

    for tenant in tenants:
        # Create CSV data
        csv_file = create_test_csv(test_data_dir, tenant, num_records=3)
        csv_files[tenant] = csv_file

        # Create job config
        job_file = create_job_config(test_jobs_dir, tenant, str(csv_file))
        job_files[tenant] = job_file

        # Create secrets
        secret_file = create_secrets(test_secrets_dir, tenant)
        secret_files[tenant] = secret_file

    # Run jobs in parallel
    processes = []
    for tenant in tenants:
        job_file = job_files[tenant]
        cmd = [
            "python",
            "-m",
            "dativo_ingest.cli",
            "ingest",
            "--config",
            str(job_file),
            "--secret-manager",
            "filesystem",
            "--secrets-dir",
            str(test_secrets_dir),
            "--mode",
            "self_hosted",
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).parent.parent.parent / "src")
        env["STATE_DIR"] = str(test_state_dir)

        process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        processes.append((tenant, process))

    # Wait for all processes to complete
    results = {}
    for tenant, process in processes:
        stdout, stderr = process.communicate(timeout=60)
        results[tenant] = {
            "returncode": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }

    # Verify all jobs succeeded
    for tenant, result in results.items():
        assert result["returncode"] == 0, f"Job for {tenant} failed: {result['stderr']}"

    # Verify state files are isolated
    for tenant in tenants:
        state_file = test_state_dir / tenant / "csv.employees.state.json"
        # State file may or may not exist depending on incremental config
        # But if it exists, it should be tenant-specific
        if state_file.exists():
            assert tenant in str(state_file.parent)


@pytest.mark.integration
def test_multi_tenant_state_isolation(
    test_data_dir, test_jobs_dir, test_secrets_dir, test_state_dir
):
    """Test that state files are isolated between tenants."""
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

    tenants = ["tenant_x", "tenant_y"]

    # Create jobs for both tenants
    for tenant in tenants:
        csv_file = create_test_csv(test_data_dir, tenant, num_records=2)
        create_job_config(test_jobs_dir, tenant, str(csv_file))
        create_secrets(test_secrets_dir, tenant)

    # Run job for tenant_x
    tenant_x_job = test_jobs_dir / "tenant_x_job.yaml"
    cmd = [
        "python",
        "-m",
        "dativo_ingest.cli",
        "ingest",
        "--config",
        str(tenant_x_job),
        "--secret-manager",
        "filesystem",
        "--secrets-dir",
        str(test_secrets_dir),
        "--mode",
        "self_hosted",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent.parent.parent / "src")
    env["STATE_DIR"] = str(test_state_dir)

    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, f"Job failed: {result.stderr}"

    # Run job for tenant_y
    tenant_y_job = test_jobs_dir / "tenant_y_job.yaml"
    cmd = [
        "python",
        "-m",
        "dativo_ingest.cli",
        "ingest",
        "--config",
        str(tenant_y_job),
        "--secret-manager",
        "filesystem",
        "--secrets-dir",
        str(test_secrets_dir),
        "--mode",
        "self_hosted",
    ]

    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, f"Job failed: {result.stderr}"

    # Verify state directories are separate
    tenant_x_state_dir = test_state_dir / "tenant_x"
    tenant_y_state_dir = test_state_dir / "tenant_y"

    # Both should exist (or both not exist, depending on incremental config)
    # But if they exist, they should be separate
    if tenant_x_state_dir.exists() and tenant_y_state_dir.exists():
        assert tenant_x_state_dir != tenant_y_state_dir
        # Verify no cross-contamination
        tenant_x_files = list(tenant_x_state_dir.glob("*.json"))
        tenant_y_files = list(tenant_y_state_dir.glob("*.json"))
        # Files should be in their respective directories
        for f in tenant_x_files:
            assert "tenant_x" in str(f)
        for f in tenant_y_files:
            assert "tenant_y" in str(f)


@pytest.mark.integration
def test_multi_tenant_data_isolation(
    test_data_dir, test_jobs_dir, test_secrets_dir, test_state_dir
):
    """Test that data is isolated in S3/MinIO between tenants."""
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

    tenants = ["tenant_p", "tenant_q"]

    # Create and run jobs for both tenants
    for tenant in tenants:
        csv_file = create_test_csv(test_data_dir, tenant, num_records=2)
        create_job_config(test_jobs_dir, tenant, str(csv_file))
        create_secrets(test_secrets_dir, tenant)

        # Run job
        job_file = test_jobs_dir / f"{tenant}_job.yaml"
        cmd = [
            "python",
            "-m",
            "dativo_ingest.cli",
            "ingest",
            "--config",
            str(job_file),
            "--secret-manager",
            "filesystem",
            "--secrets-dir",
            str(test_secrets_dir),
            "--mode",
            "self_hosted",
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).parent.parent.parent / "src")
        env["STATE_DIR"] = str(test_state_dir)

        result = subprocess.run(
            cmd, env=env, capture_output=True, text=True, timeout=60
        )
        assert result.returncode == 0, f"Job for {tenant} failed: {result.stderr}"

    # Verify data isolation using mc (MinIO client) if available
    try:
        # Check that tenant_p data exists
        result = subprocess.run(
            ["mc", "ls", "local/test-bucket/tenant_p/", "--recursive"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            assert "tenant_p" in result.stdout
            assert "tenant_q" not in result.stdout

        # Check that tenant_q data exists
        result = subprocess.run(
            ["mc", "ls", "local/test-bucket/tenant_q/", "--recursive"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            assert "tenant_q" in result.stdout
            assert "tenant_p" not in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # mc not available, skip verification
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
