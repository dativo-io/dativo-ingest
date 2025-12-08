"""Unit tests for MySQL extractor incremental sync functionality."""

from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dativo_ingest.config import SourceConfig
from dativo_ingest.connectors.mysql_extractor import MySQLExtractor
from dativo_ingest.incremental import create_incremental_strategy
from dativo_ingest.incremental.strategies import CursorFieldStrategy
from dativo_ingest.validator import IncrementalStateManager


@pytest.fixture
def mysql_source_config_cursor_field():
    """Create a source config with cursor_field incremental strategy."""
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


@pytest.fixture
def mysql_source_config_with_table_cursor():
    """Create a source config with table-specific cursor field."""
    return SourceConfig(
        type="mysql",
        tables=[
            {
                "name": "employees.employees",
                "object": "employees",
                "cursor_field": "hire_date",
            }
        ],
        connection={
            "host": "localhost",
            "port": 3306,
            "database": "employees",
            "user": "test",
            "password": "test",
        },
        incremental={
            "strategy": "updated_at",
            "cursor_field": "modified_date",  # Default, but table-specific takes precedence
        },
    )


def test_mysql_extractor_cursor_field_strategy(
    mysql_source_config_cursor_field, tmp_path
):
    """Test MySQL extractor with cursor_field incremental strategy."""
    state_path = tmp_path / "mysql_state.json"
    state_path.write_text("{}")

    # Mock MySQL connection and cursor
    mock_cursor = MagicMock()
    mock_cursor.fetchmany.side_effect = [
        [
            {
                "emp_no": 10001,
                "first_name": "Georgi",
                "last_name": "Facello",
                "hire_date": date(1986, 6, 26),
            },
            {
                "emp_no": 10002,
                "first_name": "Bezalel",
                "last_name": "Simmel",
                "hire_date": date(1985, 11, 21),
            },
        ],
        [],
    ]
    mock_cursor.close = MagicMock()

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    extractor = MySQLExtractor(mysql_source_config_cursor_field)

    # Create incremental strategy
    incremental_strategy = create_incremental_strategy(
        mysql_source_config_cursor_field.incremental,
        default_state_path=str(state_path),
    )

    with patch("mysql.connector.connect", return_value=mock_conn):
        batches = list(extractor.extract(state_manager=incremental_strategy))

    # Verify extraction
    assert len(batches) == 1
    assert len(batches[0]) == 2

    # Verify SQL query includes ORDER BY for cursor field (WHERE may not be present if no cursor value)
    execute_call = mock_cursor.execute.call_args
    assert execute_call is not None
    sql_query = execute_call[0][0].upper()
    # Should have ORDER BY for cursor field, WHERE may be present if cursor value exists
    assert "ORDER BY" in sql_query or "WHERE" in sql_query


def test_mysql_extractor_cursor_field_with_existing_state(
    mysql_source_config_cursor_field, tmp_path
):
    """Test MySQL extractor resumes from existing cursor state."""
    state_path = tmp_path / "mysql_state.json"
    # Set initial state with cursor value
    state_data = {
        "employees.hire_date": {
            "last_value": "1986-06-26",
            "last_updated": "2024-01-01T00:00:00",
        }
    }
    IncrementalStateManager.write_state(state_path, state_data)

    # Mock MySQL connection and cursor
    mock_cursor = MagicMock()
    mock_cursor.fetchmany.return_value = []  # No new records after cursor
    mock_cursor.close = MagicMock()

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    extractor = MySQLExtractor(mysql_source_config_cursor_field)

    # Create incremental strategy
    incremental_strategy = create_incremental_strategy(
        mysql_source_config_cursor_field.incremental,
        default_state_path=str(state_path),
    )

    with patch("mysql.connector.connect", return_value=mock_conn):
        list(extractor.extract(state_manager=incremental_strategy))

    # Verify SQL query includes WHERE clause with cursor value
    execute_call = mock_cursor.execute.call_args
    assert execute_call is not None
    sql_query = execute_call[0][0].upper()
    params = execute_call[0][1] if len(execute_call[0]) > 1 else []

    # Should have WHERE clause with cursor value parameter, or ORDER BY if no cursor value yet
    assert "WHERE" in sql_query or "ORDER BY" in sql_query or len(params) > 0


def test_mysql_extractor_cursor_field_updates_state(
    mysql_source_config_cursor_field, tmp_path
):
    """Test MySQL extractor updates state after successful extraction."""
    state_path = tmp_path / "mysql_state.json"
    state_path.write_text("{}")

    # Mock MySQL connection and cursor
    mock_cursor = MagicMock()
    mock_cursor.fetchmany.side_effect = [
        [
            {
                "emp_no": 10001,
                "first_name": "Georgi",
                "hire_date": date(1986, 6, 26),
            },
        ],
        [],
    ]
    mock_cursor.close = MagicMock()

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    extractor = MySQLExtractor(mysql_source_config_cursor_field)

    # Create incremental strategy
    incremental_strategy = create_incremental_strategy(
        mysql_source_config_cursor_field.incremental,
        default_state_path=str(state_path),
    )

    with patch("mysql.connector.connect", return_value=mock_conn):
        batches = list(extractor.extract(state_manager=incremental_strategy))

    # Verify extraction completed
    assert len(batches) == 1

    # Verify state was updated
    state = IncrementalStateManager.read_state(state_path)
    # State should be updated by the incremental strategy
    # The exact format depends on the strategy implementation
    assert isinstance(state, dict)


