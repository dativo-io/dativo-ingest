"""Synthetic data extractor powered by the Mimesis library."""

from __future__ import annotations

import datetime
import os
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import pandas as pd
from mimesis import Field
from mimesis.keys import maybe
from mimesis.schema import Schema

from ..config import AssetDefinition, JobConfig, SourceConfig
from ..logging import get_logger


class MimesisExtractor:
    """Generate synthetic tabular data that conforms to an asset definition."""

    def __init__(self, source_config: SourceConfig, job_config: JobConfig):
        self.source_config = source_config
        self.job_config = job_config
        self.logger = get_logger()

        self.engine_options = self._resolve_engine_options()
        self.row_count = int(self.engine_options.get("row_count", 1000))
        self.batch_size = int(self.engine_options.get("batch_size", 10000))
        self.locale = self.engine_options.get("locale", "en")
        self.null_probability = float(self.engine_options.get("null_probability", 0.1))
        self.float_precision = int(self.engine_options.get("float_precision", 2))
        self.start_year = int(self.engine_options.get("start_year", 2015))
        self.end_year = int(self.engine_options.get("end_year", 2025))

        self.field = Field(locale=self.locale)
        self.random = self.field.get_random_instance()
        self.asset_definition = self._load_asset_definition()
        self.ingest_date = datetime.datetime.now(
            datetime.timezone.utc
        ).date().isoformat()
        self.local_output_path, self.local_output_format = self._resolve_local_output()

        self.field_generators = self._build_field_generators()

    def _resolve_engine_options(self) -> Dict[str, Any]:
        options: Dict[str, Any] = {}
        if self.source_config.engine:
            engine_opts = self.source_config.engine.get("options", {})
            if isinstance(engine_opts, dict):
                options.update(engine_opts)
                native_opts = engine_opts.get("native", {})
                if isinstance(native_opts, dict):
                    options.update(native_opts)
        return options

    def _load_asset_definition(self) -> AssetDefinition:
        asset_path = Path(self.job_config.get_asset_path())
        return AssetDefinition.from_yaml(asset_path)

    def _resolve_local_output(self) -> Tuple[Optional[Path], Optional[str]]:
        target_cfg = self.asset_definition.target or {}
        path = target_cfg.get("target_path") or target_cfg.get("path")
        path = self.engine_options.get("target_path", path)

        if not path:
            return None, None

        expanded = Path(os.path.expandvars(os.path.expanduser(str(path))))
        file_format = (
            self.engine_options.get(
                "file_format", target_cfg.get("file_format", "parquet")
            )
            or "parquet"
        ).lower()

        suffix = expanded.suffix.lower()
        if suffix == ".csv":
            file_format = "csv"
        elif suffix in {".parquet", ".pq"}:
            file_format = "parquet"

        return expanded, file_format

    def _build_field_generators(self) -> Dict[str, Callable[[], Any]]:
        generators: Dict[str, Callable[[], Any]] = {}

        for field_def in self.asset_definition.schema:
            field_name = field_def["name"]
            field_type = (field_def.get("type") or "string").lower()
            required = field_def.get("required", False)

            if field_name == "ingest_date":
                generators[field_name] = lambda value=self.ingest_date: value
                continue

            generator = self._create_generator(field_name, field_type)

            if not required:
                maybe_fn = maybe(None, self.null_probability)

                def optional_wrapper(
                    base_generator: Callable[[], Any],
                    wrapper=maybe_fn,
                ) -> Callable[[], Any]:
                    def _wrapped() -> Any:
                        value = base_generator()
                        return wrapper(value, self.random)

                    return _wrapped

                generator = optional_wrapper(generator)

            generators[field_name] = generator

        if "ingest_date" not in generators:
            generators["ingest_date"] = lambda value=self.ingest_date: value

        return generators

    def _create_generator(self, field_name: str, field_type: str) -> Callable[[], Any]:
        normalized = field_name.lower()

        if field_type == "integer" and "id" in normalized:
            return lambda: self.field("increment")

        if field_type == "integer":
            start = int(self.engine_options.get("integer_start", 1))
            end = int(self.engine_options.get("integer_end", 1_000_000))
            return lambda: self.field("numeric.integer_number", start=start, end=end)

        if field_type in {"float", "double"}:
            start = float(self.engine_options.get("float_start", 0))
            end = float(self.engine_options.get("float_end", 10_000))

            def float_generator() -> float:
                value = self.field("numeric.float_number", start=start, end=end)
                return round(value, self.float_precision)

            return float_generator

        if field_type in {"timestamp", "datetime"}:
            return lambda: self.field(
                "datetime.datetime", start=self.start_year, end=self.end_year
            )

        if field_type == "date":
            return lambda: self.field(
                "datetime.date", start=self.start_year, end=self.end_year
            )

        if field_type == "boolean":
            return lambda: self.field("development.boolean")

        # String patterns
        if "email" in normalized:
            return lambda: self.field("person.email")
        if "name" in normalized:
            return lambda: self.field("person.full_name")
        if "company" in normalized:
            return lambda: self.field("business.company")

        if field_type == "string":
            return lambda: self.field("text.word")

        # Default fallback
        return lambda: self.field("text.word")

    def _record_factory(self) -> Dict[str, Any]:
        record: Dict[str, Any] = {}
        for field_name, generator in self.field_generators.items():
            record[field_name] = generator()
        record.setdefault("ingest_date", self.ingest_date)
        return record

    def _generate_records(self) -> List[Dict[str, Any]]:
        if self.row_count <= 0:
            return []

        schema = Schema(schema=self._record_factory, iterations=self.row_count)
        records = schema.create()

        self.logger.info(
            "Synthetic rows generated",
            extra={
                "event_type": "synthetic_generation_complete",
                "row_count": len(records),
                "source_type": self.source_config.type,
                "locale": self.locale,
            },
        )
        return records

    def extract(
        self,
        state_manager: Optional[Any] = None,
        checkpoint_context: Optional[Dict[str, Any]] = None,
    ) -> Iterator[List[Dict[str, Any]]]:
        """Yield generated records in batches."""
        del state_manager, checkpoint_context  # Not applicable for synthetic connector

        records = self._generate_records()
        if self.local_output_path:
            self._persist_to_local_output(records)

        for batch in self._yield_batches(records):
            yield batch

    def _yield_batches(
        self, records: List[Dict[str, Any]]
    ) -> Iterator[List[Dict[str, Any]]]:
        if not records:
            return

        for start in range(0, len(records), self.batch_size):
            yield records[start : start + self.batch_size]

    def _persist_to_local_output(self, records: List[Dict[str, Any]]) -> None:
        if not self.local_output_path:
            return

        self.local_output_path.parent.mkdir(parents=True, exist_ok=True)

        if self.local_output_format == "csv":
            pd.DataFrame(records).to_csv(self.local_output_path, index=False)
        else:
            pd.DataFrame(records).to_parquet(
                self.local_output_path, index=False, engine="pyarrow"
            )

        self.logger.info(
            "Synthetic data materialized locally",
            extra={
                "event_type": "synthetic_data_materialized",
                "path": str(self.local_output_path),
                "format": self.local_output_format or "parquet",
                "row_count": len(records),
            },
        )

    def get_total_records_estimate(self) -> Optional[int]:
        return self.row_count

    def extract_metadata(self) -> Dict[str, Any]:
        tags = {field["name"]: "synthetic" for field in self.asset_definition.schema}
        return {"tags": tags}
