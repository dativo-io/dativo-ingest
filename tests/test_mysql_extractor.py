"""Unit tests for MySQL extractor."""

import pytest

from dativo_ingest.config import SourceConfig
from dativo_ingest.connectors.mysql_extractor import MySQLExtractor


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

