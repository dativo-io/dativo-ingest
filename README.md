# Dativo Ingestion Platform

Dativo-Ingest is a headless, config-driven data ingestion platform that extracts data from SaaS APIs (Stripe, HubSpot) and databases (PostgreSQL, MySQL) into object storage (S3, MinIO) as Apache Iceberg-backed datasets—all defined through YAML configuration files, no code required. Unlike traditional ETL tools that require UI-based setup and single-tenant architectures, Dativo runs entirely headless via CLI or API, making it ideal for embedding into your existing infrastructure, CI/CD pipelines, or multi-tenant SaaS platforms where each customer needs isolated data pipelines. For data engineers building modern data stacks, this means version-controlled, GitOps-friendly ingestion configs that integrate seamlessly with your orchestration layer (Dagster, Airflow, or custom schedulers), while startup CTOs benefit from a battle-tested, multi-tenant-ready solution that scales from prototype to production without architectural rewrites.

## Table of Contents

- [Comparison: Dativo vs. Airbyte vs. Meltano](#comparison-dativo-vs-airbyte-vs-meltano)
- [Testing & Validation](#testing--validation)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [CLI Usage](#cli-usage)
- [Execution Flow](#execution-flow)
- [Configuration](#configuration)
- [Supported Connectors](#supported-connectors)
- [Plugin System](#plugin-system)
- [Data Catalog Integration](#data-catalog-integration)
- [Exit Codes](#exit-codes)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [Documentation](#documentation)
- [Advanced Features](#advanced-features)

## Comparison: Dativo vs. Airbyte vs. Meltano

| Feature | Dativo | Airbyte | Meltano |
|---------|--------|---------|---------|
| **Configuration** | ✅ **YAML-only, no code required** | ❌ Requires UI or API calls | ⚠️ YAML + Singer taps/targets (code) |
| **UI Dependency** | ✅ **Fully headless (CLI/API only)** | ❌ Web UI required for setup | ⚠️ Optional UI (CLI-first) |
| **Iceberg/Nessie Support** | ✅ **Native support with Nessie catalog** | ⚠️ Limited (via custom destinations) | ⚠️ Limited (via custom targets) |
| **Plugin Flexibility** | ✅ **Python + Rust plugins (10-100x performance)** | ⚠️ Python/Java SDK only | ⚠️ Singer-based (Python) |
| **Multi-Tenant Architecture** | ✅ **Built-in tenant isolation** | ❌ Single-tenant focus | ❌ Single-tenant focus |
| **GitOps-Friendly** | ✅ **100% config-driven, version-controlled** | ⚠️ Config export available | ✅ Git-native workflow |
| **Connector Count** | ⚠️ Focused set (Stripe, HubSpot, DBs, CSV) | ✅ 600+ connectors | ✅ 600+ connectors |
| **Custom Connector Development** | ✅ **Simple Python/Rust classes** | ⚠️ CDK required | ⚠️ Singer SDK required |
| **Deployment Model** | ✅ **Headless (Docker, CLI, API)** | ⚠️ Self-hosted or Cloud (UI) | ✅ Self-hosted (CLI) |
| **Schema Validation** | ✅ **ODCS v3.0.2 compliant, strict/warn modes** | ⚠️ Basic validation | ⚠️ Basic validation |
| **Incremental Sync** | ✅ **Cursor-based + WAL checkpointing** | ✅ CDC + incremental | ✅ Incremental sync |
| **Target Formats** | ✅ **Iceberg (Parquet) + S3/MinIO** | ⚠️ Warehouses + lakes | ⚠️ Warehouses + lakes |
| **Orchestration Integration** | ✅ **Native Dagster, Airflow-ready** | ⚠️ Via API/CLI | ✅ Native Airflow/dbt integration |

**When to choose Dativo:**
- Building multi-tenant SaaS platforms requiring isolated pipelines
- Need native Iceberg/Nessie integration for modern data lakes
- Want 100% config-driven, GitOps-friendly workflows
- Require headless operation (no UI dependency)
- Need high-performance custom connectors (Rust plugins)
- Prefer simple YAML configs over code-based connector development

## Testing & Validation

**NEW!** Comprehensive testing resources for all capabilities:
- **[docs/testing-guide-index.md](docs/testing-guide-index.md)** - Complete testing documentation index
- **[docs/testing-playbook.md](docs/testing-playbook.md)** - 20 detailed test cases with step-by-step instructions
- **[docs/testing-quick-reference.md](docs/testing-quick-reference.md)** - Quick command reference and troubleshooting
- **[docs/environment-setup.md](docs/environment-setup.md)** - Environment variables reference
- **[scripts/preflight-check.sh](scripts/preflight-check.sh)** - Validate your environment is ready
- **[scripts/generate-test-data.sh](scripts/generate-test-data.sh)** - Generate sample test datasets

Quick start testing:
```bash
./scripts/preflight-check.sh    # Validate environment
./scripts/generate-test-data.sh  # Generate test data
source .env                      # Load environment variables
dativo run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets --mode self_hosted
```

## Architecture

Config-driven ingestion engine. All behavior is controlled by YAML configs validated against a connector registry and asset schemas.

### Key Components
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

### Python Version Check
```bash
python3 --version  # Should show 3.10.0 or higher

# If you have Python 3.9 or below, upgrade using:
# • Conda: conda create -n dativo python=3.10 && conda activate dativo
# • Homebrew (macOS): brew install python@3.10
# • pyenv: pyenv install 3.10.13 && pyenv local 3.10.13
```

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

For detailed instructions, see:
- [docs/quickstart.md](docs/quickstart.md) - Quick reference guide
- [docs/environment-setup.md](docs/environment-setup.md) - Environment variables reference
- [docs/SETUP_AND_ONBOARDING.md](docs/SETUP_AND_ONBOARDING.md) - Comprehensive setup guide

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

**Note**: Iceberg catalog is optional. Without catalog, Parquet files are written directly to S3/MinIO. See [docs/CATALOG_LIMITATIONS.md](docs/CATALOG_LIMITATIONS.md).

## Configuration

### Job Config

Defines source, target, asset, and tenant overrides.

### Path Conventions
- **Local Development**: Use relative paths (e.g., `connectors/stripe.yaml`)
- **Docker**: Use absolute paths (e.g., `/app/connectors/stripe.yaml`)
- **Assets**: Always use versioned paths (e.g., `assets/examples/stripe/v1.0/customers.yaml`)

```yaml
tenant_id: acme
source_connector: stripe
source_connector_path: connectors/stripe.yaml  # Local: relative, Docker: /app/connectors/stripe.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
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
target:
  file_format: parquet
  partitioning: [ingest_date]
```

### Quick Templates
```bash
# Generate job template
./scripts/generate-job-template.sh mytenant my_job csv iceberg

# Generate asset template
./scripts/generate-asset-template.sh csv my_asset your-email@company.com
```

See [docs/CONFIG_REFERENCE.md](docs/CONFIG_REFERENCE.md) for complete reference.  
See [docs/MINIMAL_ASSET_EXAMPLE.md](docs/MINIMAL_ASSET_EXAMPLE.md) for minimal asset example.


## Supported Connectors

### Sources
- **Stripe** - Payments API (customers, charges, invoices)
- **HubSpot** - CRM API (contacts, deals, companies)
- **Google Drive CSV** - CSV files from Google Drive
- **Google Sheets** - Spreadsheet data
- **CSV** - Local CSV files
- **Markdown-KV** - Markdown-KV files for LLM-optimized ingestion
- **PostgreSQL** - Database (self-hosted only)
- **MySQL** - Database (self-hosted only)

### Targets
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

#### Python Plugin (Easy to develop)

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

#### Rust Plugin (Maximum performance)

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

Rust plugins provide dramatic improvements:
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

### Supported Catalogs
- **OpenMetadata** - Open-source metadata management platform
- **AWS Glue** - AWS data catalog service
- **Databricks Unity Catalog** - Databricks' unified catalog
- **Nessie** - Git-like data catalog (lineage via Iceberg table properties)

### Quick Example

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

### Getting Started
- **[Quick Start Guide](docs/quickstart.md)** - Get up and running in 5 minutes
- **[Python Setup](docs/python-setup.md)** - Python 3.10+ installation guide
- **[Environment Setup](docs/environment-setup.md)** - Environment variables reference
- **[Setup & Onboarding](docs/SETUP_AND_ONBOARDING.md)** - Comprehensive setup guide

### Configuration & Architecture
- **[Config Reference](docs/CONFIG_REFERENCE.md)** - Complete configuration documentation
- **[Data Flow Architecture](docs/data-flow-architecture.md)** - How data moves from readers to writers
- **[Design Decisions](docs/DESIGN_ONE_ASSET_PER_JOB.md)** - Why one asset per job
- **[Minimal Asset Example](docs/MINIMAL_ASSET_EXAMPLE.md)** - Simple asset definition example

### Connectors & Plugins
- **[Custom Plugins](docs/CUSTOM_PLUGINS.md)** - Python and Rust plugin development guide
- **[Plugin Decision Tree](docs/PLUGIN_DECISION_TREE.md)** - When to use connectors vs. plugins
- **[Plugin Sandboxing](docs/PLUGIN_SANDBOXING.md)** - Security and isolation for plugins

### Data Management
- **[Schema Validation](docs/SCHEMA_VALIDATION.md)** - Schema validation modes and rules
- **[Ingestion Execution](docs/INGESTION_EXECUTION.md)** - How jobs execute end-to-end
- **[WAL Checkpointing](docs/WAL_CHECKPOINTING.md)** - Write-ahead log for fault tolerance
- **[Markdown-KV Storage](docs/MARKDOWN_KV_STORAGE.md)** - LLM-optimized data ingestion

### Data Catalogs
- **[Catalog Integration](docs/CATALOG_INTEGRATION.md)** - OpenMetadata, AWS Glue, Unity Catalog, Nessie
- **[Catalog Limitations](docs/CATALOG_LIMITATIONS.md)** - Current limitations and workarounds

### Security & Secrets
- **[Secret Management](docs/SECRET_MANAGEMENT.md)** - All secret backends (env, filesystem, Vault, AWS, GCP)
- **[Tag Propagation](docs/TAG_PROPAGATION.md)** - Data classification and governance tags
- **[Tag Precedence](docs/TAG_PRECEDENCE.md)** - How tags are prioritized and applied

### Orchestration & Operations
- **[Runner & Orchestration](docs/RUNNER_AND_ORCHESTRATION.md)** - Dagster orchestration and oneshot modes
- **[Git Commit Guide](docs/git-commit-guide.md)** - Contribution guidelines

### Testing
- **[Testing Guide Index](docs/testing-guide-index.md)** - Complete testing documentation index
- **[Testing Playbook](docs/testing-playbook.md)** - 20 detailed test cases
- **[Testing Quick Reference](docs/testing-quick-reference.md)** - Quick command reference
- **[Testing Resources Summary](docs/testing-resources-summary.md)** - Testing infrastructure overview
- **[Test Documentation](tests/README.md)** - Detailed test suite documentation

### Advanced Features
- **[Agentic AI Orchestration](docs/experimental/AGENTIC_AI_ORCHESTRATION_Dativo.md)** - AI-powered orchestration and workflow automation
- **[Governance and FinOps](docs/experimental/GOVERNANCE_AND_FINOPS_Dativo.md)** - Advanced governance, compliance, and financial operations features


