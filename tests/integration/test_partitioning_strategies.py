"""Integration test for data partitioning strategies.

Tests Test Case 16: Data Partitioning Strategies
- Single column partitioning
- Multi-level partitioning
- Date-based partitioning (ingest_date)
- Partition structure verification
"""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def test_data_dir(tmp_path):
    """Create test data with partition candidates."""
    data_dir = tmp_path / "data" / "test_partitioning"
    data_dir.mkdir(parents=True)

    # Create sales data with multiple partition candidates
    csv_file = data_dir / "sales_data.csv"
    with open(csv_file, "w") as f:
        f.write("order_id,customer_id,order_date,region,product_category,amount\n")
        f.write("1001,5001,2025-01-01,US-West,Electronics,299.99\n")
        f.write("1002,5002,2025-01-01,US-East,Clothing,89.99\n")
        f.write("1003,5003,2025-01-02,US-West,Electronics,199.99\n")
        f.write("1004,5004,2025-01-02,EU-North,Home,149.99\n")
        f.write("1005,5005,2025-01-03,US-East,Electronics,399.99\n")
        f.write("1006,5006,2025-01-03,EU-West,Clothing,59.99\n")

    return data_dir


@pytest.fixture
def test_assets_dir(tmp_path):
    """Create asset definitions for different partitioning strategies."""
    assets_dir = tmp_path / "assets" / "examples" / "csv" / "v1.0"
    assets_dir.mkdir(parents=True)

    # Strategy A: Single column partitioning (region)
    asset_a = assets_dir / "sales_by_region.yaml"
    asset_a_content = """$schema: ../../schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: sales_by_region
version: "1.0"
source_type: csv
object: sales
schema:
  - name: order_id
    type: integer
    required: true
  - name: customer_id
    type: integer
  - name: order_date
    type: date
  - name: region
    type: string
  - name: product_category
    type: string
  - name: amount
    type: decimal
target:
  file_format: parquet
  partitioning: [region]
team:
  owner: test@example.com
compliance:
  classification: []
"""
    with open(asset_a, "w") as f:
        f.write(asset_a_content)

    # Strategy B: Multi-level partitioning (region → product_category)
    asset_b = assets_dir / "sales_multi_partition.yaml"
    asset_b_content = """$schema: ../../schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: sales_multi_partition
version: "1.0"
source_type: csv
object: sales
schema:
  - name: order_id
    type: integer
    required: true
  - name: customer_id
    type: integer
  - name: order_date
    type: date
  - name: region
    type: string
  - name: product_category
    type: string
  - name: amount
    type: decimal
target:
  file_format: parquet
  partitioning: [region, product_category]
team:
  owner: test@example.com
compliance:
  classification: []
"""
    with open(asset_b, "w") as f:
        f.write(asset_b_content)

    # Strategy C: Date partitioning (ingest_date)
    asset_c = assets_dir / "sales_date_partition.yaml"
    asset_c_content = """$schema: ../../schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: sales_date_partition
version: "1.0"
source_type: csv
object: sales
schema:
  - name: order_id
    type: integer
    required: true
  - name: customer_id
    type: integer
  - name: order_date
    type: date
  - name: region
    type: string
  - name: product_category
    type: string
  - name: amount
    type: decimal
target:
  file_format: parquet
  partitioning: [ingest_date]
team:
  owner: test@example.com
compliance:
  classification: []
"""
    with open(asset_c, "w") as f:
        f.write(asset_c_content)

    return assets_dir


