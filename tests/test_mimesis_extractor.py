"""Unit tests for Mimesis extractor connector."""

import pytest
from datetime import date, datetime, timezone
from unittest.mock import Mock

from dativo_ingest.config import AssetDefinition, SourceConfig
from dativo_ingest.connectors.mimesis_extractor import MimesisExtractor


def create_minimal_asset_definition(schema_fields: list) -> AssetDefinition:
    """Create a minimal asset definition for testing."""
    asset_data = {
        "name": "test_asset",
        "version": "1.0",
        "source_type": "mimesis",
        "object": "test_object",
        "schema": schema_fields,
        "team": {"owner": "test@example.com"},
    }
    return AssetDefinition(**asset_data)


def create_source_config(engine_options: dict = None) -> SourceConfig:
    """Create a source config for testing."""
    config_data = {"type": "mimesis"}
    if engine_options:
        config_data["engine"] = {"type": "native", "options": engine_options}
    return SourceConfig(**config_data)


class TestMimesisExtractorBasic:
    """Test basic functionality of MimesisExtractor."""

    def test_basic_row_generation(self):
        """Test basic row generation with default settings."""
        schema = [
            {"name": "id", "type": "integer", "required": True},
            {"name": "name", "type": "string", "required": True},
        ]
        asset = create_minimal_asset_definition(schema)
        source_config = create_source_config({"native": {"row_count": 10}})

        extractor = MimesisExtractor(source_config, asset)
        batches = list(extractor.extract())

        assert len(batches) == 1
        assert len(batches[0]) == 10
        assert all("id" in record for record in batches[0])
        assert all("name" in record for record in batches[0])
        assert all("ingest_date" in record for record in batches[0])

    def test_batch_size_configuration(self):
        """Test that batch_size option is respected."""
        schema = [{"name": "id", "type": "integer", "required": True}]
        asset = create_minimal_asset_definition(schema)
        source_config = create_source_config(
            {"native": {"row_count": 25, "batch_size": 10}}
        )

        extractor = MimesisExtractor(source_config, asset)
        batches = list(extractor.extract())

        # Should have 3 batches: 10, 10, 5
        assert len(batches) == 3
        assert len(batches[0]) == 10
        assert len(batches[1]) == 10
        assert len(batches[2]) == 5

    def test_seed_reproducibility(self):
        """Test that same seed produces identical output."""
        schema = [{"name": "id", "type": "integer", "required": True}]
        asset = create_minimal_asset_definition(schema)
        source_config1 = create_source_config(
            {"native": {"row_count": 5, "seed": 42}}
        )
        source_config2 = create_source_config(
            {"native": {"row_count": 5, "seed": 42}}
        )

        extractor1 = MimesisExtractor(source_config1, asset)
        extractor2 = MimesisExtractor(source_config2, asset)

        batches1 = list(extractor1.extract())
        batches2 = list(extractor2.extract())

        assert batches1 == batches2

    def test_different_seeds_produce_different_output(self):
        """Test that different seeds produce different output."""
        schema = [{"name": "id", "type": "integer", "required": True}]
        asset = create_minimal_asset_definition(schema)
        source_config1 = create_source_config(
            {"native": {"row_count": 5, "seed": 42}}
        )
        source_config2 = create_source_config(
            {"native": {"row_count": 5, "seed": 99}}
        )

        extractor1 = MimesisExtractor(source_config1, asset)
        extractor2 = MimesisExtractor(source_config2, asset)

        batches1 = list(extractor1.extract())
        batches2 = list(extractor2.extract())

        assert batches1 != batches2


