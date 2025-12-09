"""Mimesis-based synthetic data extractor.

Generates realistic synthetic data conforming to asset definitions using the Mimesis library.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import yaml

from ..config import SourceConfig
from ..logging import get_logger


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

    def _get_engine_options(self) -> Dict[str, Any]:
        """Get engine options from source config.

        Returns:
            Dictionary of engine options
        """
        merged = {
            "row_count": 1000,
            "locale": "en",
            "seed": None,
        }

        if self.source_config.engine:
            options = self.source_config.engine.get("options", {})
            if isinstance(options, dict):
                merged.update(options)

        return merged

    def _load_asset_schema(self) -> List[Dict[str, Any]]:
        """Load schema from asset definition YAML.

        Returns:
            List of field definitions from asset schema
        """
        if not self.asset_path:
            raise ValueError(
                "Asset path is required for Mimesis extractor to determine schema"
            )

        asset_path = Path(os.path.expandvars(self.asset_path))
        if not asset_path.exists():
            raise FileNotFoundError(f"Asset definition not found: {asset_path}")

        self.logger.info(
            f"Loading asset definition from: {asset_path}",
            extra={
                "asset_path": str(asset_path),
                "event_type": "mimesis_asset_loading",
            },
        )

        with open(asset_path, "r") as f:
            asset_def = yaml.safe_load(f)

        schema = asset_def.get("schema", [])
        if not schema:
            raise ValueError(f"Asset definition has no schema: {asset_path}")

        return schema

    def _map_field_to_mimesis(
        self, field_name: str, field_type: str, required: bool
    ) -> callable:
        """Map Dativo field definition to Mimesis generator function.

        Args:
            field_name: Name of the field
            field_type: Dativo type (string, integer, double, date, timestamp)
            required: Whether field is required (false -> wrap with maybe)

        Returns:
            Callable that generates a value for this field
        """
        try:
            from mimesis import Field, Locale
            from mimesis.enums import Gender
        except ImportError:
            raise ImportError(
                "mimesis is required for synthetic data generation. "
                "Install with: pip install mimesis"
            )

        locale_str = self.engine_options.get("locale", "en")
        locale = Locale.EN  # Default
        if locale_str.upper() in Locale.__members__:
            locale = Locale[locale_str.upper()]

        seed = self.engine_options.get("seed")
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
                generator = lambda: field("numeric.integer_number", start=1, end=100000)

        elif field_type in ("double", "float", "decimal"):
            if "salary" in field_lower or "balance" in field_lower or "amount" in field_lower:
                generator = lambda: round(field("numeric.float_number", start=0.0, end=100000.0), 2)
            elif "commission" in field_lower or "pct" in field_lower or "percentage" in field_lower:
                generator = lambda: round(field("numeric.float_number", start=0.0, end=1.0), 4)
            else:
                generator = lambda: round(field("numeric.float_number", start=0.0, end=10000.0), 2)

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
            generator = lambda: field("text.word")

        # Wrap with maybe if not required (10% chance of None)
        if not required:
            original_generator = generator

            def nullable_generator():
                import random

                if random.random() < 0.1:
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
            Batches of synthetic records as dictionaries
        """
        try:
            from mimesis import Schema
        except ImportError:
            raise ImportError(
                "mimesis is required for synthetic data generation. "
                "Install with: pip install mimesis"
            )

        # Load asset schema
        asset_schema = self._load_asset_schema()

        # Build Mimesis schema lambda
        schema_lambda = self._build_schema_lambda(asset_schema)

        # Get generation parameters
        row_count = self.engine_options.get("row_count", 1000)
        batch_size = self.engine_options.get("batch_size", 1000)

        self.logger.info(
            f"Generating {row_count} synthetic records",
            extra={
                "row_count": row_count,
                "batch_size": batch_size,
                "event_type": "mimesis_generation_start",
            },
        )

        # Generate data
        schema = Schema(schema=schema_lambda, iterations=row_count)
        all_records = schema.create()

        # Yield in batches
        for i in range(0, len(all_records), batch_size):
            batch = all_records[i : i + batch_size]
            self.logger.info(
                f"Generated synthetic batch: {len(batch)} records",
                extra={
                    "batch_size": len(batch),
                    "total_generated": i + len(batch),
                    "event_type": "mimesis_batch_generated",
                },
            )
            yield batch

        self.logger.info(
            f"Finished generating {row_count} synthetic records",
            extra={
                "total_records": row_count,
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
            asset_schema = self._load_asset_schema()
            source_tags = {}
            for field_def in asset_schema:
                field_name = field_def.get("name")
                if field_name:
                    source_tags[field_name] = "synthetic"
            return {"tags": source_tags}
        except Exception:
            return {"tags": {}}
