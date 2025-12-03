"""Native CSV extractor using pandas."""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from ..config import SourceConfig
from ..incremental import create_incremental_strategy
from ..incremental.base import IncrementalStrategy
from ..incremental.strategies import FileModifiedTimeStrategy
from ..logging import get_logger
from ..validator import IncrementalStateManager


class CSVExtractor:
    """Extracts data from CSV files using pandas."""

    def __init__(self, source_config: SourceConfig):
        """Initialize CSV extractor.

        Args:
            source_config: Source configuration with files and engine options
        """
        self.source_config = source_config
        self.engine_options = self._get_engine_options()
        self.logger = get_logger()

    def _get_engine_options(self) -> Dict[str, Any]:
        """Get engine options from source config.

        Returns:
            Dictionary of engine options
        """
        # Default options
        merged = {
            "chunk_size": 10000,
            "encoding": "utf-8",
            "delimiter": ",",
            "quote_char": '"',
        }

        if self.source_config.engine:
            options = self.source_config.engine.get("options", {})
            if not isinstance(options, dict):
                options = {}

            # Check both top-level options and native options
            native_opts = options.get("native", {})
            if not isinstance(native_opts, dict):
                native_opts = {}

            # First, update with native options
            merged.update(native_opts)

            # Support batch_size as alias for chunk_size (for consistency with other extractors)
            # Check if chunk_size was explicitly set in native_opts
            chunk_size_explicitly_set = "chunk_size" in native_opts

            # If chunk_size wasn't explicitly set, try to use batch_size
            if not chunk_size_explicitly_set:
                if "batch_size" in options:
                    merged["chunk_size"] = options["batch_size"]
                elif "batch_size" in native_opts:
                    merged["chunk_size"] = native_opts["batch_size"]

            # Update with other top-level options (excluding native)
            # This allows top-level chunk_size to override native chunk_size or batch_size
            for key, value in options.items():
                if key != "native":
                    merged[key] = value

            # Final check: if chunk_size is explicitly set in top-level options, use it
            # This takes highest precedence
            if "chunk_size" in options:
                merged["chunk_size"] = options["chunk_size"]

        return merged

    def extract(
        self,
        state_manager: Optional[IncrementalStateManager] = None,
        checkpoint_context: Optional[Dict[str, Any]] = None,
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data from CSV files.

        Args:
            state_manager: Optional incremental state manager (deprecated, use incremental strategy)
            checkpoint_context: Optional checkpoint context for WAL resume

        Yields:
            Batches of records as dictionaries
        """
        if not self.source_config.files:
            raise ValueError("CSV source requires 'files' configuration")

        chunk_size = self.engine_options.get("chunk_size", 10000)
        encoding = self.engine_options.get("encoding", "utf-8")
        delimiter = self.engine_options.get("delimiter", ",")
        quote_char = self.engine_options.get("quote_char", '"')

        # Create incremental strategy if configured
        incremental_strategy: Optional[IncrementalStrategy] = None
        if self.source_config.incremental:
            # State path should already be set in config by JobConfig._merge_source_with_recipe
            # But we'll use it if provided, otherwise create strategy without state path
            incremental_strategy = create_incremental_strategy(
                self.source_config.incremental,
                default_state_path=None,  # State path should be in config
            )

        # Process each file
        for file_config in self.source_config.files:
            file_path_str = file_config.get("path") or file_config.get("file")
            if not file_path_str:
                raise ValueError(
                    "CSV file configuration must include 'path' or 'file' field"
                )

            file_path = Path(file_path_str)
            if not file_path.exists():
                raise FileNotFoundError(f"CSV file not found: {file_path}")

            self.logger.info(
                f"Processing CSV file: {file_path}",
                extra={
                    "file_path": str(file_path),
                    "event_type": "csv_file_processing",
                },
            )

            # Prepare entity metadata for incremental strategy
            file_id = file_config.get("id") or str(file_path)
            file_stat = file_path.stat()
            modified_time = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
            object_name = file_config.get("object", "default")

            entity_metadata = {
                "file_id": file_id,
                "file_path": str(file_path),
                "path": str(file_path),
                "modified_time": modified_time,
                "object_name": object_name,
                "name": object_name,
            }

            # Check if entity should be processed (for file_modified_time strategy)
            if incremental_strategy and not incremental_strategy.should_process_entity(
                entity_metadata
            ):
                self.logger.info(
                    f"Skipping file (already processed): {file_path}",
                    extra={
                        "file_path": str(file_path),
                        "file_id": file_id,
                        "event_type": "csv_file_skipped",
                    },
                )
                continue  # Skip this file

            # Read CSV file in chunks
            try:
                import pandas as pd
            except ImportError:
                raise ImportError(
                    "pandas is required for CSV extraction. Install with: pip install pandas"
                )

            # Check for WAL checkpoint to resume from
            start_chunk = 0
            wal_manager = None
            if checkpoint_context:
                checkpoint = checkpoint_context.get("checkpoint")
                wal_manager = checkpoint_context.get("wal_manager")
                if checkpoint and checkpoint.get("type") == "chunk_based":
                    start_chunk = checkpoint.get("chunk_number", 0)
                    self.logger.info(
                        f"Resuming CSV extraction from chunk {start_chunk + 1}",
                        extra={
                            "file_path": str(file_path),
                            "resume_chunk": start_chunk + 1,
                            "event_type": "csv_resume",
                        },
                    )

            # Read CSV with specified options
            try:
                chunk_count = 0
                total_records_read = 0
                all_processed_records = []  # Track all records for state update

                for chunk_df in pd.read_csv(
                    file_path,
                    chunksize=chunk_size,
                    encoding=encoding,
                    sep=delimiter,
                    quotechar=quote_char,
                    dtype=str,  # Read all as strings initially, let schema validator handle types
                    na_values=["", "NULL", "null", "None"],
                    keep_default_na=False,
                ):
                    # Skip chunks before resume point
                    if chunk_count < start_chunk:
                        chunk_count += 1
                        continue

                    # Convert DataFrame to list of dictionaries
                    records = chunk_df.to_dict("records")
                    chunk_count += 1
                    total_records_read += len(records)

                    # Replace NaN with None for JSON serialization
                    for record in records:
                        for key, value in record.items():
                            if pd.isna(value):
                                record[key] = None

                    # Filter records using incremental strategy
                    if incremental_strategy:
                        original_count = len(records)
                        records = incremental_strategy.filter_records(
                            records, entity_metadata
                        )
                        if len(records) < original_count:
                            self.logger.info(
                                f"Filtered CSV chunk: {len(records)}/{original_count} records after incremental filtering (chunk {chunk_count})",
                                extra={
                                    "file_path": str(file_path),
                                    "chunk_number": chunk_count,
                                    "records_before": original_count,
                                    "records_after": len(records),
                                    "event_type": "csv_chunk_filtered",
                                },
                            )

                    if records:
                        all_processed_records.extend(records)
                        self.logger.info(
                            f"Read CSV chunk: {len(records)} records (chunk {chunk_count})",
                            extra={
                                "file_path": str(file_path),
                                "chunk_number": chunk_count,
                                "records_in_chunk": len(records),
                                "event_type": "csv_chunk_read",
                            },
                        )

                        # Update WAL checkpoint after each chunk
                        if wal_manager and checkpoint_context:
                            stream_name = checkpoint_context.get("stream_name", file_id)
                            checkpoint_data = {
                                "type": "chunk_based",
                                "file_id": file_id,
                                "chunk_number": chunk_count,
                                "records_in_chunk": len(records),
                                "total_records_read": total_records_read,
                            }
                            wal_manager.update_checkpoint(stream_name, checkpoint_data)

                        yield records

                self.logger.info(
                    f"Finished reading CSV file: {file_path} ({total_records_read} total records, {chunk_count} chunks)",
                    extra={
                        "file_path": str(file_path),
                        "total_records": total_records_read,
                        "total_chunks": chunk_count,
                        "event_type": "csv_file_read_complete",
                    },
                )

                # Update state after successful processing
                # For file-based strategies (FileModifiedTimeStrategy), update state even if
                # there are no processed records, as they only need the modification time.
                # For cursor-based strategies, only update if there are processed records.
                if incremental_strategy:
                    is_file_based_strategy = isinstance(
                        incremental_strategy, FileModifiedTimeStrategy
                    )
                    # File-based strategies need state update even for empty files to prevent infinite reprocessing
                    # Cursor-based strategies only update when there are processed records
                    should_update_state = (
                        is_file_based_strategy or len(all_processed_records) > 0
                    )
                    if should_update_state:
                        incremental_strategy.update_state(
                            entity_metadata, all_processed_records
                        )
                        self.logger.info(
                            f"Updated incremental state for file: {file_path}",
                            extra={
                                "file_path": str(file_path),
                                "strategy": incremental_strategy.strategy_name,
                                "records_processed": len(all_processed_records),
                                "event_type": "incremental_state_updated",
                            },
                        )

            except Exception as e:
                raise RuntimeError(
                    f"Failed to read CSV file {file_path}: {str(e)}"
                ) from e

    def get_total_records_estimate(self) -> Optional[int]:
        """Get estimated total number of records across all files.

        Returns:
            Estimated record count or None if cannot estimate
        """
        if not self.source_config.files:
            return None

        total = 0
        for file_config in self.source_config.files:
            file_path_str = file_config.get("path") or file_config.get("file")
            if not file_path_str:
                continue

            file_path = Path(file_path_str)
            if not file_path.exists():
                continue

            try:
                import pandas as pd

                # Quick count using pandas (reads full file but efficient)
                df = pd.read_csv(
                    file_path,
                    encoding=self.engine_options.get("encoding", "utf-8"),
                    sep=self.engine_options.get("delimiter", ","),
                    quotechar=self.engine_options.get("quote_char", '"'),
                )
                total += len(df)
            except Exception:
                # If we can't count, return None
                return None

        return total

    def extract_metadata(self) -> Dict[str, Any]:
        """Extract naturally available metadata from CSV files.

        Extracts metadata that is naturally available in CSV files:
        - Column names from the header row
        - File metadata (size, modification time)

        Returns:
            Dictionary with "tags" key containing field_name -> metadata mapping.
            For CSV, column names are extracted as available metadata.
            e.g., {"tags": {"email": "column", "phone": "column"}}
        """
        if not self.source_config.files:
            return {"tags": {}}

        source_tags = {}

        try:
            import pandas as pd
        except ImportError:
            return {"tags": {}}

        # Process each file
        for file_config in self.source_config.files:
            file_path_str = file_config.get("path") or file_config.get("file")
            if not file_path_str:
                continue

            file_path = Path(file_path_str)
            if not file_path.exists():
                continue

            try:
                # Read just the header to get column names
                encoding = self.engine_options.get("encoding", "utf-8")
                delimiter = self.engine_options.get("delimiter", ",")
                quote_char = self.engine_options.get("quote_char", '"')

                # Read first row to get column names
                df_header = pd.read_csv(
                    file_path,
                    nrows=0,  # Only read header
                    encoding=encoding,
                    sep=delimiter,
                    quotechar=quote_char,
                )

                # Extract column names as naturally available metadata
                # Mark them as "column" to indicate they're from CSV structure
                for col_name in df_header.columns:
                    source_tags[col_name] = "column"

            except Exception:
                # If reading fails, continue to next file
                continue

        return {"tags": source_tags}
