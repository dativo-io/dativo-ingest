# Connector vs Custom Plugin: Decision Tree Guide

This guide helps you decide when to use a standard connector versus a custom plugin in the Dativo platform.

## Quick Decision Tree

```
Do you need to extract data from a source?
│
├─ YES → Is there a standard connector for your source?
│         (stripe, hubspot, postgres, mysql, csv, etc.)
│         │
│         ├─ YES → Does the standard connector meet your needs?
│         │         │
│         │         ├─ YES → ✅ Use standard connector
│         │         │         - Fastest setup
│         │         │         - Fully tested
│         │         │         - Auto-maintained
│         │         │
│         │         └─ NO → What's missing?
│         │                 │
│         │                 ├─ Custom transformation logic → Use custom plugin
│         │                 ├─ Proprietary data format → Use custom plugin
│         │                 ├─ Special authentication → Use custom plugin
│         │                 └─ Performance requirements → Consider Rust plugin
│         │
│         └─ NO → Need high performance (>1M records)?
│                 │
│                 ├─ YES → ✅ Use Rust custom plugin
│                 │         - 10-100x faster
│                 │         - Lower memory usage
│                 │         - Best for large datasets
│                 │
│                 └─ NO → ✅ Use Python custom plugin
│                           - Easy to develop
│                           - Quick iteration
│                           - Full ecosystem access
│
└─ NO → You need to write data to a target
          │
          └─ Is Parquet + Iceberg sufficient?
              │
              ├─ YES → ✅ Use standard Parquet writer
              │         - Native Iceberg support
              │         - Automatic partitioning
              │         - S3/MinIO integration
              │
              └─ NO → ✅ Use custom writer plugin
                        - Custom format (JSON, Avro, etc.)
                        - Custom destination (database, API)
                        - Special requirements
```

## Detailed Comparison

### Standard Connectors

**✅ Use When:**
- Extracting from well-known SaaS APIs (Stripe, HubSpot, etc.)
- Reading from standard databases (PostgreSQL, MySQL)
- Processing common file formats (CSV, Parquet)
- You need the fastest time to value
- You want automatic updates and maintenance

**Pros:**
- Zero code required
- Declarative YAML configuration
- Pre-built, tested, and optimized
- Automatic schema mapping
- Built-in error handling
- Connector registry validation
- Community support

**Cons:**
- Limited customization
- Fixed extraction logic
- Must fit connector's data model
- May extract unnecessary data

**Example Use Cases:**
- Extract Stripe customers → Standard `stripe` connector
- Load PostgreSQL tables → Standard `postgres` connector
- Process CSV files → Standard `csv` connector

### Python Custom Plugins

**✅ Use When:**
- No standard connector exists for your source
- You need custom transformation logic
- Working with proprietary APIs or formats
- Medium-sized datasets (< 1M records)
- Rapid prototyping and iteration
- Complex business logic required

**Pros:**
- Full control over extraction logic
- Easy to develop and test
- Access to entire Python ecosystem
- Can handle complex transformations
- Quick iteration cycle
- Good for prototyping

**Cons:**
- Requires Python development
- Slower than native/Rust plugins
- Higher memory usage
- You maintain the code
- Must implement error handling

**Example Use Cases:**
- Extract from internal REST API
- Parse proprietary file format
- Custom data transformation pipeline
- Integration with legacy system

### Rust Custom Plugins

**✅ Use When:**
- Processing large datasets (> 1M records)
- Performance is critical
- Memory efficiency matters
- Format-aware processing needed (CSV, Parquet, JSON)
- Long-running batch jobs
- Production-scale workloads

**Pros:**
- **10-100x faster** than Python
- **10-20x lower memory** usage
- Constant memory with streaming
- Better compression ratios
- Concurrent processing
- Memory safety guarantees

**Cons:**
- Requires Rust development
- Longer development time
- More complex debugging
- Steeper learning curve
- Build process required

**Example Use Cases:**
- Process 100M+ row CSV files
- High-frequency data extraction
- Real-time streaming pipelines
- Memory-constrained environments

## Performance Comparison

| Plugin Type | Records/sec | Memory (1M rows) | Development Time | Complexity |
|-------------|-------------|------------------|------------------|------------|
| Standard Connector | 1,000-10,000 | Low | Minutes | ⭐ Easy |
| Python Plugin | 500-5,000 | Medium-High | Hours | ⭐⭐ Medium |
| Rust Plugin | 50,000-500,000 | Very Low | Days | ⭐⭐⭐ Hard |

## Real-World Scenarios

### Scenario 1: Extract Stripe Customers
**Best Choice:** Standard `stripe` connector

**Why:**
- Pre-built connector exists
- Handles pagination automatically
- Supports incremental sync
- Zero development time

**Configuration:**
```yaml
source:
  type: stripe
  objects: [customers]
  incremental:
    lookback_days: 1
```

---

### Scenario 2: Extract from Internal API
**Best Choice:** Python custom plugin

