"""Native Mimesis extractor for generating synthetic data."""

import random
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, Iterator, List, Optional

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

        # Parse engine options with defaults and validation
        self.options = self._parse_engine_options()

        # Initialize instance-based RNG (not global random)
        seed_value = self._canonicalize_seed(self.options["seed"])
        if seed_value is not None:
            self.random = random.Random(seed_value)
        else:
            self.random = random.Random()

        # Initialize Mimesis field generator with locale and seed
        locale = self._get_locale(self.options["locale"])
        mimesis_seed = seed_value  # Use same canonicalized seed for Mimesis
        self.field = Field(locale=locale, seed=mimesis_seed)

        # Check if ingest_date is in schema
        self.ingest_date_field = self._find_ingest_date_field()

        # Build schema mapping
        self.schema_fields = self._build_schema_fields()

    def _canonicalize_seed(self, seed: Any) -> Optional[int]:
        """Canonicalize seed value to integer or None.

        Args:
            seed: Seed value (int, string, or None)

        Returns:
            Canonicalized integer seed or None
        """
        if seed is None:
            return None
        if isinstance(seed, int):
            return seed
        if isinstance(seed, str) and seed.isdigit():
            return int(seed)
        # Hash string seeds to integer
        return hash(str(seed))

    def _parse_engine_options(self) -> Dict[str, Any]:
        """Parse engine options from source config with defaults and validation.

        Returns:
            Dictionary of parsed options with defaults applied

        Raises:
            ValueError: If any option has an invalid value
        """
        defaults = {
            "row_count": 1000,
            "batch_size": 10_000,
            "locale": "en",
            "seed": None,
            "null_probability": 0.1,
            "integer_start": 1,
            "integer_end": 1_000_000,
            "float_start": 0.0,
            "float_end": 10_000.0,
            "float_precision": 2,
        }

        options = defaults.copy()

        if self.source_config.engine:
            engine_options = self.source_config.engine.get("options", {})
            if isinstance(engine_options, dict):
                # Check native options first
                native_opts = engine_options.get("native", {})
                if isinstance(native_opts, dict):
                    for key in defaults:
                        if key in native_opts:
                            options[key] = native_opts[key]

                # Then check top-level options (override native)
                for key in defaults:
                    if key in engine_options:
                        options[key] = engine_options[key]

        # Type conversions
        if options["seed"] is not None:
            # Keep as-is for canonicalization later
            pass
        options["row_count"] = int(options["row_count"])
        options["batch_size"] = int(options["batch_size"])
        options["null_probability"] = float(options["null_probability"])
        options["integer_start"] = int(options["integer_start"])
        options["integer_end"] = int(options["integer_end"])
        options["float_start"] = float(options["float_start"])
        options["float_end"] = float(options["float_end"])
        options["float_precision"] = int(options["float_precision"])

        # Validation
        if options["row_count"] < 0:
            raise ValueError(
                f"row_count must be >= 0, got {options['row_count']}"
            )
        if options["batch_size"] <= 0:
            raise ValueError(
                f"batch_size must be > 0, got {options['batch_size']}"
            )
        if not (0.0 <= options["null_probability"] <= 1.0):
            raise ValueError(
                f"null_probability must be between 0.0 and 1.0, got {options['null_probability']}"
            )
        if options["integer_end"] < options["integer_start"]:
            raise ValueError(
                f"integer_end ({options['integer_end']}) must be >= integer_start ({options['integer_start']})"
            )
        if options["float_end"] < options["float_start"]:
            raise ValueError(
                f"float_end ({options['float_end']}) must be >= float_start ({options['float_start']})"
            )

        return options

    def _get_locale(self, locale_str: str) -> Locale:
        """Convert locale string to Mimesis Locale enum.

        Args:
            locale_str: Locale string (e.g., "en", "ru", "de")

        Returns:
            Mimesis Locale enum value
        """
        locale_map = {
            "en": Locale.EN,
            "ru": Locale.RU,
            "de": Locale.DE,
            "es": Locale.ES,
            "fr": Locale.FR,
            "it": Locale.IT,
            "ja": Locale.JA,
            "ko": Locale.KO,
            "pl": Locale.PL,
            "pt": Locale.PT,
            "zh": Locale.ZH,
        }
        return locale_map.get(locale_str.lower(), Locale.EN)

    def _find_ingest_date_field(self) -> Optional[Dict[str, Any]]:
        """Find ingest_date field in asset definition schema.

        Returns:
            Field definition if found, None otherwise
        """
        for field in self.asset_definition.schema:
            if field.get("name") == "ingest_date":
                return field
        return None

    def _map_field_to_mimesis(self, field: Dict[str, Any]) -> Optional[Callable[[], Any]]:
        """Map Dativo field definition to Mimesis field generator.

        Field mapping priority (most specific first):
        - Integer: id → sequential, age → 18-80, salary → 30k-200k, else → configured range
        - Float: salary/amount/balance → monetary (0-100k, 2 decimals),
                commission/pct/percentage → 0-1 (4 decimals),
                else → configured range/precision
        - String: email → email, first_name/last_name → name parts,
                  full_name/name → full name, company → company,
                  job/role/title → occupation, department → company_type,
                  status → choice, phone/mobile/telephone → phone,
                  street/address → address, city → city,
                  state/province → state, country → country,
                  zip/postal → zip_code, else → word
        - Date: → ISO date string
        - Timestamp/Datetime: → ISO datetime string
        - Boolean: → True/False choice

        Args:
            field: Field definition from asset schema

        Returns:
            Mimesis field generator function, or None if field should be skipped
        """
        field_name = field.get("name", "").lower()
        field_type = field.get("type", "string").lower()
        required = field.get("required", True)

        # Skip ingest_date - handled separately
        if field.get("name") == "ingest_date":
            return None

        # Map based on type and name patterns
        # Priority: more specific patterns first
        if field_type == "integer":
            if "id" in field_name:
                # Sequential ID (most specific)
                def gen_increment():
                    return self.field("increment")

                generator = gen_increment
            elif "age" in field_name:
                # Age (18-80)
                def gen_age():
                    return self.field("person.age", minimum=18, maximum=80)

                generator = gen_age
            elif "salary" in field_name:
                # Salary (30k-200k)
                def gen_salary():
                    return self.field(
                        "numeric.integer_number", start=30_000, end=200_000
                    )

                generator = gen_salary
            else:
                # Random integer with configured range (fallback)
                def gen_integer():
                    return self.field(
                        "numeric.integer_number",
                        start=self.options["integer_start"],
                        end=self.options["integer_end"],
                    )

                generator = gen_integer

        elif field_type in ("double", "float", "decimal"):
            if "salary" in field_name or "amount" in field_name or "balance" in field_name:
                # Monetary values (0-100k, 2 decimals) - most specific
                def gen_monetary():
                    value = self.field(
                        "numeric.float_number", start=0.0, end=100_000.0
                    )
                    return round(value, 2)

                generator = gen_monetary
            elif "commission" in field_name or "pct" in field_name or "percentage" in field_name:
                # Percentage (0-1, 4 decimals)
                def gen_percentage():
                    value = self.field("numeric.float_number", start=0.0, end=1.0)
                    return round(value, 4)

                generator = gen_percentage
            else:
                # Random float with configured range and precision (fallback)
                def gen_float():
                    value = self.field(
                        "numeric.float_number",
                        start=self.options["float_start"],
                        end=self.options["float_end"],
                    )
                    return round(value, self.options["float_precision"])

                generator = gen_float

        elif field_type == "date":
            def gen_date():
                return self.field("datetime.date", start=2015, end=2025).isoformat()

            generator = gen_date

        elif field_type in ("timestamp", "datetime"):
            def gen_datetime():
                return self.field("datetime.datetime", start=2015, end=2025).isoformat()

            generator = gen_datetime

        elif field_type == "string":
            # String patterns - most specific first to avoid shadowing
            if "email" in field_name:
                def gen_email():
                    return self.field("person.email")

                generator = gen_email
            elif "first_name" in field_name or field_name == "firstname":
                # More specific than "name"
                def gen_first_name():
                    return self.field("person.first_name")

                generator = gen_first_name
            elif "last_name" in field_name or field_name == "lastname":
                # More specific than "name"
                def gen_last_name():
                    return self.field("person.last_name")

                generator = gen_last_name
            elif "full_name" in field_name:
                # More specific than just "name"
                def gen_full_name():
                    return self.field("person.full_name")

                generator = gen_full_name
            elif "name" in field_name:
                # Generic name (after first_name, last_name, full_name)
                def gen_name():
                    return self.field("person.full_name")

                generator = gen_name
            elif "company" in field_name:
                def gen_company():
                    return self.field("business.company")

                generator = gen_company
            elif "job" in field_name or "role" in field_name or "title" in field_name:
                def gen_job():
                    return self.field("person.occupation")

                generator = gen_job
            elif "department" in field_name:
                def gen_department():
                    return self.field("business.company_type")

                generator = gen_department
            elif "status" in field_name:
                def gen_status():
                    return self.field("choice", items=["active", "inactive", "pending"])

                generator = gen_status
            elif "phone" in field_name or "mobile" in field_name or "telephone" in field_name:
                def gen_phone():
                    return self.field("person.telephone")

                generator = gen_phone
            elif "street" in field_name:
                # More specific than "address"
                def gen_street():
                    return self.field("address.address")

                generator = gen_street
            elif "address" in field_name:
                def gen_address():
                    return self.field("address.address")

                generator = gen_address
            elif "city" in field_name:
                def gen_city():
                    return self.field("address.city")

                generator = gen_city
            elif "state" in field_name or "province" in field_name:
                def gen_state():
                    return self.field("address.state")

                generator = gen_state
            elif "country" in field_name:
                def gen_country():
                    return self.field("address.country")

                generator = gen_country
            elif "zip" in field_name or "postal" in field_name:
                def gen_zip():
                    return self.field("address.zip_code")

                generator = gen_zip
            else:
                # Default: random word (fallback)
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

        # Wrap with nullability if not required
        # Use instance-based RNG (self.random) instead of global random
        if not required:
            original_generator = generator
            null_prob = self.options["null_probability"]

            def optional_generator():
                # Use configured null_probability with instance RNG
                if self.random.random() < null_prob:
                    return None
                return original_generator()

            generator = optional_generator

        return generator

    def _build_schema_fields(self) -> Dict[str, Callable[[], Any]]:
        """Build Mimesis schema fields from asset definition.

        Returns:
            Dictionary mapping field names to Mimesis generators
        """
        schema_fields = {}

        for field in self.asset_definition.schema:
            field_name = field.get("name")
            if not field_name:
                continue

            # Skip ingest_date - handled separately
            if field_name == "ingest_date":
                continue

            generator = self._map_field_to_mimesis(field)
            if generator is not None:
                schema_fields[field_name] = generator

        return schema_fields

    def _get_ingest_date_value(self) -> Any:
        """Get ingest_date value based on schema definition.

        Returns:
            ingest_date value (date object, ISO string, or timestamp)
            - If schema defines ingest_date as date → Python date object
            - If schema defines ingest_date as string → ISO date string (YYYY-MM-DD)
            - If schema defines ingest_date as timestamp/datetime → ISO datetime string with UTC
            - If not in schema → Python date object (default)
        """
        current_date = datetime.now(timezone.utc).date()

        if self.ingest_date_field:
            field_type = self.ingest_date_field.get("type", "date").lower()
            if field_type in ("timestamp", "datetime"):
                # Return datetime as ISO string with UTC timezone
                return datetime.combine(current_date, datetime.min.time()).replace(
                    tzinfo=timezone.utc
                ).isoformat()
            elif field_type == "string":
                # Return as ISO date string
                return current_date.isoformat()
            else:
                # Default: date object (for type: date or unknown)
                return current_date
        else:
            # Not in schema, add as date object
            return current_date

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
        # Handle edge case: row_count == 0
        if self.options["row_count"] == 0:
            self.logger.info(
                "row_count is 0, skipping data generation",
                extra={
                    "row_count": 0,
                    "event_type": "mimesis_generation_skipped",
                },
            )
            return

        self.logger.info(
            f"Generating {self.options['row_count']} synthetic records using Mimesis",
            extra={
                "row_count": self.options["row_count"],
                "batch_size": self.options["batch_size"],
                "locale": self.options["locale"],
                "seed": self.options["seed"],
                "field_count": len(self.schema_fields),
                "event_type": "mimesis_generation_started",
            },
        )

        # Create Mimesis schema
        schema = Schema(
            schema=lambda: {
                field_name: generator()
                for field_name, generator in self.schema_fields.items()
            }
        )

        # Generate data in batches
        batch_size = self.options["batch_size"]
        total_generated = 0
        ingest_date_value = self._get_ingest_date_value()

        while total_generated < self.options["row_count"]:
            batch_count = min(batch_size, self.options["row_count"] - total_generated)

            # Generate batch
            batch_data = schema.create(iterations=batch_count)

            # Add ingest_date column to all records (always present)
            for record in batch_data:
                record["ingest_date"] = ingest_date_value

            total_generated += len(batch_data)

            self.logger.info(
                f"Generated batch: {len(batch_data)} records (total: {total_generated}/{self.options['row_count']})",
                extra={
                    "batch_size": len(batch_data),
                    "total_generated": total_generated,
                    "total_requested": self.options["row_count"],
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
        return self.options["row_count"]

    def extract_metadata(self) -> Dict[str, Any]:
        """Extract metadata from synthetic data source.

        Returns:
            Dictionary with "tags" key containing field metadata.
            For synthetic data, fields are marked as "synthetic".
            Note: ingest_date is included if present in schema, but is always
            generated regardless of schema presence.
        """
        source_tags = {}
        for field in self.asset_definition.schema:
            field_name = field.get("name")
            if field_name:
                source_tags[field_name] = "synthetic"

        return {"tags": source_tags}
