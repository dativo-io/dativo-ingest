#!/usr/bin/env python3
"""Performance benchmark: Python vs Rust CSV Reading.

This benchmark focuses on CPU-intensive CSV parsing, where Rust should show
significant advantages (10-15x faster according to documentation).

Usage:
    python scripts/benchmark_csv_reading.py --records 10000000
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dativo_ingest.config import JobConfig, SourceConfig, TargetConfig
from dativo_ingest.job_executor import JobExecutor


def generate_test_csv(output_path: Path, num_records: int):
    """Generate a test CSV file with synthetic data."""
    print(f"Generating {num_records:,} records to {output_path}...")
    
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['id', 'name', 'email', 'age', 'city', 'country', 'salary', 'active'])
        
        for i in range(num_records):
            writer.writerow([
                i,
                f"User_{i}",
                f"user_{i}@example.com",
                20 + (i % 50),
                f"City_{i % 100}",
                f"Country_{i % 10}",
                30000 + (i % 100000),
                i % 2 == 0
            ])
    
    file_size = output_path.stat().st_size / (1024 * 1024)  # MB
    print(f"Generated {file_size:.2f} MB CSV file")
    return file_size


def benchmark_python_csv_reader(csv_path: Path, num_records: int) -> dict:
    """Benchmark Python CSV reader."""
    print("\n" + "="*70)
    print("Testing Python CSV Reader")
    print("="*70)
    
    # Create temporary job config
    workspace_root = Path(__file__).parent.parent
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        config_content = f"""tenant_id: benchmark
environment: test

source_connector: csv
source_connector_path: {workspace_root}/connectors/csv.yaml

target_connector: s3
target_connector_path: {workspace_root}/connectors/s3.yaml

asset: benchmark_csv
asset_path: {workspace_root}/assets/examples/csv/v1.0/benchmark_csv.yaml

source:
  type: csv
  files:
    - path: {csv_path}
      object: benchmark_csv
  engine:
    options:
      batch_size: 100000
      delimiter: ","
      encoding: "utf-8"

target:
  connection:
    s3:
      bucket: "dativo_benchmark_python_reader"

schema_validation_mode: warn
logging:
  redaction: false
  level: INFO
"""
        f.write(config_content)
        config_path = Path(f.name)
    
    try:
        # Find dativo command
        workspace_root = Path(__file__).parent.parent
        venv_python = workspace_root / "venv" / "bin" / "python"
        if venv_python.exists():
            dativo_cmd = [str(venv_python), "-m", "dativo_ingest.cli"]
        else:
            dativo_cmd = ["python3", "-m", "dativo_ingest.cli"]
        
        # Set PYTHONPATH
        env = os.environ.copy()
        env["PYTHONPATH"] = str(workspace_root / "src")
        
        start_time = time.time()
        result = subprocess.run(
            dativo_cmd + ["ingest", "--config", str(config_path), "--mode", "self_hosted"],
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        elapsed = time.time() - start_time
        
        success = result.returncode == 0
        
        return {
            "success": success,
            "elapsed_seconds": elapsed,
            "records_per_second": num_records / elapsed if elapsed > 0 else 0,
            "return_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    finally:
        config_path.unlink()


def benchmark_rust_csv_reader(csv_path: Path, num_records: int) -> dict:
    """Benchmark Rust CSV reader."""
    print("\n" + "="*70)
    print("Testing Rust CSV Reader")
    print("="*70)
    
    workspace_root = Path(__file__).parent.parent
    
    # Detect library extension
    import platform
    system = platform.system().lower()
    if system == "darwin":
        lib_ext = "dylib"
    elif system == "linux":
        lib_ext = "so"
    else:
        lib_ext = "dll"
    
    rust_lib_path = workspace_root / "examples" / "plugins" / "rust" / "target" / "release" / f"libcsv_reader_plugin.{lib_ext}"
    
    if not rust_lib_path.exists():
        print(f"ERROR: Rust CSV reader plugin not found: {rust_lib_path}")
        print("Please build it first:")
        print(f"  cd {workspace_root / 'examples' / 'plugins' / 'rust'}")
        print("  cargo build --release")
        return {"success": False, "error": "Rust plugin not found"}
    
    # Create temporary job config
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        config_content = f"""tenant_id: benchmark
environment: test