**Why:**
- No standard connector
- API has custom authentication
- Need to transform response format
- Medium data volume

**Example:**
```python
class InternalAPIReader(BaseReader):
    __version__ = "1.0.0"
    
    def check_connection(self):
        try:
            self.client.ping()
            return ConnectionTestResult(True, "Connected")
        except Exception as e:
            return ConnectionTestResult(False, str(e), "CONNECTION_FAILED")
    
    def extract(self, state_manager=None):
        for page in self.client.fetch_paginated():
            yield self.transform_records(page)
```

---

### Scenario 3: Process 100GB CSV Files
**Best Choice:** Rust custom plugin

**Why:**
- Massive dataset (billions of rows)
- Memory constraints
- Needs streaming processing
- Production workload

**Performance:**
- Python: 50 MB/s, 2 GB RAM
- **Rust: 750 MB/s, 150 MB RAM** ⚡

---

### Scenario 4: Write to Custom Database
**Best Choice:** Python custom writer

**Why:**
- Need to write to non-standard target
- Custom connection pooling
- Business logic in writes
- Medium throughput

**Example:**
```python
class CustomDBWriter(BaseWriter):
    __version__ = "1.0.0"
    
    def check_connection(self):
        try:
            self.db.test_connection()
            return ConnectionTestResult(True, "Database accessible")
        except Exception as e:
            return ConnectionTestResult(False, str(e), "DB_ERROR")
    
    def write_batch(self, records, file_counter):
        with self.db.transaction():
            self.db.bulk_insert(records)
        return [{"path": f"batch_{file_counter}", "size_bytes": len(records)}]
```

## Migration Path

### Starting Simple → Adding Custom Logic

1. **Phase 1:** Start with standard connector
   - Get data flowing quickly
   - Validate data quality
   - Understand requirements

2. **Phase 2:** Add Python plugin if needed
   - Implement custom transformations
   - Handle edge cases
   - Add business logic

3. **Phase 3:** Optimize with Rust if needed
   - Profile performance bottlenecks
   - Rewrite hot paths in Rust
   - Keep simple logic in Python

## Feature Matrix

| Feature | Standard Connector | Python Plugin | Rust Plugin |
|---------|-------------------|---------------|-------------|
| Connection Testing | ✅ Built-in | ✅ Implement `check_connection()` | ✅ Implement trait |
| Discovery | ✅ Built-in | ✅ Implement `discover()` | ✅ Implement trait |
| Schema Validation | ✅ Automatic | ✅ Automatic | ✅ Automatic |
| Incremental Sync | ✅ Built-in | ✅ Use `state_manager` | ✅ Use state API |
| Error Handling | ✅ Standardized | ⚠️ Your responsibility | ⚠️ Your responsibility |
| Retries | ✅ Automatic | ⚠️ Implement yourself | ⚠️ Implement yourself |
| Monitoring | ✅ Full metrics | ⚠️ Partial metrics | ⚠️ Partial metrics |
| Versioning | ✅ Managed | ⚠️ Set `__version__` | ⚠️ Set version |

## Best Practices

### For Standard Connectors
✅ **DO:**
- Use for all supported sources
- Leverage built-in features
- Report bugs/requests to maintainers
- Follow connector documentation

❌ **DON'T:**
- Fork and modify connector code
- Try to work around limitations
- Ignore connector warnings

### For Python Plugins
✅ **DO:**
- Implement `check_connection()` for testing
- Implement `discover()` if applicable
- Set `__version__` attribute
- Use standard error codes
- Log important events
- Handle errors gracefully
- Document your plugin

❌ **DON'T:**
- Load entire dataset into memory
- Ignore connection errors
- Skip input validation
- Hardcode credentials

### For Rust Plugins
✅ **DO:**
- Use streaming for large data
- Implement proper error types
- Use connection pooling
- Profile before optimizing
- Write comprehensive tests
- Document FFI boundaries

❌ **DON'T:**
- Optimize prematurely
- Use unsafe unnecessarily
- Skip error handling
- Block on I/O operations

## Getting Help

### Connector Issues
- Check connector documentation
- Review connector registry
- File issue in GitHub repo
- Ask in community Slack

### Plugin Development
- Read [CUSTOM_PLUGINS.md](CUSTOM_PLUGINS.md)
- Check example plugins
- Review plugin interface docs
- Test with small datasets first

## Summary

**Use Standard Connectors** for:
- Common sources (Stripe, HubSpot, databases)
- Fast time to value
- Zero maintenance

**Use Python Plugins** for:
- Custom sources/targets
- Medium data volumes
- Rapid development
- Complex logic

**Use Rust Plugins** for:
- Large datasets (>1M records)
- Performance-critical paths
- Memory constraints
- Production scale

**Decision Rule of Thumb:**
1. Can standard connector work? → Use it
2. Need custom logic? → Python plugin
3. Need extreme performance? → Rust plugin

The platform is designed to let you start simple and optimize later. Begin with standard connectors or Python plugins, then migrate to Rust only when performance becomes critical.
