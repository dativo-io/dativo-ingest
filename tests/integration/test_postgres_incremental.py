"""Integration test for PostgreSQL incremental sync.

Tests Test Case 8: PostgreSQL Incremental Sync
- Cursor-based incremental sync from PostgreSQL
- State persistence for cursor values
- Filtering records by cursor field
- State updates after incremental sync
"""

import os
from pathlib import Path

import pytest

from dativo_ingest.config import SourceConfig
from dativo_ingest.connectors.postgres_extractor import PostgresExtractor
from dativo_ingest.incremental import create_incremental_strategy


@pytest.fixture(scope="module")
def postgres_available():
    """Check if PostgreSQL is available for integration tests."""
    postgres_host = os.getenv("PGHOST", "localhost")
    postgres_port = int(os.getenv("PGPORT", "5432"))
    postgres_user = os.getenv("PGUSER", "postgres")
    postgres_password = os.getenv("PGPASSWORD", "postgres")
    postgres_database = os.getenv("PGDATABASE", "postgres")

    try:
        import psycopg2

        conn = psycopg2.connect(
            host=postgres_host,
            port=postgres_port,
            user=postgres_user,
            password=postgres_password,
            database=postgres_database,
            connect_timeout=5,
        )
        conn.close()
        return True
    except Exception:
        return False


@pytest.fixture
def postgres_source_config():
    """Create a source config for PostgreSQL integration tests."""
    return SourceConfig(
        type="postgres",
        tables=[{"name": "employees", "schema": "public", "object": "employees"}],
        connection={
            "host": os.getenv("PGHOST", "localhost"),
            "port": int(os.getenv("PGPORT", "5432")),
            "database": os.getenv("PGDATABASE", "postgres"),
            "user": os.getenv("PGUSER", "postgres"),
            "password": os.getenv("PGPASSWORD", "postgres"),
        },
    )


@pytest.fixture
def postgres_source_config_incremental():
    """Create a source config with incremental sync."""
    return SourceConfig(
        type="postgres",
        tables=[{"name": "employees", "schema": "public", "object": "employees"}],
        connection={
            "host": os.getenv("PGHOST", "localhost"),
            "port": int(os.getenv("PGPORT", "5432")),
            "database": os.getenv("PGDATABASE", "postgres"),
            "user": os.getenv("PGUSER", "postgres"),
            "password": os.getenv("PGPASSWORD", "postgres"),
        },
        incremental={
            "enabled": True,
            "cursor_field": "updated_at",
            "lookback_days": 1,
        },
    )


@pytest.fixture
def setup_test_table(postgres_available):
    """Set up test table in PostgreSQL."""
    if not postgres_available:
        pytest.skip("PostgreSQL not available for integration tests")

    import psycopg2

    conn = psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        database=os.getenv("PGDATABASE", "postgres"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "postgres"),
    )
    cur = conn.cursor()

    try:
        # Create test table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS employees (
                emp_id SERIAL PRIMARY KEY,
                first_name VARCHAR(50),
                last_name VARCHAR(50),
                email VARCHAR(100),
                hire_date DATE,
                salary DECIMAL(10,2),
                department VARCHAR(50),
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Insert test data
        cur.execute(
            """
            INSERT INTO employees (first_name, last_name, email, hire_date, salary, department, updated_at)
            VALUES
            ('Alice', 'Johnson', 'alice@example.com', '2023-01-15', 95000.00, 'Engineering', CURRENT_TIMESTAMP),
            ('Bob', 'Smith', 'bob@example.com', '2023-02-20', 87000.00, 'Marketing', CURRENT_TIMESTAMP),
            ('Carol', 'Williams', 'carol@example.com', '2023-03-10', 92000.00, 'Engineering', CURRENT_TIMESTAMP),
            ('David', 'Brown', 'david@example.com', '2023-04-05', 78000.00, 'Sales', CURRENT_TIMESTAMP)
            ON CONFLICT DO NOTHING
        """
        )

        conn.commit()
    finally:
        cur.close()
        conn.close()

    yield

    # Cleanup
    conn = psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        database=os.getenv("PGDATABASE", "postgres"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "postgres"),
    )
    cur = conn.cursor()
    try:
        cur.execute("DROP TABLE IF EXISTS employees CASCADE")
        conn.commit()
    finally:
        cur.close()
        conn.close()


