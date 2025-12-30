"""Integration tests for MySQL extractor with real database connection."""

import os
from pathlib import Path

import pytest

from dativo_ingest.config import SourceConfig
from dativo_ingest.connectors.mysql_extractor import MySQLExtractor
from dativo_ingest.incremental import create_incremental_strategy


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
def mysql_source_config():
    """Create a source config for MySQL integration tests."""
    return SourceConfig(
        type="mysql",
        tables=[{"name": "employees.employees", "object": "employees"}],
        connection={
            "host": os.getenv("MYSQL_HOST", "localhost"),
            "port": int(os.getenv("MYSQL_PORT", "3306")),
            "database": os.getenv("MYSQL_DATABASE", "employees"),
            "user": os.getenv("MYSQL_USER", "test"),
            "password": os.getenv("MYSQL_PASSWORD", "test"),
        },
    )


@pytest.fixture
def mysql_source_config_incremental():
    """Create a source config with incremental sync."""
    return SourceConfig(
        type="mysql",
        tables=[{"name": "employees.employees", "object": "employees"}],
        connection={
            "host": os.getenv("MYSQL_HOST", "localhost"),
            "port": int(os.getenv("MYSQL_PORT", "3306")),
            "database": os.getenv("MYSQL_DATABASE", "employees"),
            "user": os.getenv("MYSQL_USER", "test"),
            "password": os.getenv("MYSQL_PASSWORD", "test"),
        },
        incremental={
            "strategy": "updated_at",
            "cursor_field": "hire_date",
            "lookback_days": 0,
        },
    )


@pytest.mark.integration
def test_mysql_extractor_connection(mysql_available, mysql_source_config):
    """Test MySQL extractor can connect to database."""
    if not mysql_available:
        pytest.skip("MySQL not available for integration tests")

    extractor = MySQLExtractor(mysql_source_config)

    # Should not raise exception
    assert extractor is not None
    assert extractor.connection["host"] == os.getenv("MYSQL_HOST", "localhost")


@pytest.mark.integration
def test_mysql_extractor_extract_data(mysql_available, mysql_source_config):
    """Test MySQL extractor extracts data from real database."""
    if not mysql_available:
        pytest.skip("MySQL not available for integration tests")

    extractor = MySQLExtractor(mysql_source_config)

    # Extract data
    batches = list(extractor.extract())

    # Verify data was extracted
    assert len(batches) > 0
    assert len(batches[0]) > 0

    # Verify record structure
    first_record = batches[0][0]
    assert isinstance(first_record, dict)
    assert "emp_no" in first_record or "first_name" in first_record


@pytest.mark.integration
def test_mysql_extractor_extract_metadata(mysql_available, mysql_source_config):
    """Test MySQL extractor extracts metadata from real database."""
    if not mysql_available:
        pytest.skip("MySQL not available for integration tests")

    extractor = MySQLExtractor(mysql_source_config)

    # Extract metadata
    metadata = extractor.extract_metadata()

    # Verify metadata structure
    assert isinstance(metadata, dict)
    assert "tags" in metadata
    assert isinstance(metadata["tags"], dict)

    # If table exists and has columns, should have some tags
    if len(metadata["tags"]) > 0:
        # Tags should be column names
        assert any(
            key in metadata["tags"]
            for key in ["emp_no", "first_name", "last_name", "hire_date"]
        )


@pytest.mark.integration
def test_mysql_extractor_incremental_sync(
    mysql_available, mysql_source_config_incremental, tmp_path
):
    """Test MySQL extractor incremental sync with real database."""
    if not mysql_available:
        pytest.skip("MySQL not available for integration tests")

    state_path = tmp_path / "mysql_incremental_state.json"
    state_path.write_text("{}")

    extractor = MySQLExtractor(mysql_source_config_incremental)

    # Create incremental strategy
    incremental_strategy = create_incremental_strategy(
        mysql_source_config_incremental.incremental,
        default_state_path=str(state_path),
    )

    # Extract data with incremental sync
    batches = list(extractor.extract(state_manager=incremental_strategy))

    # Verify data was extracted
    assert len(batches) > 0

    # Verify state was updated
    from dativo_ingest.validator import IncrementalStateManager

    state = IncrementalStateManager.read_state(state_path)
    # State should be updated if records were processed
    if len(batches[0]) > 0:
        assert isinstance(state, dict)


