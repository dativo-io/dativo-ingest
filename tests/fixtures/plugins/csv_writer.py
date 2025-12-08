"""Custom Python writer for CSV files.

This writer demonstrates:
- Writing records to CSV files
- S3/MinIO upload support
- Configurable formatting options
"""

import csv
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add src to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from dativo_ingest.plugins import BaseWriter, ConnectionTestResult
from dativo_ingest.utils import expand_env_variable


class CSVWriter(BaseWriter):
    """Custom writer for CSV files.

    Configuration example:
        target:
          custom_writer: "tests/fixtures/plugins/csv_writer.py:CSVWriter"
          connection:
            s3:
              bucket: "test-bucket"
              endpoint: "${S3_ENDPOINT}"
              access_key_id: "${AWS_ACCESS_KEY_ID}"
              secret_access_key: "${AWS_SECRET_ACCESS_KEY}"
              region: "${AWS_REGION}"
              path_style_access: true
          engine:
            options:
              delimiter: ","
              include_header: true
    """

    def __init__(self, asset_definition, target_config, output_base):
        """Initialize CSV writer.

        Args:
            asset_definition: Asset definition with schema and metadata
            target_config: Target configuration including connection details
            output_base: Base output path for writing files
        """
        super().__init__(asset_definition, target_config, output_base)

        # Get engine options
        if target_config.engine and isinstance(target_config.engine, dict):
            engine_opts = target_config.engine.get("options", {})
        else:
            engine_opts = {}
        self.delimiter = engine_opts.get("delimiter", ",")
        self.include_header = engine_opts.get("include_header", True)

        # Get S3 configuration
        s3_config = (
            target_config.connection.get("s3", {}) if target_config.connection else {}
        )
        # Expand environment variables in config values
        self.bucket = expand_env_variable(s3_config.get("bucket"))
        self.endpoint = expand_env_variable(s3_config.get("endpoint"))
        region_expanded = expand_env_variable(s3_config.get("region"))
        self.region = region_expanded if region_expanded else os.getenv("AWS_REGION", "us-east-1")
        access_key_expanded = expand_env_variable(s3_config.get("access_key_id"))
        self.access_key_id = access_key_expanded if access_key_expanded else os.getenv("AWS_ACCESS_KEY_ID")
        secret_key_expanded = expand_env_variable(s3_config.get("secret_access_key"))
        self.secret_access_key = secret_key_expanded if secret_key_expanded else os.getenv("AWS_SECRET_ACCESS_KEY")

        # Initialize S3 client if bucket is configured
        self.s3_client = None
        if self.bucket:
            self.s3_client = self._setup_s3_client()

        # Track if header has been written (for multi-file writes)
        self.header_written = False

    def check_connection(self) -> ConnectionTestResult:
        """Test connection to S3/target."""
        if not self.s3_client or not self.bucket:
            # Local mode - check write permissions
            try:
                local_dir = Path(self.output_base.replace("s3://", ""))
                local_dir.mkdir(parents=True, exist_ok=True)
                test_file = local_dir / ".connection_test"
                test_file.write_text("test")
                test_file.unlink()
                return ConnectionTestResult(
                    success=True,
                    message="Local filesystem writable",
                    details={"output_base": str(local_dir)},
                )
            except Exception as e:
                return ConnectionTestResult(
                    success=False,
                    message=f"Cannot write to local filesystem: {str(e)}",
                    error_code="PERMISSION_ERROR",
                )

        # S3 mode - test bucket access
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

    def _setup_s3_client(self):
        """Set up S3 client with credentials."""
        try:
            import boto3

            # Use expanded instance variables
            endpoint = self.endpoint
            access_key = self.access_key_id
            secret_key = self.secret_access_key
            region = self.region

            if endpoint:
                # MinIO or S3-compatible storage
                return boto3.client(
                    "s3",
                    endpoint_url=endpoint,
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key,
                    region_name=region,
                )
            elif access_key and secret_key:
                return boto3.client(
                    "s3",
                    region_name=region,
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key,
                )
            else:
                return boto3.client("s3", region_name=region)

        except ImportError:
            raise ImportError(
                "boto3 is required for S3 uploads. Install with: pip install boto3"
            )

    def write_batch(
        self, records: List[Dict[str, Any]], file_counter: int
    ) -> List[Dict[str, Any]]:
        """Write a batch of records to CSV file."""
        if not records:
            return []

        # Get field names from schema or first record
        if hasattr(self.asset_definition, "schema") and self.asset_definition.schema:
            fieldnames = [field["name"] for field in self.asset_definition.schema]
        else:
            fieldnames = list(records[0].keys())

        # Generate file name
        file_name = f"part-{file_counter:05d}.csv"

        # Write to temporary file
        with tempfile.NamedTemporaryFile(
            mode="w",
            delete=False,
            suffix=".csv",
            newline="",
        ) as tmp_file:
            tmp_path = tmp_file.name

            writer = csv.DictWriter(
                tmp_file,
                fieldnames=fieldnames,
                delimiter=self.delimiter,
                extrasaction="ignore",
            )

            # Write header if needed
            if self.include_header and not self.header_written:
                writer.writeheader()
                self.header_written = True

            # Write records
            for record in records:
                writer.writerow(record)

        # Get file size
        file_size = os.path.getsize(tmp_path)

        # Upload to S3 or keep locally
        if self.s3_client and self.bucket:
            # Determine S3 key
            if self.output_base.startswith(f"s3://{self.bucket}/"):
                s3_key = f"{self.output_base.replace(f's3://{self.bucket}/', '')}/{file_name}"
            else:
                s3_key = f"{self.output_base}/{file_name}"

            self.s3_client.upload_file(tmp_path, self.bucket, s3_key)
            file_path = f"s3://{self.bucket}/{s3_key}"

            # Clean up temp file
            os.unlink(tmp_path)
        else:
            # Keep file locally
            local_dir = Path(self.output_base.replace("s3://", ""))
            local_dir.mkdir(parents=True, exist_ok=True)
            local_path = local_dir / file_name

            # Move temp file to final location
            os.rename(tmp_path, str(local_path))
            file_path = str(local_path)

        return [
            {
                "path": file_path,
                "size_bytes": file_size,
                "record_count": len(records),
                "format": "csv",
            }
        ]

    def commit_files(self, file_metadata: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Commit files (optional post-write operations)."""
        total_records = sum(fm.get("record_count", 0) for fm in file_metadata)
        total_bytes = sum(fm.get("size_bytes", 0) for fm in file_metadata)

        return {
            "status": "success",
            "files_added": len(file_metadata),
            "total_records": total_records,
            "total_bytes": total_bytes,
        }
