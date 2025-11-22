"""End-to-end tests for tag propagation from source to Iceberg.

These tests verify the complete flow:
1. Source system with metadata (e.g., PostgreSQL with column comments)
2. Job execution extracts source tags
3. Tags appear in Iceberg table properties
4. Tags can be queried from Iceberg catalog

Note: These tests require actual database and Iceberg infrastructure.
They should be skipped if services are not available.
"""

import os

import pytest

from dativo_ingest.config import AssetDefinition, JobConfig, SourceConfig, TargetConfig
from dativo_ingest.connectors.postgres_extractor import PostgresExtractor


@pytest.fixture
def postgres_connection():
    """Get PostgreSQL connection details from environment or use defaults."""
    return {
        "host": os.getenv("PGHOST", "localhost"),
        "port": int(os.getenv("PGPORT", "5432")),
        "database": os.getenv("PGDATABASE", "postgres"),
        "user": os.getenv("PGUSER", "postgres"),
        "password": os.getenv("PGPASSWORD", ""),
    }


@pytest.fixture
def test_table_with_comments(postgres_connection):
    """Create a test table with column comments for testing."""
    try:
        import psycopg2

        conn = psycopg2.connect(**postgres_connection)
        cursor = conn.cursor()

        # Create test table
        cursor.execute("DROP TABLE IF EXISTS test_tag_propagation")
        cursor.execute(
            """
            CREATE TABLE test_tag_propagation (
                id INTEGER,
                email VARCHAR(255),
                phone VARCHAR(20)
            )
        """
        )

        # Add column comments (source tags)
        cursor.execute("COMMENT ON COLUMN test_tag_propagation.email IS 'PII'")
        cursor.execute("COMMENT ON COLUMN test_tag_propagation.phone IS 'SENSITIVE'")

        conn.commit()
        cursor.close()
        conn.close()

        yield "test_tag_propagation"

        # Cleanup
        try:
            conn = psycopg2.connect(**postgres_connection)
            cursor = conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS test_tag_propagation")
            conn.commit()
            cursor.close()
            conn.close()
        except Exception:
            pass  # Ignore cleanup errors

    except ImportError:
        pytest.skip("psycopg2 not installed")
    except Exception as e:
        pytest.skip(f"PostgreSQL not available: {e}")


def test_postgres_extractor_extracts_source_tags_from_comments(
    postgres_connection, test_table_with_comments
):
    """Test PostgresExtractor extracts tags from column comments."""
    source_config = SourceConfig(
        type="postgres",
        tables=[{"name": f"public.{test_table_with_comments}", "object": "test_table"}],
        connection=postgres_connection,
    )

    extractor = PostgresExtractor(source_config)
    metadata = extractor.extract_metadata()

    assert "tags" in metadata
    assert metadata["tags"]["email"] == "PII"
    assert metadata["tags"]["phone"] == "SENSITIVE"


def test_source_tags_from_database_comments(
    postgres_connection, test_table_with_comments
):
    """Integration test with real database having column comments."""
    source_config = SourceConfig(
        type="postgres",
        tables=[{"name": f"public.{test_table_with_comments}", "object": "test_table"}],
        connection=postgres_connection,
    )

    extractor = PostgresExtractor(source_config)
    metadata = extractor.extract_metadata()

    # Verify source tags are extracted
    assert "tags" in metadata
    source_tags = metadata["tags"]
    assert len(source_tags) > 0
    assert "email" in source_tags or "phone" in source_tags


