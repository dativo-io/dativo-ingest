"""Mimesis-based synthetic data extractor.

Generates realistic synthetic data conforming to asset definitions using the Mimesis library.
"""

import os
import random
from datetime import datetime, timezone, date as date_type
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import yaml

from ..config import SourceConfig
from ..logging import get_logger


class AssetSchemaLoader:
    """Helper class for loading and validating asset schemas."""

    @staticmethod
    def load_schema(asset_path: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Load and validate asset schema from YAML.

        Args:
            asset_path: Path to asset definition YAML file

        Returns:
            Tuple of (schema fields list, full asset definition dict)

        Raises:
            ValueError: If asset_path is missing, file not found, or schema is invalid
        """
        if not asset_path:
            raise ValueError(
                "Asset path is required for Mimesis extractor to determine schema. "
                "Please specify 'asset_path' in your job configuration."
            )

        # Expand environment variables and resolve path
        expanded_path = os.path.expandvars(asset_path)
        asset_path_obj = Path(expanded_path)

        if not asset_path_obj.exists():
            raise FileNotFoundError(
                f"Asset definition file not found: {asset_path_obj} "
                f"(expanded from: {asset_path}). "
                f"Please verify the asset_path in your job configuration."
            )

        # Load YAML file
        try:
            with open(asset_path_obj, "r") as f:
                asset_def = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(
                f"Failed to parse asset definition YAML: {asset_path_obj}. "
                f"Error: {e}"
            ) from e
        except Exception as e:
            raise ValueError(
                f"Failed to read asset definition file: {asset_path_obj}. "
                f"Error: {e}"
            ) from e

        if not asset_def or not isinstance(asset_def, dict):
            raise ValueError(
                f"Asset definition is empty or invalid: {asset_path_obj}. "
                f"Expected a YAML dictionary."
            )

        # Validate schema field
        schema = asset_def.get("schema")
        if schema is None:
            raise ValueError(
                f"Asset definition is missing required 'schema' field: {asset_path_obj}. "
                f"Available fields: {list(asset_def.keys())}"
            )

        if not isinstance(schema, list):
            raise ValueError(
                f"Asset definition 'schema' field must be a list: {asset_path_obj}. "
                f"Got type: {type(schema).__name__}"
            )

        if len(schema) == 0:
            raise ValueError(
                f"Asset definition 'schema' field is empty: {asset_path_obj}. "
                f"At least one field definition is required."
            )

        # Validate each field definition
        for idx, field_def in enumerate(schema):
            if not isinstance(field_def, dict):
                raise ValueError(
                    f"Schema field at index {idx} is not a dictionary: {asset_path_obj}. "
                    f"Got: {field_def}"
                )

            if "name" not in field_def:
                raise ValueError(
                    f"Schema field at index {idx} is missing 'name': {asset_path_obj}. "
                    f"Field: {field_def}"
                )

            if "type" not in field_def:
                raise ValueError(
                    f"Schema field at index {idx} ('{field_def.get('name')}') "
                    f"is missing 'type': {asset_path_obj}. "
                    f"Field: {field_def}"
                )

        return schema, asset_def


class MimesisExtractor:
    """Extracts synthetic data using the Mimesis library."""

    def __init__(self, source_config: SourceConfig, asset_path: Optional[str] = None):
        """Initialize Mimesis extractor.

        Args:
            source_config: Source configuration with generation options
            asset_path: Path to asset definition YAML (for schema inference)
        """
        self.source_config = source_config
        self.asset_path = asset_path
        self.logger = get_logger()
        self.engine_options = self._get_engine_options()
        
        # Initialize deterministic random source if seed is provided
        seed = self.engine_options.get("seed")
        self.rng = random.Random(seed) if seed is not None else random.Random()

    def _get_engine_options(self) -> Dict[str, Any]:
        """Get engine options from source config with defaults.

        Returns:
            Dictionary of engine options with defaults applied
        """
        # Default configuration
        merged = {
            "row_count": 1000,
            "batch_size": 10000,  # Process in 10k batches by default
            "locale": "en",
            "seed": None,
            # Numeric range defaults
            "integer_start": 1,
            "integer_end": 100000,
            "float_start": 0.0,
            "float_end": 10000.0,
            "float_precision": 2,
            # Nullability configuration
            "null_probability": 0.1,  # 10% chance of None for optional fields
        }

        if self.source_config.engine:
            options = self.source_config.engine.get("options", {})
            if isinstance(options, dict):
                # Support both top-level options and nested "native" options
                native_opts = options.get("native", {})
                if isinstance(native_opts, dict):
                    merged.update(native_opts)
                
                # Top-level options override native
                for key, value in options.items():
                    if key != "native":
                        merged[key] = value

        return merged

    def _load_asset_schema(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Load schema from asset definition YAML.

        Returns:
            Tuple of (schema fields list, full asset definition dict)

        Raises:
            ValueError: If asset loading or validation fails
        """
        schema, asset_def = AssetSchemaLoader.load_schema(self.asset_path)
        
        self.logger.info(
            f"Loaded asset definition with {len(schema)} fields",
            extra={
                "asset_path": self.asset_path,
                "field_count": len(schema),
                "event_type": "mimesis_asset_loaded",
            },
        )
        
        return schema, asset_def

    def _get_ingest_date_type(self, schema: List[Dict[str, Any]]) -> Optional[str]:
        """Check if schema defines ingest_date field and return its type.

        Args:
            schema: List of field definitions

        Returns:
            Type of ingest_date field if present, None otherwise
        """
        for field_def in schema:
            if field_def.get("name") == "ingest_date":
                return field_def.get("type")
        return None

    def _create_ingest_date_value(self, field_type: Optional[str]) -> Any:
        """Create ingest_date value with appropriate type.

        Args:
            field_type: Type from schema (date, string, timestamp) or None

        Returns:
            Ingest date value with appropriate type
        """
        now_utc = datetime.now(timezone.utc)
        today_utc = now_utc.date()
        
        if field_type == "date":
            return today_utc
        elif field_type == "timestamp":
            return now_utc
        elif field_type == "string":
            return today_utc.isoformat()
        else:
            # Default to date object if not specified
            return today_utc

    def _map_field_to_mimesis(
        self, field_name: str, field_type: str, required: bool
    ) -> callable:
        """Map Dativo field definition to Mimesis generator function.

        Args:
            field_name: Name of the field
            field_type: Dativo type (string, integer, double, date, timestamp)
            required: Whether field is required (false -> wrap with nullable)

        Returns:
            Callable that generates a value for this field
        """
        try:
            from mimesis import Field, Locale
        except ImportError:
            raise ImportError(
                "mimesis is required for synthetic data generation. "
                "Install with: pip install mimesis"
            )

        # Get configuration
        locale_str = self.engine_options.get("locale", "en")
        seed = self.engine_options.get("seed")
        integer_start = self.engine_options.get("integer_start", 1)
        integer_end = self.engine_options.get("integer_end", 100000)
        float_start = self.engine_options.get("float_start", 0.0)
        float_end = self.engine_options.get("float_end", 10000.0)
        float_precision = self.engine_options.get("float_precision", 2)
        
        # Set up locale
        locale = Locale.EN  # Default
        if locale_str.upper() in Locale.__members__:
            locale = Locale[locale_str.upper()]

        field = Field(locale=locale, seed=seed)
        field_lower = field_name.lower()

        # Type and name-based mapping logic
        if field_type == "integer":
            if "id" in field_lower:
                # For ID fields, use increment
                counter = {"value": 0}

                def increment():
                    counter["value"] += 1
                    return counter["value"]

                generator = increment
            elif "age" in field_lower:
                generator = lambda: field("person.age")
            elif "salary" in field_lower:
                generator = lambda: field("numeric.integer_number", start=30000, end=200000)
            else:
                # Use configurable range
                generator = lambda: field("numeric.integer_number", start=integer_start, end=integer_end)

        elif field_type in ("double", "float", "decimal"):
            if "salary" in field_lower or "balance" in field_lower or "amount" in field_lower:
                generator = lambda: round(field("numeric.float_number", start=0.0, end=100000.0), float_precision)
            elif "commission" in field_lower or "pct" in field_lower or "percentage" in field_lower:
                generator = lambda: round(field("numeric.float_number", start=0.0, end=1.0), 4)
            else:
                # Use configurable range and precision
                generator = lambda: round(field("numeric.float_number", start=float_start, end=float_end), float_precision)

        elif field_type == "date":
            generator = lambda: field("datetime.date", start=2015, end=2025)

        elif field_type == "timestamp":
            generator = lambda: field("datetime.datetime", start=2015, end=2025)

        elif field_type == "string":
            if "email" in field_lower:
                generator = lambda: field("person.email")
            elif "phone" in field_lower:
                generator = lambda: field("person.telephone")
            elif "first_name" in field_lower or "firstname" in field_lower:
                generator = lambda: field("person.first_name")
            elif "last_name" in field_lower or "lastname" in field_lower:
                generator = lambda: field("person.last_name")
            elif "name" in field_lower and "company" not in field_lower:
                generator = lambda: field("person.full_name")
            elif "company" in field_lower or "organization" in field_lower:
                generator = lambda: field("finance.company")
            elif "address" in field_lower:
                generator = lambda: field("address.address")
            elif "city" in field_lower:
                generator = lambda: field("address.city")
            elif "country" in field_lower:
                generator = lambda: field("address.country")
            elif "state" in field_lower or "province" in field_lower:
                generator = lambda: field("address.state")
            elif "zip" in field_lower or "postal" in field_lower:
                generator = lambda: field("address.zip_code")
            elif "department" in field_lower:
                generator = lambda: field("choice", items=["Engineering", "Sales", "Marketing", "HR", "Finance", "Operations", "Support", "IT"])
            elif "status" in field_lower:
                generator = lambda: field("choice", items=["active", "inactive", "pending", "archived"])
            elif "job" in field_lower:
                generator = lambda: field("person.occupation")
            elif "title" in field_lower:
                generator = lambda: field("text.title")
            elif "description" in field_lower:
                generator = lambda: field("text.sentence")
            elif "url" in field_lower or "website" in field_lower:
                generator = lambda: field("internet.url")
            else:
                # Default fallback
                generator = lambda: field("text.word")
        else:
            # Unsupported type fallback
            self.logger.warning(
                f"Unsupported field type '{field_type}' for field '{field_name}', using default generator",
                extra={"field_name": field_name, "field_type": field_type, "event_type": "mimesis_unsupported_type"}
            )
            generator = lambda: field("text.word")

        # Wrap with nullable if not required (using deterministic RNG)
        if not required:
            original_generator = generator
            null_probability = self.engine_options.get("null_probability", 0.1)

            def nullable_generator():
                if self.rng.random() < null_probability:
                    return None
                return original_generator()

            return nullable_generator

        return generator

    def _build_schema_lambda(self, schema: List[Dict[str, Any]]) -> callable:
        """Build schema lambda function for Mimesis Schema.

        Args:
            schema: List of field definitions from asset

        Returns:
            Lambda function that returns a dictionary of generated values
        """
        field_generators = {}

        for field_def in schema:
            field_name = field_def.get("name")
            field_type = field_def.get("type")
            required = field_def.get("required", True)

            if not field_name or not field_type:
                self.logger.warning(
                    f"Skipping field definition missing name or type: {field_def}",
                    extra={"field_def": field_def, "event_type": "mimesis_invalid_field"}
                )
                continue
            
            # Skip ingest_date as it will be added separately
            if field_name == "ingest_date":
                continue

            field_generators[field_name] = self._map_field_to_mimesis(
                field_name, field_type, required
            )

        def schema_lambda():
            """Generate a single record."""
            record = {}
            for field_name, generator in field_generators.items():
                record[field_name] = generator()
            return record

        return schema_lambda

    def extract(
        self,
        state_manager=None,
        checkpoint_context: Optional[Dict[str, Any]] = None,
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract synthetic data using Mimesis.

        Args:
            state_manager: Optional incremental state manager (not used for synthetic data)
            checkpoint_context: Optional checkpoint context (not used for synthetic data)

        Yields:
            Batches of synthetic records as dictionaries, each with ingest_date added
        """
        try:
            from mimesis import Schema
        except ImportError:
            raise ImportError(
                "mimesis is required for synthetic data generation. "
                "Install with: pip install mimesis"
            )

        # Load asset schema
        asset_schema, _ = self._load_asset_schema()

        # Check if ingest_date is in schema and get its type
        ingest_date_type = self._get_ingest_date_type(asset_schema)
        ingest_date_value = self._create_ingest_date_value(ingest_date_type)
        
        if ingest_date_type:
            self.logger.info(
                f"Schema defines ingest_date field with type '{ingest_date_type}'",
                extra={"ingest_date_type": ingest_date_type, "event_type": "mimesis_ingest_date_schema"}
            )
        else:
            self.logger.info(
                "Adding ingest_date field (not defined in schema, defaulting to date type)",
                extra={"event_type": "mimesis_ingest_date_default"}
            )

        # Build Mimesis schema lambda (excluding ingest_date)
        schema_lambda = self._build_schema_lambda(asset_schema)

        # Get generation parameters
        row_count = self.engine_options.get("row_count", 1000)
        batch_size = self.engine_options.get("batch_size", 10000)

        self.logger.info(
            f"Generating {row_count} synthetic records in batches of {batch_size}",
            extra={
                "row_count": row_count,
                "batch_size": batch_size,
                "locale": self.engine_options.get("locale"),
                "seed": self.engine_options.get("seed"),
                "event_type": "mimesis_generation_start",
            },
        )

        # Generate data in batches to avoid memory issues with large row_count
        remaining_rows = row_count
        total_generated = 0
        
        while remaining_rows > 0:
            current_batch_size = min(batch_size, remaining_rows)
            
            # Generate batch
            schema = Schema(schema=schema_lambda, iterations=current_batch_size)
            batch_records = schema.create()
            
            # Add ingest_date to each record in the batch
            for record in batch_records:
                record["ingest_date"] = ingest_date_value
            
            total_generated += len(batch_records)
            remaining_rows -= current_batch_size
            
            self.logger.info(
                f"Generated synthetic batch: {len(batch_records)} records",
                extra={
                    "batch_size": len(batch_records),
                    "total_generated": total_generated,
                    "remaining": remaining_rows,
                    "event_type": "mimesis_batch_generated",
                },
            )
            
            yield batch_records

        self.logger.info(
            f"Finished generating {row_count} synthetic records",
            extra={
                "total_records": total_generated,
                "event_type": "mimesis_generation_complete",
            },
        )

    def get_total_records_estimate(self) -> Optional[int]:
        """Get estimated total number of records to be generated.

        Returns:
            Row count from configuration
        """
        return self.engine_options.get("row_count", 1000)

    def extract_metadata(self) -> Dict[str, Any]:
        """Extract naturally available metadata.

        For synthetic data, we can extract field names from the schema.

        Returns:
            Dictionary with "tags" key containing field_name -> "synthetic" mapping
        """
        if not self.asset_path:
            return {"tags": {}}

        try:
            asset_schema, _ = self._load_asset_schema()
            source_tags = {}
            for field_def in asset_schema:
                field_name = field_def.get("name")
                if field_name:
                    source_tags[field_name] = "synthetic"
            # Also tag ingest_date if we're adding it
            source_tags["ingest_date"] = "synthetic"
            return {"tags": source_tags}
        except Exception as e:
            self.logger.warning(
                f"Failed to extract metadata: {e}",
                extra={"event_type": "mimesis_metadata_extraction_failed"}
            )
            return {"tags": {}}
