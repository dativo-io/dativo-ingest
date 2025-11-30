# Dativo Examples

This directory contains complete, runnable examples for common use cases.

## Complete Examples

### 1. [Stripe to S3/Iceberg](stripe_to_s3_iceberg/)

Ingest Stripe customer data into S3 as Iceberg-backed Parquet tables.

**What you'll learn:**
- SaaS API ingestion (Stripe)
- Incremental sync with lookback
- S3/MinIO target configuration
- Iceberg catalog integration

**Run this:**
```bash
cd stripe_to_s3_iceberg
cat README.md
```

### 2. [PostgreSQL Incremental Sync](postgres_incremental_sync/)

Incremental sync of PostgreSQL tables with cursor-based state tracking.

**What you'll learn:**
- Database ingestion (PostgreSQL)
- Cursor-based incremental sync
- State management
- Handling late-arriving updates

**Run this:**
```bash
cd postgres_incremental_sync
cat README.md
```

## Quick Examples (Job Configs Only)

These are standalone job configurations demonstrating specific features:

### [csv_to_iceberg_with_catalog.yaml](jobs/csv_to_iceberg_with_catalog.yaml)

Simple CSV ingestion with Iceberg catalog.

**Features:**
- CSV file reader
- Schema validation
- Parquet writer
- Iceberg catalog commit

**Run this:**
```bash
dativo run --config examples/jobs/csv_to_iceberg_with_catalog.yaml --mode self_hosted
```

### [custom_plugin_example.yaml](jobs/custom_plugin_example.yaml)

Python custom plugin example (JSON API to JSON files).

**Features:**
- Custom Python reader (JSON API)
- Custom Python writer (JSON files)
- Plugin configuration

**Run this:**
```bash
dativo run --config examples/jobs/custom_plugin_example.yaml --mode self_hosted
```

### [rust_plugin_example_full.yaml](jobs/rust_plugin_example_full.yaml)

Full Rust plugin pipeline (CSV to Parquet with Rust plugins).

**Features:**
- Custom Rust reader (CSV)
- Custom Rust writer (Parquet)
- 10-50x performance improvement

**Run this:**
```bash
# Build Rust plugins first
cd plugins/rust && make build-release

# Run job
dativo run --config examples/jobs/rust_plugin_example_full.yaml --mode self_hosted
```

### [rust_plugin_example_mixed.yaml](jobs/rust_plugin_example_mixed.yaml)

Mixed Python/Rust pipeline (built-in reader + Rust writer).

**Features:**
- Built-in CSV reader
- Custom Rust Parquet writer
- Best of both worlds

## Custom Plugins

See [plugins/](plugins/) directory for custom plugin examples:

- **[Python Plugins](plugins/)** - JSON API reader, JSON file writer
  - Easy to develop
  - Good for API integrations
  - Flexible and quick to prototype

- **[Rust Plugins](plugins/rust/)** - High-performance CSV reader, Parquet writer
  - 10-100x performance gains
  - Constant memory usage
  - Ideal for large files

## Choosing an Example

| I want to...                          | Use this example                          |
|---------------------------------------|-------------------------------------------|
| Ingest from a SaaS API                | [Stripe to S3/Iceberg](stripe_to_s3_iceberg/) |
| Sync database tables incrementally    | [PostgreSQL Incremental](postgres_incremental_sync/) |
| Process CSV files                     | [csv_to_iceberg_with_catalog.yaml](jobs/csv_to_iceberg_with_catalog.yaml) |
| Build a custom Python plugin          | [custom_plugin_example.yaml](jobs/custom_plugin_example.yaml) + [plugins/](plugins/) |
| Get maximum performance with Rust     | [rust_plugin_example_full.yaml](jobs/rust_plugin_example_full.yaml) + [plugins/rust/](plugins/rust/) |

## Running Examples

### Prerequisites

1. **Local setup** - Run the setup script:
   ```bash
   ./scripts/setup-dev.sh
   source .env
   ```

2. **Set up secrets** - Create secrets for your connectors:
   ```bash
   mkdir -p secrets/acme
   echo '{"api_key": "your_key"}' > secrets/acme/stripe.json
   ```

3. **Configure environment** - Set S3/MinIO credentials:
   ```bash
   export AWS_ACCESS_KEY_ID="your_access_key"
   export AWS_SECRET_ACCESS_KEY="your_secret_key"
   export S3_BUCKET="your-bucket-name"
   ```

### Run a Complete Example

```bash
cd examples/stripe_to_s3_iceberg
cat README.md  # Read the detailed guide

dativo run --config job.yaml \
  --secret-manager filesystem \
  --secrets-dir ../../secrets \
  --mode self_hosted
```

### Run a Quick Example

```bash
dativo run --config examples/jobs/csv_to_iceberg_with_catalog.yaml --mode self_hosted
```

## Modifying Examples

All examples are fully editable and can serve as templates for your own jobs:

1. **Copy an example:**
   ```bash
   cp -r examples/stripe_to_s3_iceberg jobs/mycompany/my_stripe_job/
   ```

2. **Update configurations:**
   - Change `tenant_id` to your organization
   - Update connector paths
   - Modify asset schemas to match your data

3. **Run your job:**
   ```bash
   dativo run --config jobs/mycompany/my_stripe_job/job.yaml --mode self_hosted
   ```

## Creating New Examples

To contribute a new example:

1. **Create a directory:**
   ```bash
   mkdir examples/my_new_example
   ```

2. **Add files:**
   - `README.md` - Detailed guide (see existing examples)
   - `job.yaml` - Job configuration
   - `connector_*.yaml` - Connector definitions
   - `asset_*.yaml` - Asset schemas

3. **Document thoroughly:**
   - Prerequisites
   - Quick start
   - Expected output
   - Troubleshooting

4. **Update this README** with your example

5. **Submit a PR**

## Support

- [Documentation Index](../docs/INDEX.md)
- [Configuration Reference](../docs/CONFIG_REFERENCE.md)
- [Custom Plugins Guide](../docs/CUSTOM_PLUGINS.md)
- [GitHub Issues](https://github.com/dativo-io/dativo-ingest/issues)

## Next Steps

After running examples, check out:

1. **[QUICKSTART.md](../QUICKSTART.md)** - Quick reference guide
2. **[CONFIG_REFERENCE.md](../docs/CONFIG_REFERENCE.md)** - Complete config documentation
3. **[CUSTOM_PLUGINS.md](../docs/CUSTOM_PLUGINS.md)** - Build your own plugins
4. **[SETUP_AND_TESTING.md](../docs/SETUP_AND_TESTING.md)** - Production deployment guide
