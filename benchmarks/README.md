# Rust vs Python Plugin Performance Benchmarks

This directory contains benchmark scripts to compare the performance of Rust and Python plugins in the Dativo Ingest framework.

## Overview

The benchmark script generates synthetic data using the Mimesis library and compares write performance between:
- **Python ParquetWriter** (native Python implementation)
- **Rust ParquetWriter** (sandboxed Rust plugin with container reuse optimization)

## Quick Start

### Prerequisites

```bash
# Install Python dependencies
pip install -e .

# Build Rust plugins (optional, for Rust benchmarks)
cd examples/plugins/rust
make build
cd ../../..

# Ensure Docker is running (for Rust sandboxed plugins)
docker ps
```

### Run Benchmarks

#### Quick Test (10K records)
```bash
python benchmarks/benchmark_rust_vs_python.py --records 10000 --batch-size 1000
```

#### Small Test (1M records)
```bash
python benchmarks/benchmark_rust_vs_python.py --records 1000000 --batch-size 10000
```

#### Medium Test (10M records)
```bash
python benchmarks/benchmark_rust_vs_python.py --records 10000000 --batch-size 10000
```

#### Full Test (100M records)
```bash
python benchmarks/benchmark_rust_vs_python.py --records 100000000 --batch-size 10000
```

**Note**: 100M records will generate significant data (~10-20GB) and may take 10-30 minutes depending on your system.

### Python Only (without Rust plugins)
```bash
python benchmarks/benchmark_rust_vs_python.py --records 1000000 --batch-size 10000 --python-only
```

### Rust Only (if Python baseline already known)
```bash
python benchmarks/benchmark_rust_vs_python.py --records 1000000 --batch-size 10000 --rust-only
```

### Custom Output Directory
```bash
python benchmarks/benchmark_rust_vs_python.py \
    --records 1000000 \
    --batch-size 10000 \
    --output-dir ./benchmark_results
```

## Benchmark Output

### Example Output

```
======================================================================
RUST VS PYTHON PLUGIN PERFORMANCE BENCHMARK
======================================================================
Configuration:
  Records:          1,000,000
  Batch Size:       10,000
  Expected Batches: 100
  Python Output:    /tmp/benchmark_xyz/python
  Rust Output:      /tmp/benchmark_xyz/rust
======================================================================

🐍 Running Python ParquetWriter benchmark...
  Processed 100,000 records (10 batches) in 5.2s (19,231 records/s)
  Processed 200,000 records (20 batches) in 10.5s (19,048 records/s)
  ...

======================================================================
Benchmark: Python ParquetWriter
======================================================================
Total Records:      1,000,000
Batches Processed:  100
Files Written:      100
Duration:           52.34 seconds
Records/Second:     19,106
Total Data Size:    0.85 GB
MB/Second:          16.24
======================================================================

🦀 Running Rust ParquetWriter benchmark...
  Processed 100,000 records (10 batches) in 1.8s (55,556 records/s)
  Processed 200,000 records (20 batches) in 3.5s (57,143 records/s)
  ...

======================================================================
Benchmark: Rust ParquetWriter (Sandboxed)
======================================================================
Total Records:      1,000,000
Batches Processed:  100
Files Written:      100
Duration:           18.45 seconds
Records/Second:     54,200
Total Data Size:    0.85 GB
MB/Second:          46.08
======================================================================

======================================================================
COMPARISON SUMMARY
======================================================================

Metric                         Python               Rust                 Speedup        
-------------------------------------------------------------------------------------
Duration (seconds)             52.34                18.45                2.84x
Records/Second                 19,106               54,200               2.84x
Batches Processed              100                  100                  N/A
Files Written                  100                  100                  N/A
Errors                         0                    0                    N/A
======================================================================

✅ Rust is 2.84x FASTER than Python
   Rust processed 54,200 records/second
   Python processed 19,106 records/second
   Time saved: 33.89 seconds
```

## Expected Performance

Based on our optimization work, we expect:

### Small Datasets (1M records)
- **Python**: ~50-60 seconds (~16-20K records/sec)
- **Rust (sandboxed)**: ~15-20 seconds (~50-65K records/sec)
- **Expected Speedup**: 2.5-4x

### Medium Datasets (10M records)
- **Python**: ~8-10 minutes (~16-20K records/sec)
- **Rust (sandboxed)**: ~3-4 minutes (~40-55K records/sec)
- **Expected Speedup**: 2.5-3x

### Large Datasets (100M records)
- **Python**: ~80-100 minutes (~16-20K records/sec)
- **Rust (sandboxed)**: ~30-40 minutes (~40-55K records/sec)
- **Expected Speedup**: 2.5-3x

**Note**: With container reuse optimization, the overhead is now minimal (<1s for 100 batches), so the speedup is primarily from Rust's faster data processing.

## Benchmark Configuration

### Data Schema

The benchmark generates realistic synthetic data with the following schema:

