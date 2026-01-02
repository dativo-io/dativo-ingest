#!/usr/bin/env python3
"""Performance benchmark script for Python vs Rust custom writers.

This script treats `dativo ingest` as a black box:
1. Generates job configs for Python and Rust writers
2. Runs `dativo ingest` for each config
3. Times the execution
4. Compares results

All components (CSV writer, YAML configs) are embedded in this script.

Usage:
    python scripts/benchmark_writers.py --records 100000000
"""

import argparse
import csv
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dativo_ingest.plugins import BaseWriter, ConnectionTestResult
from dativo_ingest.utils import expand_env_variable


# ============================================================================
# Embedded CSV Writer Plugin
# ============================================================================

class CSVWriter(BaseWriter):
    """Custom Python CSV writer for benchmarking.
    
    This writer is embedded in the benchmark script and handles local filesystem
    writes when no S3 credentials are provided.
    """

    def __init__(self, asset_definition, target_config, output_base):
        """Initialize CSV writer."""
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
        self.region = (
            region_expanded if region_expanded else os.getenv("AWS_REGION", "us-east-1")
        )
        access_key_expanded = expand_env_variable(s3_config.get("access_key_id"))
        self.access_key_id = (
            access_key_expanded
            if access_key_expanded
            else os.getenv("AWS_ACCESS_KEY_ID")
        )
        secret_key_expanded = expand_env_variable(s3_config.get("secret_access_key"))
        self.secret_access_key = (
            secret_key_expanded
            if secret_key_expanded
            else os.getenv("AWS_SECRET_ACCESS_KEY")
        )

        # Initialize S3 client if bucket is configured and looks like a real S3 bucket
        # If bucket starts with "/", treat it as a local filesystem path
        # Also treat as local if no S3 credentials are provided
        self.s3_client = None
        self.is_local_path = self.bucket and self.bucket.startswith("/")
        
        # Check if we have S3 credentials - if not, treat as local filesystem
        has_credentials = (
            self.access_key_id or 
            self.secret_access_key or 
            os.getenv("AWS_ACCESS_KEY_ID") or 
            os.getenv("AWS_SECRET_ACCESS_KEY")
        )
        
        # If bucket doesn't look like local path but we have no credentials, treat as local
        if self.bucket and not self.is_local_path and not has_credentials:
            self.is_local_path = True
        
        # Only try to create S3 client if we have a bucket, it's not a local path, and we have credentials
        if self.bucket and not self.is_local_path and has_credentials:
            try:
                self.s3_client = self._setup_s3_client()
            except Exception:
                # If S3 client setup fails, fall back to local filesystem
                self.s3_client = None
                self.is_local_path = True

        # Track if header has been written (for multi-file writes)
        self.header_written = False

    def check_connection(self) -> ConnectionTestResult:
        """Test connection to S3/target."""
        if self.is_local_path or not self.s3_client or not self.bucket:
            # Local mode - check write permissions
            try:
                if self.is_local_path and self.bucket:
                    if self.bucket.startswith("/"):
                        local_base = Path(self.bucket)
                        output_path = self.output_base.replace("s3://", "").replace(f"{self.bucket}/", "")
                        local_dir = local_base / output_path
                    else:
                        local_base = Path("/tmp") / self.bucket
                        output_path = self.output_base.replace("s3://", "").replace(f"{self.bucket}/", "")
                        local_dir = local_base / output_path
                else:
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

            endpoint = self.endpoint
            access_key = self.access_key_id
            secret_key = self.secret_access_key
            region = self.region

            if endpoint:
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
        if self.s3_client and self.bucket and not self.is_local_path:
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
            if self.is_local_path and self.bucket:
                if self.bucket.startswith("/"):
                    local_base = Path(self.bucket)
                    output_path = self.output_base.replace("s3://", "").replace(f"{self.bucket}/", "")
                    local_dir = local_base / output_path
                else:
                    local_base = Path("/tmp") / self.bucket
                    output_path = self.output_base.replace("s3://", "").replace(f"{self.bucket}/", "")
                    local_dir = local_base / output_path
            else:
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


# ============================================================================
# YAML Config Generation
# ============================================================================

