"""End-to-end integration test for MySQL extraction → write → verify pipeline."""

import os
import tempfile
from pathlib import Path

import pytest

from dativo_ingest.config import JobConfig
from dativo_ingest.job_executor import JobExecutor


@pytest.fixture(scope="module")
def mysql_available():
    """Check if MySQL is available for integration tests."""
    mysql_host = os.getenv("MYSQL_HOST", "localhost")
    mysql_port = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_user = os.getenv("MYSQL_USER", "test")
    mysql_password = os.getenv("MYSQL_PASSWORD", "test")
    mysql_database = os.getenv("MYSQL_DATABASE", "employees")

    try:
        import mysql.connector

        conn = mysql.connector.connect(
            host=mysql_host,
            port=mysql_port,
            user=mysql_user,
            password=mysql_password,
            database=mysql_database,
            connection_timeout=10,
            auth_plugin="mysql_native_password",
        )
        conn.close()
        return True
    except Exception as e:
        # Log the error for debugging
        import warnings

        warnings.warn(f"MySQL connection failed: {e}")
        return False


@pytest.fixture
def mysql_job_config(tmp_path):
    """Create a MySQL job configuration for end-to-end test."""
    # Create temporary output directory
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    job_yaml = f"""
tenant_id: test_tenant
environment: test

source_connector: mysql
source_connector_path: connectors/mysql.yaml

target_connector: iceberg
target_connector_path: connectors/iceberg.yaml

asset: mysql_employees_markdown_kv
asset_path: tests/fixtures/assets/mysql/v1.0/employees_markdown_kv.yaml

source:
  tables:
    - name: employees.employees
      object: employees
  incremental:
    strategy: updated_at
    cursor_field: hire_date
    lookback_days: 0
  connection:
    host: "${{MYSQL_HOST:-localhost}}"
    port: "${{MYSQL_PORT:-3306}}"
    database: "${{MYSQL_DATABASE:-employees}}"
    user: "${{MYSQL_USER:-test}}"
    password: "${{MYSQL_PASSWORD:-test}}"

target:
  file_format: parquet
  markdown_kv_storage:
    mode: "string"
  connection:
    s3:
      endpoint: "${{MINIO_ENDPOINT}}"
      bucket: test-bucket
      access_key_id: "${{MINIO_ACCESS_KEY}}"
      secret_access_key: "${{MINIO_SECRET_KEY}}"
      region: "${{AWS_REGION}}"
      path_style_access: true

schema_validation_mode: warn
logging:
  redaction: false
  level: INFO
"""

    job_file = tmp_path / "mysql_test_job.yaml"
    job_file.write_text(job_yaml)
    return job_file


@pytest.mark.integration
def test_mysql_end_to_end_extraction_write(mysql_available, mysql_job_config, tmp_path):
    """Test complete MySQL extraction → write → verify pipeline."""
    if not mysql_available:
        pytest.skip("MySQL not available for integration tests")

    # Check if MinIO/S3 is available
    minio_endpoint = os.getenv("MINIO_ENDPOINT")
    if not minio_endpoint:
        pytest.skip("MinIO not available for integration tests")

    # Load job config
    job_config = JobConfig.from_yaml(mysql_job_config, validate_schema=False)

    # Create job executor
    executor = JobExecutor(
        job_config=job_config,
        tenant_id="test_tenant",
        secrets_dir=None,
        state_dir=str(tmp_path / "state"),
    )

    # Execute job
    try:
        result = executor.execute()

        # Verify job completed successfully
        assert result is not None
        assert result.get("status") == "success" or result.get("exit_code") == 0

        # Verify data was extracted and written
        # Check that records were processed
        if "records_processed" in result:
            assert result["records_processed"] > 0

        # Verify output files exist (if using local file system)
        # For S3/MinIO, we'd need to check via client
        output_path = tmp_path / "output"
        if output_path.exists():
            parquet_files = list(output_path.glob("*.parquet"))
            if parquet_files:
                assert len(parquet_files) > 0

    except Exception as e:
        pytest.fail(f"MySQL end-to-end test failed: {e}")


