# Dativo Ingestion Platform

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CI Status](https://github.com/dativo-io/dativo-ingest/workflows/CI/badge.svg)](https://github.com/dativo-io/dativo-ingest/actions)

A headless, config-driven ingestion engine. Extracts data from SaaS APIs (Stripe, HubSpot) and databases (PostgreSQL, MySQL) into object storage (S3, MinIO) as Iceberg-backed datasets. Supports Markdown-KV format for LLM-optimized data ingestion.

## Use Cases

Dativo is for teams who:
- **Need to ingest SaaS and database data into a data lake** (S3/MinIO + Iceberg) without running a full Airbyte/Fivetran stack
- **Want config-driven ingestion** with strong schema validation and governance (ODCS v3.0.2 compliant)
- **Care about LLM-friendly data formats** (Markdown-KV storage for RAG pipelines)
- **Require custom data processing** with Python or high-performance Rust plugins (10-100x faster)
- **Need lightweight orchestration** with optional Dagster integration and incremental sync support

## At a Glance

| Feature                 | Details                                                                 |
|-------------------------|-------------------------------------------------------------------------|
| **Sources**             | Stripe, HubSpot, Postgres, MySQL, CSV, Google Drive/Sheets, Markdown-KV |
| **Targets**             | S3 / MinIO (Parquet, Iceberg-backed)                                    |
| **Orchestration**       | Optional Dagster integration with scheduling and retry policies         |
| **Config Style**        | YAML, validated against connector registry and ODCS schemas             |
| **Secret Management**   | Env vars, filesystem, Vault, AWS Secrets Manager, GCP Secret Manager    |
| **Custom Plugins**      | Python (easy to develop) and Rust (10-100x performance gain)            |
| **Schema Validation**   | ODCS v3.0.2 compliant with strict/warn modes                            |
| **Data Catalog**        | OpenMetadata, AWS Glue, Databricks Unity, Nessie                        |

## How is This Different from Airbyte / Singer / Fivetran?

- **Headless & config-driven** - No heavy UI, everything controlled via YAML configs and CLI
- **Iceberg-first data layout** - Native Parquet tuning with industry-standard path structures
- **Strong schema validation** - ODCS v3.0.2 compliant asset definitions with governance metadata
- **Markdown-KV for LLMs** - First-class support for LLM-optimized ingestion (RAG pipelines)
- **Custom plugin system** - Python for flexibility, Rust for 10-100x performance gains
- **Lightweight** - Run as a CLI, Docker container, or with optional Dagster orchestration

## Quick Start

### One-Command Local Setup

```bash
git clone https://github.com/dativo-io/dativo-ingest.git
cd dativo-ingest

# Automated setup: Python env, dependencies, and local infrastructure (MinIO + Nessie)
./scripts/setup-dev.sh

# Source environment variables
source .env

# Run end-to-end test with filesystem secrets
dativo run --job-dir tests/fixtures/jobs \
  --secret-manager filesystem \
  --secrets-dir tests/fixtures/secrets \
  --mode self_hosted
```

**What you should see:**
```
[INFO] Starting job execution: test_tenant/csv_to_iceberg
[INFO] Extracting data from CSV: tests/fixtures/data/sample.csv
[INFO] Validating 1000 records against schema
[INFO] Writing Parquet files to s3://dativo-test/raw/csv/sample/
[INFO] Committed 3 files (256.4 MB) to Iceberg table
[SUCCESS] Job completed in 12.3s
```

**For detailed setup instructions, see:**
- [QUICKSTART.md](QUICKSTART.md) - Quick reference guide
- [docs/SETUP_AND_TESTING.md](docs/SETUP_AND_TESTING.md) - Comprehensive setup guide
- [docs/INDEX.md](docs/INDEX.md) - Complete documentation index

## CLI Usage

### View All Commands

```bash
dativo --help
```

**Available commands:**
- `dativo run` - Execute a single job or all jobs in a directory
- `dativo check` - Test source/target connectivity without running the full job
- `dativo discover` - List available tables/streams from a connector
- `dativo start orchestrated` - Start Dagster orchestrator with scheduled jobs
- `dativo --version` - Show version information

### Common Recipes

**Validate a job config only (dry run):**
```bash
dativo check --config jobs/acme/stripe_customers.yaml --mode self_hosted --verbose
```

**List all streams from a Postgres database:**
```bash
dativo discover --config jobs/acme/postgres_analytics.yaml --verbose
```

**Run all jobs in a directory using filesystem secrets:**
```bash
dativo run --job-dir jobs/acme \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted
```

**Run a single job with AWS Secrets Manager:**
```bash
dativo run --config jobs/acme/stripe_customers.yaml \
  --secret-manager aws \
  --secret-manager-config '{"region": "us-east-1"}' \
  --mode self_hosted
```

**Start orchestrated mode with Dagster:**
```bash
dativo start orchestrated --runner-config configs/runner.yaml
```
Then open http://localhost:3000 to view the Dagster UI.

## Docker Deployment

### Build the Image

```bash
docker build -t dativo:latest .
```

### Run a Single Job (Oneshot Mode)

```bash
docker run --rm \
  -v $(pwd)/connectors:/app/connectors:ro \
  -v $(pwd)/assets:/app/assets:ro \
  -v $(pwd)/jobs:/app/jobs \
  -v $(pwd)/configs:/app/configs \
  -v $(pwd)/secrets:/app/secrets:ro \
  -v $(pwd)/state:/app/state \
  -e AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY \
  dativo:latest run \
    --config /app/jobs/acme/stripe_customers.yaml \
    --mode self_hosted
```

**What's mounted:**
- `/app/connectors` - Connector definitions (read-only)
- `/app/assets` - Asset schemas (read-only)
- `/app/jobs` - Job configurations
- `/app/state` - Incremental sync state (persisted)
- `/app/secrets` - Filesystem secrets (read-only, optional)

**Data output:**
- Parquet files written to S3/MinIO bucket configured in job
- State files written to `/app/state/{tenant_id}/{job_name}.json`

### Start Orchestrated Mode (Dagster)

```bash
docker run --rm -p 3000:3000 \
  -v $(pwd)/connectors:/app/connectors:ro \
  -v $(pwd)/assets:/app/assets:ro \
  -v $(pwd)/jobs:/app/jobs \
  -v $(pwd)/configs:/app/configs \
  -v $(pwd)/state:/app/state \
  -e AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY \
  dativo:latest start orchestrated \
    --runner-config /app/configs/runner.yaml
```

Then navigate to http://localhost:3000 for the Dagster UI.

> **Note:** Omit the `/app/secrets` volume when using cloud secret managers (AWS, GCP, Vault).

## Architecture

Config-driven ingestion engine. All behavior is controlled by YAML configs validated against a connector registry and asset schemas.

**Key Components:**
- **CLI Runner** - Executes `run` (oneshot) and `start` (orchestrated) commands
- **Dagster Orchestrator** - Optional scheduler for scheduled jobs with retry policies
- **Connector Registry** - Validates connector types, engines, and modes
- **Asset Schemas** - ODCS v3.0.2 compliant schema definitions with governance
- **Custom Plugins** - Python and Rust plugins for custom readers/writers
- **Parquet Writer** - Writes validated data with partitioning and file sizing (128-200 MB target)
- **Iceberg Committer** - Optional catalog integration (files always written to S3)

## Execution Flow

1. **Extract** - Read data from source (API, database, files)
2. **Validate** - Validate records against asset schema (strict or warn mode)
3. **Write** - Write to Parquet files (target: 128-200 MB, supports partitioning)
4. **Commit** - Optional: Commit to Iceberg catalog (files always written to S3)
5. **Update State** - Track incremental sync state

**Catalog Note**: Iceberg catalog is optional. Without catalog, Parquet files are written directly to S3/MinIO. See [docs/CATALOG_LIMITATIONS.md](docs/CATALOG_LIMITATIONS.md).

## Configuration

### Job Config

Defines source, target, asset, and tenant overrides:

**Path Conventions:**
- **Local Development**: Use relative paths (e.g., `connectors/stripe.yaml`)
- **Docker**: Use absolute paths (e.g., `/app/connectors/stripe.yaml`)
- **Assets**: Always use versioned paths (e.g., `assets/stripe/v1.0/customers.yaml`)

```yaml
tenant_id: acme
source_connector: stripe
source_connector_path: connectors/stripe.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: stripe_customers
asset_path: assets/stripe/v1.0/customers.yaml
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

### Asset Definition

ODCS v3.0.2 schema with governance:

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
  - name: email
    type: string
    required: false
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

## Supported Connectors

**Sources:**
- **Stripe** - Payments API (customers, charges, invoices)
- **HubSpot** - CRM API (contacts, deals, companies)
- **PostgreSQL** - Database with incremental sync (self-hosted only)
- **MySQL** - Database with incremental sync (self-hosted only)
- **Google Drive CSV** - CSV files from Google Drive
- **Google Sheets** - Spreadsheet data
- **CSV** - Local CSV files with chunking and incremental sync
- **Markdown-KV** - Markdown-KV files for LLM-optimized ingestion

**Targets:**
- **Iceberg** - Apache Iceberg tables (Parquet format, optional catalog)
- **S3** - Amazon S3 object storage
- **MinIO** - Self-hosted S3-compatible object storage

## Custom Plugin System

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

### Enterprise Security (Cloud Mode)

**Plugin sandboxing** with Docker-based isolation:
- Resource limits (CPU, memory)
- Network isolation
- Seccomp security profiles
- Automatic sandboxing in cloud mode

### Documentation

- [Custom Plugins Guide](docs/CUSTOM_PLUGINS.md) - Comprehensive guide for Python and Rust
- [Plugin Decision Tree](docs/PLUGIN_DECISION_TREE.md) - When to use connectors vs. plugins
- [Python Examples](examples/plugins/) - JSON API reader, JSON file writer, etc.
- [Rust Examples](examples/plugins/rust/) - High-performance CSV reader, Parquet writer

## Secret Management

Dativo supports multiple secret backends for flexible credential management:

| Backend             | Use Case                              | Configuration |
|---------------------|---------------------------------------|---------------|
| **Environment**     | Simple local development              | `--secret-manager env` |
| **Filesystem**      | Docker volumes, local testing         | `--secret-manager filesystem --secrets-dir secrets/` |
| **HashiCorp Vault** | Centralized secret management         | `--secret-manager vault --secret-manager-config vault.yaml` |
| **AWS Secrets**     | AWS deployments with IAM              | `--secret-manager aws --secret-manager-config '{"region": "us-east-1"}'` |
| **GCP Secret Mgr**  | GCP deployments with service accounts | `--secret-manager gcp --secret-manager-config '{"project": "my-project"}'` |

**Example filesystem structure:**
```
secrets/
  acme/              # tenant_id
    stripe.json      # source_connector name
    s3.env           # target_connector name
```

See [docs/SECRET_MANAGEMENT.md](docs/SECRET_MANAGEMENT.md) for complete documentation.

## Data Catalog Integration

Dativo supports integration with data catalogs for automatic lineage tracking and metadata management:

**Supported Catalogs:**
- **OpenMetadata** - Open-source metadata management platform
- **AWS Glue** - AWS data catalog service
- **Databricks Unity Catalog** - Databricks' unified catalog
- **Nessie** - Git-like data catalog (lineage via Iceberg table properties)

**Quick Example:**

```yaml
catalog:
  type: openmetadata
  connection:
    api_url: "${OPENMETADATA_API_URL:-http://localhost:8585/api}"
  database: my_database
  push_lineage: true
  push_metadata: true
```

See [docs/CATALOG_INTEGRATION.md](docs/CATALOG_INTEGRATION.md) for complete documentation.

## Security Considerations

### Secrets and Credentials

- **No secrets in configs** - All sensitive values use `${VAR}` expansion or secret managers
- **Filesystem secrets** - Restricted to tenant-specific directories with read-only Docker mounts
- **Cloud secret managers** - Recommended for production (AWS, GCP, Vault)
- **IAM roles** - Use IAM instance profiles or service accounts instead of static credentials

### S3/MinIO Access

**Least privilege IAM policy example:**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::dativo-data-lake",
        "arn:aws:s3:::dativo-data-lake/*"
      ]
    }
  ]
}
```

### Plugin Security (Cloud Mode)

- **Docker sandboxing** - All custom plugins run in isolated containers
- **Resource limits** - CPU and memory constraints prevent resource exhaustion
- **Network isolation** - Optional network restrictions for untrusted plugins
- **Seccomp profiles** - Linux security profiles restrict system calls

See [docs/PLUGIN_SANDBOXING.md](docs/PLUGIN_SANDBOXING.md) for details.

### API Rate Limiting

Built-in retry policies with exponential backoff:
- Configurable initial delay, max delay, and backoff multiplier
- Automatic handling of 429 (rate limit) and 5xx (server error) responses
- Per-connector rate limiting to avoid API throttling

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

## Quality

| Check              | Tool         | Status |
|--------------------|--------------|--------|
| **Tests**          | pytest       | ✅ 76+ tests, 90%+ coverage |
| **Linting**        | flake8       | ✅ Enforced in CI |
| **Formatting**     | black, isort | ✅ Auto-formatted |
| **Type Checking**  | mypy         | 🔄 Planned |
| **CI/CD**          | GitHub Actions | ✅ Complete pipeline |

**CI Pipeline (all PRs):**
1. Linting and code formatting
2. Core unit tests (Python 3.10, 3.11)
3. Plugin unit and integration tests
4. Rust plugin builds (Ubuntu, macOS)
5. End-to-end smoke tests

See [.github/workflows/](https://github.com/dativo-io/dativo-ingest/tree/main/.github/workflows) for details.

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
examples/            # Example jobs and custom plugins
  jobs/              # Example job configurations
  plugins/           # Python and Rust plugin examples
docs/                # Documentation
tests/               # Test suite
```

## Documentation

**Getting Started:**
- [QUICKSTART.md](QUICKSTART.md) - Quick reference guide
- [docs/SETUP_AND_TESTING.md](docs/SETUP_AND_TESTING.md) - Comprehensive setup guide
- [docs/INDEX.md](docs/INDEX.md) - Complete documentation index

**Configuration:**
- [docs/CONFIG_REFERENCE.md](docs/CONFIG_REFERENCE.md) - Complete config reference
- [docs/SECRET_MANAGEMENT.md](docs/SECRET_MANAGEMENT.md) - Secret backend configuration
- [docs/MINIMAL_ASSET_EXAMPLE.md](docs/MINIMAL_ASSET_EXAMPLE.md) - Minimal asset example

**Advanced:**
- [docs/CUSTOM_PLUGINS.md](docs/CUSTOM_PLUGINS.md) - Custom plugin development
- [docs/PLUGIN_SANDBOXING.md](docs/PLUGIN_SANDBOXING.md) - Plugin security
- [docs/CATALOG_INTEGRATION.md](docs/CATALOG_INTEGRATION.md) - Data catalog integration
- [docs/MARKDOWN_KV_STORAGE.md](docs/MARKDOWN_KV_STORAGE.md) - Markdown-KV patterns

**Testing:**
- [tests/README.md](tests/README.md) - Testing guide

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](.github/CONTRIBUTING.md) for:
- Development setup
- Coding style and tools
- Testing requirements
- Pull request process

**Quick links:**
- [Open issues](https://github.com/dativo-io/dativo-ingest/issues)
- [Roadmap](ROADMAP.md) - Upcoming features and connectors

## Exit Codes

- `0`: Success - All jobs completed successfully
- `1`: Partial success - Some jobs succeeded, some failed
- `2`: Failure - Configuration errors, missing files, or startup failures

## Roadmap

See [ROADMAP.md](ROADMAP.md) for upcoming features, connectors, and improvements.

**Highlights:**
- Additional SaaS connectors (Salesforce, Shopify, Snowflake)
- dbt integration for transformations
- Data quality checks and anomaly detection
- Enhanced observability with metrics and distributed tracing
- PyPI package distribution

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

Built with:
- [Apache Iceberg](https://iceberg.apache.org/) - Table format
- [Apache Parquet](https://parquet.apache.org/) - Columnar storage
- [Dagster](https://dagster.io/) - Orchestration
- [PyArrow](https://arrow.apache.org/docs/python/) - Data processing
- [Pydantic](https://pydantic-docs.helpmanual.io/) - Config validation

---

**Questions?** Open an issue or check the [documentation](docs/INDEX.md).

**Need help?** See [CONTRIBUTING.md](.github/CONTRIBUTING.md#getting-help) for resources.
