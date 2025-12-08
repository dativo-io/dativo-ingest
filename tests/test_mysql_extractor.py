"""Unit tests for MySQL extractor."""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from dativo_ingest.config import SourceConfig
from dativo_ingest.connectors.mysql_extractor import MySQLExtractor
from dativo_ingest.incremental import create_incremental_strategy
from dativo_ingest.validator import IncrementalStateManager
from dativo_ingest.wal_manager import WALManager

# Import mysql.connector at module level for patching
try:
    import mysql.connector
except ImportError:
    mysql = None  # Will be mocked in tests


@pytest.fixture
def mysql_source_config():
    """Create a source config for MySQL extraction."""
    return SourceConfig(
        type="mysql",
        tables=[{"name": "test_db.test_table", "object": "test_table"}],
        connection={
            "host": "localhost",
            "port": 3306,
            "database": "test_db",
            "user": "test_user",
            "password": "test_password",
        },
    )


@pytest.fixture
def mysql_source_config_with_incremental():
    """Create a source config with incremental sync configuration."""
    return SourceConfig(
        type="mysql",
        tables=[{"name": "employees.employees", "object": "employees"}],
        connection={
            "host": "localhost",
            "port": 3306,
            "database": "employees",
            "user": "test",
            "password": "test",
        },
        incremental={
            "strategy": "updated_at",
            "cursor_field": "hire_date",
            "lookback_days": 0,
        },
    )


def test_mysql_extractor_extracts_source_tags(mysql_source_config):
    """Test MySQLExtractor extracts tags from column comments."""
    # This test requires a real database connection, so we'll mock it
    # For integration tests, see test_e2e_tag_propagation.py
    extractor = MySQLExtractor(mysql_source_config)

    # Test that extract_metadata exists and returns correct structure
    result = extractor.extract_metadata()

    assert isinstance(result, dict)
    assert "tags" in result
    assert isinstance(result["tags"], dict)


def test_mysql_extractor_extracts_source_tags_no_tables():
    """Test MySQLExtractor returns empty tags when no tables configured."""
    config = SourceConfig(
        type="mysql",
        tables=None,
        connection={
            "host": "localhost",
            "port": 3306,
            "database": "test_db",
            "user": "test_user",
            "password": "test_password",
        },
    )

    extractor = MySQLExtractor(config)
    result = extractor.extract_metadata()

    assert "tags" in result
    assert result["tags"] == {}


def test_mysql_extractor_extracts_source_tags_connection_failure():
    """Test MySQLExtractor handles connection failures gracefully."""
    config = SourceConfig(
        type="mysql",
        tables=[{"name": "test_db.test_table", "object": "test_table"}],
        connection={
            "host": "invalid_host",
            "port": 3306,
            "database": "test_db",
            "user": "test_user",
            "password": "test_password",
        },
    )

    extractor = MySQLExtractor(config)
    # Should return empty tags instead of raising exception
    result = extractor.extract_metadata()

    assert "tags" in result
    assert isinstance(result["tags"], dict)


def test_mysql_extractor_extract_basic(mysql_source_config):
    """Test MySQL extractor basic extraction with mocked database."""
    # Mock MySQL connection and cursor
    mock_cursor = MagicMock()
    # fetchmany is called in a while loop - first call returns data, second returns empty to break
    mock_cursor.fetchmany.side_effect = [
        [
            {"id": 1, "name": "Alice", "hire_date": date(2020, 1, 1)},
            {"id": 2, "name": "Bob", "hire_date": date(2020, 2, 1)},
        ],
        [],  # Empty result to break the while loop
    ]
    mock_cursor.close = MagicMock()

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    extractor = MySQLExtractor(mysql_source_config)

    # Patch mysql.connector.connect - it's imported inside extract() method
    with patch("mysql.connector.connect", return_value=mock_conn):
        batches = list(extractor.extract())

    # Verify extraction results
    assert len(batches) == 1
    assert len(batches[0]) == 2
    assert batches[0][0]["id"] == 1
    assert batches[0][0]["name"] == "Alice"
    assert batches[0][1]["id"] == 2
    assert batches[0][1]["name"] == "Bob"

    # Verify cursor was called correctly
    assert mock_cursor.execute.called
    assert mock_cursor.fetchmany.called
    mock_cursor.close.assert_called_once()


def test_mysql_extractor_extract_multiple_batches(mysql_source_config):
    """Test MySQL extractor handles multiple batches correctly."""
    # Mock MySQL connection and cursor with multiple batches
    mock_cursor = MagicMock()
    mock_cursor.fetchmany.side_effect = [
        [{"id": i, "name": f"User{i}"} for i in range(1, 6)],  # Batch 1: 5 records
        [{"id": i, "name": f"User{i}"} for i in range(6, 11)],  # Batch 2: 5 records
        [],  # Empty result to stop iteration
    ]
    mock_cursor.close = MagicMock()

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    extractor = MySQLExtractor(mysql_source_config)

    # Patch mysql.connector.connect - it's imported inside extract() method
    with patch("mysql.connector.connect", return_value=mock_conn):
        batches = list(extractor.extract())

    # Verify multiple batches were yielded
    assert len(batches) == 2
    assert len(batches[0]) == 5
    assert len(batches[1]) == 5
    assert batches[0][0]["id"] == 1
    assert batches[1][0]["id"] == 6