```python
[
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
```

### Mimesis Configuration

- **Locale**: English (en)
- **Seed**: 42 (for reproducible results)
- **Null Probability**: 0.1 (10% null values)

### Rust Sandbox Configuration

For fair comparison, Rust plugins run in sandboxed mode with:

```python
{
    "enabled": True,
    "reuse_container": True,     # Container reuse optimization
    "max_retries": 3,            # Retry failed requests
    "timeout": 600,              # 10-minute timeout
}
```

## Understanding the Results

### Metrics Explained

- **Duration**: Total time to process all records (seconds)
- **Records/Second**: Throughput (higher is better)
- **Batches Processed**: Number of batches (records / batch_size)
- **Files Written**: Number of Parquet files created
- **Total Data Size**: Size of all output files (GB)
- **MB/Second**: Data write throughput
- **Speedup**: Rust duration / Python duration (higher is better)

### What to Look For

1. **Speedup > 1.0**: Rust is faster (expected with optimization)
2. **Speedup 2-4x**: Good performance improvement
3. **Speedup < 1.0**: Something is wrong (needs investigation)
4. **Similar throughput**: Bottleneck may be elsewhere (I/O, data generation)

### Factors Affecting Performance

- **Batch Size**: Larger batches reduce per-batch overhead
- **Record Complexity**: More fields = more serialization work
- **Disk I/O**: Fast SSD improves write performance
- **CPU**: Rust benefits more from multiple cores
- **Container Overhead**: Minimized with container reuse optimization

## Troubleshooting

### Rust Plugin Not Found

```
⚠️  Rust benchmark had errors:
   Rust plugin not found. Please build it first: cd examples/plugins/rust && make build
```

**Solution**: Build the Rust plugins:
```bash
cd examples/plugins/rust
make build
cd ../../..
```

### Docker Not Available

```
SandboxError: Failed to connect to Docker
```

**Solution**: Start Docker daemon:
```bash
# Linux/Mac
sudo systemctl start docker

# Mac (Docker Desktop)
open -a Docker
```

### Out of Memory

```
MemoryError: Unable to allocate array
```

**Solution**: Reduce batch size or total records:
```bash
python benchmarks/benchmark_rust_vs_python.py --records 1000000 --batch-size 5000
```

### Slow Performance

If both Python and Rust are slow:
- Check disk I/O (use SSD if possible)
- Reduce batch size
- Check CPU usage
- Free up memory

## Advanced Usage

### Custom Schema

Modify the `create_test_schema()` function in the benchmark script to test with your own schema.

### Different Batch Sizes

Test how batch size affects performance:

```bash
# Small batches (more overhead)
python benchmarks/benchmark_rust_vs_python.py --records 100000 --batch-size 1000

# Medium batches (balanced)
python benchmarks/benchmark_rust_vs_python.py --records 100000 --batch-size 10000

# Large batches (less overhead)
python benchmarks/benchmark_rust_vs_python.py --records 100000 --batch-size 50000
```

### Performance Profiling

To profile Python performance:

```bash
python -m cProfile -o python.prof benchmarks/benchmark_rust_vs_python.py \
    --records 100000 --batch-size 10000 --python-only

# Analyze results
python -m pstats python.prof
>>> sort cumulative
>>> stats 20
```

### Memory Profiling

To profile memory usage:

```bash
pip install memory_profiler
python -m memory_profiler benchmarks/benchmark_rust_vs_python.py \
    --records 100000 --batch-size 10000
```

## Interpreting Results for Your Use Case

### When to Use Rust Plugins

Use Rust plugins when:
- ✅ Processing large datasets (>1M records)
- ✅ CPU-intensive operations (parsing, validation)
- ✅ Performance is critical
- ✅ Willing to maintain Rust code

### When Python Is Fine

Use Python plugins when:
- ✅ Small datasets (<100K records)
- ✅ Rapid prototyping
- ✅ Simple transformations
- ✅ Team only knows Python

### Cost-Benefit Analysis

Example: Processing 100M records daily

**Python**:
- Runtime: ~90 minutes/day = 45 hours/month
- Cost: Compute time, infrastructure

**Rust**:
- Runtime: ~30 minutes/day = 15 hours/month
- Cost: Compute time + Rust development/maintenance
- **Savings**: 30 hours/month compute time

If compute costs $1/hour: **Save $30/month** with Rust

## Contributing

To add new benchmarks:

1. Create a new benchmark script in `benchmarks/`
2. Follow the naming convention: `benchmark_<feature>.py`
3. Use the `BenchmarkResults` class for consistent output
4. Document usage in this README

## References

- [Rust Plugin Performance Optimization](../RUST_PLUGIN_PERFORMANCE_OPTIMIZATION.md)
- [Production Readiness Guide](../PRODUCTION_READINESS_GUIDE.md)
- [Mimesis Documentation](https://mimesis.name/)
- [Apache Parquet](https://parquet.apache.org/)
