# Dativo Examples

This directory contains complete, runnable examples for common ingestion scenarios.

## Quick Start

Each example includes:
- Job configuration YAML
- Asset definitions (if needed)
- Connector recipes (if custom)
- Setup instructions in each subdirectory's README

## Available Examples

### Job Examples

- **[CSV to Iceberg](jobs/csv_to_iceberg_with_catalog.yaml)** - Basic CSV ingestion with Iceberg catalog
- **[Custom Plugin Example](jobs/custom_plugin_example.yaml)** - Using custom Python/Rust plugins
- **[Rust Plugin Examples](jobs/rust_plugin_example_*.yaml)** - High-performance Rust plugin examples

### Plugin Examples

- **[Python Plugins](plugins/)** - Custom Python reader/writer examples
- **[Rust Plugins](plugins/rust/)** - High-performance Rust plugin examples

## Running Examples

### Prerequisites

1. Complete [setup](../QUICKSTART.md)
2. Source environment variables: `source .env`
3. Ensure infrastructure is running (MinIO, Nessie)

### Example: CSV to Iceberg

```bash
# 1. Ensure you have a CSV file
echo "id,name,value
1,Alice,100
2,Bob,200" > /tmp/test.csv

# 2. Update job config with your file path
# Edit examples/jobs/csv_to_iceberg_with_catalog.yaml

# 3. Run the job
dativo run --config examples/jobs/csv_to_iceberg_with_catalog.yaml \
  --mode self_hosted \
  --secret-manager filesystem \
  --secrets-dir tests/fixtures/secrets
```

### Example: Custom Plugin

```bash
# 1. Ensure plugin is built/available
# For Python: plugin file must be accessible
# For Rust: build with `cargo build --release`

# 2. Run job with custom plugin
dativo run --config examples/jobs/custom_plugin_example.yaml \
  --mode self_hosted
```

## Creating Your Own Example

1. **Create job config** in `examples/jobs/your_example.yaml`
2. **Add asset definition** (if needed) in `assets/`
3. **Create README** in `examples/your_example/README.md` with:
   - What this example demonstrates
   - Prerequisites
   - Setup steps
   - Expected output
   - Troubleshooting

4. **Test it**:
   ```bash
   dativo check --config examples/jobs/your_example.yaml
   dativo run --config examples/jobs/your_example.yaml --mode self_hosted
   ```

## Full Examples

For complete end-to-end examples with multiple files, see:
- **[docs/examples/jobs/](../docs/examples/jobs/)** - Complete job examples with assets and connectors

## Need Help?

- See [Documentation Index](../docs/INDEX.md)
- Check [Config Reference](../docs/CONFIG_REFERENCE.md)
- Review [Custom Plugins Guide](../docs/CUSTOM_PLUGINS.md)
