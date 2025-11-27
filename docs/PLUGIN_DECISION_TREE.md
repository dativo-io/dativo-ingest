# Connector vs Custom Plugin: Decision Tree

This guide helps you decide when to use a built-in connector versus a custom plugin, and what the trade-offs are for each approach.

## Quick Decision Tree

```
Do you need to extract/write data?
│
├─ Is there a built-in connector for your source/target?
│  │
│  ├─ YES → Use built-in connector
│  │   └─ Advantages: Pre-configured, tested, maintained
│  │
│  └─ NO → Continue to next question
│
├─ Is your source/target a standard system (database, API, file format)?
│  │
│  ├─ YES → Consider contributing a connector
│  │   └─ Advantages: Reusable, community benefit
│  │
│  └─ NO → Continue to next question
│
├─ Do you need custom logic or format handling?
│  │
│  ├─ YES → Use custom plugin
│  │   └─ Advantages: Full control, custom transformations
│  │
│  └─ NO → Continue to next question
│
└─ Is performance critical (large datasets, real-time)?
   │
   ├─ YES → Consider Rust plugin
   │   └─ Advantages: 10-100x faster, lower memory
   │
   └─ NO → Python plugin is sufficient
       └─ Advantages: Easier development, faster iteration
```

## Detailed Comparison

### Built-in Connectors

**When to Use:**
- Standard systems (PostgreSQL, MySQL, Stripe, HubSpot, etc.)
- No custom transformations needed
- Standard data formats (CSV, Parquet, etc.)

**Advantages:**
- ✅ Pre-configured and tested
- ✅ Maintained by the Dativo team
- ✅ No code to write or maintain
- ✅ Automatic updates and bug fixes
- ✅ Well-documented
- ✅ Optimized for common use cases

**Disadvantages:**
- ❌ Limited customization
- ❌ May not support all features of the source/target
- ❌ Slower to add new features (requires platform update)

**Examples:**
- PostgreSQL → Iceberg
- Stripe → S3
- CSV → Parquet

### Custom Python Plugins

**When to Use:**
- Proprietary APIs or systems
- Custom file formats
- Complex transformations during extraction
- Rapid prototyping
- Moderate performance requirements

**Advantages:**
- ✅ Full control over extraction/writing logic
- ✅ Easy to develop and iterate
- ✅ Can implement custom business logic
- ✅ Access to Python ecosystem
- ✅ No compilation needed

**Disadvantages:**
- ❌ You maintain the code
- ❌ Slower than Rust for large datasets
- ❌ Requires sandboxing in cloud mode (security)
- ❌ More memory usage than Rust

**Examples:**
- Custom REST API reader
- Proprietary file format writer
- Data transformation during extraction

### Custom Rust Plugins

**When to Use:**
- Very large datasets (millions+ records)
- Performance-critical workloads
- Memory-constrained environments
- High-throughput requirements
- Real-time processing

**Advantages:**
- ✅ 10-100x faster than Python
- ✅ 10-50% less memory usage
- ✅ Type safety and memory safety
- ✅ No sandboxing overhead (native code)
- ✅ Better for streaming large datasets

**Disadvantages:**
- ❌ Longer development time
- ❌ Requires Rust knowledge
- ❌ Compilation step needed
- ❌ More complex debugging
- ❌ Platform-specific builds (.so, .dylib, .dll)

**Examples:**
- High-performance CSV reader (15x faster)
- Large Parquet writer (3.5x faster)
- Streaming data processor

## Migration Paths

### From Custom Plugin to Built-in Connector

If your custom plugin becomes widely used:

1. **Contribute to Dativo:**
   - Submit your plugin as a pull request
   - Follow connector development guidelines
   - Add tests and documentation

2. **Benefits:**
   - No maintenance burden
   - Automatic updates
   - Community support

### From Python Plugin to Rust Plugin

If you need better performance:

1. **Profile First:**
   - Identify bottlenecks
   - Measure current performance
   - Set performance targets

2. **Port to Rust:**
   - Rewrite in Rust using the Rust plugin interface
   - Maintain same API/interface
   - Benchmark improvements

3. **Gradual Migration:**
   - Keep Python version for development
   - Use Rust version in production
   - A/B test performance

## Best Practices

### Choosing a Connector

1. **Check the registry first** (`registry/connectors.yaml`)
2. **Review connector capabilities** (incremental sync, rate limits, etc.)
3. **Test with sample data** before production use
4. **Monitor performance** and adjust as needed

### Developing a Custom Plugin

1. **Start with Python** for rapid development
2. **Profile before optimizing** - measure, don't guess
3. **Consider Rust** only if performance is a bottleneck
4. **Follow plugin interface** - implement required methods
5. **Add error handling** - use standardized error types
6. **Write tests** - unit tests for your plugin
7. **Document usage** - provide examples

### Security Considerations

- **Self-hosted mode:** Plugins run with full system access
- **Cloud mode:** Python plugins are sandboxed (Docker)
- **Rust plugins:** Run natively (trusted code only)
- **Secrets:** Never hardcode credentials in plugins

## Examples

### Example 1: Standard Database → Iceberg

**Use Case:** Extract from PostgreSQL to Iceberg

**Decision:** Built-in connector
- ✅ Standard system (PostgreSQL)
- ✅ Standard target (Iceberg)
- ✅ No custom logic needed

**Configuration:**
```yaml
source_connector: postgres
target_connector: iceberg
```

### Example 2: Proprietary API → S3

**Use Case:** Extract from custom REST API to S3

**Decision:** Custom Python plugin
- ❌ No built-in connector
- ✅ Custom API logic needed
- ✅ Moderate data volume

**Implementation:**
```python
class CustomAPIReader(BaseReader):
    def extract(self, state_manager=None):
        # Custom API logic
        ...
```

### Example 3: Large CSV Processing

**Use Case:** Process 100GB CSV files

**Decision:** Custom Rust plugin
- ✅ Very large dataset
- ✅ Performance critical
- ✅ Memory constraints

**Implementation:**
- Rust plugin for CSV reading
- 15x faster than Python
- Constant memory usage

## Summary

| Factor | Built-in Connector | Python Plugin | Rust Plugin |
|--------|-------------------|---------------|-------------|
| **Development Time** | None | Fast | Slow |
| **Performance** | Good | Moderate | Excellent |
| **Maintenance** | None (you) | You | You |
| **Customization** | Limited | Full | Full |
| **Security** | High | Sandboxed (cloud) | Native |
| **Best For** | Standard systems | Custom logic | Performance |

**Recommendation:** Start with built-in connectors, use Python plugins for custom needs, and upgrade to Rust only when performance is a proven bottleneck.
