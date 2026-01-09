# Performance & Scaling

This document covers performance characteristics, benchmarks, and scaling strategies for Dativo Ingestion Platform.

## Current Performance Characteristics

### Rust Plugin Performance

When using custom Rust plugins:

- **Parquet Writing**: ~3x faster than PyArrow with better compression (see [benchmarks/BENCHMARK_RESULTS.md](../benchmarks/BENCHMARK_RESULTS.md) for actual results)
- **Throughput**: Can process 25,000-55,000 records/second with optimized Rust plugins (based on benchmark results)
- **Memory Efficiency**: Constant memory usage with streaming for large datasets
- **Performance varies** by dataset size, batch size, and workload - see benchmarks for details

### Python Plugin Performance

- Suitable for moderate workloads (1,000-10,000 records/second)
- Easier to develop and iterate
- Good for custom business logic and rapid prototyping

### Built-in Connectors

- Optimized for common use cases (Stripe, HubSpot, PostgreSQL, etc.)
- Handle rate limiting, pagination, and incremental sync automatically
- Performance varies by connector type and data volume

## Performance Benchmarks

### Actual Benchmark Results (1M records)

- **Python ParquetWriter**: 52.89s, 18,908 records/second
- **Rust ParquetWriter**: 18.00s, 55,556 records/second
- **Speedup**: ~2.94x faster with Rust

> **Note**: Performance results vary by dataset size, batch size, and system configuration. The examples above show actual benchmark results from [benchmarks/BENCHMARK_RESULTS.md](../benchmarks/BENCHMARK_RESULTS.md).

For detailed performance comparisons and benchmarks, see:
- [Benchmark Results](../benchmarks/BENCHMARK_RESULTS.md) - Actual performance metrics
- [Custom Plugins Guide](CUSTOM_PLUGINS.md) - Plugin development and performance details
- [Benchmark README](../benchmarks/README.md) - How to run benchmarks

## Scaling Architecture

### Current Capabilities

- ✅ **Multiple Parallel Jobs**: Run multiple independent jobs concurrently via Dagster orchestration
- ✅ **Per-Tenant Isolation**: Each tenant's jobs run independently with isolated state and secrets
- ✅ **Spark Engine Support**: Use Apache Spark for large-scale processing (`target.engine.type: spark`)
- ✅ **Batch Processing**: Efficient batch-based extraction and writing (configurable batch sizes)
- ✅ **Incremental Sync**: Only process new/changed data, reducing processing time

### Current Limitations (Transparent Disclosure)

- ⚠️ **Single-Threaded Per Job**: Each job runs in a single process (no intra-job parallelism)
- ⚠️ **No Horizontal Scaling**: Jobs run on a single node (no distributed execution yet)
- ⚠️ **Serial Tenant Execution**: Jobs within a tenant execute serially to prevent catalog conflicts

## Scaling Strategies Today

### 1. Use Rust Plugins

For high-throughput workloads, use Rust plugins for significant performance improvements. See [benchmarks](../benchmarks/BENCHMARK_RESULTS.md) for actual metrics.

**When to Use Rust Plugins:**
- Processing large datasets (> 1M records)
- Performance-critical workloads
- Memory-constrained environments
- High-frequency data extraction
- Production-scale workloads requiring maximum throughput

See [Custom Plugins](CUSTOM_PLUGINS.md) for Rust plugin development guide.

### 2. Parallel Job Execution

Run multiple independent jobs concurrently via Dagster orchestration. Each job runs independently, allowing true parallelism across different assets/tenants.

**Configuration Example:**
```yaml
# runner.yaml
schedules:
  - name: hourly_stripe
    cron: "0 * * * *"
    jobs:
      - jobs/tenant_a/stripe_customers.yaml
      - jobs/tenant_b/stripe_charges.yaml
  # These jobs run in parallel if they're for different tenants
```

See [Runner and Orchestration](RUNNER_AND_ORCHESTRATION.md) for orchestration details.

### 3. Spark Engine

For very large datasets, use Apache Spark for distributed processing:

```yaml
target:
  engine:
    type: spark
    options:
      # Spark-specific options
```

See [SPARK_SETUP.md](SPARK_SETUP.md) for Spark configuration details.

### 4. Optimize Batch Sizes

Tune `batch_size` and `row_group_size` for your workload:

```yaml
target:
  batch_size: 50000  # Larger batches for high-throughput
  row_group_size: 128000000  # ~128MB row groups
```

**Guidelines:**
- **Small datasets (< 1M records)**: Default batch sizes (10k-50k) work well
- **Large datasets (> 10M records)**: Increase batch sizes (50k-100k) for better throughput
- **Memory-constrained**: Reduce batch sizes to limit memory usage
- **High-throughput**: Increase batch sizes for better CPU utilization

### 5. Incremental Sync

Use incremental sync to minimize data processing:

```yaml
source:
  incremental:
    lookback_days: 1  # Only sync last 24 hours
    cursor_field: updated_at
```

**Benefits:**
- Reduces processing time by only syncing changed data
- Lowers API quota usage
- Improves job reliability (smaller batches fail less often)

See [Configuration Reference](CONFIG_REFERENCE.md) for incremental sync configuration.

## Performance Optimization Tips

### 1. Connection Pooling

For database connectors, ensure proper connection pooling:

```yaml
source:
  connection:
    pool_size: 10  # Adjust based on database limits
    max_overflow: 20
```

### 2. Streaming Processing

Dativo uses streaming processing by default, but ensure you're not loading entire datasets into memory:

- Use batch-based extraction (default)
- Configure appropriate batch sizes
- Use Rust plugins for constant memory usage

### 3. Network Optimization

- Use regional endpoints for cloud services
- Enable compression where available
- Batch API calls when possible

### 4. Storage Optimization

- Use appropriate Parquet compression (zstd, snappy)
- Configure row group sizes for your query patterns
- Use partitioning to improve query performance

```yaml
target:
  partitioning: [ingest_date, tenant_id]  # Partition by common query patterns
  compression: zstd  # Better compression than snappy
```

## Roadmap: Future Scaling Features

Planned for **v2.0.0** (Q2 2025):

- 🔜 **Parallel Job Execution Within Tenants**: Run multiple jobs per tenant concurrently
- 🔜 **Horizontal Scaling**: Distributed execution across multiple nodes
- 🔜 **Connection Pooling**: Optimized database connection management
- 🔜 **Caching**: Frequently accessed data caching for improved performance
- 🔜 **Optimized Parquet Writing**: Columnar compression improvements

See [Roadmap](roadmap.md) for complete details on planned scaling features.

## Monitoring Performance

### Metrics

Dativo exposes performance metrics via Prometheus and OpenTelemetry:

- Job execution time
- Records processed per second
- Memory usage
- Batch processing times
- Error rates

See [Observability Metrics](OBSERVABILITY_METRICS.md) for complete metrics documentation.

### Logging

Performance information is logged during job execution:

- Batch processing times
- Throughput metrics
- Memory usage
- Processing statistics

Enable verbose logging for detailed performance information:

```bash
dativo ingest --config job.yaml --verbose
```

## Benchmarking Your Workload

### Run Built-in Benchmarks

```bash
# CSV reading benchmarks
python scripts/benchmark_csv_reading.py

# Parquet writing benchmarks
python scripts/benchmark_writers.py
```

### Custom Benchmarking

1. Create test dataset matching your schema
2. Run jobs with different batch sizes
3. Compare Python vs Rust plugins
4. Measure throughput, memory usage, and latency

See [benchmarks/README.md](../benchmarks/README.md) for benchmark suite details.

## Summary

**For Best Performance:**
1. Use Rust plugins for high-throughput workloads
2. Configure appropriate batch sizes for your data volume
3. Use incremental sync to minimize processing
4. Enable parallel job execution via Dagster
5. Use Spark engine for very large datasets
6. Monitor metrics to identify bottlenecks

**Performance Expectations:**
- **Rust plugins**: 25k-55k records/second
- **Python plugins**: 1k-10k records/second
- **Built-in connectors**: Varies by connector type

**Scaling Limits:**
- Current: Single node, parallel jobs across tenants
- Future: Horizontal scaling, intra-tenant parallelism (v2.0.0)

For more details, see:
- [Custom Plugins](CUSTOM_PLUGINS.md) - Plugin development and optimization
- [Benchmark Results](../benchmarks/BENCHMARK_RESULTS.md) - Actual performance metrics
- [Runner and Orchestration](RUNNER_AND_ORCHESTRATION.md) - Orchestration configuration

