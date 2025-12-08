# Dativo Ingestion Platform

A **headless, config-driven** ingestion engine for modern data stacks. Extract data from SaaS APIs (Stripe, HubSpot) and databases (PostgreSQL, MySQL) into object storage (S3, MinIO) as Iceberg-backed datasets. Supports Markdown-KV format for LLM-optimized data ingestion.

## Table of Contents

- [Why Dativo?](#why-dativo)
- [Comparison: Dativo vs. Alternatives](#comparison-dativo-vs-alternatives)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Demo Environment](#demo-environment)
- [CLI Usage](#cli-usage)
- [Configuration](#configuration)
- [Supported Connectors](#supported-connectors)
- [Plugin System](#plugin-system)
- [Data Catalog Integration](#data-catalog-integration)
- [Multi-Tenant Architecture](#multi-tenant-architecture)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [Documentation](#documentation)
- [License](#license)

## Why Dativo?

Dativo is designed for teams that need:

- **Headless Operation**: No UI required - perfect for GitOps, CI/CD, and infrastructure-as-code
- **Config-Driven**: Everything is YAML - connectors, assets, jobs, and schedules
- **Multi-Tenant First**: Built-in tenant isolation for state, secrets, and data
- **Iceberg Native**: Direct integration with Apache Iceberg for modern data lakes
- **Plugin Architecture**: Extend with Python or Rust plugins for custom logic
- **Production Ready**: Enterprise features like sandboxing, retry policies, and observability

## Comparison: Dativo vs. Alternatives

| Feature | Dativo | Airbyte | Meltano |
|--------|--------|---------|---------|
| **Architecture** | Headless, config-driven | UI-first, API-driven | CLI-first, plugin-based |
| **Deployment** | Docker, Kubernetes | Docker, Cloud | Python package |
| **Configuration** | YAML files (GitOps) | Web UI + API | YAML files |
| **Multi-Tenancy** | ✅ Built-in isolation | ❌ Single tenant | ❌ Single tenant |
| **Iceberg Support** | ✅ Native | ❌ Limited | ❌ Limited |
| **Custom Plugins** | ✅ Python + Rust | ❌ Connectors only | ✅ Python (Singer) |
| **Orchestration** | ✅ Dagster built-in | ❌ External only | ❌ External only |
| **Catalog Integration** | ✅ OpenMetadata, Glue, Unity | ❌ Limited | ❌ Limited |
| **Markdown-KV** | ✅ Native support | ❌ No | ❌ No |
| **Schema Validation** | ✅ ODCS v3.0.2 | ⚠️ Basic | ⚠️ Basic |
| **Secret Management** | ✅ Multiple backends | ⚠️ Basic | ⚠️ Basic |
| **Best For** | Multi-tenant SaaS, data platforms | Single-tenant, UI-driven | Singer ecosystem |

**When to Choose Dativo:**
- Building a multi-tenant data platform
- Need headless, GitOps-friendly ingestion
- Require Iceberg-native integration
- Want custom plugins (Python/Rust)
- Need built-in orchestration (Dagster)

**When to Choose Airbyte:**
- Need 300+ pre-built connectors
- Prefer UI-driven configuration
- Single-tenant use case
- Don't need Iceberg integration

**When to Choose Meltano:**
- Already using Singer taps/targets
- Prefer Python-only plugins
- CLI-first workflow
- Don't need multi-tenancy

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

- **Python 3.10+** (Required - Python 3.9 and below are not supported)
- Docker and Docker Compose (for local infrastructure)
- Node.js 18+ (optional, for schema validation)

**Python Version Check:**
```bash
python3 --version  # Should show 3.10.0 or higher

# If you have Python 3.9 or below, upgrade using:
# • Conda: conda create -n dativo python=3.10 && conda activate dativo
# • Homebrew (macOS): brew install python@3.10
# • pyenv: pyenv install 3.10.13 && pyenv local 3.10.13
```

See [docs/python-setup.md](docs/python-setup.md) for detailed Python setup instructions.

### Setup and Run

```bash
# 1. Run automated setup
./scripts/setup-dev.sh

# 2. Source environment variables
source .env.example  # Or create your own .env file

# 3. Run end-to-end test (filesystem secret manager)
dativo run --job-dir tests/fixtures/jobs \
  --secret-manager filesystem \
  --secrets-dir tests/fixtures/secrets \
  --mode self_hosted
```

**For detailed instructions, see:**
- [docs/quickstart.md](docs/quickstart.md) - Quick reference guide
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

## Demo Environment

**NEW!** One-command demo environment:

```bash
# Start demo infrastructure (Nessie + MinIO)
docker-compose -f docker-compose.demo.yml up -d

# Run demo job
dativo run --config demo/jobs/csv_to_iceberg.yaml --mode self_hosted
```

See [demo/README.md](demo/README.md) for complete demo instructions.

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

### Discover Available Streams

List available tables/streams from a connector:

```bash
# Using connector type
dativo discover --connector stripe [--json] [--verbose]

# Using job config
dativo discover --config jobs/acme/stripe_customers.yaml [--json] [--verbose]
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

## Configuration

**Job Config** - Defines source, target, asset, and tenant overrides:

**Path Conventions:**
- **Local Development**: Use relative paths (e.g., `connectors/examples/stripe.yaml`)
- **Docker**: Use absolute paths (e.g., `/app/connectors/examples/stripe.yaml`)
- **Assets**: Always use versioned paths (e.g., `assets/examples/stripe/v1.0/customers.yaml`)

```yaml
tenant_id: acme
source_connector: stripe
source_connector_path: connectors/examples/stripe.yaml  # Local: relative, Docker: /app/connectors/examples/stripe.yaml
target_connector: iceberg
target_connector_path: connectors/examples/iceberg.yaml
asset: stripe_customers
asset_path: assets/examples/stripe/v1.0/customers.yaml  # Always versioned
source:
  object: customers
  incremental:
    lookback_days: 1
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
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

## Execution Flow

1. **Extract** - Read data from source (API, database, files)
2. **Validate** - Validate records against asset schema (strict or warn mode)
3. **Write** - Write to Parquet files (target: 128-200 MB, supports partitioning)
4. **Commit** - Optional: Commit to Iceberg catalog (files always written to S3)
5. **Update State** - Track incremental sync state

**Catalog Note**: Iceberg catalog is optional. Without catalog, Parquet files are written directly to S3/MinIO. See [docs/CATALOG_LIMITATIONS.md](docs/CATALOG_LIMITATIONS.md).

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

See [docs/connectors.md](docs/connectors.md) for complete connector reference.

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

## Multi-Tenant Architecture

Dativo is built with **multi-tenancy as a first-class feature**:

### Tenant Isolation

- **State Isolation**: Each tenant has separate state files (`state/{tenant_id}/`)
- **Secret Isolation**: Secrets are tenant-scoped (`secrets/{tenant_id}/`)
- **Data Isolation**: Tenant ID included in S3 paths and Iceberg table names
- **Logging Isolation**: Tenant ID tagged in all log entries

### Tenant Configuration

```yaml
tenant_id: acme  # Required in all job configs
environment: prod
```

### Orchestration

- **Serial Execution**: One job per tenant at a time (prevents Nessie commit conflicts)
- **Tenant-Level Scheduling**: Schedules are tenant-aware
- **Resource Quotas**: (Future) Tenant-level resource limits

See [docs/RUNNER_AND_ORCHESTRATION.md](docs/RUNNER_AND_ORCHESTRATION.md) for orchestration details.

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
connectors/
  examples/          # Connector recipes (tenant-agnostic)
assets/              # Asset schemas (ODCS v3.0.2)
  {source}/v{version}/
jobs/                # Job configs (tenant-specific)
  {tenant_id}/
configs/             # Runner and policy configs
registry/            # Connector capabilities registry
secrets/             # (Optional) filesystem secrets (tenant-organized)
  {tenant_id}/
state/               # Incremental sync state
  {tenant_id}/
demo/                # Demo environment
  data/              # Sample data
  jobs/              # Demo job configs
src/dativo_ingest/   # Source code
docs/                # Documentation
  index.md           # Documentation index
  connectors.md      # Connector reference
  quickstart.md      # Quick start guide
  experimental/      # Experimental features
```

## Documentation

**Documentation Index:** [docs/index.md](docs/index.md) - Complete documentation navigation

**Quick Start:**
- [Quick Start Guide](docs/quickstart.md)
- [Python Setup Guide](docs/python-setup.md)
- [Setup and Testing](docs/SETUP_AND_TESTING.md)

**Core Documentation:**
- [Configuration Reference](docs/CONFIG_REFERENCE.md)
- [Connector Reference](docs/connectors.md)
- [Secret Management](docs/SECRET_MANAGEMENT.md)
- [Schema Validation](docs/SCHEMA_VALIDATION.md)

**Architecture:**
- [Data Flow Architecture](DATA_FLOW_ARCHITECTURE.md)
- [Design: One Asset Per Job](docs/DESIGN_ONE_ASSET_PER_JOB.md)
- [Runner and Orchestration](docs/RUNNER_AND_ORCHESTRATION.md)

**Advanced:**
- [Custom Plugins](docs/CUSTOM_PLUGINS.md)
- [Catalog Integration](docs/CATALOG_INTEGRATION.md)
- [WAL Checkpointing](docs/WAL_CHECKPOINTING.md)
- [Tag Propagation](docs/TAG_PROPAGATION.md)

**Roadmap:**
- [Roadmap](docs/roadmap.md)

## License

Apache License 2.0 - See [LICENSE](LICENSE) file for details.
