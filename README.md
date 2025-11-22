# Dativo Ingestion Platform

A headless, config-driven ingestion engine. Extracts data from SaaS APIs (Stripe, HubSpot) and databases (PostgreSQL, MySQL) into object storage (S3, MinIO) as Iceberg-backed datasets. Supports Markdown-KV format for LLM-optimized data ingestion.

## Architecture

Config-driven ingestion engine. All behavior is controlled by YAML configs validated against a connector registry and asset schemas.

**Key Components:**
- **CLI Runner** - Executes `run` (oneshot) and `start` (orchestrated) commands
- **Dagster Orchestrator** - Optional scheduler for scheduled jobs
- **Connector Registry** - Validates connector types, engines, and modes
- **Asset Schemas** - ODCS v3.0.2 compliant schema definitions
- **Custom Plugins** - Python and Rust plugins for custom readers/writers
- **Parquet Writer** - Writes validated data with partitioning and file sizing
- **Iceberg Committer** - Optional catalog integration (files always written to S3)

## Quick Start

### Prerequisites

- Python 3.10+
- Docker and Docker Compose (for local infrastructure)
- Node.js 18+ (optional, for schema validation)

### Setup and Run

```bash
# 1. Run automated setup
./scripts/setup-dev.sh

# 2. Source environment variables
source .env

# 3. Run end-to-end test (filesystem secret manager)
dativo run --job-dir tests/fixtures/jobs \
  --secret-manager filesystem \
  --secrets-dir tests/fixtures/secrets \
  --mode self_hosted
```

**For detailed instructions, see:**
- [QUICKSTART.md](QUICKSTART.md) - Quick reference guide
- [docs/SETUP_AND_TESTING.md](docs/SETUP_AND_TESTING.md) - Comprehensive setup guide

### Docker Deployment

1. Build the image:
```bash
docker build -t dativo:1.1.0 .
```

2. Run a single job (oneshot mode):
```bash
docker run --rm \
  -v $(pwd)/connectors:/app/connectors:ro \
  -v $(pwd)/assets:/app/assets:ro \
  -v $(pwd)/jobs:/app/jobs \
  -v $(pwd)/configs:/app/configs \
  -v $(pwd)/secrets:/app/secrets \
  -v $(pwd)/state:/app/state \
  dativo:1.1.0 run --config /app/jobs/acme/stripe_customers_to_iceberg.yaml --mode self_hosted
```

3. Start orchestrated mode:
```bash
docker run --rm -p 3000:3000 \
  -v $(pwd)/connectors:/app/connectors:ro \
  -v $(pwd)/assets:/app/assets:ro \
  -v $(pwd)/jobs:/app/jobs \
  -v $(pwd)/configs:/app/configs \
  -v $(pwd)/secrets:/app/secrets \
  -v $(pwd)/state:/app/state \
  dativo:1.1.0 start orchestrated --runner-config /app/configs/runner.yaml
```

> Omit the `/app/secrets` volume and `--secrets-dir` flag when using non-filesystem secret managers.

## CLI Usage

### Run a Single Job

```bash
dativo run --config <path> --mode <self_hosted|cloud>
```

**Options:**
- `--config`: Path to job configuration YAML file (required)
- `--mode`: Execution mode - `self_hosted` (default) or `cloud`
- `--job-dir`: Run all jobs in a directory (requires secrets via a selected manager)
- `--secret-manager`: Secret backend (`env`, `filesystem`, `vault`, `aws`, `gcp`). Defaults to environment variables or `DATIVO_SECRET_MANAGER`.
- `--secret-manager-config`: Path to YAML/JSON (or inline JSON string) with manager-specific settings. Defaults to `DATIVO_SECRET_MANAGER_CONFIG`.
- `--secrets-dir`: Path to secrets directory (used only when `--secret-manager filesystem`)

**Examples:**
```bash
# Single job
dativo run --config jobs/acme/stripe_customers.yaml --mode self_hosted

# Multiple jobs from directory (filesystem secrets)
dativo run --job-dir jobs/acme \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted
```

> Detailed configuration examples for every secret backend live in [docs/SECRET_MANAGEMENT.md](docs/SECRET_MANAGEMENT.md).

### Start Orchestrated Mode

```bash
dativo start orchestrated --runner-config <path>
```

Starts Dagster orchestrator with scheduled jobs. Default config: `/app/configs/runner.yaml`

## Execution Flow

1. **Extract** - Read data from source (API, database, files)
2. **Validate** - Validate records against asset schema (strict or warn mode)
3. **Write** - Write to Parquet files (target: 128-200 MB, supports partitioning)
4. **Commit** - Optional: Commit to Iceberg catalog (files always written to S3)
5. **Update State** - Track incremental sync state

**Catalog Note**: Iceberg catalog is optional. Without catalog, Parquet files are written directly to S3/MinIO. See [docs/CATALOG_LIMITATIONS.md](docs/CATALOG_LIMITATIONS.md).

## Configuration

**Job Config** - Defines source, target, asset, and tenant overrides:

**Path Conventions:**
- **Local Development**: Use relative paths (e.g., `connectors/stripe.yaml`)
- **Docker**: Use absolute paths (e.g., `/app/connectors/stripe.yaml`)
- **Assets**: Always use versioned paths (e.g., `assets/stripe/v1.0/customers.yaml`)

```yaml
tenant_id: acme
source_connector: stripe
source_connector_path: connectors/stripe.yaml  # Local: relative, Docker: /app/connectors/stripe.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: stripe_customers
asset_path: assets/stripe/v1.0/customers.yaml  # Always versioned
source:
  objects: [customers]
  incremental:
    lookback_days: 1
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
      prefix: "raw/stripe/customers"
```

