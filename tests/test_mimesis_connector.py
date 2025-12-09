"""Tests for Mimesis synthetic data connector."""

import os
from datetime import date, datetime, timezone
from pathlib import Path
import tempfile

import pytest

from src.dativo_ingest.config import SourceConfig
from src.dativo_ingest.connectors.mimesis_extractor import MimesisExtractor, AssetSchemaLoader


class TestAssetSchemaLoader:
    """Test suite for AssetSchemaLoader."""

    def test_load_valid_schema(self):
        """Test loading a valid schema."""
        asset_path = "tests/fixtures/assets/mimesis/v1.0/customers.yaml"
        schema, asset_def = AssetSchemaLoader.load_schema(asset_path)
        
        assert isinstance(schema, list)
        assert len(schema) > 0
        assert isinstance(asset_def, dict)
        assert "schema" in asset_def

    def test_missing_asset_path_error(self):
        """Test that missing asset path raises clear error."""
        with pytest.raises(ValueError, match="Asset path is required"):
            AssetSchemaLoader.load_schema(None)

    def test_nonexistent_file_error(self):
        """Test that nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Asset definition file not found"):
            AssetSchemaLoader.load_schema("nonexistent.yaml")

    def test_empty_schema_error(self):
        """Test that empty schema raises clear error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("schema: []")
            temp_file = f.name
        
        try:
            with pytest.raises(ValueError, match="schema.*is empty"):
                AssetSchemaLoader.load_schema(temp_file)
        finally:
            os.unlink(temp_file)

    def test_missing_schema_field_error(self):
        """Test that missing schema field raises clear error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("name: test\nversion: 1.0")
            temp_file = f.name
        
        try:
            with pytest.raises(ValueError, match="missing required 'schema' field"):
                AssetSchemaLoader.load_schema(temp_file)
        finally:
            os.unlink(temp_file)

    def test_invalid_field_definition_error(self):
        """Test that field missing name or type raises clear error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("schema:\n  - type: string\n")  # Missing name
            temp_file = f.name
        
        try:
            with pytest.raises(ValueError, match="missing 'name'"):
                AssetSchemaLoader.load_schema(temp_file)
        finally:
            os.unlink(temp_file)