def generate_python_writer_config(
    workspace_root: Path, output_dir: Path, records: int, lib_ext: str
) -> Path:
    """Generate Python writer job config with embedded CSV writer plugin."""
    config_path = output_dir / "python_writer_benchmark.yaml"
    
    # Generate CSV writer plugin file (embedded in this script)
    csv_writer_path = output_dir / "csv_writer_plugin.py"
    with open(csv_writer_path, "w") as f:
        # Write the complete CSV writer plugin
        f.write(f'''"""CSV writer plugin for benchmark (auto-generated from benchmark_writers.py)."""
import csv
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

# Add src to path
sys.path.insert(0, r"{workspace_root / "src"}")

from dativo_ingest.plugins import BaseWriter, ConnectionTestResult
from dativo_ingest.utils import expand_env_variable


class CSVWriter(BaseWriter):
    """Custom Python CSV writer for benchmarking."""

    def __init__(self, asset_definition, target_config, output_base):
        super().__init__(asset_definition, target_config, output_base)

        # Get engine options
        if target_config.engine and isinstance(target_config.engine, dict):
            engine_opts = target_config.engine.get("options", {{}})
        else:
            engine_opts = {{}}
        self.delimiter = engine_opts.get("delimiter", ",")
        self.include_header = engine_opts.get("include_header", True)

        # Get S3 configuration
        s3_config = (
            target_config.connection.get("s3", {{}}) if target_config.connection else {{}}
        )
        self.bucket = expand_env_variable(s3_config.get("bucket"))
        self.endpoint = expand_env_variable(s3_config.get("endpoint"))
        region_expanded = expand_env_variable(s3_config.get("region"))
        self.region = (
            region_expanded if region_expanded else os.getenv("AWS_REGION", "us-east-1")
        )
        access_key_expanded = expand_env_variable(s3_config.get("access_key_id"))
        self.access_key_id = (
            access_key_expanded
            if access_key_expanded
            else os.getenv("AWS_ACCESS_KEY_ID")
        )
        secret_key_expanded = expand_env_variable(s3_config.get("secret_access_key"))
        self.secret_access_key = (
            secret_key_expanded
            if secret_key_expanded
            else os.getenv("AWS_SECRET_ACCESS_KEY")
        )

        # Initialize S3 client if bucket is configured and looks like a real S3 bucket
        self.s3_client = None
        self.is_local_path = self.bucket and self.bucket.startswith("/")
        
        # Check if we have S3 credentials - if not, treat as local filesystem
        has_credentials = (
            self.access_key_id or 
            self.secret_access_key or 
            os.getenv("AWS_ACCESS_KEY_ID") or 
            os.getenv("AWS_SECRET_ACCESS_KEY")
        )
        
        if self.bucket and not self.is_local_path and not has_credentials:
            self.is_local_path = True
        
        if self.bucket and not self.is_local_path and has_credentials:
            try:
                self.s3_client = self._setup_s3_client()
            except Exception:
                self.s3_client = None
                self.is_local_path = True

        self.header_written = False

    def check_connection(self) -> ConnectionTestResult:
        if self.is_local_path or not self.s3_client or not self.bucket:
            try:
                if self.is_local_path and self.bucket:
                    if self.bucket.startswith("/"):
                        local_base = Path(self.bucket)
                        output_path = self.output_base.replace("s3://", "").replace(f"{{self.bucket}}/", "")
                        local_dir = local_base / output_path
                    else:
                        local_base = Path("/tmp") / self.bucket
                        output_path = self.output_base.replace("s3://", "").replace(f"{{self.bucket}}/", "")
                        local_dir = local_base / output_path
                else:
                    local_dir = Path(self.output_base.replace("s3://", ""))
                local_dir.mkdir(parents=True, exist_ok=True)
                test_file = local_dir / ".connection_test"
                test_file.write_text("test")
                test_file.unlink()
                return ConnectionTestResult(
                    success=True,
                    message="Local filesystem writable",
                    details={{"output_base": str(local_dir)}},
                )
            except Exception as e:
                return ConnectionTestResult(
                    success=False,
                    message=f"Cannot write to local filesystem: {{str(e)}}",
                    error_code="PERMISSION_ERROR",
                )

        try:
            self.s3_client.head_bucket(Bucket=self.bucket)
            return ConnectionTestResult(
                success=True,
                message="S3 bucket accessible",
                details={{"bucket": self.bucket, "endpoint": self.endpoint, "region": self.region}},
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
                    message=f"S3 bucket not found: {{self.bucket}}",
                    error_code="RESOURCE_NOT_FOUND",
                )
            else:
                return ConnectionTestResult(
                    success=False,
                    message=f"S3 connection failed: {{error_msg}}",
                    error_code="CONNECTION_ERROR",
                )

    def _setup_s3_client(self):
        try:
            import boto3
            endpoint = self.endpoint
            access_key = self.access_key_id
            secret_key = self.secret_access_key
            region = self.region
            if endpoint:
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
            raise ImportError("boto3 is required for S3 uploads. Install with: pip install boto3")

    def write_batch(self, records: List[Dict[str, Any]], file_counter: int) -> List[Dict[str, Any]]:
        if not records:
            return []

        if hasattr(self.asset_definition, "schema") and self.asset_definition.schema:
            fieldnames = [field["name"] for field in self.asset_definition.schema]
        else:
            fieldnames = list(records[0].keys())

        file_name = f"part-{{file_counter:05d}}.csv"

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
            if self.include_header and not self.header_written:
                writer.writeheader()
                self.header_written = True
            for record in records:
                writer.writerow(record)

        file_size = os.path.getsize(tmp_path)

        if self.s3_client and self.bucket and not self.is_local_path:
            if self.output_base.startswith(f"s3://{{self.bucket}}/"):
                s3_key = f"{{self.output_base.replace(f's3://{{self.bucket}}/', '')}}/{{file_name}}"
            else:
                s3_key = f"{{self.output_base}}/{{file_name}}"
            self.s3_client.upload_file(tmp_path, self.bucket, s3_key)
            file_path = f"s3://{{self.bucket}}/{{s3_key}}"
            os.unlink(tmp_path)
        else:
            if self.is_local_path and self.bucket:
                if self.bucket.startswith("/"):
                    local_base = Path(self.bucket)
                    output_path = self.output_base.replace("s3://", "").replace(f"{{self.bucket}}/", "")
                    local_dir = local_base / output_path
                else:
                    local_base = Path("/tmp") / self.bucket
                    output_path = self.output_base.replace("s3://", "").replace(f"{{self.bucket}}/", "")
                    local_dir = local_base / output_path
            else:
                local_dir = Path(self.output_base.replace("s3://", ""))
            local_dir.mkdir(parents=True, exist_ok=True)
            local_path = local_dir / file_name
            os.rename(tmp_path, str(local_path))
            file_path = str(local_path)

        return [{{
            "path": file_path,
            "size_bytes": file_size,
            "record_count": len(records),
            "format": "csv",
        }}]

    def commit_files(self, file_metadata: List[Dict[str, Any]]) -> Dict[str, Any]:
        total_records = sum(fm.get("record_count", 0) for fm in file_metadata)
        total_bytes = sum(fm.get("size_bytes", 0) for fm in file_metadata)
        return {{
            "status": "success",
            "files_added": len(file_metadata),
            "total_records": total_records,
            "total_bytes": total_bytes,
        }}
''')
    
    config_content = f"""# Benchmark job: Python CSV writer with {records:,} Mimesis records
# Auto-generated by benchmark_writers.py

tenant_id: benchmark
environment: test

source_connector: mimesis
source_connector_path: {workspace_root}/connectors/mimesis.yaml

target_connector: s3
target_connector_path: {workspace_root}/connectors/s3.yaml

asset: mimesis_customers
asset_path: {workspace_root}/assets/examples/mimesis/v1.0/customers.yaml

source:
  type: mimesis
  object: customers
  engine:
    type: native
    options:
      native:
        row_count: {records}
        batch_size: 100000
        locale: "en"
        seed: 42
        null_probability: 0.1

target:
  custom_writer: "{csv_writer_path}:CSVWriter"
  connection:
    s3:
      bucket: "dativo_benchmark_python"
  engine:
    options:
      delimiter: ","
      include_header: true

schema_validation_mode: warn

logging:
  redaction: false
  level: INFO
"""
    
    config_path.write_text(config_content)
    return config_path


