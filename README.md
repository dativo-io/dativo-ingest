# Dativo Ingestion Platform

A headless, config-driven ingestion engine. Extracts data from third party SaaS APIs(like Stripe or Hubspot) and databases(like Postgres or Mysql) into vendor-owned object storage (S3, MinIO, Azure Blob) as Iceberg-backed datasets. Supports Markdown-KV format for LLM-optimized data ingestion.

## Architecture

Dativo is a **config-only ingestion engine** that built in:

- **Self-hosted mode:** Fully isolated Docker image with Dagster bundled as orchestrator

All behavior is driven by YAML configs, validated by a connectors registry and asset specs-as-code files.

### Components

- **Runner Engine**: Dockerized CLI entrypoint that executes `run` and `start` commands # TODO: Add generate config command
- **Orchestrator**: Bundled Dagster instance that reads `runner.yaml`, registers schedules, and enforces tenant-level serialization
- **Config Loader**: Parses job configs, resolves env vars, validates against registry
- **Registry Validator**: Confirms supported connector types, auth methods, and allowed modes
- **Specs-as-Code**: Versioned dataset schema references with presence validation

## Quick Start

### Prerequisites

- Python 3.10+
- Docker (for containerized deployment)
- Node.js 18+ (for schema validation)

### Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
npm install --include=dev
```

2. Validate schemas:
```bash
make schema-validate
```

3. Run a job:
```bash
python -m dativo_ingest.cli run --config configs/jobs/stripe.yaml --mode self_hosted
```

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

## CLI Usage

### Run Command

Execute a single job in oneshot mode:

```bash
dativo run --config <path> --mode <self_hosted|cloud>
```

**Options:**
- `--config`: Path to job configuration YAML file (required)
- `--mode`: Execution mode - `self_hosted` (default) or `cloud`. Database connectors are only allowed in `self_hosted` mode.

**Example:**
```bash
dativo run --config /app/configs/jobs/stripe.yaml --mode self_hosted
```

### Start Command

Start Dagster orchestrator in long-running mode:

```bash
dativo start orchestrated --runner-config <path>
```

**Options:**
- `--runner-config`: Path to runner configuration YAML file (default: `/app/configs/runner.yaml`)

**Example:**
```bash
dativo start orchestrated --runner-config /app/configs/runner.yaml
```

## Configuration

### Job Configuration

Job configs define the source connector, target connector, asset, and tenant-specific overrides:

```yaml
tenant_id: acme
environment: prod

# Reference to source connector recipe
source_connector: stripe
source_connector_path: /app/connectors/sources/stripe.yaml

# Reference to target connector recipe
target_connector: iceberg
target_connector_path: /app/connectors/targets/iceberg.yaml

# Reference to asset definition
asset: stripe_customers
asset_path: /app/assets/stripe/v1.0/customers.yaml

# Source configuration
source:
  objects: [customers]
  incremental:
    lookback_days: 1

# Target configuration
target:
  branch: acme
  warehouse: s3://lake/acme/
  connection:
    nessie:
      uri: "http://nessie.acme.internal:19120/api/v1"
    s3:
      bucket: "acme-data-lake"
      prefix: "raw/stripe/customers"

logging:
  redaction: true
  level: INFO
```

### Runner Configuration

Runner configs define schedules for orchestrated mode:

```yaml
runner:
  mode: orchestrated
  orchestrator:
    type: dagster
    schedules:
      - name: stripe_customers_hourly
        config: /app/jobs/acme/stripe_customers_to_iceberg.yaml
        cron: "0 * * * *"
    concurrency_per_tenant: 1
```

### Asset Definitions

Asset definitions define the schema, governance metadata, and target configuration:

```yaml
asset:
  name: stripe_customers
  source_type: stripe
  object: customers
  version: "1.0"
  
  schema:
    - name: id
      type: string
      required: true
    - name: email
      type: string
      required: false
      classification: PII
  
  governance:
    owner: data-team@company.com
    tags: [payments, customer-data]
    classification: [PII]
    retention_days: 30
  
  target:
    file_format: parquet
    partitioning: [ingest_date]
    mode: strict
```

## Supported Connectors

- **Stripe**: Payments data (customers, charges, invoices)
- **HubSpot**: CRM data (contacts, deals, companies)
- **Google Drive CSV**: CSV files from Google Drive
- **Google Sheets**: Spreadsheet data
- **CSV**: Local CSV files (for testing and development)
- **Markdown-KV**: Markdown-KV files for LLM-optimized data ingestion
- **PostgreSQL**: Database tables (self-hosted only)
- **MySQL**: Database tables (self-hosted only)

### Markdown-KV Storage Options

Dativo supports three storage patterns for Markdown-KV format:
1. **STRING storage**: Store as STRING column in Iceberg Parquet tables
2. **Raw file storage**: Store files directly in S3/MinIO buckets
3. **Structured storage**: Parse and store as structured data (row-per-KV, document-level, or hybrid)

See [docs/MARKDOWN_KV_STORAGE.md](docs/MARKDOWN_KV_STORAGE.md) for detailed documentation.

## Exit Codes

- `0`: Success
- `1`: Partial success
- `2`: Failure (validation error, missing files, etc.)

## Testing

Dativo uses a two-tier testing approach:

### Unit Tests

Test internal functions (config loading, validation, state management):

```bash
# Run all unit tests
pytest tests/test_*.py -v

# Or using Makefile
make test-unit
```

### Smoke Tests (E2E)

Run actual CLI commands with test fixtures to verify end-to-end execution:

```bash
# Direct CLI command (recommended)
dativo_ingest run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets

# Or using Makefile
make test-smoke
```

Smoke tests are simply running the CLI directly with test fixtures - no special test code needed!

### Run All Tests

```bash
make test
```

See [tests/README.md](tests/README.md) for detailed testing documentation.

Validate schemas:

```bash
make schema-validate
```

## Project Structure

```
/app
  connectors/
    sources/
      stripe.yaml
      hubspot.yaml
      postgres.yaml
      mysql.yaml
      gdrive_csv.yaml
      google_sheets.yaml
    targets/
      iceberg.yaml
      s3.yaml
      minio.yaml
  assets/
    stripe/v1.0/customers.yaml
    hubspot/v1.0/contacts.yaml
    postgres/v1.0/db_orders.yaml
    mysql/v1.0/db_customers.yaml
    gdrive_csv/v1.0/deals_daily.yaml
    google_sheets/v1.0/vendors_master.yaml
  jobs/
    acme/
      stripe_customers_to_iceberg.yaml
      hubspot_contacts_to_iceberg.yaml
      postgres_orders_to_iceberg.yaml
      mysql_customers_to_s3.yaml
      gdrive_deals_to_iceberg.yaml
      gsheets_vendors_to_minio.yaml
  configs/
    runner.yaml
    policy.yaml
  registry/
    connectors.yaml
  src/
    dativo_ingest/
      cli.py
      config.py
      validator.py
      orchestrated.py
      logging.py
```

## License

[Add license information]