**Asset Definition** - ODCS v3.0.2 schema with governance:
```yaml
$schema: schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: stripe_customers
version: "1.0"
source_type: stripe
object: customers
schema:
  - name: id
    type: string
    required: true
target:
  file_format: parquet
  partitioning: [ingest_date]
```

**Quick Templates:**
```bash
# Generate job template
./scripts/generate-job-template.sh mytenant my_job csv iceberg

# Generate asset template
./scripts/generate-asset-template.sh csv my_asset your-email@company.com
```

See [docs/CONFIG_REFERENCE.md](docs/CONFIG_REFERENCE.md) for complete reference.  
See [docs/MINIMAL_ASSET_EXAMPLE.md](docs/MINIMAL_ASSET_EXAMPLE.md) for minimal asset example.


## Supported Connectors

**Sources:**
- **Stripe** - Payments API (customers, charges, invoices)
- **HubSpot** - CRM API (contacts, deals, companies)
- **Google Drive CSV** - CSV files from Google Drive
- **Google Sheets** - Spreadsheet data
- **CSV** - Local CSV files
- **Markdown-KV** - Markdown-KV files for LLM-optimized ingestion
- **PostgreSQL** - Database (self-hosted only)
- **MySQL** - Database (self-hosted only)

**Targets:**
- **Iceberg** - Apache Iceberg tables (Parquet format)
- **S3** - Amazon S3 object storage
- **MinIO** - MinIO object storage

## Custom Plugins

Dativo supports custom readers and writers in **Python and Rust**, allowing you to:
- Read from any source format or system (e.g., proprietary APIs, custom file formats)
- Write to any target format or system (e.g., Delta Lake, custom databases)
- Implement format-aware, high-performance data processing
- Achieve **10-100x performance gains** with Rust plugins

### Quick Examples

**Python Plugin (Easy to develop):**

```python
# my_reader.py
from dativo_ingest.plugins import BaseReader

class MyCustomReader(BaseReader):
    def extract(self, state_manager=None):
        connection = self.source_config.connection
        # Your extraction logic
        yield batch_of_records
```

```yaml
source:
  custom_reader: "/app/plugins/my_reader.py:MyCustomReader"
  connection:
    endpoint: "https://api.example.com"
```

**Rust Plugin (Maximum performance):**

```bash
# Build Rust plugin
cd examples/plugins/rust
make build-release
```

```yaml
source:
  # Rust plugin - 10-50x faster for large CSV files
  custom_reader: "/app/plugins/rust/target/release/libcsv_reader_plugin.so:create_reader"
  files:
    - path: "/data/large_file.csv"
  engine:
    options:
      batch_size: 50000  # Larger batches with Rust
```

### Performance Benefits

**Rust plugins provide dramatic improvements:**
- **CSV Reading:** 15x faster, 12x less memory
- **Parquet Writing:** 3.5x faster, 27% better compression
- **Large Datasets:** Constant memory usage with streaming

### Documentation

- [Custom Plugins Guide](docs/CUSTOM_PLUGINS.md) - Comprehensive guide for Python and Rust
- [Python Examples](examples/plugins/) - JSON API reader, JSON file writer, etc.
- [Rust Examples](examples/plugins/rust/) - High-performance CSV reader, Parquet writer

### Markdown-KV Storage Options

Dativo supports three storage patterns for Markdown-KV format:
1. **STRING storage**: Store as STRING column in Iceberg Parquet tables
2. **Raw file storage**: Store files directly in S3/MinIO buckets
3. **Structured storage**: Parse and store as structured data (row-per-KV, document-level, or hybrid)

See [docs/MARKDOWN_KV_STORAGE.md](docs/MARKDOWN_KV_STORAGE.md) for detailed documentation.

## Exit Codes

- `0`: Success - All jobs completed successfully
- `1`: Partial success - Some jobs succeeded, some failed
- `2`: Failure - Configuration errors, missing files, or startup failures. Note: Jobs may complete with validation warnings but still return exit code 2.

## Testing

### Run Tests

```bash
# All tests (unit + integration + smoke)
make test

# Individual test suites
make test-unit          # Unit tests
make test-integration   # Integration tests
make test-smoke         # End-to-end smoke tests

# Schema validation
make schema-validate
```

See [tests/README.md](tests/README.md) for detailed testing documentation.

## Project Structure

```
connectors/          # Connector recipes (tenant-agnostic)
assets/              # Asset schemas (ODCS v3.0.2)
  {source}/v{version}/
jobs/                # Job configs (tenant-specific)
  {tenant_id}/
configs/             # Runner and policy configs
registry/            # Connector capabilities registry
secrets/             # (Optional) filesystem secrets (tenant-organized)
state/               # Incremental sync state
src/dativo_ingest/   # Source code
```

## Documentation

**Quick Start:** [QUICKSTART.md](QUICKSTART.md)  
**Setup Guide:** [docs/SETUP_AND_ONBOARDING.md](docs/SETUP_AND_ONBOARDING.md)  
**Config Reference:** [docs/CONFIG_REFERENCE.md](docs/CONFIG_REFERENCE.md)  
**Custom Plugins:** [docs/CUSTOM_PLUGINS.md](docs/CUSTOM_PLUGINS.md)  
**Secrets Reference:** [docs/SECRET_MANAGEMENT.md](docs/SECRET_MANAGEMENT.md)  
**Testing:** [tests/README.md](tests/README.md)