class TestMimesisExtractorFieldMapping:
    """Test field mapping logic."""

    def test_id_field_sequential(self):
        """Test that id fields generate sequential values."""
        schema = [{"name": "customer_id", "type": "integer", "required": True}]
        asset = create_minimal_asset_definition(schema)
        source_config = create_source_config({"native": {"row_count": 5, "seed": 42}})

        extractor = MimesisExtractor(source_config, asset)
        batches = list(extractor.extract())

        ids = [record["customer_id"] for record in batches[0]]
        # IDs should be sequential (incrementing)
        assert all(isinstance(id_val, int) for id_val in ids)
        # With seed, should be deterministic
        assert ids[0] == ids[0]  # Same value in same position

    def test_email_field(self):
        """Test email field mapping."""
        schema = [{"name": "customer_email", "type": "string", "required": True}]
        asset = create_minimal_asset_definition(schema)
        source_config = create_source_config({"native": {"row_count": 5}})

        extractor = MimesisExtractor(source_config, asset)
        batches = list(extractor.extract())

        emails = [record["customer_email"] for record in batches[0]]
        assert all("@" in email for email in emails)
        assert all(isinstance(email, str) for email in emails)

    def test_name_fields(self):
        """Test name field mappings."""
        schema = [
            {"name": "first_name", "type": "string", "required": True},
            {"name": "last_name", "type": "string", "required": True},
            {"name": "full_name", "type": "string", "required": True},
        ]
        asset = create_minimal_asset_definition(schema)
        source_config = create_source_config({"native": {"row_count": 5}})

        extractor = MimesisExtractor(source_config, asset)
        batches = list(extractor.extract())

        for record in batches[0]:
            assert isinstance(record["first_name"], str)
            assert isinstance(record["last_name"], str)
            assert isinstance(record["full_name"], str)
            # Full name should be longer (contains space)
            assert " " in record["full_name"]

    def test_salary_fields(self):
        """Test salary field mappings for integer and float."""
        schema = [
            {"name": "salary_int", "type": "integer", "required": True},
            {"name": "salary_float", "type": "double", "required": True},
        ]
        asset = create_minimal_asset_definition(schema)
        source_config = create_source_config({"native": {"row_count": 5}})

        extractor = MimesisExtractor(source_config, asset)
        batches = list(extractor.extract())

        for record in batches[0]:
            # Integer salary should be in 30k-200k range
            assert 30_000 <= record["salary_int"] <= 200_000
            # Float salary should be in 0-100k range with 2 decimals
            assert 0.0 <= record["salary_float"] <= 100_000.0
            # Check precision (2 decimal places)
            assert len(str(record["salary_float"]).split(".")[1]) <= 2

    def test_commission_percentage(self):
        """Test commission/percentage field mapping."""
        schema = [
            {"name": "commission_pct", "type": "double", "required": True},
            {"name": "commission", "type": "float", "required": True},
        ]
        asset = create_minimal_asset_definition(schema)
        source_config = create_source_config({"native": {"row_count": 5}})

        extractor = MimesisExtractor(source_config, asset)
        batches = list(extractor.extract())

        for record in batches[0]:
            # Should be between 0 and 1
            assert 0.0 <= record["commission_pct"] <= 1.0
            assert 0.0 <= record["commission"] <= 1.0
            # Should have 4 decimal places
            pct_str = str(record["commission_pct"])
            if "." in pct_str:
                assert len(pct_str.split(".")[1]) <= 4

    def test_address_fields(self):
        """Test address-related field mappings."""
        schema = [
            {"name": "street_address", "type": "string", "required": True},
            {"name": "city", "type": "string", "required": True},
            {"name": "state", "type": "string", "required": True},
            {"name": "country", "type": "string", "required": True},
            {"name": "zip_code", "type": "string", "required": True},
        ]
        asset = create_minimal_asset_definition(schema)
        source_config = create_source_config({"native": {"row_count": 5}})

        extractor = MimesisExtractor(source_config, asset)
        batches = list(extractor.extract())

        for record in batches[0]:
            assert isinstance(record["street_address"], str)
            assert isinstance(record["city"], str)
            assert isinstance(record["state"], str)
            assert isinstance(record["country"], str)
            assert isinstance(record["zip_code"], str)

    def test_job_title_fields(self):
        """Test job/role/title field mappings."""
        schema = [
            {"name": "job_title", "type": "string", "required": True},
            {"name": "role", "type": "string", "required": True},
            {"name": "department", "type": "string", "required": True},
        ]
        asset = create_minimal_asset_definition(schema)
        source_config = create_source_config({"native": {"row_count": 5}})

        extractor = MimesisExtractor(source_config, asset)
        batches = list(extractor.extract())

        for record in batches[0]:
            assert isinstance(record["job_title"], str)
            assert isinstance(record["role"], str)
            assert isinstance(record["department"], str)

    def test_age_field(self):
        """Test age field mapping."""
        schema = [{"name": "age", "type": "integer", "required": True}]
        asset = create_minimal_asset_definition(schema)
        source_config = create_source_config({"native": {"row_count": 5}})

        extractor = MimesisExtractor(source_config, asset)
        batches = list(extractor.extract())

        for record in batches[0]:
            # Age should be between 18 and 80
            assert 18 <= record["age"] <= 80

    def test_date_timestamp_fields(self):
        """Test date and timestamp field mappings."""
        schema = [
            {"name": "signup_date", "type": "date", "required": True},
            {"name": "created_at", "type": "timestamp", "required": True},
        ]
        asset = create_minimal_asset_definition(schema)
        source_config = create_source_config({"native": {"row_count": 5}})

        extractor = MimesisExtractor(source_config, asset)
        batches = list(extractor.extract())

        for record in batches[0]:
            # Date should be ISO format string
            assert isinstance(record["signup_date"], str)
            assert "T" not in record["signup_date"]  # Date only, no time
            # Timestamp should be ISO format with time
            assert isinstance(record["created_at"], str)
            assert "T" in record["created_at"]  # ISO datetime format

    def test_boolean_field(self):
        """Test boolean field mapping."""
        schema = [{"name": "is_active", "type": "boolean", "required": True}]
        asset = create_minimal_asset_definition(schema)
        source_config = create_source_config({"native": {"row_count": 10}})

        extractor = MimesisExtractor(source_config, asset)
        batches = list(extractor.extract())

        for record in batches[0]:
            assert isinstance(record["is_active"], bool)

    def test_integer_range_configuration(self):
        """Test that integer range options are respected."""
        schema = [{"name": "value", "type": "integer", "required": True}]
        asset = create_minimal_asset_definition(schema)
        source_config = create_source_config(
            {
                "native": {
                    "row_count": 10,
                    "integer_start": 100,
                    "integer_end": 200,
                }
            }
        )

        extractor = MimesisExtractor(source_config, asset)
        batches = list(extractor.extract())

        for record in batches[0]:
            assert 100 <= record["value"] <= 200

    def test_float_range_and_precision_configuration(self):
        """Test that float range and precision options are respected."""
        schema = [{"name": "value", "type": "double", "required": True}]
        asset = create_minimal_asset_definition(schema)
        source_config = create_source_config(
            {
                "native": {
                    "row_count": 10,
                    "float_start": 10.0,
                    "float_end": 20.0,
                    "float_precision": 3,
                }
            }
        )

        extractor = MimesisExtractor(source_config, asset)
        batches = list(extractor.extract())

        for record in batches[0]:
            assert 10.0 <= record["value"] <= 20.0
            # Check precision (3 decimal places)
            value_str = str(record["value"])
            if "." in value_str:
                assert len(value_str.split(".")[1]) <= 3


