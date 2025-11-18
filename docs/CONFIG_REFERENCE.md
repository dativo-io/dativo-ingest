# Configuration Reference

## Job Configuration (New Architecture)

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

# Optional: generate enriched metadata via LLM (disabled by default)
metadata_generation:
  enabled: true
  source_api_definition_path: /app/apis/stripe_openapi.yaml
  prompt_template: |
    Dataset name: {asset_name}
    Domain: {domain}
    Tenant: {tenant}
    Source type: {source_type}
    Source objects: {source_objects}

    API:
    {api_definition}
  llm:
    provider: openai
    model: gpt-4o-mini
    api_key_env: OPENAI_API_KEY
    temperature: 0.2
    max_tokens: 400
```

### LLM Metadata Generation

- **disabled by default**; set `metadata_generation.enabled: true` to opt-in.
- Requires a **source API definition file** (YAML/JSON/OpenAPI) referenced via `source_api_definition_path`.
- Provide LLM credentials under `metadata_generation.llm`. Supply either `api_key` or reference an environment variable with `api_key_env`.
- Generates a structured summary (`summary`, `recommended_tags`, `field_insights`, etc.) that is:
  - Logged alongside job metrics.
  - Attached to Iceberg/S3 object metadata (prefixed with `llm-*`) for downstream discovery.
- Customize prompts with `prompt_template` placeholders (`{asset_name}`, `{domain}`, `{source_type}`, `{api_definition}`, ...). If omitted, the default template is used.

## Asset Definition (ODCS v3.0.2)

Asset definitions follow the **Open Data Contract Standard (ODCS) v3.0.2** structure with dativo-specific extensions:

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

## Architecture

- **Connectors** (`/connectors/`): Tenant-agnostic recipes that define HOW to connect
- **Assets** (`/assets/`): Schema and governance definitions (ODCS v3.0.2) that define WHAT structure to ingest
- **Jobs** (`/jobs/<tenant>/`): Tenant-specific strategy implementations that compose connectors with assets
