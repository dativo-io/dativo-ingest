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

infrastructure:
  provider: aws
  region: us-east-1
  runtime:
    type: aws_fargate
  resource_identifiers:
    cluster_name: "{{terraform_outputs.cluster_name}}"
    service_name: "{{terraform_outputs.service_name}}"
    service_endpoint: "{{terraform_outputs.service_endpoint}}"
  tags:
    job_name: hubspot_contacts_to_iceberg
    team: marketing_ops
    pipeline_type: ingestion
    environment: prod
    cost_center: FINOPS-ACME

logging:
  redaction: true
  level: INFO
```

### Infrastructure Runtime Metadata

- `provider`: Cloud provider managing execution (one of `aws`, `azure`, `gcp`).
- `runtime.type`: Normalised runtime identifier (`aws_fargate`, `azure_container_apps`, `gcp_cloud_run`).
- `resource_identifiers`: References to Terraform outputs using the `{{terraform_outputs.<name>}}` syntax. These are resolved when the pipeline injects module outputs into the job definition (e.g., cluster name, service endpoint).
- `tags`: Metadata propagated into Terraform so every resource is tagged/labelled with ownership, environment, pipeline classification, and cost centre data. The keys `job_name`, `team`, `pipeline_type`, `environment`, and `cost_center` are required. The environment tag must match the job’s `environment` field.

Validation ensures only supported provider/runtime combinations are used and that all required metadata is present.

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