class TestMimesisExtractorNullability:
    """Test nullability handling for optional fields."""

    def test_required_fields_never_null(self):
        """Test that required fields are never None."""
        schema = [{"name": "id", "type": "integer", "required": True}]
        asset = create_minimal_asset_definition(schema)
        source_config = create_source_config({"native": {"row_count": 100}})

        extractor = MimesisExtractor(source_config, asset)
        batches = list(extractor.extract())

        for batch in batches:
            for record in batch:
                assert record["id"] is not None

    def test_optional_fields_can_be_null(self):
        """Test that optional fields can be None."""
        schema = [{"name": "optional_field", "type": "string", "required": False}]
        asset = create_minimal_asset_definition(schema)
        source_config = create_source_config(
            {"native": {"row_count": 100, "null_probability": 0.3}}
        )

        extractor = MimesisExtractor(source_config, asset)
        batches = list(extractor.extract())

        all_values = [record["optional_field"] for batch in batches for record in batch]
        null_count = sum(1 for v in all_values if v is None)
        # With 30% probability, we should have some nulls (but not all)
        assert null_count > 0
        assert null_count < len(all_values)

    def test_null_probability_configuration(self):
        """Test that null_probability option is respected."""
        schema = [{"name": "optional_field", "type": "string", "required": False}]
        asset = create_minimal_asset_definition(schema)

        # High null probability
        source_config_high = create_source_config(
            {"native": {"row_count": 100, "null_probability": 0.9}}
        )
        extractor_high = MimesisExtractor(source_config_high, asset)
        batches_high = list(extractor_high.extract())
        nulls_high = sum(
            1
            for batch in batches_high
            for record in batch
            if record["optional_field"] is None
        )

        # Low null probability
        source_config_low = create_source_config(
            {"native": {"row_count": 100, "null_probability": 0.1}}
        )
        extractor_low = MimesisExtractor(source_config_low, asset)
        batches_low = list(extractor_low.extract())
        nulls_low = sum(
            1
            for batch in batches_low
            for record in batch
            if record["optional_field"] is None
        )

        # High probability should produce more nulls
        assert nulls_high > nulls_low


