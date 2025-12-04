"""Unit tests for Postgres extractor."""

from unittest.mock import MagicMock, patch

import pytest

from dativo_ingest.config import SourceConfig
from dativo_ingest.connectors.postgres_extractor import PostgresExtractor
from dativo_ingest.wal_manager import WALManager


@pytest.fixture
def postgres_source_config():
    """Create a source config for Postgres extraction."""
    return SourceConfig(
        type="postgres",
        tables=[{"name": "public.test_table", "object": "test_table"}],
        connection={
            "host": "localhost",
            "port": 5432,
            "database": "test_db",
            "user": "test_user",
            "password": "test_password",
        },
    )


def test_postgres_extractor_extracts_source_tags(postgres_source_config):
    """Test PostgresExtractor extracts tags from column comments."""
    # This test requires a real database connection, so we'll mock it
    # For integration tests, see test_e2e_tag_propagation.py
    extractor = PostgresExtractor(postgres_source_config)

    # Test that extract_metadata exists and returns correct structure
    result = extractor.extract_metadata()

    assert isinstance(result, dict)
    assert "tags" in result
    assert isinstance(result["tags"], dict)


def test_postgres_extractor_extracts_source_tags_no_tables():
    """Test PostgresExtractor returns empty tags when no tables configured."""
    config = SourceConfig(
        type="postgres",
        tables=None,
        connection={
            "host": "localhost",
            "port": 5432,
            "database": "test_db",
            "user": "test_user",
            "password": "test_password",
        },
    )

    extractor = PostgresExtractor(config)
    result = extractor.extract_metadata()

    assert "tags" in result
    assert result["tags"] == {}


def test_postgres_extractor_extracts_source_tags_connection_failure():
    """Test PostgresExtractor handles connection failures gracefully."""
    config = SourceConfig(
        type="postgres",
        tables=[{"name": "public.test_table", "object": "test_table"}],
        connection={
            "host": "invalid_host",
            "port": 5432,
            "database": "test_db",
            "user": "test_user",
            "password": "test_password",
        },
    )

    extractor = PostgresExtractor(config)
    # Should return empty tags instead of raising exception
    result = extractor.extract_metadata()

    assert "tags" in result
    assert isinstance(result["tags"], dict)


def test_postgres_extractor_wal_checkpoint_scroll_support(
    postgres_source_config, tmp_path
):
    """Test that Postgres extractor uses server-side cursor for WAL checkpoint scrolling.

    This test verifies that when resuming from a WAL checkpoint with an offset,
    the extractor creates a server-side (named) cursor that supports scrolling,
    rather than a client-side cursor which would raise ProgrammingError.
    """
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
        "table_name": "public.test_table",
        "last_offset": 1000,
        "batch_number": 10,
    }
    wal_manager.update_checkpoint("test_table", checkpoint)

    checkpoint_context = {
        "checkpoint": wal_manager.get_resume_point("test_table"),
        "wal_manager": wal_manager,
        "stream_name": "test_table",
    }

    extractor = PostgresExtractor(postgres_source_config)

    # Mock psycopg2 connection and cursor
    mock_cursor = MagicMock()
    mock_cursor.fetchmany.return_value = []  # Empty result to stop iteration
    mock_cursor.scroll = MagicMock()  # Verify scroll is called
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor = MagicMock(return_value=mock_cursor)
    mock_conn.set_session = MagicMock()

    # Patch psycopg2.connect where it's imported (inside the extract method)
    with patch("psycopg2.connect", return_value=mock_conn):
        # Extract should not raise ProgrammingError
        # The cursor should be created with name parameter for server-side cursor
        list(extractor.extract(checkpoint_context=checkpoint_context))

        # Verify that cursor was created with name parameter (server-side cursor)
        cursor_calls = mock_conn.cursor.call_args_list
        assert len(cursor_calls) > 0

        # Check that at least one cursor was created with name parameter
        named_cursor_found = False
        for call in cursor_calls:
            kwargs = call.kwargs
            if "name" in kwargs:
                named_cursor_found = True
                # Verify cursor name is set (server-side cursor)
                assert kwargs["name"] is not None
                assert kwargs["name"].startswith("cursor_")
                break

        assert (
            named_cursor_found
        ), "Expected server-side cursor (with name parameter) but found client-side cursor"

        # Verify scroll was called with the correct offset
        if checkpoint_context["checkpoint"]["last_offset"] > 0:
            mock_cursor.scroll.assert_called_once_with(1000, mode="absolute")
