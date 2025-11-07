"""Parquet file writer with target file size and partitioning support."""

import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import AssetDefinition, TargetConfig


class ParquetWriter:
    """Writes records to Parquet files with target file size and partitioning."""

    def __init__(
        self,
        asset_definition: AssetDefinition,
        target_config: TargetConfig,
        output_base_path: str,
    ):
        """Initialize Parquet writer.

        Args:
            asset_definition: Asset definition containing schema
            target_config: Target configuration with partitioning and file size settings
            output_base_path: Base path for output files (S3/MinIO compatible)
        """
        self.asset_definition = asset_definition
        self.target_config = target_config
        self.output_base_path = output_base_path

        # Get target file size (default: 128-200 MB range, use 150 MB as default)
        self.target_size_mb = target_config.parquet_target_size_mb or 150
        self.target_size_bytes = self.target_size_mb * 1024 * 1024

        # Get partitioning columns
        self.partitioning = target_config.partitioning or []

    def _create_pyarrow_schema(self) -> Any:
        """Create PyArrow schema from asset definition.

        Returns:
            PyArrow schema object
        """
        try:
            import pyarrow as pa
        except ImportError:
            raise ImportError(
                "pyarrow is required for Parquet writing. Install with: pip install pyarrow"
            )

        fields = []
        for field_def in self.asset_definition.schema:
            field_name = field_def["name"]
            field_type = field_def.get("type", "string")

            # Map to PyArrow types
            if field_type == "string":
                pa_type = pa.string()
            elif field_type == "integer":
                pa_type = pa.int64()
            elif field_type in ["float", "double"]:
                pa_type = pa.float64()
            elif field_type == "boolean":
                pa_type = pa.bool_()
            elif field_type in ["timestamp", "datetime", "date"]:
                pa_type = pa.timestamp("us")  # Microsecond precision
            else:
                # Default to string for unknown types
                pa_type = pa.string()

            # Check if nullable
            is_required = field_def.get("required", False)
            nullable = not is_required

            fields.append(pa.field(field_name, pa_type, nullable=nullable))

        return pa.schema(fields)

    def _get_partition_value(self, record: Dict[str, Any], partition_col: str) -> str:
        """Get partition value from record.

        Args:
            record: Record dictionary
            partition_col: Partition column name

        Returns:
            Partition value as string
        """
        if partition_col == "ingest_date":
            # Use current date for ingest_date partition
            return datetime.date.today().isoformat()

        # Get value from record
        value = record.get(partition_col)
        if value is None:
            return "unknown"

        # Convert to string
        if isinstance(value, datetime.datetime):
            return value.date().isoformat()
        if isinstance(value, datetime.date):
            return value.isoformat()

        return str(value)

    def _get_partition_path(self, record: Dict[str, Any]) -> str:
        """Get partition path for a record following Hive-style partitioning.

        Industry standard: column=value/column2=value2/ format
        - Lowercase column names
        - URL-safe values
        - Forward slashes as separators

        Args:
            record: Record dictionary

        Returns:
            Partition path string (e.g., "ingest_date=2024-01-01/" or "year=2024/month=01/day=15/")
        """
        if not self.partitioning:
            return ""

        parts = []
        for partition_col in self.partitioning:
            # Normalize column name: lowercase, replace spaces/hyphens with underscores
            normalized_col = partition_col.lower().replace(" ", "_").replace("-", "_")
            partition_value = self._get_partition_value(record, partition_col)
            
            # Normalize partition value: ensure URL-safe
            # Dates should be in ISO format (YYYY-MM-DD)
            # Other values: lowercase, replace spaces with underscores, remove special chars
            if isinstance(partition_value, str):
                # Keep ISO date format as-is
                if len(partition_value) == 10 and partition_value.count("-") == 2:
                    normalized_value = partition_value
                else:
                    # Normalize other string values
                    normalized_value = partition_value.lower().replace(" ", "_")
                    # Remove or replace special characters (keep alphanumeric, underscore, hyphen)
                    import re
                    normalized_value = re.sub(r'[^a-z0-9_-]', '_', normalized_value)
            else:
                normalized_value = str(partition_value).lower().replace(" ", "_")
            
            parts.append(f"{normalized_col}={normalized_value}")

        # Return Hive-style partition path with trailing slash
        return "/".join(parts) + "/"

    def write_batch(
        self,
        records: List[Dict[str, Any]],
        file_counter: int = 0,
    ) -> List[Dict[str, Any]]:
        """Write a batch of records to Parquet files.

        Args:
            records: List of record dictionaries
            file_counter: Counter for generating unique file names

        Returns:
            List of file metadata dictionaries with:
            - path: Full file path
            - record_count: Number of records in file
            - size_bytes: File size in bytes
        """
        if not records:
            return []

        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            raise ImportError(
                "pyarrow is required for Parquet writing. Install with: pip install pyarrow"
            )

        # Group records by partition
        partitioned_records: Dict[str, List[Dict[str, Any]]] = {}
        for record in records:
            partition_path = self._get_partition_path(record)
            if partition_path not in partitioned_records:
                partitioned_records[partition_path] = []
            partitioned_records[partition_path].append(record)

        file_metadata = []

        # Write each partition separately
        for partition_path, partition_records in partitioned_records.items():
            # Create PyArrow schema
            schema = self._create_pyarrow_schema()

            # Convert records to PyArrow table
            # Build arrays for each field
            arrays = {}
            for field_def in self.asset_definition.schema:
                field_name = field_def["name"]
                field_type = field_def.get("type", "string")

                values = [record.get(field_name) for record in partition_records]

                # Convert to appropriate PyArrow array
                if field_type == "string":
                    arrays[field_name] = pa.array(values, type=pa.string())
                elif field_type == "integer":
                    arrays[field_name] = pa.array(
                        [int(v) if v is not None else None for v in values],
                        type=pa.int64(),
                    )
                elif field_type in ["float", "double"]:
                    arrays[field_name] = pa.array(
                        [float(v) if v is not None else None for v in values],
                        type=pa.float64(),
                    )
                elif field_type == "boolean":
                    arrays[field_name] = pa.array(
                        [bool(v) if v is not None else None for v in values],
                        type=pa.bool_(),
                    )
                elif field_type in ["timestamp", "datetime", "date"]:
                    # Convert datetime objects to timestamps
                    timestamp_values = []
                    for v in values:
                        if v is None:
                            timestamp_values.append(None)
                        elif isinstance(v, datetime.datetime):
                            timestamp_values.append(v)
                        elif isinstance(v, datetime.date):
                            timestamp_values.append(
                                datetime.datetime.combine(v, datetime.time.min)
                            )
                        elif isinstance(v, str):
                            # Try to parse
                            try:
                                timestamp_values.append(
                                    datetime.datetime.fromisoformat(v.replace("Z", "+00:00"))
                                )
                            except ValueError:
                                timestamp_values.append(None)
                        else:
                            timestamp_values.append(None)
                    arrays[field_name] = pa.array(timestamp_values, type=pa.timestamp("us"))
                else:
                    # Default to string
                    arrays[field_name] = pa.array(
                        [str(v) if v is not None else None for v in values],
                        type=pa.string(),
                    )

            # Create table
            table = pa.table(arrays, schema=schema)

            # Write in chunks if table is too large
            current_size = 0
            chunk_start = 0
            chunk_file_counter = file_counter

            while chunk_start < len(partition_records):
                # Estimate chunk size
                # Get a sample of rows to estimate size
                sample_size = min(1000, len(partition_records) - chunk_start)
                sample_table = table.slice(chunk_start, sample_size)

                # Write to temporary location to measure size
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".parquet", delete=True) as tmp_file:
                    pq.write_table(sample_table, tmp_file.name)
                    sample_size_bytes = tmp_file.tell()

                # Estimate rows per file
                if sample_size_bytes > 0:
                    estimated_rows_per_file = int(
                        (self.target_size_bytes / sample_size_bytes) * sample_size
                    )
                else:
                    estimated_rows_per_file = len(partition_records)

                # Ensure we don't exceed remaining records
                chunk_end = min(
                    chunk_start + estimated_rows_per_file, len(partition_records)
                )

                # Write chunk
                chunk_table = table.slice(chunk_start, chunk_end - chunk_start)

                # Generate file path following industry standards
                # File naming: lowercase, underscores, zero-padded counter
                table_name = self.asset_definition.name.lower().replace("-", "_")
                file_name = f"{table_name}_{chunk_file_counter:06d}.parquet"
                
                # Build S3 path following industry standards:
                # s3://bucket/domain/data_product/table/partition/file.parquet
                # Partition format: Hive-style (column=value/column2=value2/)
                if self.output_base_path.startswith("s3://"):
                    # Remove trailing slash from base path
                    base = self.output_base_path.rstrip("/")
                    # Add partition path (already in Hive format: column=value/)
                    # Ensure single forward slash between components
                    if partition_path:
                        s3_path = f"{base}/{partition_path.rstrip('/')}/{file_name}"
                    else:
                        s3_path = f"{base}/{file_name}"
                else:
                    # Non-S3 path (shouldn't happen, but handle gracefully)
                    if partition_path:
                        s3_path = f"{self.output_base_path}/{partition_path.rstrip('/')}/{file_name}"
                    else:
                        s3_path = f"{self.output_base_path}/{file_name}"

                # Write Parquet file to local temporary directory
                # Files will be uploaded to S3/MinIO later
                import tempfile
                import os
                temp_dir = Path(tempfile.gettempdir()) / "dativo_ingest" / table_name
                temp_dir.mkdir(parents=True, exist_ok=True)
                local_path = temp_dir / file_name

                pq.write_table(
                    chunk_table,
                    str(local_path),
                    compression="snappy",
                    use_dictionary=True,
                )

                # Get actual file size
                actual_size = local_path.stat().st_size

                file_metadata.append(
                    {
                        "path": s3_path,  # S3 path for upload
                        "local_path": str(local_path),  # Local temporary file path
                        "record_count": chunk_end - chunk_start,
                        "size_bytes": actual_size,
                        "partition": partition_path.rstrip("/") if partition_path else None,
                    }
                )

                chunk_start = chunk_end
                chunk_file_counter += 1

        return file_metadata