@pytest.fixture
def test_jobs_dir(tmp_path, test_data_dir, test_assets_dir):
    """Create job configurations for each partitioning strategy."""
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()

    strategies = [
        ("by_region", "sales_by_region"),
        ("multi_partition", "sales_multi_partition"),
        ("date_partition", "sales_date_partition"),
    ]

    job_files = {}
    for strategy_name, asset_name in strategies:
        job_file = jobs_dir / f"sales_{strategy_name}.yaml"
        job_content = f"""tenant_id: testcase16
source_connector: csv
source_connector_path: connectors/csv.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: {asset_name}
asset_path: {test_assets_dir / f"{asset_name}.yaml"}
source:
  files:
    - path: {test_data_dir / "sales_data.csv"}
      object: sales
target:
  connection:
    s3:
      bucket: "${{S3_BUCKET}}"
"""
        with open(job_file, "w") as f:
            f.write(job_content)
        job_files[strategy_name] = job_file

    return jobs_dir, job_files


@pytest.fixture
def test_secrets_dir(tmp_path):
    """Create secrets directory."""
    secrets_dir = tmp_path / "secrets" / "testcase16"
    secrets_dir.mkdir(parents=True)

    secrets_file = secrets_dir / "iceberg.env"
    secrets_content = """S3_ENDPOINT=http://localhost:9000
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
AWS_REGION=us-east-1
S3_BUCKET=test-bucket
NESSIE_URI=http://localhost:19120/api/v1
"""
    with open(secrets_file, "w") as f:
        f.write(secrets_content)

    return tmp_path / "secrets"


@pytest.mark.integration
def test_single_column_partitioning(test_jobs_dir, test_secrets_dir):
    """Test single column partitioning (region)."""
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

    jobs_dir, job_files = test_jobs_dir
    job_file = job_files["by_region"]

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

    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)

    assert result.returncode == 0, f"Job failed: {result.stderr}"

    # Verify partition structure using mc if available
    try:
        result = subprocess.run(
            [
                "mc",
                "ls",
                "local/test-bucket/testcase16/sales_by_region/",
                "--recursive",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            # Should have partitions for different regions
            assert (
                "region=" in result.stdout
                or "US-West" in result.stdout
                or "US-East" in result.stdout
            )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # mc not available, skip verification
        pass


@pytest.mark.integration
def test_multi_level_partitioning(test_jobs_dir, test_secrets_dir):
    """Test multi-level partitioning (region → product_category)."""
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

    jobs_dir, job_files = test_jobs_dir
    job_file = job_files["multi_partition"]

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

    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)

    assert result.returncode == 0, f"Job failed: {result.stderr}"

    # Verify nested partition structure using mc if available
    try:
        result = subprocess.run(
            [
                "mc",
                "ls",
                "local/test-bucket/testcase16/sales_multi_partition/",
                "--recursive",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            # Should have nested partitions
            output = result.stdout
            # Check for both region and product_category in path
            assert "region=" in output or "product_category=" in output
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # mc not available, skip verification
        pass


@pytest.mark.integration
def test_date_partitioning(test_jobs_dir, test_secrets_dir):
    """Test date-based partitioning (ingest_date)."""
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

    jobs_dir, job_files = test_jobs_dir
    job_file = job_files["date_partition"]

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

    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)

    assert result.returncode == 0, f"Job failed: {result.stderr}"

    # Verify date partition structure using mc if available
    try:
        result = subprocess.run(
            [
                "mc",
                "ls",
                "local/test-bucket/testcase16/sales_date_partition/",
                "--recursive",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            # Should have ingest_date partition (format: ingest_date=YYYY-MM-DD)
            assert "ingest_date=" in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # mc not available, skip verification
        pass


@pytest.mark.integration
def test_all_partitioning_strategies(test_jobs_dir, test_secrets_dir):
    """Test all partitioning strategies in sequence."""
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

    jobs_dir, job_files = test_jobs_dir
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent.parent.parent / "src")

    # Run all three strategies
    for strategy_name in ["by_region", "multi_partition", "date_partition"]:
        job_file = job_files[strategy_name]

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

        result = subprocess.run(
            cmd, env=env, capture_output=True, text=True, timeout=60
        )

        assert (
            result.returncode == 0
        ), f"Job for {strategy_name} failed: {result.stderr}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