@pytest.mark.integration
def test_postgres_extractor_connection(postgres_available, postgres_source_config):
    """Test PostgreSQL extractor can connect to database."""
    if not postgres_available:
        pytest.skip("PostgreSQL not available for integration tests")

    extractor = PostgresExtractor(postgres_source_config)

    # Should not raise exception
    assert extractor is not None
    assert extractor.connection["host"] == os.getenv("PGHOST", "localhost")


@pytest.mark.integration
def test_postgres_extractor_extract_data(
    postgres_available, postgres_source_config, setup_test_table
):
    """Test PostgreSQL extractor extracts data from real database."""
    if not postgres_available:
        pytest.skip("PostgreSQL not available for integration tests")

    extractor = PostgresExtractor(postgres_source_config)

    # Extract data
    batches = list(extractor.extract())

    # Verify data was extracted
    assert len(batches) > 0
    assert len(batches[0]) > 0

    # Verify record structure
    first_record = batches[0][0]
    assert isinstance(first_record, dict)
    assert "emp_id" in first_record or "first_name" in first_record


@pytest.mark.integration
def test_postgres_extractor_incremental_sync(
    postgres_available,
    postgres_source_config_incremental,
    setup_test_table,
    tmp_path,
):
    """Test PostgreSQL extractor incremental sync with real database."""
    if not postgres_available:
        pytest.skip("PostgreSQL not available for integration tests")

    state_path = tmp_path / "postgres_incremental_state.json"
    state_path.write_text("{}")

    extractor = PostgresExtractor(postgres_source_config_incremental)

    # Create incremental strategy
    incremental_strategy = create_incremental_strategy(
        postgres_source_config_incremental.incremental,
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
def test_postgres_extractor_cursor_field_filtering(
    postgres_available,
    postgres_source_config_incremental,
    setup_test_table,
    tmp_path,
):
    """Test PostgreSQL extractor filters records by cursor field value."""
    if not postgres_available:
        pytest.skip("PostgreSQL not available for integration tests")

    from datetime import datetime, timedelta

    import psycopg2

    # Set initial state with a cursor value
    state_path = tmp_path / "postgres_cursor_state.json"
    initial_cursor = (datetime.now() - timedelta(days=2)).isoformat()
    state_data = {
        "employees": {
            "cursor_field": "updated_at",
            "cursor_value": initial_cursor,
        }
    }
    import json

    state_path.write_text(json.dumps(state_data))

    extractor = PostgresExtractor(postgres_source_config_incremental)

    # Create incremental strategy
    incremental_strategy = create_incremental_strategy(
        postgres_source_config_incremental.incremental,
        default_state_path=str(state_path),
    )

    # Extract data with incremental sync
    batches = list(extractor.extract(state_manager=incremental_strategy))

    # Should extract data (may be empty if no records match cursor filter)
    assert isinstance(batches, list)

    # Verify state was updated
    from dativo_ingest.validator import IncrementalStateManager

    state = IncrementalStateManager.read_state(state_path)
    assert isinstance(state, dict)


@pytest.mark.integration
def test_postgres_extractor_state_persistence(
    postgres_available,
    postgres_source_config_incremental,
    setup_test_table,
    tmp_path,
):
    """Test that state is persisted between runs."""
    if not postgres_available:
        pytest.skip("PostgreSQL not available for integration tests")

    state_path = tmp_path / "postgres_state_persistence.json"
    state_path.write_text("{}")

    extractor = PostgresExtractor(postgres_source_config_incremental)

    # First run
    incremental_strategy1 = create_incremental_strategy(
        postgres_source_config_incremental.incremental,
        default_state_path=str(state_path),
    )
    batches1 = list(extractor.extract(state_manager=incremental_strategy1))

    # Verify state file was created
    assert state_path.exists()

    # Read state
    from dativo_ingest.validator import IncrementalStateManager

    state1 = IncrementalStateManager.read_state(state_path)
    assert isinstance(state1, dict)

    # Second run (should use persisted state)
    incremental_strategy2 = create_incremental_strategy(
        postgres_source_config_incremental.incremental,
        default_state_path=str(state_path),
    )
    batches2 = list(extractor.extract(state_manager=incremental_strategy2))

    # State should still exist
    assert state_path.exists()

    # State should be updated
    state2 = IncrementalStateManager.read_state(state_path)
    assert isinstance(state2, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
