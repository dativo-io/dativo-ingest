"""Native Mimesis extractor for generating synthetic data."""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from mimesis import Field, Schema
from mimesis.locales import Locale

from ..config import AssetDefinition, SourceConfig
from ..logging import get_logger


class MimesisExtractor:
    """Extracts synthetic data using Mimesis library."""

    def __init__(self, source_config: SourceConfig, asset_definition: AssetDefinition):
        """Initialize Mimesis extractor.

        Args:
            source_config: Source configuration with row count and options
            asset_definition: Asset definition with schema fields
        """
        self.source_config = source_config
        self.asset_definition = asset_definition
        self.logger = get_logger()
        
        # Get row count from source config (default: 1000)
        self.row_count = self._get_row_count()
        
        # Initialize Mimesis field generator
        self.field = Field(locale=Locale.EN)
        
        # Build schema mapping
        self.schema_fields = self._build_schema_fields()

    def _get_row_count(self) -> int:
        """Get row count from source config.
        
        Returns:
            Number of rows to generate (default: 1000)
        """
        if self.source_config.engine:
            options = self.source_config.engine.get("options", {})
            if isinstance(options, dict):
                native_opts = options.get("native", {})
                if isinstance(native_opts, dict) and "row_count" in native_opts:
                    return int(native_opts["row_count"])
                if "row_count" in options:
                    return int(options["row_count"])
        
        # Check top-level source config for row_count
        if hasattr(self.source_config, "row_count"):
            return int(self.source_config.row_count)
        
        return 1000  # Default

    def _map_field_to_mimesis(self, field: Dict[str, Any]) -> Any:
        """Map Dativo field definition to Mimesis field generator.
        
        Args:
            field: Field definition from asset schema
            
        Returns:
            Mimesis field generator function
        """
        field_name = field.get("name", "").lower()
        field_type = field.get("type", "string").lower()
        required = field.get("required", True)
        
        # Map based on type and name patterns
        # Use helper functions to avoid lambda closure issues
        if field_type == "integer":
            if "id" in field_name:
                # Incrementing ID
                def gen_increment():
                    return self.field("increment")
                generator = gen_increment
            else:
                # Random integer
                def gen_integer():
                    return self.field("numeric.integer_number", start=1, end=1000000)
                generator = gen_integer
        elif field_type == "double" or field_type == "float":
            def gen_float():
                return self.field("numeric.float_number", start=0, end=10000)
            generator = gen_float
        elif field_type == "date":
            def gen_date():
                return self.field("datetime.date", start=2015, end=2025).isoformat()
            generator = gen_date
        elif field_type == "timestamp" or field_type == "datetime":
            def gen_datetime():
                return self.field("datetime.datetime", start=2015, end=2025).isoformat()
            generator = gen_datetime
        elif field_type == "string":
            if "email" in field_name:
                def gen_email():
                    return self.field("person.email")
                generator = gen_email
            elif "name" in field_name:
                def gen_name():
                    return self.field("person.full_name")
                generator = gen_name
            elif "company" in field_name:
                def gen_company():
                    return self.field("business.company")
                generator = gen_company
            elif "phone" in field_name or "mobile" in field_name:
                def gen_phone():
                    return self.field("person.telephone")
                generator = gen_phone
            elif "address" in field_name:
                def gen_address():
                    return self.field("address.address")
                generator = gen_address
            elif "city" in field_name:
                def gen_city():
                    return self.field("address.city")
                generator = gen_city
            elif "country" in field_name:
                def gen_country():
                    return self.field("address.country")
                generator = gen_country
            elif "zip" in field_name or "postal" in field_name:
                def gen_zip():
                    return self.field("address.zip_code")
                generator = gen_zip
            else:
                # Default: random word
                def gen_word():
                    return self.field("text.word")
                generator = gen_word
        elif field_type == "boolean":
            def gen_boolean():
                return self.field("choice", items=[True, False])
            generator = gen_boolean
        else:
            # Fallback: random word
            def gen_word_fallback():
                return self.field("text.word")
            generator = gen_word_fallback
        
        # Wrap with choice() if not required (10% chance of None)
        if not required:
            original_generator = generator
            def optional_generator():
                # 10% chance of None, 90% chance of generating value
                import random
                if random.random() < 0.1:
                    return None
                return original_generator()
            generator = optional_generator
        
        return generator

    def _build_schema_fields(self) -> Dict[str, Any]:
        """Build Mimesis schema fields from asset definition.
        
        Returns:
            Dictionary mapping field names to Mimesis generators
        """
        schema_fields = {}
        
        for field in self.asset_definition.schema:
            field_name = field.get("name")
            if not field_name:
                continue
            
            generator = self._map_field_to_mimesis(field)
            schema_fields[field_name] = generator
        
        return schema_fields

    def extract(
        self,
        state_manager: Optional[Any] = None,
        checkpoint_context: Optional[Dict[str, Any]] = None,
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract synthetic data using Mimesis.
        
        Args:
            state_manager: Optional incremental state manager (not used for synthetic data)
            checkpoint_context: Optional checkpoint context (not used for synthetic data)
            
        Yields:
            Batches of records as dictionaries
        """
        self.logger.info(
            f"Generating {self.row_count} synthetic records using Mimesis",
            extra={
                "row_count": self.row_count,
                "field_count": len(self.schema_fields),
                "event_type": "mimesis_generation_started",
            },
        )
        
        # Create Mimesis schema
        schema = Schema(schema=lambda: {
            field_name: generator()
            for field_name, generator in self.schema_fields.items()
        })
        
        # Generate data in batches
        batch_size = 10000  # Generate in batches of 10k
        total_generated = 0
        
        while total_generated < self.row_count:
            batch_count = min(batch_size, self.row_count - total_generated)
            
            # Generate batch
            batch_data = schema.create(iterations=batch_count)
            
            # Add ingest_date column (current UTC date)
            current_date = datetime.now(timezone.utc).date().isoformat()
            for record in batch_data:
                record["ingest_date"] = current_date
            
            total_generated += len(batch_data)
            
            self.logger.info(
                f"Generated batch: {len(batch_data)} records (total: {total_generated}/{self.row_count})",
                extra={
                    "batch_size": len(batch_data),
                    "total_generated": total_generated,
                    "total_requested": self.row_count,
                    "event_type": "mimesis_batch_generated",
                },
            )
            
            yield batch_data
        
        self.logger.info(
            f"Finished generating {total_generated} synthetic records",
            extra={
                "total_records": total_generated,
                "event_type": "mimesis_generation_complete",
            },
        )

    def get_total_records_estimate(self) -> Optional[int]:
        """Get total number of records to be generated.
        
        Returns:
            Row count (exact, not an estimate)
        """
        return self.row_count

    def extract_metadata(self) -> Dict[str, Any]:
        """Extract metadata from synthetic data source.
        
        Returns:
            Dictionary with "tags" key containing field metadata.
            For synthetic data, fields are marked as "synthetic".
        """
        source_tags = {}
        for field in self.asset_definition.schema:
            field_name = field.get("name")
            if field_name:
                source_tags[field_name] = "synthetic"
        
        return {"tags": source_tags}