def generate_rust_writer_config(
    workspace_root: Path, output_dir: Path, records: int, lib_ext: str
) -> Path:
    """Generate Rust writer job config."""
    config_path = output_dir / "rust_writer_benchmark.yaml"
    
    rust_lib_path = workspace_root / "examples" / "plugins" / "rust" / "target" / "release" / f"libcsv_writer_plugin.{lib_ext}"
    
    config_content = f"""# Benchmark job: Rust CSV writer with {records:,} Mimesis records
# Auto-generated by benchmark_writers.py

tenant_id: benchmark
environment: test

# Source connector - Mimesis for synthetic data generation
source_connector: mimesis
source_connector_path: {workspace_root}/connectors/mimesis.yaml

# Target connector - using S3 as base (for metadata)
target_connector: s3
target_connector_path: {workspace_root}/connectors/s3.yaml

# Asset definition
asset: mimesis_customers
asset_path: {workspace_root}/assets/examples/mimesis/v1.0/customers.yaml

# Source configuration - generate {records:,} rows
source:
  type: mimesis
  object: customers
  engine:
    type: native
    options:
      native:
        row_count: {records}
        batch_size: 100000
        locale: "en"
        seed: 42  # For reproducibility (same as Python test)
        null_probability: 0.1

# Target configuration - Rust CSV writer
target:
  # Specify Rust plugin
  custom_writer: "{rust_lib_path}:create_writer"
  
  # Connection details (local filesystem for benchmark)
  connection:
    s3:
      bucket: "dativo_benchmark_rust"
  
  # Engine options
  engine:
    options:
      delimiter: ","
      include_header: true
      target_size_mb: 50  # Target file size in MB

# Execution configuration
schema_validation_mode: warn

# Logging configuration
logging:
  redaction: false
  level: INFO
"""
    
    config_path.write_text(config_content)
    return config_path


