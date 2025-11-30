# Dativo Ingestion Platform

[![Tests](https://github.com/dativo-io/dativo-ingest/actions/workflows/tests.yml/badge.svg)](https://github.com/dativo-io/dativo-ingest/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/dativo-io/dativo-ingest?display_name=tag)](https://github.com/dativo-io/dativo-ingest/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Config-driven ingestion engine for teams that need SaaS + DB data delivered to S3/MinIO (Iceberg-backed) with strong schema validation and LLM-friendly Markdown-KV support. Fully headless—no heavy UI or control plane required.

## Use cases

- Ingest Stripe, HubSpot, Google Workspace, Postgres, or MySQL data into Iceberg/Parquet on S3 or MinIO.
- Roll out config-driven ingestion jobs without running a full Airbyte/Fivetran deployment.
- Enforce ODCS v3.0.2 contracts, Markdown-KV storage, and connector governance with CI-grade tooling.

## At a glance

| Feature | Status |
| --- | --- |
| Sources | Stripe, HubSpot, Google Sheets/Drive CSV, CSV, Markdown-KV, Postgres, MySQL |
| Targets | Iceberg-backed Parquet on S3 or MinIO (raw S3 supported too) |
| Orchestration | Optional Dagster runner (`dativo start orchestrated`) |
| Config style | YAML validated against registry + schemas |
| Secret management | Env, filesystem, Vault, AWS Secrets Manager, GCP Secret Manager |
| Formats | Parquet + Markdown-KV (string/structured/raw) |

## Getting started quickly

Use these docs as your first stop:

- [`docs/README.md`](docs/README.md) – documentation index with prerequisites per persona.
- [`QUICKSTART.md`](QUICKSTART.md) – command reference for the dev loop.
- [`docs/SETUP_AND_TESTING.md`](docs/SETUP_AND_TESTING.md) – detailed environment + smoke tests.
- [`ROADMAP.md`](ROADMAP.md) – upcoming connectors, governance, and platform milestones.

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
- Docker + Docker Compose (for local infrastructure and optional Dagster runner)
- Node.js 18+ (optional, for schema validation helpers)
- AWS/GCP CLIs or `mc` (optional, to inspect landing zones)

### Copy-paste runbook (3 minutes)

```bash
git clone https://github.com/dativo-io/dativo-ingest.git
cd dativo-ingest

./scripts/setup-dev.sh
source .env

dativo run --job-dir tests/fixtures/jobs \
  --secret-manager filesystem \
  --secrets-dir tests/fixtures/secrets \
  --mode self_hosted
```

> Swap `--secret-manager filesystem` for `env`, `vault`, `aws`, or `gcp` once you wire up real secrets. The sample jobs land data under `./state`.

### What you should see

```
[INFO] Tenant ID 'test_tenant' inferred from job configurations | event_type=tenant_inferred
[INFO] Starting job execution | connector_type=stripe event_type=job_started
[INFO] Wrote batch: 1200 records, 2 files | event_type=batch_written
[INFO] Job execution completed | records=1200 valid_records=1200 files_written=2 exit_code=0 event_type=job_finished
```

### Need more?

- [QUICKSTART.md](QUICKSTART.md) – copy-paste snippets for every secret backend.
- [docs/SETUP_AND_TESTING.md](docs/SETUP_AND_TESTING.md) – smoke tests + troubleshooting.
- [docs/SECRET_MANAGEMENT.md](docs/SECRET_MANAGEMENT.md) – production recommendations per backend.
- [`examples/stripe_to_s3_iceberg/README.md`](examples/stripe_to_s3_iceberg/README.md) – end-to-end walkthrough.

### Docker Deployment

1. Build (or pull) the image:
```bash
docker build -t dativo:1.1.0 .
# Matches release v1.1.0. Use dativo:latest for tip-of-main experiments.
```

2. Run a single job (oneshot mode) with explicit bind mounts so you know where data lives:
```bash
docker run --rm \
  -v $(pwd)/connectors:/app/connectors:ro \
  -v $(pwd)/assets:/app/assets:ro \
  -v $(pwd)/jobs:/app/jobs \
  -v $(pwd)/configs:/app/configs:ro \
  -v $(pwd)/secrets:/app/secrets \
  -v $(pwd)/state:/app/state \
  dativo:1.1.0 run --config /app/jobs/acme/stripe_customers_to_iceberg.yaml \
  --secret-manager filesystem \
  --secrets-dir /app/secrets \
  --mode self_hosted
```

   - Logs: stream to STDOUT (can be scraped by Docker/Kubernetes).
   - Data landing zone: `/app/state` (mounted to `./state` locally).
   - Configuration + registry: `/app/{connectors,assets,jobs,configs}` (read-only in prod).

3. Start orchestrated mode (Dagster UI exposed on `:3000`):
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

> Prefer the curated Docker quickstart in [`examples/stripe_to_s3_iceberg`](examples/stripe_to_s3_iceberg/README.md) for a local MinIO + Stripe mock environment. Use the `latest` tag only when you are comfortable with tip-of-main behavior.

## Common recipes

- **Validate a job config only**  
  `dativo check --config jobs/acme/stripe_customers.yaml --mode self_hosted`

- **List all available streams for Postgres**  
  `dativo discover --connector postgres --verbose`

- **Run every job in a directory using filesystem secrets**  
  `dativo run --job-dir jobs/acme --secret-manager filesystem --secrets-dir secrets`

- **Dry-run Markdown-KV transformations with warnings only**  
  `dativo run --config jobs/acme/markdown_kv.yaml --mode self_hosted --schema-validation-mode warn`

## CLI in one screen

```
$ dativo --help
usage: dativo [-h] {run,start,check,discover} ...

Commands:
  run        Execute one job or every job in a directory
  start      Launch Dagster orchestrator (dativo start orchestrated)
  check      Validate credentials + connectivity without writing data
  discover   List available tables/streams to seed asset definitions

Global flags:
  --secret-manager {env,filesystem,vault,aws,gcp}
  --secret-manager-config <path-or-json>
  --mode {self_hosted,cloud}
  --version
```

## Examples

- [`examples/stripe_to_s3_iceberg/`](examples/stripe_to_s3_iceberg/README.md) – Stripe + MinIO "hello world" with Docker Compose, filesystem secrets, and Markdown-KV output.
- [`examples/postgres_incremental_sync/`](examples/postgres_incremental_sync/README.md) – local Postgres container with incremental state tracking and Iceberg commits.
- [`examples/plugins/`](examples/plugins/README.md) – JSON API reader/writer plus Rust CSV/Parquet plugins.

## CLI Usage

### Run a Single Job

```bash
dativo run --config <path> --mode <self_hosted|cloud>
```

### Check Connection

Test connectivity and credentials without running the full job:

```bash
dativo check --config <path> [--json] [--verbose] --mode <self_hosted|cloud>
```

This validates:
- Source connection and authentication
- Target connection (S3 bucket access, etc.)
- Returns detailed error information with retryable flags

**Options:**
- `--json`: Output results in JSON format
- `--verbose`: Show detailed information including error details

**Example:**
```bash
dativo check --config jobs/acme/stripe_customers.yaml --verbose

# Output:
# ============================================================
# Connection Check Results
# ============================================================
# 
# Source: success
#   Connection successful: API accessible
#   Details: {'api_version': 'v1', 'account_id': 'acct_123'}
# 
# Target: success
#   S3 bucket 'my-bucket' is accessible
```

### Discover Available Streams

List available tables/streams from a connector:

```bash
# Using connector type
dativo discover --connector stripe [--json] [--verbose]

# Using job config
dativo discover --config jobs/acme/stripe_customers.yaml [--json] [--verbose]
```

This helps generate asset definitions by discovering what data is available.

**Options:**
- `--json`: Output results as JSON
- `--verbose`: Show detailed information including column schemas

**Example:**
```bash
dativo discover --config jobs/postgres_job.yaml --verbose

# Output:
# ============================================================
# Discovery Results
# ============================================================
# 
# Found 12 stream(s):
# 
# 1. customers
#    Type: table
#    Schema: {"id": "integer", "email": "varchar", ...}
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

## Plugin System

Dativo supports custom readers and writers in **Python and Rust**, with enterprise-grade features:

### Key Features

- **Plugin Sandboxing**: Docker-based isolation for Python plugins in cloud mode
  - Resource limits (CPU, memory)
  - Network isolation
  - Seccomp security profiles
- **Connection Testing**: Validate credentials before job execution
  - `check_connection()` method in all plugins
  - CLI command: `dativo check --config job.yaml`
- **Discovery Interface**: Discover available tables/streams
  - `discover()` method returns available data sources
  - CLI command: `dativo discover --connector <name>`
- **Version Management**: Plugin version compatibility checks
  - `__version__` attribute tracking
  - SDK version validation
- **Standardized Errors**: Comprehensive error hierarchy
  - Retryable vs. permanent failure detection
  - Error codes for observability

### Custom Plugins

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
- [Plugin Decision Tree](docs/PLUGIN_DECISION_TREE.md) - When to use connectors vs. plugins
- [Python Examples](examples/plugins/) - JSON API reader, JSON file writer, etc.
- [Rust Examples](examples/plugins/rust/) - High-performance CSV reader, Parquet writer

## Data Catalog Integration

Dativo supports integration with data catalogs for automatic lineage tracking and metadata management. When configured, lineage information (source → target relationships) and metadata (tags, owners, descriptions) are automatically pushed to your catalog.

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

## Quality

| Check | Status |
| --- | --- |
| Tests | ✅ `pytest` via [`tests.yml`](.github/workflows/tests.yml) and targeted smoke/integration suites |
| Lint & formatting | ✅ `ruff` + `black` enforced in [`ci.yml`](.github/workflows/ci.yml) |
| Schema validation | ✅ `jsonschema` + ODCS helpers (`make schema-validate`) |
| Type checking | ⚪️ `mypy` planned (tracked in [ROADMAP.md](ROADMAP.md)) |

## Security considerations

- **Secrets** – sample configs rely on filesystem secrets, but production runs should use Vault, AWS Secrets Manager, or GCP Secret Manager (`--secret-manager` flag). See [docs/SECRET_MANAGEMENT.md](docs/SECRET_MANAGEMENT.md) for end-to-end guidance.
- **Least privilege** – target connectors expect IAM policies scoped to the landing bucket/prefix. See `connectors/*.yaml` for the exact structure and copy/pasteable examples.
- **Retries and backoff** – the built-in retry policy (`src/dativo_ingest/retry_policy.py`) avoids hammering APIs and respects rate limits by default.
- **No committed secrets** – this repo ships with `.env.example` files only; `scripts/setup-dev.sh` creates a local `.env` ignored by git.

## How is this different from Airbyte / Singer / Fivetran?

- **Headless + config-driven** – no heavy server or UI to babysit; GitOps-friendly YAML.
- **Iceberg-first** – Parquet layout, commit semantics, and catalog integration are first-class features instead of afterthoughts.
- **LLM-friendly** – Markdown-KV transforms, ODCS validation, and metadata tagging ship out of the box.
- **Pluggable engines** – mix native connectors, Airbyte/Singer engines, and custom Python/Rust plugins within the same run.

## Roadmap & contributing

- [ROADMAP.md](ROADMAP.md) lists near-term connectors, governance upgrades, and observability work.
- Contribution guide lives in [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md) and links to dev environment steps plus coding standards.
- New contributors should start with [`docs/CONNECTOR_DEVELOPMENT.md`](docs/CONNECTOR_DEVELOPMENT.md) (how to add connectors/assets) and [`docs/README.md`](docs/README.md) for persona-based indexes.
- Issues tagged with `good first issue` and the new issue templates (bug + connector request) make triage approachable—open one if you need a scenario documented.

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
**Documentation index:** [docs/README.md](docs/README.md)  
**Config Reference:** [docs/CONFIG_REFERENCE.md](docs/CONFIG_REFERENCE.md)  
**Custom Plugins:** [docs/CUSTOM_PLUGINS.md](docs/CUSTOM_PLUGINS.md)  
**Secrets Reference:** [docs/SECRET_MANAGEMENT.md](docs/SECRET_MANAGEMENT.md)  
**Testing:** [tests/README.md](tests/README.md)

## License

Released under the [MIT License](LICENSE). Mention the license when you redistribute binaries or container images so downstream teams know they can adopt it safely.


