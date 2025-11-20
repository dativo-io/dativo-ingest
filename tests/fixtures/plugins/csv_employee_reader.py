"""Custom Python reader for CSV Employee files.

This reader demonstrates:
- Reading CSV files with custom logic
- Data transformation
- Error handling
"""

import csv
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

# Add src to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from dativo_ingest.plugins import BaseReader


class CSVEmployeeReader(BaseReader):
    """Custom reader for CSV Employee files.

    Configuration example:
        source:
          custom_reader: "tests/fixtures/plugins/csv_employee_reader.py:CSVEmployeeReader"
          files:
            - path: "tests/fixtures/seeds/adventureworks/Employee.csv"
              object: Employee
          engine:
            options:
              batch_size: 100
    """

    def __init__(self, source_config):
        """Initialize CSV Employee reader."""
        super().__init__(source_config)

        # Get files configuration
        self.files = source_config.files or []

        # Engine options
        if source_config.engine and isinstance(source_config.engine, dict):
            engine_opts = source_config.engine.get("options", {})
        else:
            engine_opts = {}
        self.batch_size = engine_opts.get("batch_size", 1000)
        self.delimiter = engine_opts.get("delimiter", ",")
        self.encoding = engine_opts.get("encoding", "utf-8")

    def extract(
        self, state_manager: Optional[Any] = None
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data from CSV files.

        Args:
            state_manager: Optional state manager (not used for CSV)

        Yields:
            Batches of records as list of dictionaries
        """
        for file_config in self.files:
            file_path_str = file_config.get("path") or file_config.get("file")
            if not file_path_str:
                continue

            # Expand environment variables in path
            file_path_str = os.path.expandvars(file_path_str)
            file_path = Path(file_path_str)

            if not file_path.exists():
                # Try relative to project root
                project_root = Path(__file__).parent.parent.parent.parent
                alt_path = project_root / file_path_str
                if alt_path.exists():
                    file_path = alt_path
                else:
                    raise FileNotFoundError(
                        f"CSV file not found: {file_path_str}\n"
                        f"  Tried: {file_path}\n"
                        f"  Tried: {alt_path}"
                    )

            # Read CSV file in batches
            batch = []
            with open(file_path, "r", encoding=self.encoding) as f:
                reader = csv.DictReader(f, delimiter=self.delimiter)

                for row in reader:
                    # Clean up values (remove whitespace, handle empty strings)
                    cleaned_row = {
                        k: (v.strip() if isinstance(v, str) else v) if v else None
                        for k, v in row.items()
                    }

                    batch.append(cleaned_row)

                    # Yield batch when size reached
                    if len(batch) >= self.batch_size:
                        yield batch
                        batch = []

                # Yield remaining records
                if batch:
                    yield batch

    def get_total_records_estimate(self) -> Optional[int]:
        """Get estimated total number of records.

        Returns:
            Estimated record count or None
        """
        total = 0
        for file_config in self.files:
            file_path_str = file_config.get("path") or file_config.get("file")
            if not file_path_str:
                continue

            file_path = Path(file_path_str)
            if not file_path.exists():
                continue

            try:
                # Quick line count (subtract 1 for header)
                with open(file_path, "r", encoding=self.encoding) as f:
                    count = sum(1 for _ in f) - 1
                    total += max(0, count)
            except Exception:
                return None

        return total if total > 0 else None