# ============================================================================
# Benchmark Functions
# ============================================================================

def detect_library_extension() -> str:
    """Detect the appropriate library extension for the current platform."""
    system = platform.system().lower()
    if system == "darwin":
        return "dylib"
    elif system == "linux":
        return "so"
    elif system == "windows":
        return "dll"
    else:
        return "so"


def find_dativo_command() -> list:
    """Find the dativo command."""
    if shutil.which("dativo"):
        return ["dativo"]
    elif shutil.which("dativo-ingest"):
        return ["dativo-ingest"]
    else:
        # Check for virtual environment first
        workspace_root = Path(__file__).parent.parent
        venv_python = workspace_root / "venv" / "bin" / "python"
        if venv_python.exists():
            return [str(venv_python), "-m", "dativo_ingest.cli"]
        
        # Try to find a Python 3.10+ executable
        # Prefer python3 over sys.executable to avoid old Python versions
        python_candidates = ["python3", "python3.13", "python3.12", "python3.11", "python3.10", "python"]
        for python_cmd in python_candidates:
            python_path = shutil.which(python_cmd)
            if python_path:
                # Check version
                try:
                    result = subprocess.run(
                        [python_path, "--version"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    version_str = result.stdout.strip() or result.stderr.strip()
                    # Extract version number (e.g., "Python 3.13.2" -> "3.13")
                    import re
                    match = re.search(r"3\.(\d+)", version_str)
                    if match and int(match.group(1)) >= 10:
                        return [python_path, "-m", "dativo_ingest.cli"]
                except Exception:
                    continue
        # Fallback to sys.executable
        return [sys.executable, "-m", "dativo_ingest.cli"]


def run_dativo_ingest(config_path: Path, output_dir: Path) -> Dict[str, any]:
    """Run dativo ingest command and measure performance."""
    dativo_cmd = find_dativo_command()
    
    log_file = output_dir / f"{config_path.stem}.log"
    
    print(f"  Running: {' '.join(dativo_cmd)} ingest --config {config_path}")
    print(f"  Log file: {log_file}")
    
    start_time = time.time()
    
    try:
        with open(log_file, "w") as log:
            # Use self_hosted mode to avoid Docker sandboxing overhead for fair comparison
            cmd = dativo_cmd + ["ingest", "--config", str(config_path), "--mode", "self_hosted"]
            # Set PYTHONPATH to include src directory for module imports
            env = os.environ.copy()
            workspace_root = Path(__file__).parent.parent
            src_path = str(workspace_root / "src")
            if "PYTHONPATH" in env:
                env["PYTHONPATH"] = f"{src_path}:{env['PYTHONPATH']}"
            else:
                env["PYTHONPATH"] = src_path
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600,
                env=env,
            )
            log.write("=== STDOUT ===\n")
            log.write(result.stdout)
            log.write("\n=== STDERR ===\n")
            log.write(result.stderr)
        
        end_time = time.time()
        elapsed = end_time - start_time
        
        # Parse output for metrics
        total_records = None
        files_written = None
        
        log_content = log_file.read_text()
        import re
        
        record_matches = re.findall(r'(\d+)\s+records?', log_content, re.IGNORECASE)
        if record_matches:
            try:
                total_records = max([int(m) for m in record_matches])
            except ValueError:
                pass
        
        file_matches = re.findall(r'(\d+)\s+files?', log_content, re.IGNORECASE)
        if file_matches:
            try:
                files_written = max([int(m) for m in file_matches])
            except ValueError:
                pass
        
        return {
            "success": result.returncode == 0,
            "elapsed_seconds": elapsed,
            "return_code": result.returncode,
            "total_records": total_records,
            "files_written": files_written,
            "log_file": str(log_file),
            "stdout": result.stdout[:1000] if result.stdout else "",
            "stderr": result.stderr[:1000] if result.stderr else "",
        }
    
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "elapsed_seconds": 3600,
            "error": "Timeout after 1 hour",
            "log_file": str(log_file),
        }
    except Exception as e:
        return {
            "success": False,
            "elapsed_seconds": time.time() - start_time,
            "error": str(e),
            "log_file": str(log_file),
        }