source_connector: csv
source_connector_path: {workspace_root}/connectors/csv.yaml

target_connector: s3
target_connector_path: {workspace_root}/connectors/s3.yaml

asset: benchmark_csv
asset_path: {workspace_root}/assets/examples/csv/v1.0/benchmark_csv.yaml

source:
  custom_reader: "{rust_lib_path}:create_reader"
  files:
    - path: {csv_path}
      object: benchmark_csv
  engine:
    options:
      batch_size: 100000
      delimiter: ","
      encoding: "utf-8"

target:
  connection:
    s3:
      bucket: "dativo_benchmark_rust_reader"

schema_validation_mode: warn
logging:
  redaction: false
  level: INFO
"""
        f.write(config_content)
        config_path = Path(f.name)
    
    try:
        # Find dativo command
        venv_python = workspace_root / "venv" / "bin" / "python"
        if venv_python.exists():
            dativo_cmd = [str(venv_python), "-m", "dativo_ingest.cli"]
        else:
            dativo_cmd = ["python3", "-m", "dativo_ingest.cli"]
        
        # Set PYTHONPATH
        env = os.environ.copy()
        env["PYTHONPATH"] = str(workspace_root / "src")
        
        start_time = time.time()
        result = subprocess.run(
            dativo_cmd + ["ingest", "--config", str(config_path), "--mode", "self_hosted"],
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        elapsed = time.time() - start_time
        
        success = result.returncode == 0
        
        return {
            "success": success,
            "elapsed_seconds": elapsed,
            "records_per_second": num_records / elapsed if elapsed > 0 else 0,
            "return_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    finally:
        config_path.unlink()


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark Python vs Rust CSV reading performance"
    )
    parser.add_argument(
        "--records",
        type=int,
        default=10_000_000,
        help="Number of records to generate (default: 10,000,000)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="/tmp/dativo_csv_benchmark",
        help="Output directory for test files (default: /tmp/dativo_csv_benchmark)",
    )
    
    args = parser.parse_args()
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    csv_path = output_dir / "benchmark_data.csv"
    
    print("="*70)
    print("CSV READING PERFORMANCE BENCHMARK")
    print("="*70)
    print(f"Records: {args.records:,}")
    print(f"Output directory: {output_dir}")
    print()
    
    # Generate test CSV
    file_size_mb = generate_test_csv(csv_path, args.records)
    
    # Benchmark Python
    python_results = benchmark_python_csv_reader(csv_path, args.records)
    
    # Benchmark Rust
    rust_results = benchmark_rust_csv_reader(csv_path, args.records)
    
    # Print results
    print("\n" + "="*70)
    print("RESULTS")
    print("="*70)
    
    print("\nPython CSV Reader:")
    print(f"  Success: {python_results.get('success', False)}")
    print(f"  Time: {python_results.get('elapsed_seconds', 0):.2f}s")
    if python_results.get('records_per_second'):
        print(f"  Throughput: {python_results['records_per_second']:,.0f} records/sec")
    
    print("\nRust CSV Reader:")
    print(f"  Success: {rust_results.get('success', False)}")
    print(f"  Time: {rust_results.get('elapsed_seconds', 0):.2f}s")
    if rust_results.get('records_per_second'):
        print(f"  Throughput: {rust_results['records_per_second']:,.0f} records/sec")
    
    # Comparison
    if python_results.get('success') and rust_results.get('success'):
        python_time = python_results.get('elapsed_seconds', 0)
        rust_time = rust_results.get('elapsed_seconds', 0)
        
        if python_time > 0 and rust_time > 0:
            speedup = python_time / rust_time
            print(f"\n{'='*70}")
            print(f"Rust is {speedup:.2f}x faster than Python")
            
            if python_results.get('records_per_second') and rust_results.get('records_per_second'):
                throughput_ratio = rust_results['records_per_second'] / python_results['records_per_second']
                print(f"Rust throughput is {throughput_ratio:.2f}x higher")
    
    # Save results
    results = {
        "python": python_results,
        "rust": rust_results,
        "file_size_mb": file_size_mb,
        "num_records": args.records,
    }
    
    results_path = output_dir / "benchmark_results.json"
    results_path.write_text(json.dumps(results, indent=2))
    print(f"\nResults saved to: {results_path}")


if __name__ == "__main__":
    main()