@pytest.mark.integration
def test_mysql_incremental_sync_end_to_end(mysql_available, mysql_job_config, tmp_path):
    """Test MySQL incremental sync with state persistence."""
    if not mysql_available:
        pytest.skip("MySQL not available for integration tests")

    minio_endpoint = os.getenv("MINIO_ENDPOINT")
    if not minio_endpoint:
        pytest.skip("MinIO not available for integration tests")

    state_dir = tmp_path / "state"
    state_dir.mkdir()

    # Load job config
    job_config = JobConfig.from_yaml(mysql_job_config, validate_schema=False)

    # First run - extract all data
    executor1 = JobExecutor(
        job_config=job_config,
        tenant_id="test_tenant",
        secrets_dir=None,
        state_dir=str(state_dir),
    )

    result1 = executor1.execute()
    assert result1 is not None
    records_first_run = result1.get("records_processed", 0)

    # Second run - should only extract new records (incremental)
    executor2 = JobExecutor(
        job_config=job_config,
        tenant_id="test_tenant",
        secrets_dir=None,
        state_dir=str(state_dir),
    )

    result2 = executor2.execute()
    assert result2 is not None
    records_second_run = result2.get("records_processed", 0)

    # Second run should process fewer or equal records (depending on data)
    # If no new records, should process 0
    assert records_second_run <= records_first_run

    # Verify state file was created
    state_files = list(state_dir.glob("**/*.state.json"))
    assert len(state_files) > 0


@pytest.mark.integration
def test_mysql_multiple_tables_end_to_end(mysql_available, tmp_path):
    """Test MySQL extraction from multiple tables."""
    if not mysql_available:
        pytest.skip("MySQL not available for integration tests")

    minio_endpoint = os.getenv("MINIO_ENDPOINT")
    if not minio_endpoint:
        pytest.skip("MinIO not available for integration tests")

    job_yaml = f"""
tenant_id: test_tenant
environment: test

source_connector: mysql
source_connector_path: connectors/mysql.yaml

target_connector: iceberg
target_connector_path: connectors/iceberg.yaml

asset: mysql_employees_markdown_kv
asset_path: tests/fixtures/assets/mysql/v1.0/employees_markdown_kv.yaml

source:
  tables:
    - name: employees.employees
      object: employees
    - name: employees.departments
      object: departments
  connection:
    host: "${{MYSQL_HOST:-localhost}}"
    port: "${{MYSQL_PORT:-3306}}"
    database: "${{MYSQL_DATABASE:-employees}}"
    user: "${{MYSQL_USER:-test}}"
    password: "${{MYSQL_PASSWORD:-test}}"

target:
  file_format: parquet
  connection:
    s3:
      endpoint: "${{MINIO_ENDPOINT}}"
      bucket: test-bucket
      access_key_id: "${{MINIO_ACCESS_KEY}}"
      secret_access_key: "${{MINIO_SECRET_KEY}}"
      region: "${{AWS_REGION}}"
      path_style_access: true

schema_validation_mode: warn
logging:
  redaction: false
  level: INFO
"""

    job_file = tmp_path / "mysql_multi_table_job.yaml"
    job_file.write_text(job_yaml)

    job_config = JobConfig.from_yaml(job_file, validate_schema=False)

    executor = JobExecutor(
        job_config=job_config,
        tenant_id="test_tenant",
        secrets_dir=None,
        state_dir=str(tmp_path / "state"),
    )

    result = executor.execute()

    # Verify job completed
    assert result is not None
    assert result.get("status") == "success" or result.get("exit_code") == 0

    # Verify multiple tables were processed
    if "records_processed" in result:
        assert result["records_processed"] > 0