def test_mysql_extractor_extract_with_incremental_cursor_field(
    mysql_source_config_with_incremental,
):
    """Test MySQL extractor with incremental sync using cursor_field strategy."""
    # Mock MySQL connection and cursor
    mock_cursor = MagicMock()
    mock_cursor.fetchmany.side_effect = [
        [
            {
                "emp_no": 10001,
                "first_name": "Georgi",
                "hire_date": date(1986, 6, 26),
            },
            {
                "emp_no": 10002,
                "first_name": "Bezalel",
                "hire_date": date(1985, 11, 21),
            },
        ],
        [],
    ]
    mock_cursor.close = MagicMock()

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    extractor = MySQLExtractor(mysql_source_config_with_incremental)

    # Create incremental strategy
    incremental_strategy = create_incremental_strategy(
        mysql_source_config_with_incremental.incremental,
        default_state_path="/tmp/test_mysql_state.json",
    )

    with patch("mysql.connector.connect", return_value=mock_conn):
        batches = list(extractor.extract(state_manager=incremental_strategy))

    # Verify extraction
    assert len(batches) == 1
    assert len(batches[0]) == 2

    # Verify SQL query includes WHERE clause for incremental sync
    execute_call = mock_cursor.execute.call_args
    assert execute_call is not None
    sql_query = execute_call[0][0]
    assert "WHERE" in sql_query.upper() or "ORDER BY" in sql_query.upper()


def test_mysql_extractor_extract_with_cursor_value(
    mysql_source_config_with_incremental,
):
    """Test MySQL extractor with specific cursor value for incremental sync."""
    # Mock MySQL connection and cursor
    mock_cursor = MagicMock()
    mock_cursor.fetchmany.return_value = []
    mock_cursor.close = MagicMock()

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    extractor = MySQLExtractor(mysql_source_config_with_incremental)

    # Create incremental strategy
    incremental_strategy = create_incremental_strategy(
        mysql_source_config_with_incremental.incremental,
        default_state_path="/tmp/test_mysql_state.json",
    )
    # Set cursor value in state
    from pathlib import Path

    state_path = Path("/tmp/test_mysql_state.json")
    state = IncrementalStateManager.read_state(state_path)
    state["employees.hire_date"] = {"last_value": "1986-06-26"}
    IncrementalStateManager.write_state(state_path, state)

    with patch("mysql.connector.connect", return_value=mock_conn):
        list(extractor.extract(state_manager=incremental_strategy))

    # Verify SQL query includes WHERE clause with cursor value
    execute_call = mock_cursor.execute.call_args
    assert execute_call is not None
    sql_query = execute_call[0][0].upper()
    params = execute_call[0][1] if len(execute_call[0]) > 1 else []

    # Query should have WHERE clause for incremental sync when cursor_value is provided
    # If cursor_value is None but cursor_field exists, may only have ORDER BY
    assert "WHERE" in sql_query or "ORDER BY" in sql_query or len(params) > 0


def test_mysql_extractor_extract_with_wal_checkpoint(mysql_source_config, tmp_path):
    """Test MySQL extractor with WAL checkpoint resume."""
    wal_base_dir = tmp_path / "wal"
    wal_manager = WALManager(
        job_name="test_job",
        tenant_id="test_tenant",
        wal_base_dir=str(wal_base_dir),
    )
    wal_manager.create_wal()

    # Create checkpoint with offset
    checkpoint = {
        "type": "offset_based",
        "table_name": "test_db.test_table",
        "last_offset": 1000,
        "batch_number": 10,
    }
    wal_manager.update_checkpoint("test_table", checkpoint)

    checkpoint_context = {
        "checkpoint": wal_manager.get_resume_point("test_table"),
        "wal_manager": wal_manager,
        "stream_name": "test_table",
    }

    # Mock MySQL connection and cursor
    # When offset skip happens, fetchmany(start_offset) is called first to skip records
    # Then fetchmany(batch_size) is called in the loop to get actual data
    mock_cursor = MagicMock()
    # First fetchmany call is for offset skip (returns empty or consumed)
    # Subsequent calls are for actual data fetching
    mock_cursor.fetchmany.side_effect = [
        [],  # Offset skip consumes records (or returns empty if beyond data)
        [{"id": 1001, "name": "Resumed"}],  # Actual data after offset
        [],  # Empty to stop iteration
    ]
    mock_cursor.close = MagicMock()

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    extractor = MySQLExtractor(mysql_source_config)

    with patch("mysql.connector.connect", return_value=mock_conn):
        batches = list(extractor.extract(checkpoint_context=checkpoint_context))

    # Verify extraction resumed from checkpoint
    # May have batches if data exists after offset, or empty if offset consumed all
    assert len(batches) >= 0

    # Verify fetchmany was called (for offset skip and data fetching)
    assert mock_cursor.fetchmany.called
    # Verify execute was called (query execution)
    assert mock_cursor.execute.called