def calculate_output_size(output_base: Path) -> int:
    """Calculate total size of output files."""
    total_size = 0
    if output_base.exists():
        for file_path in output_base.rglob("*"):
            if file_path.is_file():
                total_size += file_path.stat().st_size
    return total_size


def count_output_files(output_base: Path) -> int:
    """Count output files."""
    if not output_base.exists():
        return 0
    return len(list(output_base.rglob("*.csv")))


def main():
    """Main benchmark function."""
    parser = argparse.ArgumentParser(
        description="Benchmark Python vs Rust CSV writers using dativo ingest"
    )
    parser.add_argument(
        "--records",
        type=int,
        default=100_000_000,
        help="Number of records to generate (default: 100,000,000)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="/tmp/dativo_writer_benchmark",
        help="Output directory for test files and logs (default: /tmp/dativo_writer_benchmark)",
    )
    parser.add_argument(
        "--skip-python",
        action="store_true",
        help="Skip Python writer test",
    )
    parser.add_argument(
        "--skip-rust",
        action="store_true",
        help="Skip Rust writer test",
    )
    
    args = parser.parse_args()
    
    # Setup
    workspace_root = Path(__file__).parent.parent
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    lib_ext = detect_library_extension()
    print(f"Detected library extension: {lib_ext}")
    
    # Verify Rust library exists if not skipping
    if not args.skip_rust:
        rust_lib_base = workspace_root / "examples" / "plugins" / "rust" / "target" / "release" / "libcsv_writer_plugin"
        rust_lib_path = rust_lib_base.with_suffix(f".{lib_ext}")
        
        if not rust_lib_path.exists():
            print(f"ERROR: Rust library not found: {rust_lib_path}")
            print("Please build it first:")
            print(f"  cd {workspace_root / 'examples' / 'plugins' / 'rust'}")
            print("  cargo build --release")
            sys.exit(1)
    
    print("=" * 70)
    print("DATIVO WRITER BENCHMARK")
    print("=" * 70)
    print(f"Records: {args.records:,}")
    print(f"Output directory: {output_dir}")
    print()
    
    results = {}
    
    # Test Python writer
    if not args.skip_python:
        print("=" * 70)
        print("Testing Python CSV Writer")
        print("=" * 70)
        
        python_config = generate_python_writer_config(workspace_root, output_dir, args.records, lib_ext)
        python_metrics = run_dativo_ingest(python_config, output_dir)
        
        if python_metrics.get("success"):
            python_output_base = Path("/tmp/dativo_benchmark_python")
            python_output_size = calculate_output_size(python_output_base)
            python_file_count = count_output_files(python_output_base)
            
            python_metrics["output_size_bytes"] = python_output_size
            python_metrics["file_count"] = python_file_count
            python_metrics["output_path"] = str(python_output_base)
            
            if python_metrics.get("elapsed_seconds", 0) > 0:
                python_metrics["records_per_second"] = (
                    args.records / python_metrics["elapsed_seconds"]
                )
                if python_output_size > 0:
                    python_metrics["mb_per_second"] = (
                        python_output_size / (1024 * 1024) / python_metrics["elapsed_seconds"]
                    )
        
        results["python"] = python_metrics
        
        print(f"  Success: {python_metrics.get('success', False)}")
        print(f"  Elapsed: {python_metrics.get('elapsed_seconds', 0):.2f} seconds")
        if python_metrics.get("records_per_second"):
            print(f"  Throughput: {python_metrics['records_per_second']:,.0f} records/sec")
        if python_metrics.get("mb_per_second"):
            print(f"  Speed: {python_metrics['mb_per_second']:,.2f} MB/sec")
        if python_metrics.get("file_count"):
            print(f"  Files: {python_metrics['file_count']}")
        print()
    
    # Test Rust writer
    if not args.skip_rust:
        print("=" * 70)
        print("Testing Rust CSV Writer")
        print("=" * 70)
        
        rust_config = generate_rust_writer_config(workspace_root, output_dir, args.records, lib_ext)
        rust_metrics = run_dativo_ingest(rust_config, output_dir)
        
        if rust_metrics.get("success"):
            rust_output_base = Path("/tmp/dativo_benchmark_rust")
            rust_output_size = calculate_output_size(rust_output_base)
            rust_file_count = count_output_files(rust_output_base)
            
            rust_metrics["output_size_bytes"] = rust_output_size
            rust_metrics["file_count"] = rust_file_count
            rust_metrics["output_path"] = str(rust_output_base)
            
            if rust_metrics.get("elapsed_seconds", 0) > 0:
                rust_metrics["records_per_second"] = (
                    args.records / rust_metrics["elapsed_seconds"]
                )
                if rust_output_size > 0:
                    rust_metrics["mb_per_second"] = (
                        rust_output_size / (1024 * 1024) / rust_metrics["elapsed_seconds"]
                    )
        
        results["rust"] = rust_metrics
        
        print(f"  Success: {rust_metrics.get('success', False)}")
        print(f"  Elapsed: {rust_metrics.get('elapsed_seconds', 0):.2f} seconds")
        if rust_metrics.get("records_per_second"):
            print(f"  Throughput: {rust_metrics['records_per_second']:,.0f} records/sec")
        if rust_metrics.get("mb_per_second"):
            print(f"  Speed: {rust_metrics['mb_per_second']:,.2f} MB/sec")
        if rust_metrics.get("file_count"):
            print(f"  Files: {rust_metrics['file_count']}")
        print()
    
    # Compare results
    if results.get("python") and results.get("rust"):
        python_metrics = results["python"]
        rust_metrics = results["rust"]
        
        if python_metrics.get("success") and rust_metrics.get("success"):
            print("=" * 70)
            print("COMPARISON RESULTS")
            print("=" * 70)
            
            python_time = python_metrics.get("elapsed_seconds", 0)
            rust_time = rust_metrics.get("elapsed_seconds", 0)
            
            if python_time > 0 and rust_time > 0:
                speedup = python_time / rust_time
                print(f"\nPython Writer:")
                print(f"  Time: {python_time:.2f}s")
                if python_metrics.get("records_per_second"):
                    print(f"  Throughput: {python_metrics['records_per_second']:,.0f} records/sec")
                if python_metrics.get("mb_per_second"):
                    print(f"  Speed: {python_metrics['mb_per_second']:,.2f} MB/sec")
                
                print(f"\nRust Writer:")
                print(f"  Time: {rust_time:.2f}s")
                if rust_metrics.get("records_per_second"):
                    print(f"  Throughput: {rust_metrics['records_per_second']:,.0f} records/sec")
                if rust_metrics.get("mb_per_second"):
                    print(f"  Speed: {rust_metrics['mb_per_second']:,.2f} MB/sec")
                
                print(f"\n{'='*70}")
                print(f"Rust is {speedup:.2f}x faster")
                if python_metrics.get("records_per_second") and rust_metrics.get("records_per_second"):
                    throughput_ratio = rust_metrics["records_per_second"] / python_metrics["records_per_second"]
                    print(f"Rust throughput is {throughput_ratio:.2f}x higher")
                print("=" * 70)
    
    # Save results to JSON
    results_file = output_dir / "benchmark_results.json"
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults saved to: {results_file}")
    
    # Exit with error if any test failed
    if results.get("python", {}).get("success") is False or results.get("rust", {}).get("success") is False:
        sys.exit(1)


if __name__ == "__main__":
    main()