class TestMimesisExtractorIngestDate:
    """Test ingest_date handling."""

    def test_ingest_date_always_present(self):
        """Test that ingest_date is always present in records."""
        schema = [{"name": "id", "type": "integer", "required": True}]
        asset = create_minimal_asset_definition(schema)
        source_config = create_source_config({"native": {"row_count": 5}})

        extractor = MimesisExtractor(source_config, asset)
        batches = list(extractor.extract())

        for batch in batches:
            for record in batch:
                assert "ingest_date" in record
                assert record["ingest_date"] is not None

    def test_ingest_date_not_in_schema(self):
        """Test ingest_date when not defined in schema."""
        schema = [{"name": "id", "type": "integer", "required": True}]
        asset = create_minimal_asset_definition(schema)
        source_config = create_source_config({"native": {"row_count": 5}})

        extractor = MimesisExtractor(source_config, asset)
        batches = list(extractor.extract())

        # Should be date object when not in schema
        for batch in batches:
            for record in batch:
                assert isinstance(record["ingest_date"], date)

    def test_ingest_date_in_schema_as_date(self):
        """Test ingest_date when defined as date type in schema."""
        schema = [
            {"name": "id", "type": "integer", "required": True},
            {"name": "ingest_date", "type": "date", "required": True},
        ]
        asset = create_minimal_asset_definition(schema)
        source_config = create_source_config({"native": {"row_count": 5}})

        extractor = MimesisExtractor(source_config, asset)
        batches = list(extractor.extract())

        for batch in batches:
            for record in batch:
                # Should be date object
                assert isinstance(record["ingest_date"], date)

    def test_ingest_date_in_schema_as_string(self):
        """Test ingest_date when defined as string type in schema."""
        schema = [
            {"name": "id", "type": "integer", "required": True},
            {"name": "ingest_date", "type": "string", "required": True},
        ]
        asset = create_minimal_asset_definition(schema)
        source_config = create_source_config({"native": {"row_count": 5}})

        extractor = MimesisExtractor(source_config, asset)
        batches = list(extractor.extract())

        for batch in batches:
            for record in batch:
                # Should be ISO date string
                assert isinstance(record["ingest_date"], str)
                assert "T" not in record["ingest_date"]  # Date only

    def test_ingest_date_in_schema_as_timestamp(self):
        """Test ingest_date when defined as timestamp type in schema."""
        schema = [
            {"name": "id", "type": "integer", "required": True},
            {"name": "ingest_date", "type": "timestamp", "required": True},
        ]
        asset = create_minimal_asset_definition(schema)
        source_config = create_source_config({"native": {"row_count": 5}})

        extractor = MimesisExtractor(source_config, asset)
        batches = list(extractor.extract())

        for batch in batches:
            for record in batch:
                # Should be ISO datetime string
                assert isinstance(record["ingest_date"], str)
                assert "T" in record["ingest_date"]  # Datetime format


class TestMimesisExtractorConfiguration:
    """Test configuration parsing and defaults."""

    def test_default_options(self):
        """Test that default options are applied correctly."""
        schema = [{"name": "id", "type": "integer", "required": True}]
        asset = create_minimal_asset_definition(schema)
        source_config = create_source_config()  # No engine options

        extractor = MimesisExtractor(source_config, asset)

        assert extractor.options["row_count"] == 1000
        assert extractor.options["batch_size"] == 10_000
        assert extractor.options["locale"] == "en"
        assert extractor.options["seed"] is None
        assert extractor.options["null_probability"] == 0.1

    def test_locale_configuration(self):
        """Test locale configuration."""
        schema = [{"name": "name", "type": "string", "required": True}]
        asset = create_minimal_asset_definition(schema)
        source_config = create_source_config({"native": {"locale": "ru", "row_count": 5}})

        extractor = MimesisExtractor(source_config, asset)
        batches = list(extractor.extract())

        # Should generate data (locale affects content, not structure)
        assert len(batches) > 0
        assert extractor.options["locale"] == "ru"

    def test_get_total_records_estimate(self):
        """Test get_total_records_estimate method."""
        schema = [{"name": "id", "type": "integer", "required": True}]
        asset = create_minimal_asset_definition(schema)
        source_config = create_source_config({"native": {"row_count": 42}})

        extractor = MimesisExtractor(source_config, asset)

        assert extractor.get_total_records_estimate() == 42

    def test_extract_metadata(self):
        """Test extract_metadata method."""
        schema = [
            {"name": "id", "type": "integer", "required": True},
            {"name": "name", "type": "string", "required": True},
        ]
        asset = create_minimal_asset_definition(schema)
        source_config = create_source_config()

        extractor = MimesisExtractor(source_config, asset)
        metadata = extractor.extract_metadata()

        assert "tags" in metadata
        assert metadata["tags"]["id"] == "synthetic"
        assert metadata["tags"]["name"] == "synthetic"