class TestMimesisExtractor:
    """Test suite for MimesisExtractor."""

    @pytest.fixture
    def asset_path(self):
        """Get path to test asset definition."""
        return "tests/fixtures/assets/mimesis/v1.0/customers.yaml"

    @pytest.fixture
    def source_config(self):
        """Create basic source config for mimesis."""
        return SourceConfig(
            type="mimesis",
            engine={"options": {"row_count": 100, "batch_size": 50, "seed": 42}},
        )

    @pytest.fixture
    def source_config_large(self):
        """Create source config for testing large batches."""
        return SourceConfig(
            type="mimesis",
            engine={"options": {"row_count": 10000, "batch_size": 1000, "seed": 42}},
        )

    def test_extractor_initialization(self, source_config, asset_path):
        """Test that extractor can be initialized."""
        extractor = MimesisExtractor(source_config, asset_path=asset_path)
        assert extractor is not None
        assert extractor.engine_options["row_count"] == 100
        assert extractor.engine_options["batch_size"] == 50
        assert extractor.engine_options["seed"] == 42
        assert extractor.rng is not None  # Deterministic RNG initialized

    def test_default_engine_options(self):
        """Test that default engine options are applied."""
        config = SourceConfig(type="mimesis")
        extractor = MimesisExtractor(config, asset_path="tests/fixtures/assets/mimesis/v1.0/customers.yaml")
        
        assert extractor.engine_options["row_count"] == 1000
        assert extractor.engine_options["batch_size"] == 10000
        assert extractor.engine_options["locale"] == "en"
        assert extractor.engine_options["seed"] is None
        assert extractor.engine_options["integer_start"] == 1
        assert extractor.engine_options["integer_end"] == 100000
        assert extractor.engine_options["float_start"] == 0.0
        assert extractor.engine_options["float_end"] == 10000.0
        assert extractor.engine_options["float_precision"] == 2
        assert extractor.engine_options["null_probability"] == 0.1

    def test_configurable_numeric_ranges(self):
        """Test that numeric ranges can be configured."""
        config = SourceConfig(
            type="mimesis",
            engine={
                "options": {
                    "row_count": 10,
                    "seed": 42,
                    "integer_start": 1000,
                    "integer_end": 2000,
                    "float_start": 100.0,
                    "float_end": 200.0,
                    "float_precision": 3,
                }
            },
        )
        extractor = MimesisExtractor(config, asset_path="tests/fixtures/assets/mimesis/v1.0/customers.yaml")
        
        assert extractor.engine_options["integer_start"] == 1000
        assert extractor.engine_options["integer_end"] == 2000
        assert extractor.engine_options["float_start"] == 100.0
        assert extractor.engine_options["float_end"] == 200.0
        assert extractor.engine_options["float_precision"] == 3

    def test_load_asset_schema(self, source_config, asset_path):
        """Test loading asset schema."""
        extractor = MimesisExtractor(source_config, asset_path=asset_path)
        schema, asset_def = extractor._load_asset_schema()
        
        assert isinstance(schema, list)
        assert len(schema) > 0
        assert isinstance(asset_def, dict)
        
        # Check that schema has required fields
        field_names = [field.get("name") for field in schema]
        assert "customer_id" in field_names
        assert "name" in field_names
        assert "email" in field_names
        assert "signup_date" in field_names
        assert "account_balance" in field_names

    def test_field_mapping(self, source_config, asset_path):
        """Test field type to Mimesis generator mapping."""
        extractor = MimesisExtractor(source_config, asset_path=asset_path)
        
        # Test integer ID field
        id_generator = extractor._map_field_to_mimesis("customer_id", "integer", True)
        id_val = id_generator()
        assert isinstance(id_val, int)
        
        # Test string email field
        email_generator = extractor._map_field_to_mimesis("email", "string", True)
        email_val = email_generator()
        assert isinstance(email_val, str)
        assert "@" in email_val
        
        # Test date field
        date_generator = extractor._map_field_to_mimesis("signup_date", "date", True)
        date_val = date_generator()
        assert date_val is not None
        
        # Test double field
        balance_generator = extractor._map_field_to_mimesis("account_balance", "double", True)
        balance_val = balance_generator()
        assert isinstance(balance_val, float)

    def test_nullable_field_with_seed(self, asset_path):
        """Test that nullable fields are deterministic with seed."""
        config = SourceConfig(
            type="mimesis",
            engine={"options": {"row_count": 20, "seed": 12345, "null_probability": 0.3}},
        )
        
        extractor = MimesisExtractor(config, asset_path=asset_path)
        nullable_generator = extractor._map_field_to_mimesis("phone_number", "string", False)
        
        # Generate values multiple times with same seed
        values1 = [nullable_generator() for _ in range(20)]
        
        # Reset extractor with same seed
        extractor2 = MimesisExtractor(config, asset_path=asset_path)
        nullable_generator2 = extractor2._map_field_to_mimesis("phone_number", "string", False)
        values2 = [nullable_generator2() for _ in range(20)]
        
        # Should have same pattern of None values
        assert values1 == values2
        
        # Should have some None values (with 0.3 probability and 20 samples)
        none_count = sum(1 for v in values1 if v is None)
        assert none_count > 0  # Should have at least one None

    def test_ingest_date_enrichment(self, source_config, asset_path):
        """Test that all records include ingest_date."""
        extractor = MimesisExtractor(source_config, asset_path=asset_path)
        
        batches = list(extractor.extract())
        assert len(batches) > 0
        
        # Check all records have ingest_date
        for batch in batches:
            for record in batch:
                assert "ingest_date" in record
                assert record["ingest_date"] is not None
                # Should be a date object by default
                assert isinstance(record["ingest_date"], date)

    def test_ingest_date_with_schema_definition(self):
        """Test ingest_date respects schema type definition."""
        # Create a temporary asset with ingest_date as string
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
schema:
  - name: id
    type: integer
    required: true
  - name: ingest_date
    type: string
    required: true
