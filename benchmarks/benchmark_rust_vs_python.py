#!/usr/bin/env python3
"""Benchmark script to compare Python vs Rust plugin performance.

This script generates synthetic data using Mimesis and compares write performance
between Python and Rust Parquet writers.

Usage:
    python benchmarks/benchmark_rust_vs_python.py --records 100000000 --batch-size 10000
    
    # Quick test (1M records)
    python benchmarks/benchmark_rust_vs_python.py --records 1000000 --batch-size 10000
    
    # Medium test (10M records)
    python benchmarks/benchmark_rust_vs_python.py --records 10000000 --batch-size 10000
    
    # Full test (100M records)
    python benchmarks/benchmark_rust_vs_python.py --records 100000000 --batch-size 10000
"""

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Any, List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dativo_ingest.config import AssetDefinition, SourceConfig, TargetConfig, TeamModel
from dativo_ingest.connectors.mimesis_extractor import MimesisExtractor
from dativo_ingest.parquet_writer import ParquetWriter


class BenchmarkResults:
    """Container for benchmark results."""
    
    def __init__(self, name: str):
        self.name = name
        self.total_records = 0
        self.batches_processed = 0
        self.start_time = None
        self.end_time = None
        self.files_written = []
        self.errors = []
        
    def start(self):
        """Mark benchmark start."""
        self.start_time = time.time()
        
    def end(self):
        """Mark benchmark end."""
        self.end_time = time.time()
        
    @property
    def duration(self) -> float:
        """Get duration in seconds."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0
        
    @property
    def records_per_second(self) -> float:
        """Get records per second."""
        if self.duration > 0:
            return self.total_records / self.duration
        return 0.0
        
    def add_batch(self, batch_size: int, files: List[Dict[str, Any]]):
        """Record a processed batch."""
        self.total_records += batch_size
        self.batches_processed += 1
        self.files_written.extend(files)
        
    def add_error(self, error: str):
        """Record an error."""
        self.errors.append(error)
        
    def print_summary(self):
        """Print benchmark summary."""
        print(f"\n{'='*70}")
        print(f"Benchmark: {self.name}")
        print(f"{'='*70}")
        print(f"Total Records:      {self.total_records:,}")
        print(f"Batches Processed:  {self.batches_processed:,}")
        print(f"Files Written:      {len(self.files_written):,}")
        print(f"Duration:           {self.duration:.2f} seconds")
        print(f"Records/Second:     {self.records_per_second:,.0f}")
        
        if self.files_written:
            total_size = sum(f.get('size_bytes', 0) for f in self.files_written)
            print(f"Total Data Size:    {total_size / (1024**3):.2f} GB")
            print(f"MB/Second:          {(total_size / (1024**2)) / self.duration:.2f}")
        
        if self.errors:
            print(f"\nErrors: {len(self.errors)}")
            for error in self.errors[:5]:  # Show first 5 errors
                print(f"  - {error}")
        
        print(f"{'='*70}\n")


def create_test_schema() -> List[Dict[str, Any]]:
    """Create a test schema for benchmarking.
    
    Returns:
        Schema with various field types
    """
    return [
        {"name": "id", "type": "integer"},
        {"name": "name", "type": "string"},
        {"name": "email", "type": "string"},
        {"name": "age", "type": "integer"},
        {"name": "salary", "type": "float"},
        {"name": "is_active", "type": "boolean"},
        {"name": "created_at", "type": "timestamp"},
        {"name": "department", "type": "string"},
        {"name": "city", "type": "string"},
        {"name": "country", "type": "string"},
    ]


def benchmark_python_writer(
    records_count: int,
    batch_size: int,
    output_dir: str,
) -> BenchmarkResults:
    """Benchmark Python Parquet writer.
    
    Args:
        records_count: Number of records to generate
        batch_size: Batch size for processing
        output_dir: Output directory for files
        
    Returns:
        Benchmark results
    """
    results = BenchmarkResults("Python ParquetWriter")
    
    # Create asset definition
    asset = AssetDefinition(
        name="benchmark_python",
        version="1.0.0",
        source_type="mimesis",
        object="test_data",
        schema=create_test_schema(),
        team=TeamModel(owner="benchmark"),
    )
    
    # Create source config for Mimesis
    source_config = SourceConfig(
        type="mimesis",
        engine={
            "row_count": records_count,
            "batch_size": batch_size,
            "seed": 42,
            "locale": "en",
        }
    )
    
    # Create target config
    target_config = TargetConfig(
        type="local",
        file_format="parquet",
    )
    
    try:
        # Initialize extractor and writer
        extractor = MimesisExtractor(source_config, asset)
        writer = ParquetWriter(asset, target_config, output_dir)
        
        # Start benchmark
        results.start()
        
        # Process batches
        file_counter = 0
        for batch in extractor.extract():
            try:
                files = writer.write_batch(batch, file_counter)
                results.add_batch(len(batch), files)
                file_counter += len(files)
                
                # Progress update every 100 batches
                if results.batches_processed % 100 == 0:
                    elapsed = time.time() - results.start_time
                    rate = results.total_records / elapsed if elapsed > 0 else 0
                    print(f"  Processed {results.total_records:,} records "
                          f"({results.batches_processed} batches) "
                          f"in {elapsed:.1f}s ({rate:,.0f} records/s)")
                    
            except Exception as e:
                results.add_error(f"Batch {file_counter} error: {e}")
                
        # End benchmark
        results.end()
        
    except Exception as e:
        results.add_error(f"Fatal error: {e}")
        results.end()
        
    return results


def benchmark_rust_writer_if_available(
    records_count: int,
    batch_size: int,
    output_dir: str,
) -> BenchmarkResults:
    """Benchmark Rust Parquet writer if available.
    
    Args:
        records_count: Number of records to generate
        batch_size: Batch size for processing
        output_dir: Output directory for files
        
    Returns:
        Benchmark results
    """
    results = BenchmarkResults("Rust ParquetWriter (Sandboxed)")
    
    # Check if Rust plugin exists
    rust_plugin_path = Path("examples/plugins/rust/parquet_writer/target/release/libparquet_writer.so")
    if not rust_plugin_path.exists():
        # Try .dylib for macOS
        rust_plugin_path = Path("examples/plugins/rust/parquet_writer/target/release/libparquet_writer.dylib")
        if not rust_plugin_path.exists():
            results.add_error("Rust plugin not found. Please build it first: cd examples/plugins/rust && make build")
            results.start()
            results.end()
            return results
    
    try:
        from dativo_ingest.rust_sandboxed_wrapper import SandboxedRustWriterWrapper
        
        # Create asset definition
        asset = AssetDefinition(
            name="benchmark_rust",
            version="1.0.0",
            source_type="mimesis",
            object="test_data",
            schema=create_test_schema(),
            team=TeamModel(owner="benchmark"),
        )
        
        # Create source config for Mimesis
        source_config = SourceConfig(
            type="mimesis",
            engine={
                "row_count": records_count,
                "batch_size": batch_size,
                "seed": 42,
                "locale": "en",
            }
        )
        
        # Create target config
        target_config = TargetConfig(
            type="local",
            file_format="parquet",
        )
        
        # Initialize extractor and writer
        extractor = MimesisExtractor(source_config, asset)
        writer = SandboxedRustWriterWrapper(
            str(rust_plugin_path),
            asset,
            target_config,
            output_dir,
            mode="cloud",
            sandbox_config={
                "enabled": True,
                "reuse_container": True,
                "max_retries": 3,
                "timeout": 600,
            }
        )
        
        # Start benchmark
        results.start()
        
        # Process batches
        file_counter = 0
        for batch in extractor.extract():
            try:
                files = writer.write_batch(batch, file_counter)
                results.add_batch(len(batch), files)
                file_counter += len(files)
                
                # Progress update every 100 batches
                if results.batches_processed % 100 == 0:
                    elapsed = time.time() - results.start_time
                    rate = results.total_records / elapsed if elapsed > 0 else 0
                    print(f"  Processed {results.total_records:,} records "
                          f"({results.batches_processed} batches) "
                          f"in {elapsed:.1f}s ({rate:,.0f} records/s)")
                    
            except Exception as e:
                results.add_error(f"Batch {file_counter} error: {e}")
                
        # End benchmark
        results.end()
        
        # Cleanup
        writer.sandbox.cleanup()
        
    except ImportError as e:
        results.add_error(f"Cannot import Rust sandbox: {e}")
        results.start()
        results.end()
    except Exception as e:
        results.add_error(f"Fatal error: {e}")
        results.end()
        
    return results


def compare_results(python_results: BenchmarkResults, rust_results: BenchmarkResults):
    """Compare and print benchmark results.
    
    Args:
        python_results: Python benchmark results
        rust_results: Rust benchmark results
    """
    print(f"\n{'='*70}")
    print("COMPARISON SUMMARY")
    print(f"{'='*70}")
    
    print(f"\n{'Metric':<30} {'Python':<20} {'Rust':<20} {'Speedup':<15}")
    print(f"{'-'*85}")
    
    # Duration
    print(f"{'Duration (seconds)':<30} "
          f"{python_results.duration:<20.2f} "
          f"{rust_results.duration:<20.2f} "
          f"{python_results.duration / rust_results.duration if rust_results.duration > 0 else 0:<15.2f}x")
    
    # Records per second
    print(f"{'Records/Second':<30} "
          f"{python_results.records_per_second:<20,.0f} "
          f"{rust_results.records_per_second:<20,.0f} "
          f"{rust_results.records_per_second / python_results.records_per_second if python_results.records_per_second > 0 else 0:<15.2f}x")
    
    # Batches processed
    print(f"{'Batches Processed':<30} "
          f"{python_results.batches_processed:<20,} "
          f"{rust_results.batches_processed:<20,} "
          f"{'N/A':<15}")
    
    # Files written
    print(f"{'Files Written':<30} "
          f"{len(python_results.files_written):<20,} "
          f"{len(rust_results.files_written):<20,} "
          f"{'N/A':<15}")
    
    # Errors
    print(f"{'Errors':<30} "
          f"{len(python_results.errors):<20} "
          f"{len(rust_results.errors):<20} "
          f"{'N/A':<15}")
    
    print(f"{'='*70}\n")
    
    # Performance summary
    if rust_results.duration > 0 and not rust_results.errors:
        speedup = python_results.duration / rust_results.duration
        if speedup > 1.0:
            print(f"✅ Rust is {speedup:.2f}x FASTER than Python")
            print(f"   Rust processed {rust_results.records_per_second:,.0f} records/second")
            print(f"   Python processed {python_results.records_per_second:,.0f} records/second")
            print(f"   Time saved: {python_results.duration - rust_results.duration:.2f} seconds")
        elif speedup < 1.0:
            print(f"⚠️  Python is {1/speedup:.2f}x faster than Rust")
            print(f"   (This suggests optimization needed)")
        else:
            print(f"➡️  Performance is similar")
    elif rust_results.errors:
        print(f"⚠️  Rust benchmark had errors:")
        for error in rust_results.errors:
            print(f"   {error}")
    
    print()


def main():
    """Main benchmark execution."""
    parser = argparse.ArgumentParser(description="Benchmark Rust vs Python plugin performance")
    parser.add_argument(
        "--records",
        type=int,
        default=1_000_000,
        help="Number of records to generate (default: 1,000,000)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10_000,
        help="Batch size for processing (default: 10,000)",
    )
    parser.add_argument(
        "--python-only",
        action="store_true",
        help="Only run Python benchmark",
    )
    parser.add_argument(
        "--rust-only",
        action="store_true",
        help="Only run Rust benchmark",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory (default: temp directory)",
    )
    
    args = parser.parse_args()
    
    # Create output directories
    if args.output_dir:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        python_output = str(output_dir / "python")
        rust_output = str(output_dir / "rust")
    else:
        temp_dir = tempfile.mkdtemp(prefix="benchmark_")
        python_output = os.path.join(temp_dir, "python")
        rust_output = os.path.join(temp_dir, "rust")
    
    os.makedirs(python_output, exist_ok=True)
    os.makedirs(rust_output, exist_ok=True)
    
    print(f"\n{'='*70}")
    print("RUST VS PYTHON PLUGIN PERFORMANCE BENCHMARK")
    print(f"{'='*70}")
    print(f"Configuration:")
    print(f"  Records:          {args.records:,}")
    print(f"  Batch Size:       {args.batch_size:,}")
    print(f"  Expected Batches: {args.records // args.batch_size:,}")
    print(f"  Python Output:    {python_output}")
    print(f"  Rust Output:      {rust_output}")
    print(f"{'='*70}\n")
    
    python_results = None
    rust_results = None
    
    # Run Python benchmark
    if not args.rust_only:
        print("🐍 Running Python ParquetWriter benchmark...")
        python_results = benchmark_python_writer(
            args.records,
            args.batch_size,
            python_output,
        )
        python_results.print_summary()
    
    # Run Rust benchmark
    if not args.python_only:
        print("🦀 Running Rust ParquetWriter benchmark...")
        rust_results = benchmark_rust_writer_if_available(
            args.records,
            args.batch_size,
            rust_output,
        )
        rust_results.print_summary()
    
    # Compare results
    if python_results and rust_results:
        compare_results(python_results, rust_results)
    
    print(f"\n📁 Output files written to:")
    print(f"   Python: {python_output}")
    print(f"   Rust:   {rust_output}")
    print()


if __name__ == "__main__":
    main()
