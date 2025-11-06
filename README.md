# Dativo Ingestion Platform

A headless, config-driven ingestion engine. Extracts data from third party SaaS APIs(like Stripe or Hubspot) and databases(like Postgres or Mysql) into vendor-owned object storage (S3, MinIO, Azure Blob) as Iceberg-backed datasets.

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
  -v $(pwd)/configs:/app/configs \
  -v $(pwd)/specs:/app/specs:ro \
  -v $(pwd)/secrets:/app/secrets \
  -v $(pwd)/state:/app/state \
  dativo:1.1.0 run --config /app/configs/jobs/stripe.yaml --mode self_hosted
```

3. Start orchestrated mode:
```bash
docker run --rm -p 3000:3000 \
  -v $(pwd)/configs:/app/configs \
  -v $(pwd)/specs:/app/specs:ro \
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

Job configs define the source, target, and execution parameters:

```yaml
tenant_id: acme
environment: prod

source:
  type: stripe
  credentials:
    from_env: STRIPE_API_KEY
  objects: [customers]
  incremental:
    strategy: created
    cursor_field: created
    lookback_days: 1
    state_path: /state/acme/stripe.customers.state.json

target:
  type: iceberg
  catalog: nessie
  branch: acme
  warehouse: s3://lake/acme/
  file_format: parquet

asset_definition: /app/specs/stripe/v1.0/customers.yaml

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
      - name: stripe_hourly
        config: /app/configs/jobs/stripe.yaml
        cron: "0 * * * *"
    concurrency_per_tenant: 1
```

### Asset Definitions

Asset specs define the schema and metadata for datasets:

```yaml
asset:
  tenant_id: acme
  source: stripe
  object: customers
  mode: strict
  schema:
    - name: id
      type: string
      required: true
    - name: email
      type: string
      required: false
  file_format: parquet
  partitioning: [ingest_date]
  target_path: s3://lake/acme/raw/stripe/customers/
  iceberg:
    catalog: nessie
    branch: acme
```

## Supported Connectors

- **Stripe**: Payments data (customers, charges, invoices)
- **HubSpot**: CRM data (contacts, deals, companies)
- **Google Drive CSV**: CSV files from Google Drive
- **Google Sheets**: Spreadsheet data
- **PostgreSQL**: Database tables (self-hosted only)
- **MySQL**: Database tables (self-hosted only)

## Exit Codes

- `0`: Success
- `1`: Partial success
- `2`: Failure (validation error, missing files, etc.)

## Testing

Run unit tests:

```bash
pytest tests/
```

Validate schemas:

```bash
make schema-validate
```

## Project Structure

```
/app
  configs/
    runner.yaml
    jobs/
      stripe.yaml
      hubspot.yaml
      gdrive_csv.yaml
      google_sheets.yaml
      postgres.yaml
      mysql.yaml
  registry/
    connectors.yaml
    templates/
      *.yaml
  specs/
    <connector>/v1.0/*.yaml
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