""")
            temp_file = f.name
        
        try:
            config = SourceConfig(
                type="mimesis",
                engine={"options": {"row_count": 5, "seed": 42}},
            )
            extractor = MimesisExtractor(config, asset_path=temp_file)
            
            batches = list(extractor.extract())
            record = batches[0][0]
            
            assert "ingest_date" in record
            # Should be string in ISO format
            assert isinstance(record["ingest_date"], str)
            assert len(record["ingest_date"]) == 10  # YYYY-MM-DD
        finally:
            os.unlink(temp_file)

    def test_extract_data(self, source_config, asset_path):
        """Test data extraction."""
        extractor = MimesisExtractor(source_config, asset_path=asset_path)
        
        batches = list(extractor.extract())
        assert len(batches) > 0
        
        # Should generate 100 rows in 2 batches of 50
        total_records = sum(len(batch) for batch in batches)
        assert total_records == 100
        
        # Check first record structure
        first_record = batches[0][0]
        assert "customer_id" in first_record
        assert "name" in first_record
        assert "email" in first_record
        assert "signup_date" in first_record
        assert "account_balance" in first_record
        assert "ingest_date" in first_record  # Should be enriched
        
        # Validate data types
        assert isinstance(first_record["customer_id"], int)
        assert isinstance(first_record["name"], str)
        assert isinstance(first_record["email"], str)
        assert isinstance(first_record["account_balance"], float)
        assert isinstance(first_record["ingest_date"], date)

    def test_memory_efficient_large_batch(self, source_config_large, asset_path):
        """Test that large row_count generates data in batches."""
        extractor = MimesisExtractor(source_config_large, asset_path=asset_path)
        
        batches = list(extractor.extract())
        
        # Should have multiple batches
        assert len(batches) > 1
        
        # Each batch should be <= batch_size
        for batch in batches:
            assert len(batch) <= 1000
        
        # Total should equal row_count
        total_records = sum(len(batch) for batch in batches)
        assert total_records == 10000

    def test_get_total_records_estimate(self, source_config, asset_path):
        """Test record count estimation."""
        extractor = MimesisExtractor(source_config, asset_path=asset_path)
        estimate = extractor.get_total_records_estimate()
        assert estimate == 100

    def test_extract_metadata(self, source_config, asset_path):
        """Test metadata extraction."""
        extractor = MimesisExtractor(source_config, asset_path=asset_path)
        metadata = extractor.extract_metadata()
        
        assert "tags" in metadata
        assert isinstance(metadata["tags"], dict)
        assert "customer_id" in metadata["tags"]
        assert metadata["tags"]["customer_id"] == "synthetic"
        assert "ingest_date" in metadata["tags"]  # Should include enriched field
        assert metadata["tags"]["ingest_date"] == "synthetic"

    def test_reproducibility_with_seed(self, asset_path):
        """Test that same seed produces same data."""
        config1 = SourceConfig(
            type="mimesis",
            engine={"options": {"row_count": 10, "seed": 12345}},
        )
        config2 = SourceConfig(
            type="mimesis",
            engine={"options": {"row_count": 10, "seed": 12345}},
        )
        
        extractor1 = MimesisExtractor(config1, asset_path=asset_path)
        extractor2 = MimesisExtractor(config2, asset_path=asset_path)
        
        records1 = list(extractor1.extract())[0]
        records2 = list(extractor2.extract())[0]
        
        # Should generate identical data with same seed
        assert len(records1) == len(records2)
        # The increment-based customer_id should definitely match
        assert records1[0]["customer_id"] == records2[0]["customer_id"]
        # Names should also match with same seed
        assert records1[0]["name"] == records2[0]["name"]

    def test_missing_asset_path_error(self, source_config):
        """Test that missing asset path raises error."""
        extractor = MimesisExtractor(source_config, asset_path=None)
        
        with pytest.raises(ValueError, match="Asset path is required"):
            list(extractor.extract())

    def test_invalid_asset_path_error(self, source_config):
        """Test that invalid asset path raises error."""
        extractor = MimesisExtractor(source_config, asset_path="nonexistent.yaml")
        
        with pytest.raises(FileNotFoundError, match="Asset definition file not found"):
            list(extractor.extract())

    def test_configurable_batch_size(self, asset_path):
        """Test that batch_size configuration works."""
        config = SourceConfig(
            type="mimesis",
            engine={"options": {"row_count": 150, "batch_size": 30, "seed": 42}},
        )
        extractor = MimesisExtractor(config, asset_path=asset_path)
        
        batches = list(extractor.extract())
        
        # Should have 5 batches of 30
        assert len(batches) == 5
        for batch in batches:
            assert len(batch) == 30

    def test_null_probability_configuration(self, asset_path):
        """Test that null_probability can be configured."""
        # High null probability
        config_high = SourceConfig(
            type="mimesis",
            engine={"options": {"row_count": 100, "seed": 42, "null_probability": 0.5}},
        )
        extractor_high = MimesisExtractor(config_high, asset_path=asset_path)
        
        # Low null probability
        config_low = SourceConfig(
            type="mimesis",
            engine={"options": {"row_count": 100, "seed": 42, "null_probability": 0.01}},
        )
        extractor_low = MimesisExtractor(config_low, asset_path=asset_path)
        
        # Generate phone_number field (which is nullable)
        gen_high = extractor_high._map_field_to_mimesis("phone_number", "string", False)
        gen_low = extractor_low._map_field_to_mimesis("phone_number", "string", False)
        
        values_high = [gen_high() for _ in range(100)]
        values_low = [gen_low() for _ in range(100)]
        
        none_count_high = sum(1 for v in values_high if v is None)
        none_count_low = sum(1 for v in values_low if v is None)
        
        # High probability should have more Nones
        assert none_count_high > none_count_low
