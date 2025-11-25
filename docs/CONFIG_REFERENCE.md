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
- `infrastructure`: Infrastructure configuration for externally provisioned resources (e.g., Terraform)

### Infrastructure Configuration

Jobs can reference infrastructure provisioned outside of Dativo (e.g., via Terraform, CloudFormation, or Pulumi). The `infrastructure` block describes the runtime environment and metadata that flows into infrastructure-as-code modules.

**Example with Terraform-provisioned EMR cluster:**

```yaml
infrastructure:
  provider: terraform
  
  terraform:
    module_source: "git::https://github.com/org/infra.git//modules/emr"
    module_version: "v2.1.0"
    workspace: "prod"
  
  runtime:
    platform: emr
    compute:
      cluster_id: "${EMR_CLUSTER_ID}"
      instance_type: "m5.xlarge"
      instance_count: 5
      auto_scaling:
        enabled: true
        min_instances: 3
        max_instances: 10
    
    network:
      vpc_id: "vpc-0a1b2c3d"
      subnet_ids: ["subnet-abc123", "subnet-def456"]
      security_group_ids: ["sg-xyz789"]
  
  metadata:
    tags:
      CostCenter: "data-engineering"
      Project: "customer-analytics"
      Environment: "production"
    
    variables:
      enable_spot_instances: true
      log_retention_days: 30
```

**Example with Kubernetes:**

```yaml
infrastructure:
  provider: terraform
  
  runtime:
    platform: kubernetes
    namespace: "data-pipelines-prod"
    service_account: "dativo-job-runner"
    
    compute:
      instance_type: "n2-standard-4"
      instance_count: 3
  
  metadata:
    labels:
      app: "dativo-ingestion"
      team: "data-platform"
      tenant: "acme"
    
    annotations:
      prometheus.io/scrape: "true"
      prometheus.io/port: "8080"
```

For comprehensive documentation, see [INFRASTRUCTURE.md](INFRASTRUCTURE.md).

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

- [SETUP_AND_ONBOARDING.md](SETUP_AND_ONBOARDING.md) - Comprehensive setup and onboarding guide
- [INFRASTRUCTURE.md](INFRASTRUCTURE.md) - Infrastructure configuration for Terraform-provisioned resources
- [MARKDOWN_KV_STORAGE.md](MARKDOWN_KV_STORAGE.md) - Detailed Markdown-KV storage documentation
- [INGESTION_EXECUTION.md](INGESTION_EXECUTION.md) - Execution flow documentation
- [SCHEMA_VALIDATION.md](SCHEMA_VALIDATION.md) - Schema validation guide
