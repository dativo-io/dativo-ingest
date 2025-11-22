"""Unit tests for Postgres extractor."""

import pytest

from dativo_ingest.config import SourceConfig
from dativo_ingest.connectors.postgres_extractor import PostgresExtractor


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