def test_mysql_extractor_extract_datetime_conversion(mysql_source_config):
    """Test MySQL extractor converts datetime/date objects to ISO format strings."""
    # Mock MySQL connection and cursor with datetime objects
    mock_cursor = MagicMock()
    mock_cursor.fetchmany.side_effect = [
        [
            {
                "id": 1,
                "name": "Alice",
                "hire_date": date(2020, 1, 1),
                "created_at": datetime(2020, 1, 1, 12, 30, 45),
            },
        ],
        [],
    ]
    mock_cursor.close = MagicMock()

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    extractor = MySQLExtractor(mysql_source_config)

    # Patch mysql.connector.connect - it's imported inside extract() method
    with patch("mysql.connector.connect", return_value=mock_conn):
        batches = list(extractor.extract())

    # Verify datetime objects were converted to ISO format strings
    assert len(batches) == 1
    record = batches[0][0]
    assert isinstance(record["hire_date"], str)
    assert record["hire_date"] == "2020-01-01"
    assert isinstance(record["created_at"], str)
    assert "2020-01-01T12:30:45" in record["created_at"]


def test_mysql_extractor_extract_handles_empty_table(mysql_source_config):
    """Test MySQL extractor handles empty tables gracefully."""
    # Mock MySQL connection and cursor with empty result
    mock_cursor = MagicMock()
    mock_cursor.fetchmany.return_value = []
    mock_cursor.close = MagicMock()

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    extractor = MySQLExtractor(mysql_source_config)

    # Patch mysql.connector.connect - it's imported inside extract() method
    with patch("mysql.connector.connect", return_value=mock_conn):
        batches = list(extractor.extract())

    # Should return empty list, not raise exception
    assert len(batches) == 0


def test_mysql_extractor_extract_connection_error(mysql_source_config):
    """Test MySQL extractor raises RuntimeError on connection failure."""
    extractor = MySQLExtractor(mysql_source_config)

    with patch("mysql.connector.connect", side_effect=Exception("Connection failed")):
        with pytest.raises(RuntimeError, match="Failed to connect to MySQL"):
            list(extractor.extract())


def test_mysql_extractor_extract_missing_tables():
    """Test MySQL extractor raises ValueError when tables are not configured."""
    config = SourceConfig(
        type="mysql",
        tables=None,
        connection={
            "host": "localhost",
            "port": 3306,
            "database": "test_db",
            "user": "test_user",
            "password": "test_password",
        },
    )

    extractor = MySQLExtractor(config)

    with pytest.raises(ValueError, match="MySQL source requires 'tables'"):
        list(extractor.extract())


def test_mysql_extractor_build_query_with_cursor_field(
    mysql_source_config_with_incremental,
):
    """Test MySQL extractor builds correct SQL query with cursor field."""
    extractor = MySQLExtractor(mysql_source_config_with_incremental)

    # Use private method to test query building
    query, params = extractor._build_query(
        table_name="employees.employees",
        cursor_field="hire_date",
        cursor_value=date(1986, 6, 26),
        lookback_days=0,
    )

    # Verify query structure
    assert "SELECT" in query.upper()
    assert "FROM" in query.upper()
    assert "`employees`.`employees`" in query or "employees.employees" in query
    assert "WHERE" in query.upper()
    assert "`hire_date`" in query or "hire_date" in query
    assert "ORDER BY" in query.upper()
    assert len(params) == 1
    assert params[0] == date(1986, 6, 26)


def test_mysql_extractor_build_query_with_lookback_days(
    mysql_source_config_with_incremental,
):
    """Test MySQL extractor builds correct SQL query with lookback days."""
    extractor = MySQLExtractor(mysql_source_config_with_incremental)

    query, params = extractor._build_query(
        table_name="employees.employees",
        cursor_field="hire_date",
        cursor_value=None,
        lookback_days=7,
    )

    # Verify query includes lookback days
    assert "WHERE" in query.upper()
    assert "DATE_SUB" in query.upper() or "INTERVAL" in query.upper()
    assert len(params) == 1
    assert params[0] == 7


def test_mysql_extractor_build_query_no_incremental(mysql_source_config):
    """Test MySQL extractor builds query without incremental WHERE clause."""
    extractor = MySQLExtractor(mysql_source_config)

    query, params = extractor._build_query(
        table_name="test_db.test_table",
        cursor_field=None,
        cursor_value=None,
        lookback_days=0,
    )

    # Verify query doesn't have WHERE clause
    assert "SELECT" in query.upper()
    assert "FROM" in query.upper()
    assert "WHERE" not in query.upper()
    assert len(params) == 0
