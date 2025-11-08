"""Native CSV extractor using pandas."""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from ..config import SourceConfig
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
        self, state_manager: Optional[IncrementalStateManager] = None
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data from CSV files.

        Args:
            state_manager: Optional incremental state manager for tracking file state

        Yields:
            Batches of records as dictionaries
        """
        if not self.source_config.files:
            raise ValueError("CSV source requires 'files' configuration")

        chunk_size = self.engine_options.get("chunk_size", 10000)
        encoding = self.engine_options.get("encoding", "utf-8")
        delimiter = self.engine_options.get("delimiter", ",")
        quote_char = self.engine_options.get("quote_char", '"')

        # Get incremental configuration
        incremental = self.source_config.incremental or {}
        strategy = incremental.get("strategy", "file_modified_time")
        lookback_days = incremental.get("lookback_days", 0)
        state_path_str = incremental.get("state_path", "")

        state_path = Path(state_path_str) if state_path_str else None

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

            # Check incremental state if enabled
            if strategy == "file_modified_time" and state_path:
                file_id = file_config.get("id") or str(file_path)
                file_stat = file_path.stat()
                modified_time = datetime.fromtimestamp(
                    file_stat.st_mtime
                ).isoformat()

                if IncrementalStateManager.should_skip_file(
                    file_id=file_id,
                    current_modified_time=modified_time,
                    state_path=state_path,
                    lookback_days=lookback_days,
                ):
                    continue  # Skip this file

            # Read CSV file in chunks
            try:
                import pandas as pd
            except ImportError:
                raise ImportError(
                    "pandas is required for CSV extraction. Install with: pip install pandas"
                )

            # Read CSV with specified options
            try:
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
                    # Convert DataFrame to list of dictionaries
                    records = chunk_df.to_dict("records")

                    # Replace NaN with None for JSON serialization
                    for record in records:
                        for key, value in record.items():
                            if pd.isna(value):
                                record[key] = None

                    yield records

                # Update state after successful processing
                if strategy == "file_modified_time" and state_path:
                    file_id = file_config.get("id") or str(file_path)
                    file_stat = file_path.stat()
                    modified_time = datetime.fromtimestamp(
                        file_stat.st_mtime
                    ).isoformat()
                    IncrementalStateManager.update_file_state(
                        file_id=file_id,
                        modified_time=modified_time,
                        state_path=state_path,
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