@pytest.mark.integration
def test_mysql_extractor_multiple_tables(mysql_available, mysql_source_config):
    """Test MySQL extractor extracts from multiple tables."""
    if not mysql_available:
        pytest.skip("MySQL not available for integration tests")

    # Add departments table
    mysql_source_config.tables.append(
        {"name": "employees.departments", "object": "departments"}
    )

    extractor = MySQLExtractor(mysql_source_config)

    # Extract data from both tables
    batches = list(extractor.extract())

    # Should have batches from both tables
    assert len(batches) > 0

    # Verify we got data from at least one table
    total_records = sum(len(batch) for batch in batches)
    assert total_records > 0


@pytest.mark.integration
def test_mysql_extractor_cursor_field_filtering(
    mysql_available, mysql_source_config_incremental, tmp_path
):
    """Test MySQL extractor filters records by cursor field value."""
    if not mysql_available:
        pytest.skip("MySQL not available for integration tests")

    state_path = tmp_path / "mysql_cursor_state.json"

    # Set cursor value to filter records
    from dativo_ingest.validator import IncrementalStateManager

    state_data = {
        "employees.hire_date": {
            "last_value": "1986-06-26",
        }
    }
    IncrementalStateManager.write_state(state_path, state_data)

    extractor = MySQLExtractor(mysql_source_config_incremental)

    incremental_strategy = create_incremental_strategy(
        mysql_source_config_incremental.incremental,
        default_state_path=str(state_path),
    )

    # Extract data with cursor filtering
    batches = list(extractor.extract(state_manager=incremental_strategy))

    # Verify all records have hire_date >= cursor value
    for batch in batches:
        for record in batch:
            if "hire_date" in record:
                # hire_date should be >= 1986-06-26
                hire_date_str = record["hire_date"]
                if isinstance(hire_date_str, str):
                    from datetime import datetime

                    hire_date = datetime.fromisoformat(
                        hire_date_str.split("T")[0]
                    ).date()
                    cursor_date = datetime.fromisoformat("1986-06-26").date()
                    assert hire_date >= cursor_date


@pytest.mark.integration
def test_mysql_extractor_batch_processing(mysql_available, mysql_source_config):
    """Test MySQL extractor processes data in batches."""
    if not mysql_available:
        pytest.skip("MySQL not available for integration tests")

    # Set small batch size
    mysql_source_config.engine = {"options": {"native": {"batch_size": 5}}}

    extractor = MySQLExtractor(mysql_source_config)

    # Extract data
    batches = list(extractor.extract())

    # Should have multiple batches if there are more than 5 records
    total_records = sum(len(batch) for batch in batches)
    if total_records > 5:
        assert len(batches) > 1

    # Each batch should not exceed batch size (allowing for last partial batch)
    for batch in batches[:-1]:  # All but last batch
        assert len(batch) <= 5


@pytest.mark.integration
def test_mysql_extractor_datetime_conversion(mysql_available, mysql_source_config):
    """Test MySQL extractor converts datetime/date objects to ISO strings."""
    if not mysql_available:
        pytest.skip("MySQL not available for integration tests")

    extractor = MySQLExtractor(mysql_source_config)

    # Extract data
    batches = list(extractor.extract())

    # Verify datetime/date conversion
    for batch in batches:
        for record in batch:
            for key, value in record.items():
                # Date/datetime objects should be converted to strings
                if key in ["hire_date", "birth_date"]:
                    assert isinstance(value, str)
                    # Should be ISO format
                    assert "-" in value  # ISO date format has dashes
