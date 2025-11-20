"""Example custom writer for JSON files.

This writer demonstrates how to:
- Write records to JSON files
- Handle batching and file naming
- Upload files to S3
- Implement commit logic
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List

# Import base classes from dativo_ingest
import sys

# Add src to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dativo_ingest.plugins import BaseWriter


class JSONFileWriter(BaseWriter):
    """Custom writer for JSON files.
    
    Configuration example:
        target:
          custom_writer: "examples/plugins/json_file_writer.py:JSONFileWriter"
          connection:
            s3:
              bucket: "my-data-lake"
              region: "us-east-1"
              access_key: "${AWS_ACCESS_KEY_ID}"
              secret_key: "${AWS_SECRET_ACCESS_KEY}"
          engine:
            options:
              format: "jsonl"  # or "json"
              indent: 2
              compress: false
    """
    
    def __init__(self, asset_definition, target_config, output_base):
        """Initialize JSON file writer.
        
        Args:
            asset_definition: Asset definition with schema
            target_config: Target configuration with connection details
            output_base: Base output path
        """
        super().__init__(asset_definition, target_config, output_base)
        
        # Get engine options
        engine_opts = target_config.engine.get("options", {}) if target_config.engine else {}
        self.format = engine_opts.get("format", "jsonl")  # jsonl or json
        self.indent = engine_opts.get("indent", None)
        self.compress = engine_opts.get("compress", False)
        
        # Get S3 configuration
        s3_config = target_config.connection.get("s3", {}) if target_config.connection else {}
        self.bucket = s3_config.get("bucket")
        self.region = s3_config.get("region", "us-east-1")
        
        # Initialize S3 client if bucket is configured
        self.s3_client = None
        if self.bucket:
            self.s3_client = self._setup_s3_client(s3_config)
    
    def _setup_s3_client(self, s3_config: Dict[str, Any]):
        """Set up S3 client with credentials.
        
        Args:
            s3_config: S3 configuration
        
        Returns:
            boto3 S3 client
        """
        try:
            import boto3
            
            # Get credentials
            access_key = s3_config.get("access_key") or os.getenv("AWS_ACCESS_KEY_ID")
            secret_key = s3_config.get("secret_key") or os.getenv("AWS_SECRET_ACCESS_KEY")
            
            if access_key and secret_key:
                return boto3.client(
                    "s3",
                    region_name=self.region,
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key,
                )
            else:
                # Use default credentials
                return boto3.client("s3", region_name=self.region)
        
        except ImportError:
            raise ImportError(
                "boto3 is required for S3 uploads. Install with: pip install boto3"
            )
    
    def write_batch(
        self, records: List[Dict[str, Any]], file_counter: int
    ) -> List[Dict[str, Any]]:
        """Write a batch of records to JSON file.
        
        Args:
            records: List of validated records
            file_counter: Counter for unique file naming
        
        Returns:
            List of file metadata dictionaries
        """
        if not records:
            return []
        
        # Generate file name
        file_extension = ".jsonl" if self.format == "jsonl" else ".json"
        if self.compress:
            file_extension += ".gz"
        
        file_name = f"part-{file_counter:05d}{file_extension}"
        
        # Write to temporary file
        with tempfile.NamedTemporaryFile(
            mode="w" if not self.compress else "wb",
            delete=False,
            suffix=file_extension,
        ) as tmp_file:
            tmp_path = tmp_file.name
            
            if self.compress:
                import gzip
                with gzip.open(tmp_path, "wt") as gz_file:
                    self._write_records(gz_file, records)
            else:
                self._write_records(tmp_file, records)
        
        # Get file size
        file_size = os.path.getsize(tmp_path)
        
        # Upload to S3 or keep locally
        if self.s3_client and self.bucket:
            s3_key = f"{self.output_base.replace(f's3://{self.bucket}/', '')}/{file_name}"
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
        
        return [{
            "path": file_path,
            "size_bytes": file_size,
            "record_count": len(records),
            "format": self.format,
            "compressed": self.compress,
        }]
    
    def _write_records(self, file_handle, records: List[Dict[str, Any]]):
        """Write records to file handle.
        
        Args:
            file_handle: File handle to write to
            records: Records to write
        """
        if self.format == "jsonl":
            # Write one JSON object per line
            for record in records:
                json_line = json.dumps(record)
                file_handle.write(json_line + "\n")
        else:
            # Write as JSON array
            json.dump(records, file_handle, indent=self.indent)
    
    def commit_files(self, file_metadata: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Commit files (optional post-write operations).
        
        Args:
            file_metadata: List of file metadata from write_batch calls
        
        Returns:
            Commit result information
        """
        total_records = sum(fm.get("record_count", 0) for fm in file_metadata)
        total_bytes = sum(fm.get("size_bytes", 0) for fm in file_metadata)
        
        # Optional: Create a manifest file
        if self.s3_client and self.bucket:
            manifest = {
                "files": file_metadata,
                "total_records": total_records,
                "total_bytes": total_bytes,
                "asset_name": self.asset_definition.name,
            }
            
            manifest_key = f"{self.output_base.replace(f's3://{self.bucket}/', '')}/_manifest.json"
            
            with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp:
                json.dump(manifest, tmp, indent=2)
                tmp_path = tmp.name
            
            self.s3_client.upload_file(tmp_path, self.bucket, manifest_key)
            os.unlink(tmp_path)
        
        return {
            "status": "success",
            "files_added": len(file_metadata),
            "total_records": total_records,
            "total_bytes": total_bytes,
        }


def main():
    """Example usage for testing."""
    from dativo_ingest.config import TargetConfig, AssetDefinition
    from pathlib import Path
    
    # Example asset definition
    class MockAsset:
        name = "test_data"
        schema = [
            {"name": "id", "type": "integer"},
            {"name": "name", "type": "string"},
        ]
    
    # Example configuration
    target_config = TargetConfig(
        type="json",
        connection={},  # No S3, write locally
        engine={
            "options": {
                "format": "jsonl",
                "indent": None,
                "compress": False,
            }
        },
    )
    
    # Create writer
    output_base = "/tmp/test_output"
    writer = JSONFileWriter(MockAsset(), target_config, output_base)
    
    # Write sample data
    sample_records = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
        {"id": 3, "name": "Charlie"},
    ]
    
    print("Writing sample data...")
    file_metadata = writer.write_batch(sample_records, file_counter=0)
    print(f"Wrote {len(sample_records)} records to: {file_metadata[0]['path']}")
    
    # Commit
    result = writer.commit_files(file_metadata)
    print(f"Commit result: {result}")


if __name__ == "__main__":
    main()
