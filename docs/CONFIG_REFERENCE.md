# Configuration Reference

Complete reference guide for configuring jobs, assets, connectors, and storage options in dativo-ingest.

## Table of Contents

1. [Job Configuration](#job-configuration)
2. [Asset Definitions](#asset-definitions)
3. [Markdown-KV Storage](#markdown-kv-storage)
4. [Architecture Overview](#architecture-overview)
5. [Additional Resources](#additional-resources)

---

## Job Configuration

Job configurations define the source connector, target connector, asset, and tenant-specific overrides for data ingestion.

### Structure

Job configs define the source connector, target connector, asset, and tenant-specific overrides:

```yaml
tenant_id: acme
environment: prod

# Reference to source connector recipe
source_connector: hubspot
source_connector_path: /app/connectors/sources/hubspot.yaml

# Reference to target connector recipe
target_connector: iceberg
target_connector_path: /app/connectors/targets/iceberg.yaml

# Reference to asset definition
asset: hubspot_contacts
asset_path: /app/assets/hubspot/v1.0/contacts.yaml

# Source configuration
source:
  objects: [contacts]
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
      prefix: "raw/hubspot/contacts"

logging:
  redaction: true
  level: INFO
```

### Required Fields

- `tenant_id`: Tenant identifier
- `source_connector`: Source connector type
- `source_connector_path`: Path to source connector recipe
- `target_connector`: Target connector type
- `target_connector_path`: Path to target connector recipe
- `asset`: Asset name
- `asset_path`: Path to asset definition

### Optional Fields

- `environment`: Environment name (defaults to `prod`)
- `source`: Source-specific configuration overrides
- `target`: Target-specific configuration overrides
- `schema_validation_mode`: Validation mode (`strict` or `warn`, defaults to `strict`)
- `logging`: Logging configuration (level, redaction)
- `catalog`: Optional lineage publishing block (see below)

### Data Catalog Block

Add the `catalog` block to push lineage metadata into external data catalogs after each run. The block accepts either a single target object or a `targets` array.

```yaml
catalog:
  targets:
    - type: aws_glue
      database: analytics
      table: customers
      region: us-east-1
    - type: databricks_unity
      workspace_url: https://example.cloud.databricks.com
      token: "${DATABRICKS_TOKEN}"
      catalog: main
      schema: analytics
      table: customers
    - type: openmetadata
      service: lakehouse_demo
      database: analytics
      schema: gold
      table: customers
      uri: "${OPENMETADATA_API:-http://localhost:8585/api}"
```

| Provider (`type`) | Required Keys | Notes |
| --- | --- | --- |
| `aws_glue` | `database` | Optional: `table`, `region`, `connection.database`, `connection.region` |
| `databricks_unity` | `workspace_url`, `token` | Optional: `catalog`, `schema`, `table`, `connection.workspace_url`, `connection.token` |
| `nessie` | none (reuses target config) | Optional: override `catalog`, `branch`, `warehouse`, `connection` |
| `openmetadata` | `uri` | Optional: `service`, `database`, `schema`, `table`, `token` |

Set `enabled: false` on a target to temporarily disable publishing without removing its configuration. Local smoke test: `pytest tests/test_data_catalogs.py::test_openmetadata_publisher_smoke -q`.

---

## Asset Definitions

Asset definitions follow the **Open Data Contract Standard (ODCS) v3.0.2** structure with dativo-specific extensions.

```yaml
$schema: schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
id: 550e8400-e29b-41d4-a716-446655440000
name: csv_person
version: "1.0"
status: active
domain: dativo
dataProduct: adventureworks
tenant: test_tenant
description:
  purpose: "Person/contact data from AdventureWorks database"
  limitations: null
  usage: "Used for customer contact information and demographics"
tags: [adventureworks, person, test-data]

# Dativo extensions
source_type: csv
object: Person
target:
  file_format: parquet
  partitioning: [ingest_date]
  mode: strict

# Schema definition
schema:
  - name: BusinessEntityID
    type: integer
    required: true
  - name: FirstName
    type: string
    required: true

# Governance sections
data_quality:
  expectations: []
  monitoring:
    enabled: true
    oncall_rotation: data-ops-oncall@company.com
  alerts:
    channels: [slack, email]
    thresholds: {}

team:
  owner: data-team@company.com
  roles:
    - name: Data Engineer
      email: engineer@company.com
      responsibility: ingestion

compliance:
  classification: [PII]
  regulations: [GDPR, CCPA]
  retention_days: 90
  security:
    access_control: role_based
    encryption_required: true
  user_consent_required: false

change_management:
  policy: non-breaking
  approval_required: true
  notification_channels: [slack, email]
  version_history: true
```

### Key Features

- **ODCS Compliance**: Follows ODCS v3.0.2 flat structure (no nested `asset:` wrapper)
- **Schema Reference**: Each asset explicitly references `schemas/odcs/dativo-odcs-3.0.2-extended.schema.json`
- **Governance Requirements**: All assets must satisfy:
  1. Strong ownership (`team.owner` required)
  2. Regulatory compliance (`compliance` section)
  3. Data quality monitoring (`data_quality.monitoring` with oncall rotation)
  4. Change management (`change_management` section)

### Required Sections

- `schema`: Field definitions with types and required flags
- `team.owner`: Data owner email (required)
- `compliance`: Regulatory compliance information
- `data_quality.monitoring`: Data quality monitoring configuration
- `change_management`: Change management policy

For detailed asset definition guide, see [SETUP_AND_ONBOARDING.md](SETUP_AND_ONBOARDING.md#32-asset-definitions).

---

## Markdown-KV Storage

Dativo supports three storage options for Markdown-KV format (LLM-optimized data):

### Option 1: Store as STRING in Iceberg

Store Markdown-KV content as a STRING column in Parquet tables:

```yaml
target:
  file_format: parquet
  markdown_kv_storage:
    mode: "string"
```

### Option 2: Store Raw Files in S3/MinIO

Store Markdown-KV files directly in S3/MinIO buckets:

```yaml
target:
  type: s3  # or minio
  connection:
    bucket: "llm-data"
  markdown_kv_storage:
    mode: "raw_file"
    file_extension: ".mdkv"  # or ".md"
    path_pattern: "docs/{doc_id}.mdkv"  # Optional
```

### Option 3: Parse and Store as Structured Data

Parse Markdown-KV into structured format with three patterns:

**Row-per-KV (query-friendly):**
```yaml
target:
  file_format: parquet
  markdown_kv_storage:
    mode: "structured"
    structured_pattern: "row_per_kv"
# Use asset: assets/markdown_kv/v1.0/kv_lines.yaml
```

**Document-level (compact):**
```yaml
target:
  file_format: parquet
  markdown_kv_storage:
    mode: "structured"
    structured_pattern: "document_level"
# Use asset: assets/markdown_kv/v1.0/docs.yaml
```

**Hybrid (both patterns):**
```yaml
target:
  file_format: parquet
  markdown_kv_storage:
    mode: "structured"
    structured_pattern: "hybrid"
# Requires dual-write or two asset definitions
```

For detailed documentation, see [MARKDOWN_KV_STORAGE.md](MARKDOWN_KV_STORAGE.md).

---

## Architecture Overview

### Component Hierarchy

- **Connectors** (`/connectors/`): Tenant-agnostic recipes that define HOW to connect
- **Assets** (`/assets/`): Schema and governance definitions (ODCS v3.0.2) that define WHAT structure to ingest
- **Jobs** (`/jobs/<tenant>/`): Tenant-specific strategy implementations that compose connectors with assets

### Configuration Flow

1. **Job Configuration** references connector recipes and asset definitions
2. **Connector Recipes** provide default connection templates and capabilities
3. **Asset Definitions** provide schema and governance metadata
4. **Job Overrides** customize connectors and assets for tenant-specific needs

---

## Additional Resources

## Engine Framework

Dativo-ingest supports multiple engine types for connectors, allowing you to choose the best approach for each data source.

### Supported Engines

- **`native`**: Python-based native implementation (default for file connectors)
- **`airbyte`**: Airbyte Docker containers (default for SaaS API connectors)
- **`meltano`**: Meltano taps/targets (planned)
- **`singer`**: Singer taps (planned)

### Engine Selection

The engine type is determined from the connector recipe's `default_engine.type` field:

```yaml
# connectors/hubspot.yaml
default_engine:
  type: airbyte
  options:
    airbyte:
      docker_image: "airbyte/source-hubspot:0.2.0"
      streams_default: ["contacts", "deals", "companies"]
      start_date_default: "2024-01-01"
```

### Airbyte Engine

The Airbyte engine executes Airbyte source connectors as Docker containers:

**Configuration:**
- `docker_image`: Docker image name (e.g., `airbyte/source-hubspot:0.2.0`)
- `streams_default`: Default streams to extract
- `start_date_default`: Default start date for incremental sync

**Credentials:**
- API keys are automatically mapped from environment variables
- Service account files are loaded from configured paths

**Incremental Sync:**
- Supports cursor-based incremental sync
- State is managed via Airbyte state messages
- Integrates with Dativo's incremental state manager

**Example Connector Recipe:**
```yaml
name: hubspot
type: hubspot
default_engine:
  type: airbyte
  options:
    airbyte:
      docker_image: "airbyte/source-hubspot:0.2.0"
      streams_default: ["contacts", "deals", "companies"]
      start_date_default: "2024-01-01"
credentials:
  type: api_key
  from_env: HUBSPOT_API_KEY
incremental:
  strategy: updated_after
  cursor_field_default: updatedAt
```

### Multi-Engine Connectors

Some connectors support multiple engines. The engine is selected based on the connector recipe configuration:

```yaml
# Google Drive CSV - supports native, airbyte, meltano
default_engine:
  type: native  # Default
  options:
    native:
      api_version: "v3"
    airbyte:
      docker_image: "airbyte/source-google-drive:latest"
    meltano:
      tap_name: "tap-google-drive"
```

The connector will automatically use the specified engine type when executing.

### Dagster Compatibility

All engine-based connectors are fully compatible with Dagster orchestration:

- **Exit Codes**: Return proper exit codes (0=success, 1=partial, 2=failure)
- **Structured Logging**: All events logged with `event_type` and metadata
- **State Management**: Incremental state persists across Dagster runs
- **Error Handling**: Errors are retryable via Dagster retry policies
- **Docker Execution**: Containers run in subprocess context for Dagster compatibility

## Additional Resources

- [SETUP_AND_ONBOARDING.md](SETUP_AND_ONBOARDING.md) - Comprehensive setup and onboarding guide
- [MARKDOWN_KV_STORAGE.md](MARKDOWN_KV_STORAGE.md) - Detailed Markdown-KV storage documentation
- [INGESTION_EXECUTION.md](INGESTION_EXECUTION.md) - Execution flow documentation
- [SCHEMA_VALIDATION.md](SCHEMA_VALIDATION.md) - Schema validation guide
