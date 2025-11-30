# Job Configuration Examples

This directory contains example job configurations for various ingestion scenarios.

## Available Examples

### Basic Examples

- **csv_to_iceberg_with_catalog.yaml** - Simple CSV file ingestion into Iceberg table with catalog integration

### Plugin Examples

- **custom_plugin_example.yaml** - Example using custom Python plugin
- **rust_plugin_example_full.yaml** - Complete Rust plugin example
- **rust_plugin_example_mixed.yaml** - Mixed Python/Rust plugin example

## Running Examples

### Prerequisites

1. Complete [setup](../../QUICKSTART.md)
2. Source environment: `source .env`
3. Infrastructure running (MinIO, Nessie)

### CSV to Iceberg Example

```bash
# 1. Prepare test data
cat > /tmp/test.csv << EOF
id,name,value
1,Alice,100
2,Bob,200
EOF

# 2. Update job config (edit file path in YAML)
# source:
#   files:
#     - path: /tmp/test.csv

# 3. Run job
dativo run --config examples/jobs/csv_to_iceberg_with_catalog.yaml \
  --mode self_hosted \
  --secret-manager filesystem \
  --secrets-dir ../../tests/fixtures/secrets
```

**Expected output:**
- Parquet files written to MinIO bucket
- Iceberg table created/updated in catalog
- Exit code 0 (success)

### Custom Plugin Example

```bash
# Ensure plugin file exists and is accessible
# For Python: /path/to/plugin.py:ClassName
# For Rust: /path/to/libplugin.so:create_reader

dativo run --config examples/jobs/custom_plugin_example.yaml \
  --mode self_hosted
```

## Configuration Details

Each example demonstrates:
- **Source configuration**: How to configure data source
- **Target configuration**: How to configure S3/MinIO and Iceberg
- **Asset references**: How to reference asset schemas
- **Secret management**: How secrets are used (via secret managers)

## Customizing Examples

1. **Copy an example**:
   ```bash
   cp examples/jobs/csv_to_iceberg_with_catalog.yaml jobs/mytenant/my_job.yaml
   ```

2. **Update paths**:
   - Source file paths
   - Asset paths (if using custom assets)
   - Connector paths (if using custom connectors)

3. **Configure secrets**:
   - Use filesystem secrets: `--secrets-dir secrets`
   - Or use environment variables
   - Or configure Vault/AWS/GCP secret manager

4. **Run**:
   ```bash
   dativo run --config jobs/mytenant/my_job.yaml --mode self_hosted
   ```

## Full Examples

For complete examples with assets, connectors, and secrets, see:
- **[docs/examples/jobs/](../../docs/examples/jobs/)** - Complete examples with all components

## Troubleshooting

**Job not found:**
- Check file path is correct
- Ensure YAML syntax is valid: `dativo check --config <file>`

**Connection errors:**
- Verify secrets are configured
- Check infrastructure is running (MinIO, Nessie)
- Test connection: `dativo check --config <file>`

**Schema validation errors:**
- Verify asset definition exists
- Check schema matches data
- Use `--mode self_hosted` with `schema_validation_mode: warn` for testing

## Next Steps

- [Config Reference](../../docs/CONFIG_REFERENCE.md) - Complete configuration options
- [Custom Plugins](../../docs/CUSTOM_PLUGINS.md) - Building custom plugins
- [Examples Index](../README.md) - All examples
