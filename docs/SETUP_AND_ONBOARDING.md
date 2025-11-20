# Setup and Onboarding Guide for Dativo-Ingest

This comprehensive guide provides step-by-step instructions for setting up dativo-ingest and onboarding new infrastructure. It is designed for both human engineers and AI agents to understand the system architecture, configuration requirements, and onboarding processes.

## Table of Contents

1. [Introduction](#introduction)
2. [Directory Structure and File Organization](#directory-structure-and-file-organization)
3. [Component Setup Guides](#component-setup-guides)
4. [Onboarding New Infrastructure](#onboarding-new-infrastructure)
5. [Validation and Testing](#validation-and-testing)
6. [Troubleshooting Guide](#troubleshooting-guide)
7. [Quick Reference](#quick-reference)

---

## Introduction

### What is Dativo-Ingest?

Dativo-Ingest is a **headless, config-driven ingestion engine** that extracts data from third-party SaaS APIs (like Stripe or HubSpot) and databases (like PostgreSQL or MySQL) into vendor-owned object storage (S3, MinIO, Azure Blob) as Iceberg-backed datasets. It is so cutting-edge that even supports Markdown-KV format for LLM-optimized data ingestion.

### Core Concepts

- **Jobs**: Tenant-specific configurations that define what data to extract, from where, and where to store it
- **Assets**: Schema definitions that specify the structure, governance, and compliance requirements for data
- **Connectors**: Tenant-agnostic recipes that define HOW to connect to sources and targets
- **Secrets**: Credentials and connection information stored securely outside of YAML files
- **Infrastructure**: Services required for data ingestion (databases, object storage, catalogs)

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Dativo-Ingest Engine                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │   Jobs       │───▶│  Connectors  │───▶│   Assets     │  │
│  │ (Tenant-Spec)│    │ (Tenant-Agn) │    │  (Schemas)   │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│         │                    │                    │          │
│         └────────────────────┼────────────────────┘          │
│                              │                                │
│                    ┌───────▼────────┐                       │
│                    │  Secrets & Env │                       │
│                    │    Variables   │                       │
│                    └───────┬────────┘                       │
│                            │                                │
│                    ┌───────▼────────┐                       │
│                    │ Infrastructure │                       │
│                    │  (DBs, S3, etc)│                       │
│                    └────────────────┘                       │
└─────────────────────────────────────────────────────────────┘
```

### Prerequisites

- **Python 3.10+**: Required for running the ingestion engine
- **Docker and Docker Compose**: For local infrastructure (databases, MinIO, Nessie)
- **Node.js 18+**: For schema validation (optional, for ODCS validation)
- **Git**: For cloning the repository

---

## Directory Structure and File Organization

### Complete Directory Tree

```
dativo-ingest/
├── connectors/              # Connector recipes (tenant-agnostic)
│   ├── sources/            # Source connector definitions
│   │   ├── stripe.yaml
│   │   ├── hubspot.yaml
│   │   ├── postgres.yaml
│   │   ├── mysql.yaml
│   │   ├── csv.yaml
│   │   ├── gdrive_csv.yaml
│   │   └── google_sheets.yaml
│   └── targets/            # Target connector definitions
│       ├── iceberg.yaml
│       ├── s3.yaml
│       └── minio.yaml
│
├── assets/                 # Asset definitions (ODCS v3.0.2 schemas)
│   ├── stripe/
│   │   └── v1.0/
│   │       └── customers.yaml
│   ├── hubspot/
│   │   └── v1.0/
│   │       └── contacts.yaml
│   ├── postgres/
│   │   └── v1.0/
│   │       └── db_orders.yaml
│   └── csv/
│       └── v1.0/
│           └── employee.yaml
│
├── jobs/                   # Job configurations (tenant-specific)
│   └── {tenant_id}/
│       ├── stripe_customers_to_iceberg.yaml
│       ├── postgres_orders_to_iceberg.yaml
│       └── mysql_customers_to_s3.yaml
│
├── registry/               # Connector registry (capabilities)
│   └── connectors.yaml
│
├── configs/                # Runner and policy configurations
│   ├── runner.yaml
│   └── policy.yaml
│
├── secrets/                # Secrets storage (tenant-organized)
│   └── {tenant_id}/
│       ├── iceberg.env
│       ├── s3.env
│       ├── postgres.env
│       ├── mysql.env
│       ├── stripe.json
│       └── hubspot.json
│
├── state/                  # Incremental sync state (per tenant)
│   └── {tenant_id}/
│       └── {job_name}.json
│
└── src/
    └── dativo_ingest/      # Source code
        ├── cli.py          # CLI entrypoint
        ├── config.py       # Configuration loading
        ├── validator.py    # Validation logic
        └── infrastructure.py  # Infrastructure checks
```

### File Organization Principles

1. **Tenant Isolation**: Jobs and secrets are organized by `tenant_id` to ensure multi-tenancy
2. **Versioning**: Assets use semantic versioning (e.g., `v1.0/`, `v1.1/`) for schema evolution
3. **Separation of Concerns**:
   - **Connectors**: Define HOW to connect (tenant-agnostic)
   - **Assets**: Define WHAT structure to ingest (schema, governance)
   - **Jobs**: Define tenant-specific strategy (compose connectors + assets)
4. **Secrets**: Never stored in YAML files, always in separate files organized by tenant

### Naming Conventions

- **Jobs**: `{source}_{asset}_to_{target}.yaml` (e.g., `stripe_customers_to_iceberg.yaml`)
- **Assets**: `{object_name}.yaml` (e.g., `customers.yaml`, `employees.yaml`)
- **Connectors**: `{connector_type}.yaml` (e.g., `stripe.yaml`, `postgres.yaml`)
- **Secrets**: `{connector_type}.env` or `{connector_type}.json` (e.g., `iceberg.env`, `stripe.json`)

---

## Component Setup Guides

### 3.1 Jobs Configuration

Jobs are **tenant-specific configurations** that define what data to extract, from where, and where to store it.

**Key Concepts:**
- Jobs reference connector recipes (HOW to connect) and asset definitions (WHAT structure to ingest)
- Jobs can override connector defaults with tenant-specific configurations
- Jobs are organized by `tenant_id` for multi-tenancy: `jobs/{tenant_id}/`

**Basic Structure:**
```yaml
tenant_id: acme
source_connector: stripe
source_connector_path: connectors/sources/stripe.yaml
target_connector: iceberg
target_connector_path: connectors/targets/iceberg.yaml
asset: stripe_customers
asset_path: assets/stripe/v1.0/customers.yaml
source:
  objects: [customers]
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
```

For complete job configuration reference with all fields and options, see [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md#job-configuration).

---

### 3.2 Asset Definitions

Asset definitions are **ODCS v3.0.2-compliant YAML files** that define the schema, governance, and target configuration for data.

**Key Components:**
- **Schema**: Field definitions with types, required flags, and classifications
- **Governance**: Team ownership, compliance requirements, data quality monitoring
- **Target Configuration**: File format, partitioning strategy, validation mode

**Basic Structure:**
```yaml
$schema: schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: stripe_customers
version: "1.0"
source_type: stripe
object: customers
target:
  file_format: parquet
  partitioning: [ingest_date]
schema:
  - name: id
    type: string
    required: true
  - name: email
    type: string
    required: true
    classification: PII
team:
  owner: data-team@company.com
compliance:
  classification: [PII]
  regulations: [GDPR, CCPA]
```

**Versioning:** Assets use semantic versioning (v1.0, v1.1, v2.0) stored in `assets/{source_type}/v{version}/`.

For complete asset definition reference with all fields and governance requirements, see [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md#asset-definitions).

---

### 3.3 Secrets Management

Secrets are organized by tenant in `secrets/{tenant_id}/` and support multiple formats:

**File Formats:**
- `.env` files: Key-value pairs (`KEY=value`)
- `.json` files: JSON objects
- Plain text files: Single values

**Example:**
```bash
# secrets/acme/iceberg.env
NESSIE_URI=http://localhost:19120/api/v1
S3_ENDPOINT=http://localhost:9000
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
AWS_REGION=us-east-1
```

**Security:** Never commit secrets to version control. Use secrets management systems in production.

---

### 3.4 Environment Variables

Environment variables are referenced in configs using `${VAR_NAME}` syntax and can be set in secrets files or environment.

**Common Variables:**
- `S3_ENDPOINT`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` - Required for S3/Iceberg targets
- `NESSIE_URI` - Required for Iceberg catalog (if catalog configured)
- `POSTGRES_*`, `MYSQL_*` - Database connection variables
- `STATE_DIR` - State directory path (defaults to `.local/state/`)

**Usage in Configs:**
```yaml
target:
  connection:
    s3:
      endpoint: "${S3_ENDPOINT}"
      bucket: "${S3_BUCKET}"
```

For complete environment variable reference, see the Quick Reference section at the end of this guide.

---

### 3.5 Infrastructure Setup

**Required Services:**
- **S3/MinIO**: Required for all targets (storage)
- **Nessie**: Optional (only if Iceberg catalog is configured)
- **PostgreSQL/MySQL**: Required for database sources

**Local Development:**
```bash
# Start services
docker-compose -f docker-compose.dev.yml up -d

# Create MinIO bucket
mc alias set local http://localhost:9000 minioadmin minioadmin
mc mb local/test-bucket
```

**Service Ports:** Nessie (19120), MinIO (9000/9001), PostgreSQL (5432), MySQL (3306)

The `startup_sequence()` function automatically validates infrastructure connectivity before job execution.

---

## Onboarding New Infrastructure

### 4.1 Step-by-Step Onboarding Process

Follow these steps to onboard new infrastructure into dativo-ingest:

#### Step 1: Identify Infrastructure Requirements

1. **Determine connector type**: Source or target?
2. **Identify service dependencies**: What services are needed?
3. **List required credentials**: What secrets are needed?
4. **Document network requirements**: Ports, endpoints, etc.

#### Step 2: Set Up Services

**Option A: Docker Compose (Local Development)**
```bash
# Add service to docker-compose.dev.yml
# Start services
docker-compose -f docker-compose.dev.yml up -d
```

**Option B: Cloud Services**
- Provision services in your cloud provider
- Configure networking and security groups
- Set up credentials and access policies

#### Step 3: Create Connector Recipe (if New Connector Type)

If the connector type doesn't exist, create a connector recipe:

```yaml
# connectors/sources/new_connector.yaml
name: new_connector
type: source
engine: native
connection_template:
  endpoint: "${NEW_CONNECTOR_ENDPOINT}"
  api_key: "${NEW_CONNECTOR_API_KEY}"
```

#### Step 4: Register Connector in Registry

Add the connector to `registry/connectors.yaml`:

```yaml
connectors:
  new_connector:
    roles: [source]  # or [target] or [source, target]
    category: api    # api, database, files, etc.
    default_engine: native
    engines_supported: [native]
    allowed_in_cloud: true
    supports_incremental: true
    incremental_strategy_default: updated_after
```

#### Step 5: Create Asset Definitions

Create asset definitions for the data you want to ingest:

```yaml
# assets/new_connector/v1.0/object.yaml
$schema: schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: new_connector_object
version: "1.0"
source_type: new_connector
object: object_name
target:
  file_format: parquet
  partitioning: [ingest_date]
schema:
  - name: id
    type: string
    required: true
  # ... more fields
```

#### Step 6: Set Up Secrets

Create secrets files for the new connector:

```bash
# secrets/{tenant_id}/new_connector.env
NEW_CONNECTOR_ENDPOINT=https://api.example.com
NEW_CONNECTOR_API_KEY=...
```

#### Step 7: Configure Environment Variables

Set required environment variables:

```bash
export NEW_CONNECTOR_ENDPOINT="https://api.example.com"
export NEW_CONNECTOR_API_KEY="..."
```

Or add them to `.env` file:
```bash
NEW_CONNECTOR_ENDPOINT=https://api.example.com
NEW_CONNECTOR_API_KEY=...
```

#### Step 8: Create Job Configurations

Create job configurations that use the new connector:

```yaml
# jobs/{tenant_id}/new_connector_object_to_iceberg.yaml
tenant_id: {tenant_id}
source_connector: new_connector
source_connector_path: connectors/sources/new_connector.yaml
target_connector: iceberg
target_connector_path: connectors/targets/iceberg.yaml
asset: new_connector_object
asset_path: assets/new_connector/v1.0/object.yaml
source:
  objects: [object_name]
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
```

#### Step 9: Test and Validate

Run the job to test the new infrastructure:

```bash
dativo_ingest run \
  --config jobs/{tenant_id}/new_connector_object_to_iceberg.yaml \
  --secrets-dir secrets \
  --mode self_hosted
```

---

### 4.2 Adding a New Connector Type

#### Connector Registry Structure

The connector registry (`registry/connectors.yaml`) defines connector capabilities:

```yaml
version: 3

connectors:
  connector_name:
    roles: [source]              # [source], [target], or [source, target]
    category: api                # api, database, files, etc.
    default_engine: native       # native, airbyte, meltano, etc.
    engines_supported: [native] # List of supported engines
    allowed_in_cloud: true      # Can be used in cloud mode
    supports_incremental: true  # Supports incremental sync
    incremental_strategy_default: updated_after  # Default incremental strategy
    objects_supported: ["object1", "object2"]    # Supported objects (optional)
```

#### Connector Recipe Structure

Connector recipes define HOW to connect:

```yaml
# connectors/sources/new_connector.yaml
name: new_connector
type: source
engine: native
connection_template:
  endpoint: "${NEW_CONNECTOR_ENDPOINT}"
  api_key: "${NEW_CONNECTOR_API_KEY}"
  timeout: 30
rate_limits:
  requests_per_second: 10
  burst_size: 20
```

#### Required vs Optional Fields

**Required Fields:**
- `name`: Connector name
- `type`: `source` or `target`
- `engine`: Engine type (e.g., `native`, `airbyte`)

**Optional Fields:**
- `connection_template`: Connection configuration template
- `rate_limits`: Rate limiting configuration
- `incremental_strategy`: Incremental sync strategy

#### Role Definitions

- **`[source]`**: Source only - can only read data
- **`[target]`**: Target only - can only write data
- **`[source, target]`**: Bidirectional - can read and write data

#### Engine Configuration

- **`native`**: Python-based native implementation
- **`airbyte`**: Airbyte connector
- **`meltano`**: Meltano tap/target
- **`spark`**: Spark-based processing

#### Incremental Strategy Support

- **`created`**: Track by creation timestamp
- **`updated_after`**: Track by last update timestamp
- **`file_modified_time`**: Track by file modification time
- **`updated_at`**: Track by `updated_at` field

#### Example: Adding a New Database Connector

**1. Register in Connector Registry:**
```yaml
# registry/connectors.yaml
connectors:
  sqlite:
    roles: [source]
    category: database
    default_engine: native
    engines_supported: [native]
    allowed_in_cloud: false
    supports_incremental: true
    incremental_strategy_default: updated_at
    requires_tables: true
    supports_queries: true
```

**2. Create Connector Recipe:**
```yaml
# connectors/sources/sqlite.yaml
name: sqlite
type: source
engine: native
connection_template:
  database_path: "${SQLITE_DATABASE_PATH}"
```

**3. Add Infrastructure Validation:**
Update `src/dativo_ingest/infrastructure.py` to validate SQLite connectivity.

---

### 4.3 Adding a New Data Source

#### Step 1: Create Asset Definition

```yaml
# assets/new_source/v1.0/object.yaml
$schema: schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: new_source_object
version: "1.0"
source_type: new_source
object: object_name
target:
  file_format: parquet
  partitioning: [ingest_date]
schema:
  - name: id
    type: string
    required: true
  - name: name
    type: string
    required: true
```

#### Step 2: Set Up Source Connector

Ensure the source connector is configured:
- Connector recipe exists in `connectors/sources/`
- Connector is registered in `registry/connectors.yaml`

#### Step 3: Configure Secrets

Create secrets file:
```bash
# secrets/{tenant_id}/new_source.env
NEW_SOURCE_API_KEY=...
NEW_SOURCE_ENDPOINT=https://api.example.com
```

#### Step 4: Create Job Configuration

```yaml
# jobs/{tenant_id}/new_source_object_to_iceberg.yaml
tenant_id: {tenant_id}
source_connector: new_source
source_connector_path: connectors/sources/new_source.yaml
target_connector: iceberg
target_connector_path: connectors/targets/iceberg.yaml
asset: new_source_object
asset_path: assets/new_source/v1.0/object.yaml
source:
  objects: [object_name]
  incremental:
    lookback_days: 1
```

#### Example: Adding a New API Source

**Asset Definition:**
```yaml
# assets/slack/v1.0/messages.yaml
$schema: schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: slack_messages
version: "1.0"
source_type: slack
object: messages
target:
  file_format: parquet
  partitioning: [ingest_date]
schema:
  - name: message_id
    type: string
    required: true
  - name: channel_id
    type: string
    required: true
  - name: user_id
    type: string
    required: true
  - name: text
    type: string
    required: true
  - name: timestamp
    type: timestamp
    required: true
```

**Job Configuration:**
```yaml
# jobs/acme/slack_messages_to_iceberg.yaml
tenant_id: acme
source_connector: slack
source_connector_path: connectors/sources/slack.yaml
target_connector: iceberg
target_connector_path: connectors/targets/iceberg.yaml
asset: slack_messages
asset_path: assets/slack/v1.0/messages.yaml
source:
  objects: [messages]
  incremental:
    lookback_days: 7
```

---

### 4.4 Adding a New Target

#### Step 1: Target Connector Configuration

Ensure the target connector is configured:
- Connector recipe exists in `connectors/targets/`
- Connector is registered in `registry/connectors.yaml`

#### Step 2: Storage Configuration

Configure storage (S3, MinIO, Azure Blob, etc.):

```yaml
# connectors/targets/azure_blob.yaml
name: azure_blob
type: target
engine: native
connection_template:
  account_name: "${AZURE_STORAGE_ACCOUNT_NAME}"
  account_key: "${AZURE_STORAGE_ACCOUNT_KEY}"
  container: "${AZURE_STORAGE_CONTAINER}"
```

#### Step 3: Catalog Setup (Optional)

If using Iceberg with catalog:
- Configure Nessie or other catalog
- Set `NESSIE_URI` environment variable
- Configure catalog in target connection

#### Step 4: Partitioning Strategy

Define partitioning strategy in asset definition:

```yaml
target:
  file_format: parquet
  partitioning: [ingest_date, region]  # Partition columns
```

#### Example: Adding Azure Blob Storage

**Connector Recipe:**
```yaml
# connectors/targets/azure_blob.yaml
name: azure_blob
type: target
engine: native
connection_template:
  account_name: "${AZURE_STORAGE_ACCOUNT_NAME}"
  account_key: "${AZURE_STORAGE_ACCOUNT_KEY}"
  container: "${AZURE_STORAGE_CONTAINER}"
```

**Secrets:**
```bash
# secrets/acme/azure_blob.env
AZURE_STORAGE_ACCOUNT_NAME=...
AZURE_STORAGE_ACCOUNT_KEY=...
AZURE_STORAGE_CONTAINER=...
```

**Job Configuration:**
```yaml
# jobs/acme/stripe_customers_to_azure_blob.yaml
tenant_id: acme
source_connector: stripe
source_connector_path: connectors/sources/stripe.yaml
target_connector: azure_blob
target_connector_path: connectors/targets/azure_blob.yaml
asset: stripe_customers
asset_path: assets/stripe/v1.0/customers.yaml
target:
  connection:
    azure_blob:
      account_name: "${AZURE_STORAGE_ACCOUNT_NAME}"
      container: "${AZURE_STORAGE_CONTAINER}"
      prefix: "raw/stripe/customers"
```

---

## Validation and Testing

### How startup_sequence() Validates Everything

The `startup_sequence()` function performs comprehensive validation:

1. **Load Jobs**: Loads all job configurations from the job directory
2. **Determine Tenant ID**: Infers or uses provided tenant ID
3. **Set Up Logging**: Initializes structured JSON logging
4. **Load Secrets**: Loads secrets from the secrets directory
5. **Validate Environment Variables**: Checks required environment variables
6. **Validate Infrastructure**: Checks infrastructure connectivity
7. **Initialize State Management**: Sets up state directories
8. **Validate Job Configurations**: Validates all job configs against registry

### Common Validation Errors and Fixes

**Error: Missing required environment variable**
```
ERROR: Missing required environment variable: S3_ENDPOINT
```
**Fix**: Set the environment variable or add it to secrets file.

**Error: Infrastructure validation failed**
```
ERROR: S3 connectivity failed: Cannot connect to S3 at http://localhost:9000
```
**Fix**: Start MinIO service or check endpoint URL.

**Error: Job validation failed**
```
ERROR: Job validation failed: Connector 'unknown_connector' not found in registry
```
**Fix**: Register the connector in `registry/connectors.yaml`.

**Error: Schema validation failed**
```
ERROR: Asset definition has empty 'schema' field
```
**Fix**: Add schema fields to the asset definition.

### Testing Checklist

Before running jobs in production, verify:

- [ ] All required environment variables are set
- [ ] Infrastructure services are running and accessible
- [ ] Secrets are configured correctly
- [ ] Connector recipes are valid
- [ ] Asset definitions have complete schemas
- [ ] Job configurations reference valid connectors and assets
- [ ] State directories are writable
- [ ] Network connectivity to all services

### Smoke Test Examples

**Run All Smoke Tests:**
```bash
./tests/run_all_smoke_tests.sh
```

**Run Specific Job:**
```bash
dativo_ingest run \
  --config tests/fixtures/jobs/csv_employee_to_iceberg.yaml \
  --secrets-dir tests/fixtures/secrets \
  --mode self_hosted
```

---

## Troubleshooting Guide

### Common Setup Issues

#### Issue: Services Not Starting

**Symptoms:**
- Docker containers fail to start
- Port conflicts
- Health checks failing

**Solutions:**
```bash
# Check container status
docker-compose -f docker-compose.dev.yml ps

# View logs
docker-compose -f docker-compose.dev.yml logs

# Check port conflicts
lsof -i :19120  # Nessie
lsof -i :9000   # MinIO
lsof -i :5432   # PostgreSQL
```

#### Issue: Missing Dependencies

**Symptoms:**
- `ModuleNotFoundError` when running CLI
- Import errors

**Solutions:**
```bash
# Install dependencies
pip install -r requirements.txt
pip install -e .

# Verify installation
python -m dativo_ingest.cli --help
```

### Environment Variable Problems

#### Issue: Environment Variables Not Set

**Symptoms:**
- `ERROR: Missing required environment variable`
- Connection failures

**Solutions:**
```bash
# Set variables in shell
export S3_ENDPOINT="http://localhost:9000"
export AWS_ACCESS_KEY_ID="minioadmin"

# Or use .env file
source .env

# Verify variables are set
echo $S3_ENDPOINT
```

#### Issue: Environment Variable Expansion Not Working

**Symptoms:**
- `${VAR_NAME}` not replaced in configs
- Connection strings contain literal `${VAR_NAME}`

**Solutions:**
- Ensure variables are set before running CLI
- Use `source .env` to load variables
- Check variable names match exactly (case-sensitive)

### Infrastructure Connectivity Issues

#### Issue: Cannot Connect to S3/MinIO

**Symptoms:**
- `S3 connectivity failed: Cannot connect to S3`
- Timeout errors

**Solutions:**
```bash
# Check MinIO is running
docker ps | grep minio

# Test connectivity
curl http://localhost:9000/minio/health/live

# Check credentials
mc alias set local http://localhost:9000 minioadmin minioadmin
mc ls local
```

#### Issue: Cannot Connect to Nessie

**Symptoms:**
- `Nessie connectivity failed: Cannot connect to Nessie`
- 404 or connection refused errors

**Solutions:**
```bash
# Check Nessie is running
docker ps | grep nessie

# Test connectivity
curl http://localhost:19120/api/v1/config

# Check NESSIE_URI environment variable
echo $NESSIE_URI
```

#### Issue: Cannot Connect to Database

**Symptoms:**
- Database connection errors
- Authentication failures

**Solutions:**
```bash
# Check database is running
docker ps | grep postgres  # or mysql

# Test connection
psql -h localhost -p 5432 -U postgres -d adventureworks

# Verify credentials in secrets file
cat secrets/{tenant_id}/postgres.env
```

### Secret Loading Failures

#### Issue: Secrets Not Found

**Symptoms:**
- `Missing required secrets for connector`
- Empty secrets dictionary

**Solutions:**
- Verify secrets directory structure: `secrets/{tenant_id}/`
- Check file names match connector type: `postgres.env`, `iceberg.env`
- Ensure secrets directory is readable

#### Issue: Invalid Secret Format

**Symptoms:**
- JSON parsing errors
- Key-value parsing errors

**Solutions:**
- Verify `.env` files use `KEY=value` format
- Verify `.json` files are valid JSON
- Check for special characters that need escaping

### Validation Errors

#### Issue: Job Validation Failed

**Symptoms:**
- `Job validation failed: Connector not found`
- `Job validation failed: Invalid connector type`

**Solutions:**
- Register connector in `registry/connectors.yaml`
- Verify connector recipe exists
- Check connector type matches registry

#### Issue: Schema Validation Failed

**Symptoms:**
- `Asset definition has empty 'schema' field`
- Schema validation errors during execution

**Solutions:**
- Add schema fields to asset definition
- Verify schema follows ODCS v3.0.2 format
- Check field types and required flags

---

## Quick Reference

### Command Cheat Sheet

```bash
# Run single job
dativo_ingest run --config jobs/acme/stripe_customers_to_iceberg.yaml --secrets-dir secrets --mode self_hosted

# Run all jobs in directory
dativo_ingest run --job-dir jobs/acme --secrets-dir secrets --mode self_hosted

# Start orchestrated mode
dativo_ingest start orchestrated --runner-config configs/runner.yaml

# Run smoke tests
./tests/run_all_smoke_tests.sh

# Run unit tests
pytest tests/test_*.py -v

# Validate schemas
make schema-validate
```

### File Path Templates

**Jobs:**
```
jobs/{tenant_id}/{source}_{asset}_to_{target}.yaml
```

**Assets:**
```
assets/{source_type}/v{version}/{object_name}.yaml
```

**Secrets:**
```
secrets/{tenant_id}/{connector_type}.env
secrets/{tenant_id}/{connector_type}.json
```

**State:**
```
state/{tenant_id}/{job_name}.json
```

### Environment Variable Reference

| Variable | Required For | Default | Example |
|----------|-------------|---------|---------|
| `S3_ENDPOINT` | Iceberg, S3 | None | `http://localhost:9000` |
| `AWS_ACCESS_KEY_ID` | Iceberg, S3 | None | `minioadmin` |
| `AWS_SECRET_ACCESS_KEY` | Iceberg, S3 | None | `minioadmin` |
| `AWS_REGION` | Iceberg, S3 | `us-east-1` | `us-east-1` |
| `NESSIE_URI` | Iceberg (catalog) | None | `http://localhost:19120/api/v1` |
| `S3_BUCKET` | Iceberg, S3 | None | `test-bucket` |
| `POSTGRES_HOST` | PostgreSQL | None | `localhost` |
| `POSTGRES_PORT` | PostgreSQL | `5432` | `5432` |
| `POSTGRES_DB` | PostgreSQL | None | `adventureworks` |
| `POSTGRES_USER` | PostgreSQL | None | `postgres` |
| `POSTGRES_PASSWORD` | PostgreSQL | None | `postgres` |
| `MYSQL_HOST` | MySQL | None | `localhost` |
| `MYSQL_PORT` | MySQL | `3306` | `3306` |
| `MYSQL_DB` | MySQL | None | `employees` |
| `MYSQL_USER` | MySQL | None | `root` |
| `MYSQL_PASSWORD` | MySQL | None | `root` |

### Connector Capabilities Matrix

| Connector | Roles | Category | Cloud Mode | Incremental | Default Engine |
|-----------|-------|----------|------------|-------------|----------------|
| `stripe` | source | payments | ✅ | ✅ | airbyte |
| `hubspot` | source | crm | ✅ | ✅ | airbyte |
| `csv` | source, target | files | ✅ | ✅ | native |
| `postgres` | source, target | database | ❌ | ✅ | meltano |
| `mysql` | source, target | database | ❌ | ✅ | meltano |
| `iceberg` | target | lake | ✅ | N/A | native |
| `s3` | source, target | storage | ✅ | N/A | native |
| `minio` | source, target | storage | ✅ | N/A | native |

### Onboarding Checklist

Use this checklist when onboarding new infrastructure:

- [ ] **Identify Requirements**
  - [ ] Connector type (source/target)
  - [ ] Service dependencies
  - [ ] Required credentials
  - [ ] Network requirements

- [ ] **Set Up Services**
  - [ ] Services running and accessible
  - [ ] Health checks passing
  - [ ] Ports open and accessible

- [ ] **Create Connector Recipe** (if new type)
  - [ ] Connector recipe created
  - [ ] Registered in `registry/connectors.yaml`
  - [ ] Connection template defined

- [ ] **Create Asset Definitions**
  - [ ] Asset definition created
  - [ ] Schema defined
  - [ ] Governance metadata added

- [ ] **Set Up Secrets**
  - [ ] Secrets files created
  - [ ] Credentials configured
  - [ ] Environment variables set

- [ ] **Create Job Configurations**
  - [ ] Job config created
  - [ ] References valid connectors and assets
  - [ ] Tenant-specific overrides configured

- [ ] **Test and Validate**
  - [ ] Job runs successfully
  - [ ] Data extracted correctly
  - [ ] Data written to target
  - [ ] Validation passes

---

## Additional Resources

- [QUICKSTART.md](../QUICKSTART.md) - Quick start guide
- [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) - Configuration reference
- [INGESTION_EXECUTION.md](INGESTION_EXECUTION.md) - Execution flow documentation
- [CUSTOM_PLUGINS.md](CUSTOM_PLUGINS.md) - Custom plugins guide
- [tests/README.md](../tests/README.md) - Testing documentation

---

**Last Updated**: 2024-01-XX
**Version**: 1.0