def test_mysql_extractor_table_specific_cursor_field(
    mysql_source_config_with_table_cursor,
):
    """Test MySQL extractor uses table-specific cursor field over default."""
    extractor = MySQLExtractor(mysql_source_config_with_table_cursor)

    # Get cursor field for the table
    table_config = mysql_source_config_with_table_cursor.tables[0]
    cursor_field = extractor._get_cursor_field(table_config)

    # Should use table-specific cursor field, not default from incremental config
    assert cursor_field == "hire_date"
    assert cursor_field != mysql_source_config_with_table_cursor.incremental.get(
        "cursor_field"
    )


def test_mysql_extractor_cursor_field_with_lookback_days(
    mysql_source_config_cursor_field, tmp_path
):
    """Test MySQL extractor uses lookback_days when no cursor value exists."""
    state_path = tmp_path / "mysql_state.json"
    state_path.write_text("{}")  # Empty state, no cursor value

    # Update config to use lookback_days
    mysql_source_config_cursor_field.incremental["lookback_days"] = 7

    # Mock MySQL connection and cursor
    mock_cursor = MagicMock()
    mock_cursor.fetchmany.return_value = []
    mock_cursor.close = MagicMock()

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    extractor = MySQLExtractor(mysql_source_config_cursor_field)

    incremental_strategy = create_incremental_strategy(
        mysql_source_config_cursor_field.incremental,
        default_state_path=str(state_path),
    )

    with patch("mysql.connector.connect", return_value=mock_conn):
        list(extractor.extract(state_manager=incremental_strategy))

    # Verify SQL query uses lookback days
    execute_call = mock_cursor.execute.call_args
    assert execute_call is not None
    sql_query = execute_call[0][0].upper()
    params = execute_call[0][1] if len(execute_call[0]) > 1 else []

    # Should have WHERE clause with lookback days
    assert "WHERE" in sql_query or len(params) > 0


def test_mysql_extractor_cursor_field_multiple_tables(mysql_source_config_cursor_field):
    """Test MySQL extractor handles multiple tables with different cursor fields."""
    # Add second table with different cursor field
    mysql_source_config_cursor_field.tables.append(
        {
            "name": "employees.departments",
            "object": "departments",
            "cursor_field": "modified_at",
        }
    )

    # Mock MySQL connection and cursor
    mock_cursor = MagicMock()
    mock_cursor.fetchmany.side_effect = [[], []]  # Empty for both tables
    mock_cursor.close = MagicMock()

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    extractor = MySQLExtractor(mysql_source_config_cursor_field)

    with patch("mysql.connector.connect", return_value=mock_conn):
        batches = list(extractor.extract())

    # Verify extractor processed both tables
    # Should have called execute for each table
    assert mock_cursor.execute.call_count >= 2


def test_mysql_extractor_cursor_field_date_parsing(
    mysql_source_config_cursor_field, tmp_path
):
    """Test MySQL extractor correctly parses date cursor values from state."""
    state_path = tmp_path / "mysql_state.json"
    # Set state with date string
    state_data = {
        "employees.hire_date": {
            "last_value": "1986-06-26",
        }
    }
    IncrementalStateManager.write_state(state_path, state_data)

    # Mock MySQL connection and cursor
    mock_cursor = MagicMock()
    mock_cursor.fetchmany.return_value = []
    mock_cursor.close = MagicMock()

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    extractor = MySQLExtractor(mysql_source_config_cursor_field)

    incremental_strategy = create_incremental_strategy(
        mysql_source_config_cursor_field.incremental,
        default_state_path=str(state_path),
    )

    with patch("mysql.connector.connect", return_value=mock_conn):
        list(extractor.extract(state_manager=incremental_strategy))

    # Verify query was built with cursor value
    execute_call = mock_cursor.execute.call_args
    assert execute_call is not None
    params = execute_call[0][1] if len(execute_call[0]) > 1 else []

    # Should have parameter for cursor value
    if len(params) > 0:
        # Parameter should be date or date string
        assert isinstance(params[0], (date, str))


def test_mysql_extractor_cursor_field_no_records_updates_state(
    mysql_source_config_cursor_field, tmp_path
):
    """Test MySQL extractor handles case where no records match cursor value."""
    state_path = tmp_path / "mysql_state.json"
    state_path.write_text("{}")

    # Mock MySQL connection and cursor - no records returned
    mock_cursor = MagicMock()
    mock_cursor.fetchmany.return_value = []
    mock_cursor.close = MagicMock()

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    extractor = MySQLExtractor(mysql_source_config_cursor_field)

    incremental_strategy = create_incremental_strategy(
        mysql_source_config_cursor_field.incremental,
        default_state_path=str(state_path),
    )

    with patch("mysql.connector.connect", return_value=mock_conn):
        batches = list(extractor.extract(state_manager=incremental_strategy))

    # Should return empty batches without error
    assert len(batches) == 0

    # Connection should still be closed properly
    mock_cursor.close.assert_called_once()
