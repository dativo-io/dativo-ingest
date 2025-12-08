"""Custom Python reader for Parquet files from S3/MinIO.

This reader demonstrates:
- Reading Parquet files from S3/MinIO
- Batch processing with configurable batch_size
- S3 connection handling
"""

import os
import sys
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

# Add src to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from dativo_ingest.plugins import BaseReader, ConnectionTestResult
from dativo_ingest.utils import expand_env_variable


class ParquetReader(BaseReader):
    """Custom reader for Parquet files from S3/MinIO.

    Configuration example:
        source:
          custom_reader: "tests/fixtures/plugins/parquet_reader.py:ParquetReader"
          connection:
            s3:
              endpoint: "${S3_ENDPOINT}"
              bucket: test-bucket
              access_key_id: "${AWS_ACCESS_KEY_ID}"
              secret_access_key: "${AWS_SECRET_ACCESS_KEY}"
              region: "${AWS_REGION}"
              path_style_access: true
          files:
            - path: "perf_test_db/test1_csv_python/data"
              object: perf_test_data
          engine:
            options:
              file_format: parquet
              batch_size: 50000
    """

    def __init__(self, source_config):
        """Initialize Parquet reader."""
        super().__init__(source_config)

        # Get S3 configuration
        connection = source_config.connection or {}
        s3_config = connection.get("s3", {})

        # Expand environment variables in config values
        # Handle both dict access (Pydantic model) and direct dict access
        if hasattr(s3_config, "get"):
            bucket_val = s3_config.get("bucket")
            endpoint_val = s3_config.get("endpoint")
            region_val = s3_config.get("region")
            access_key_val = s3_config.get("access_key_id")
            secret_key_val = s3_config.get("secret_access_key")
        else:
            bucket_val = (
                s3_config.get("bucket") if isinstance(s3_config, dict) else None
            )
            endpoint_val = (
                s3_config.get("endpoint") if isinstance(s3_config, dict) else None
            )
            region_val = (
                s3_config.get("region") if isinstance(s3_config, dict) else None
            )
            access_key_val = (
                s3_config.get("access_key_id") if isinstance(s3_config, dict) else None
            )
            secret_key_val = (
                s3_config.get("secret_access_key")
                if isinstance(s3_config, dict)
                else None
            )

        self.bucket = expand_env_variable(bucket_val)
        self.endpoint = expand_env_variable(endpoint_val)
        region_expanded = expand_env_variable(region_val)
        self.region = (
            region_expanded if region_expanded else os.getenv("AWS_REGION", "us-east-1")
        )
        access_key_expanded = expand_env_variable(access_key_val)
        self.access_key_id = (
            access_key_expanded
            if access_key_expanded
            else os.getenv("AWS_ACCESS_KEY_ID")
        )
        secret_key_expanded = expand_env_variable(secret_key_val)
        self.secret_access_key = (
            secret_key_expanded
            if secret_key_expanded
            else os.getenv("AWS_SECRET_ACCESS_KEY")
        )
        self.path_style_access = (
            s3_config.get("path_style_access", False)
            if isinstance(s3_config, dict)
            else False
        )

        # Get files configuration
        self.files = source_config.files or []

        # Engine options
        if source_config.engine and isinstance(source_config.engine, dict):
            engine_opts = source_config.engine.get("options", {})
        else:
            engine_opts = {}
        self.batch_size = engine_opts.get("batch_size", 50000)
        self.file_format = engine_opts.get("file_format", "parquet")

        # Initialize S3 client
        self.s3_client = self._setup_s3_client()

    def _setup_s3_client(self):
        """Set up S3 client with credentials."""
        try:
            import boto3

            # Ensure region is expanded and not None
            region = self.region or "us-east-1"

            # Ensure endpoint is expanded (can be None for AWS S3)
            endpoint = self.endpoint if self.endpoint else None

            if endpoint:
                # MinIO or S3-compatible storage
                return boto3.client(
                    "s3",
                    endpoint_url=endpoint,
                    aws_access_key_id=self.access_key_id,
                    aws_secret_access_key=self.secret_access_key,
                    region_name=region,
                )
            elif self.access_key_id and self.secret_access_key:
                return boto3.client(
                    "s3",
                    region_name=region,
                    aws_access_key_id=self.access_key_id,
                    aws_secret_access_key=self.secret_access_key,
                )
            else:
                return boto3.client("s3", region_name=region)

        except ImportError:
            raise ImportError(
                "boto3 is required for S3 Parquet reading. Install with: pip install boto3"
            )

    def check_connection(self) -> ConnectionTestResult:
        """Test connection to S3."""
        if not self.bucket:
            return ConnectionTestResult(
                success=False,
                message="S3 bucket not configured",
                error_code="CONFIG_ERROR",
            )

        try:
            self.s3_client.head_bucket(Bucket=self.bucket)
            return ConnectionTestResult(
                success=True,
                message="S3 bucket accessible",
                details={
                    "bucket": self.bucket,
                    "endpoint": self.endpoint,
                    "region": self.region,
                },
            )
        except Exception as e:
            error_msg = str(e)
            if "403" in error_msg or "Access Denied" in error_msg:
                return ConnectionTestResult(
                    success=False,
                    message="Access denied to S3 bucket",
                    error_code="AUTH_FAILED",
                )
            elif "404" in error_msg or "NoSuchBucket" in error_msg:
                return ConnectionTestResult(
                    success=False,
                    message=f"S3 bucket not found: {self.bucket}",
                    error_code="RESOURCE_NOT_FOUND",
                )
            else:
                return ConnectionTestResult(
                    success=False,
                    message=f"S3 connection failed: {error_msg}",
                    error_code="CONNECTION_ERROR",
                )

    def _list_parquet_files(self, prefix: str) -> List[str]:
        """List Parquet files in S3 prefix.

        Args:
            prefix: S3 prefix/path to list files from

        Returns:
            List of S3 keys for Parquet files
        """
        parquet_files = []
        paginator = self.s3_client.get_paginator("list_objects_v2")

        try:
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                if "Contents" in page:
                    for obj in page["Contents"]:
                        key = obj["Key"]
                        if key.endswith(".parquet"):
                            parquet_files.append(key)
        except Exception as e:
            raise ValueError(f"Failed to list Parquet files in S3: {e}")

        return sorted(parquet_files)

    def _read_parquet_file(self, s3_key: str) -> List[Dict[str, Any]]:
        """Read a Parquet file from S3 and convert to records.

        Args:
            s3_key: S3 object key for the Parquet file

        Returns:
            List of records as dictionaries
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError(
                "pandas is required for Parquet reading. Install with: pip install pandas pyarrow"
            )

        try:
            # Download Parquet file from S3
            response = self.s3_client.get_object(Bucket=self.bucket, Key=s3_key)
            parquet_file = BytesIO(response["Body"].read())

            # Read Parquet file into DataFrame
            df = pd.read_parquet(parquet_file)

            # Convert DataFrame to list of dictionaries
            records = df.to_dict("records")

            # Replace NaN with None for JSON serialization
            for record in records:
                for key, value in record.items():
                    if pd.isna(value):
                        record[key] = None

            return records

        except Exception as e:
            raise ValueError(f"Failed to read Parquet file {s3_key} from S3: {e}")

    def extract(
        self,
        state_manager: Optional[Any] = None,
        checkpoint_context: Optional[Dict[str, Any]] = None,
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data from Parquet files in S3.

        Args:
            state_manager: Optional state manager (not used for Parquet)
            checkpoint_context: Optional checkpoint context for WAL resume

        Yields:
            Batches of records as list of dictionaries
        """
        for file_config in self.files:
            path = file_config.get("path")
            if not path:
                continue

            # List Parquet files in the S3 path
            parquet_files = self._list_parquet_files(path)

            if not parquet_files:
                # No Parquet files found - this might be expected for empty tables
                continue

            # Process each Parquet file
            for parquet_file_key in parquet_files:
                # Read entire Parquet file
                records = self._read_parquet_file(parquet_file_key)

                # Yield records in batches
                batch = []
                for record in records:
                    batch.append(record)

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
            path = file_config.get("path")
            if not path:
                continue

            try:
                parquet_files = self._list_parquet_files(path)
                for parquet_file_key in parquet_files:
                    # Get file metadata to estimate row count
                    # Note: This is approximate - actual count may differ
                    try:
                        response = self.s3_client.head_object(
                            Bucket=self.bucket, Key=parquet_file_key
                        )
                        # Rough estimate: assume ~1KB per row (very approximate)
                        size_bytes = response.get("ContentLength", 0)
                        estimated_rows = size_bytes // 1024
                        total += estimated_rows
                    except Exception:
                        # If we can't estimate, return None
                        return None
            except Exception:
                return None

        return total if total > 0 else None