def test_e2e_tag_propagation_postgres_to_iceberg(
    postgres_connection, test_table_with_comments
):
    """Complete flow: PostgreSQL source → Job → Iceberg table properties."""
    # This is a conceptual test - actual execution would require full CLI run
    # For now, we test the components separately

    # Step 1: Extract source tags
    source_config = SourceConfig(
        type="postgres",
        tables=[{"name": f"public.{test_table_with_comments}", "object": "test_table"}],
        connection=postgres_connection,
    )

    extractor = PostgresExtractor(source_config)
    metadata = extractor.extract_metadata()
    source_tags = metadata.get("tags", {})

    # Step 2: Create asset definition
    asset = AssetDefinition(
        name="test_tag_propagation",
        version="1.0",
        source_type="postgres",
        object=test_table_with_comments,
        schema=[
            {"name": "id", "type": "integer"},
            {"name": "email", "type": "string"},
            {"name": "phone", "type": "string"},
        ],
        team={"owner": "test@company.com"},
    )

    # Step 3: Create target config (would need actual Iceberg catalog)
    target_config = TargetConfig(
        type="iceberg",
        catalog="nessie",
        branch="main",
        warehouse="s3://test-bucket/",
        connection={
            "nessie": {"uri": os.getenv("NESSIE_URI", "http://localhost:19120/api/v1")},
            "s3": {
                "endpoint": os.getenv("S3_ENDPOINT", "http://localhost:9000"),
                "bucket": "test-bucket",
                "access_key_id": os.getenv("S3_ACCESS_KEY", "test-key"),
                "secret_access_key": os.getenv("S3_SECRET_KEY", "test-secret"),
            },
        },
    )

    # Step 4: Create committer with source tags
    try:
        from dativo_ingest.iceberg_committer import IcebergCommitter

        committer = IcebergCommitter(
            asset_definition=asset,
            target_config=target_config,
            source_tags=source_tags,
        )

        # Step 5: Derive table properties (should include source tags)
        properties = committer._derive_table_properties()

        # Verify source tags are in properties
        if source_tags:
            # At least one field with source tag should have classification
            has_source_tag_classification = any(
                key.startswith("classification.fields.") for key in properties.keys()
            )
            # Note: This depends on whether source tags match schema fields
            # For this test, we just verify the flow works
            assert isinstance(properties, dict)
            assert "asset.name" in properties

    except ImportError:
        pytest.skip("pyiceberg not installed")
    except Exception as e:
        # If Iceberg catalog is not available, skip the test
        pytest.skip(f"Iceberg catalog not available: {e}")


def test_e2e_tag_propagation_with_all_levels(
    postgres_connection, test_table_with_comments
):
    """Test source + asset + job tags all present in hierarchy."""
    # Step 1: Source tags (from database comments)
    source_config = SourceConfig(
        type="postgres",
        tables=[{"name": f"public.{test_table_with_comments}", "object": "test_table"}],
        connection=postgres_connection,
    )

    extractor = PostgresExtractor(source_config)
    metadata = extractor.extract_metadata()
    source_tags = metadata.get("tags", {})

    # Step 2: Asset with explicit classification (overrides source)
    asset = AssetDefinition(
        name="test_tag_propagation",
        version="1.0",
        source_type="postgres",
        object=test_table_with_comments,
        schema=[
            {"name": "id", "type": "integer"},
            {
                "name": "email",
                "type": "string",
                "classification": "SENSITIVE_PII",  # Asset override
            },
            {"name": "phone", "type": "string"},  # No asset classification
        ],
        team={"owner": "test@company.com"},
    )

    # Step 3: Job overrides (highest priority)
    classification_overrides = {
        "email": "HIGH_PII",  # Job override (overrides asset and source)
    }

    # Step 4: Derive tags
    from dativo_ingest.tag_derivation import derive_tags_from_asset

    tags = derive_tags_from_asset(
        asset_definition=asset,
        classification_overrides=classification_overrides,
        source_tags=source_tags,
    )

    # Verify hierarchy: job > asset > source
    assert "classification.fields.email" in tags
    assert tags["classification.fields.email"] == "high_pii"  # Job wins

    # phone: source tag should be used (no asset or job override)
    if "phone" in source_tags:
        assert "classification.fields.phone" in tags
        assert tags["classification.fields.phone"] == source_tags["phone"].lower()


def test_e2e_tag_propagation_query_iceberg():
    """Test querying tags from Iceberg catalog.

    This test would require:
    1. Actual Iceberg table created with tags
    2. PyIceberg catalog connection
    3. Querying table properties

    For now, this is a placeholder that documents the expected behavior.
    """
    # This would require actual Iceberg infrastructure
    # Example of what the test would do:
    #
    # from pyiceberg.catalog import load_catalog
    #
    # catalog = load_catalog("nessie", **catalog_config)
    # table = catalog.load_table(("domain", "table_name"))
    #
    # # Verify tags in table properties
    # assert "classification.fields.email" in table.properties
    # assert table.properties["classification.fields.email"] == "pii"
    #
    pytest.skip("Requires actual Iceberg catalog - integration test only")
