# Connector Reference

Complete reference for all available connectors in the Dativo Ingestion Platform.

## Overview

Connectors are tenant-agnostic, reusable YAML recipes that define how to connect to data sources and targets. Each connector specifies:
- **Connection details**: Credentials, endpoints, rate limits
- **Engine support**: Native, Airbyte, Meltano, Singer, JDBC, Spark
- **Capabilities**: Supported objects, incremental strategies, roles (source/target)
- **Metadata**: Registered in `registry/connectors.yaml` with standardized patterns

## Connector Capabilities Matrix

| Connector | Roles | Category | Cloud Mode | Incremental | Default Engine | Objects Supported |
|-----------|-------|----------|------------|-------------|----------------|-------------------|
| `stripe` | source | payments | ✅ | ✅ | airbyte | charges, customers, invoices |
| `hubspot` | source | crm | ✅ | ✅ | airbyte | contacts, deals, companies |
| `gdrive_csv` | source | files | ✅ | ✅ | native | file |
| `google_sheets` | source, target | files | ✅ | ✅ | native | sheet |
| `csv` | source, target | files | ✅ | ✅ | native | file |
| `markdown_kv` | source, target | files | ✅ | ✅ | native | file |
| `postgres` | source, target | database | ❌ | ✅ | meltano | tables |
| `mysql` | source, target | database | ❌ | ✅ | meltano | tables |
| `iceberg` | target | lake | ✅ | N/A | native | tables |
| `s3` | source, target | storage | ✅ | N/A | native | objects |
| `minio` | source, target | storage | ✅ | N/A | native | objects |

## Source Connectors

### Stripe

**Type**: `stripe`  
**Category**: Payments  
**Roles**: Source only  
**Cloud Mode**: ✅ Supported  
**Incremental**: ✅ Supported (default: `created`)

**Description**: Extract data from Stripe payments API including customers, charges, and invoices.

**Supported Objects**:
- `charges` - Payment charges
- `customers` - Customer records
- `invoices` - Invoice records

**Engines**:
- `airbyte` (default) - Uses `airbyte/source-stripe:2.1.5`
- `singer` - Singer tap support
- `native` - Native Python implementation

**Incremental Strategies**:
- `created` (default) - Timestamp-based incremental sync

**Configuration Example**:
```yaml
source_connector: stripe
source_connector_path: connectors/examples/stripe.yaml
source:
  object: customers
  incremental:
    strategy: created
    lookback_days: 1
```

**Credentials**:
- `STRIPE_API_KEY` - Stripe API key (required)

---

### HubSpot

**Type**: `hubspot`  
**Category**: CRM  
**Roles**: Source only  
**Cloud Mode**: ✅ Supported  
**Incremental**: ✅ Supported (default: `updated_after`)

**Description**: Extract data from HubSpot CRM API including contacts, deals, and companies.

**Supported Objects**:
- `contacts` - Contact records
- `deals` - Deal records
- `companies` - Company records

**Engines**:
- `airbyte` (default) - Uses `airbyte/source-hubspot:0.2.0`
- `singer` - Singer tap support
- `native` - Native Python implementation

**Incremental Strategies**:
- `updated_after` (default) - Cursor-based incremental sync

**Configuration Example**:
```yaml
source_connector: hubspot
source_connector_path: connectors/examples/hubspot.yaml
source:
  object: contacts
  incremental:
    strategy: updated_after
```

**Credentials**:
- `HUBSPOT_API_KEY` - HubSpot API key (required)

---

### Google Drive CSV

**Type**: `gdrive_csv`  
**Category**: Files  
**Roles**: Source only  
**Cloud Mode**: ✅ Supported  
**Incremental**: ✅ Supported (default: `file_modified_time`)

**Description**: Extract CSV files from Google Drive with file discovery and modification time tracking.

**Supported Objects**:
- `file` - CSV files from Google Drive

**Engines**:
- `native` (default) - Native Python implementation
- `airbyte` - Airbyte connector support
- `meltano` - Meltano tap support

**Incremental Strategies**:
- `file_modified_time` (default) - File modification time-based sync

**Configuration Example**:
```yaml
source_connector: gdrive_csv
source_connector_path: connectors/examples/gdrive_csv.yaml
source:
  file_id: "1abc123..."
  path: "/path/to/file.csv"
  incremental:
    strategy: file_modified_time
```

**Credentials**:
- Google Service Account JSON credentials (required)

---

### Google Sheets

**Type**: `google_sheets`  
**Category**: Files  
**Roles**: Source and Target (bidirectional)  
**Cloud Mode**: ✅ Supported  
**Incremental**: ✅ Supported (default: `spreadsheet_modified_time`)

**Description**: Extract and write data to Google Sheets spreadsheets.

**Supported Objects**:
- `sheet` - Google Sheets spreadsheets

**Engines**:
- `native` (default) - Native Python implementation
- `airbyte` - Airbyte connector support
- `meltano` - Meltano tap support

**Incremental Strategies**:
- `spreadsheet_modified_time` (default) - Spreadsheet modification time-based sync

**Configuration Example**:
```yaml
source_connector: google_sheets
source_connector_path: connectors/examples/google_sheets.yaml
source:
  spreadsheet_id: "1abc123..."
  range: "Sheet1!A1:Z1000"
  incremental:
    strategy: spreadsheet_modified_time
```

**Credentials**:
- Google Service Account JSON credentials (required)

---

### CSV

**Type**: `csv`  
**Category**: Files  
**Roles**: Source and Target (bidirectional)  
**Cloud Mode**: ✅ Supported  
**Incremental**: ✅ Supported (default: `file_modified_time`)

**Description**: Read and write CSV files from local filesystem or object storage.

**Supported Objects**:
- `file` - CSV files

**Engines**:
- `native` (default) - Native Python implementation

**Incremental Strategies**:
- `file_modified_time` (default) - File modification time-based sync

**Configuration Example**:
```yaml
source_connector: csv
source_connector_path: connectors/examples/csv.yaml
source:
  files:
    - path: "/data/employees.csv"
      object: employees
  incremental:
    strategy: file_modified_time
```

---

### Markdown-KV

**Type**: `markdown_kv`  
**Category**: Files  
**Roles**: Source and Target (bidirectional)  
**Cloud Mode**: ✅ Supported  
**Incremental**: ✅ Supported (default: `file_modified_time`)

**Description**: Read and write Markdown-KV format files for LLM-optimized data ingestion.

**Supported Objects**:
- `file` - Markdown-KV files

**Engines**:
- `native` (default) - Native Python implementation

**Incremental Strategies**:
- `file_modified_time` (default) - File modification time-based sync

**Storage Patterns**:
1. **STRING storage**: Store as STRING column in Iceberg Parquet tables
2. **Raw file storage**: Store files directly in S3/MinIO buckets
3. **Structured storage**: Parse and store as structured data

See [Markdown-KV Storage](MARKDOWN_KV_STORAGE.md) for detailed documentation.

---

### PostgreSQL

**Type**: `postgres`  
**Category**: Database  
**Roles**: Source and Target (bidirectional)  
**Cloud Mode**: ❌ Not supported (self-hosted only)  
**Incremental**: ✅ Supported (default: `updated_at`)

**Description**: Extract and write data to PostgreSQL databases.

**Supported Objects**:
- Tables - Database tables

**Engines**:
- `meltano` (default) - Meltano tap/target support
- `airbyte` - Airbyte connector support
- `jdbc` - JDBC-based access

**Incremental Strategies**:
- `updated_at` (default) - Timestamp-based incremental sync
- `cdc` - Change Data Capture (future)

**Configuration Example**:
```yaml
source_connector: postgres
source_connector_path: connectors/examples/postgres.yaml
source:
  object: customers
  incremental:
    strategy: updated_at
    cursor_field: updated_at
```

**Credentials**:
- `POSTGRES_HOST` - Database host
- `POSTGRES_PORT` - Database port (default: 5432)
- `POSTGRES_DB` - Database name
- `POSTGRES_USER` - Database user
- `POSTGRES_PASSWORD` - Database password

---

### MySQL

**Type**: `mysql`  
**Category**: Database  
**Roles**: Source and Target (bidirectional)  
**Cloud Mode**: ❌ Not supported (self-hosted only)  
**Incremental**: ✅ Supported (default: `updated_at`)

**Description**: Extract and write data to MySQL databases.

**Supported Objects**:
- Tables - Database tables

**Engines**:
- `meltano` (default) - Meltano tap/target support
- `airbyte` - Airbyte connector support
- `jdbc` - JDBC-based access

**Incremental Strategies**:
- `updated_at` (default) - Timestamp-based incremental sync
- `cdc` - Change Data Capture (future)

**Configuration Example**:
```yaml
source_connector: mysql
source_connector_path: connectors/examples/mysql.yaml
source:
  object: customers
  incremental:
    strategy: updated_at
    cursor_field: updated_at
```

**Credentials**:
- `MYSQL_HOST` - Database host
- `MYSQL_PORT` - Database port (default: 3306)
- `MYSQL_DB` - Database name
- `MYSQL_USER` - Database user
- `MYSQL_PASSWORD` - Database password

---

## Target Connectors

### Iceberg

**Type**: `iceberg`  
**Category**: Data Lake  
**Roles**: Target only  
**Cloud Mode**: ✅ Supported  
**Incremental**: N/A

**Description**: Write data to Apache Iceberg tables in Parquet format with optional catalog integration.

**File Formats**:
- `parquet` (default) - Parquet columnar format
- `markdown_kv` - Markdown-KV stored as STRING in Parquet

**Engines**:
- `native` (default) - Native Python implementation
- `spark` - Apache Spark support

**Features**:
- Schema evolution support
- Partitioning support
- Catalog integration (Nessie, AWS Glue, Databricks Unity, OpenMetadata)
- Metadata tagging and governance

**Configuration Example**:
```yaml
target_connector: iceberg
target_connector_path: connectors/examples/iceberg.yaml
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
  catalog:
    type: nessie
    uri: "${NESSIE_URI}"
    database: my_database
    table: my_table
```

**Credentials**:
- S3/MinIO credentials (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
- Catalog credentials (if using catalog)

---

### S3

**Type**: `s3`  
**Category**: Storage  
**Roles**: Source and Target (bidirectional)  
**Cloud Mode**: ✅ Supported  
**Incremental**: N/A

**Description**: Read and write objects to Amazon S3 or S3-compatible storage.

**Engines**:
- `native` (default) - Native Python implementation

**Configuration Example**:
```yaml
target_connector: s3
target_connector_path: connectors/examples/s3.yaml
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
      endpoint: "${S3_ENDPOINT}"
```

**Credentials**:
- `AWS_ACCESS_KEY_ID` - AWS access key
- `AWS_SECRET_ACCESS_KEY` - AWS secret key
- `AWS_REGION` - AWS region
- `S3_ENDPOINT` - S3 endpoint (for S3-compatible storage)

---

### MinIO

**Type**: `minio`  
**Category**: Storage  
**Roles**: Source and Target (bidirectional)  
**Cloud Mode**: ✅ Supported  
**Incremental**: N/A

**Description**: Read and write objects to MinIO object storage (S3-compatible).

**Engines**:
- `native` (default) - Native Python implementation

**Configuration Example**:
```yaml
target_connector: minio
target_connector_path: connectors/examples/minio.yaml
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
      endpoint: "${S3_ENDPOINT}"
```

**Credentials**:
- `AWS_ACCESS_KEY_ID` - MinIO access key (default: minioadmin)
- `AWS_SECRET_ACCESS_KEY` - MinIO secret key (default: minioadmin)
- `AWS_REGION` - Region (default: us-east-1)
- `S3_ENDPOINT` - MinIO endpoint (default: http://localhost:9000)

---

## Connector Configuration

### Connector Recipe Structure

Connector recipes are YAML files that define connection templates:

```yaml
name: stripe
type: stripe
default_engine:
  type: airbyte
  options:
    airbyte:
      docker_image: "airbyte/source-stripe:2.1.5"
credentials:
  type: api_key
  from_env: STRIPE_API_KEY
rate_limits:
  requests_per_second: 100
  requests_per_minute: 6000
```

### Using Connectors in Job Configs

```yaml
tenant_id: acme
source_connector: stripe
source_connector_path: connectors/examples/stripe.yaml
target_connector: iceberg
target_connector_path: connectors/examples/iceberg.yaml
asset: stripe_customers
asset_path: assets/examples/stripe/v1.0/customers.yaml
source:
  object: customers
  incremental:
    strategy: created
    lookback_days: 1
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
```

## Incremental Sync Strategies

### Timestamp-Based (`created`, `updated_at`, `updated_after`)
- Uses timestamp fields to track last sync
- Supports lookback windows
- Automatic cursor management

### File-Based (`file_modified_time`, `spreadsheet_modified_time`)
- Tracks file modification times
- Skips unchanged files
- Efficient for file-based sources

### Cursor-Based (`cdc`)
- Change Data Capture support
- Tracks change logs
- Real-time sync capability

## Engine Support

### Native Engine
- Python-based implementation
- Direct API/database access
- Fastest for simple use cases

### Airbyte Engine
- Docker container execution
- Uses Airbyte connector images
- Supports 300+ connectors

### Meltano Engine
- Meltano tap/target support
- Singer protocol compatible
- Plugin ecosystem

### JDBC Engine
- Database connectivity
- SQL-based extraction
- Connection pooling

### Spark Engine (Iceberg Targets)
- Apache Spark integration for writing to Iceberg tables
- Large-scale processing and distributed execution
- Better performance for datasets > 10GB
- Supports Spark clusters and adaptive query execution

**Configuration Example:**
```yaml
target:
  type: iceberg
  engine:
    type: spark
    options:
      spark:
        max_file_size_mb: 200
        config:
          spark.sql.adaptive.enabled: "true"
```

**See Also:**
- [Spark Setup Guide](SPARK_SETUP.md) - Complete setup and configuration guide
- [Configuration Reference - Spark Engine](CONFIG_REFERENCE.md#spark-engine-iceberg-targets) - Detailed configuration options

## Best Practices

1. **Use Connector Recipes**: Store connector configurations in `connectors/examples/` for reuse
2. **Version Control**: Track connector recipe changes in git
3. **Credentials**: Use secret managers, never hardcode credentials
4. **Incremental Sync**: Enable incremental sync for large datasets
5. **Error Handling**: Configure retry policies for transient errors
6. **Rate Limiting**: Respect API rate limits in connector recipes

## See Also

- [Configuration Reference](CONFIG_REFERENCE.md) - Complete configuration guide
- [Connector vs Plugin Decision Tree](CONNECTOR_VS_PLUGIN_DECISION_TREE.md) - When to use connectors vs plugins
- [Custom Plugins](CUSTOM_PLUGINS.md) - Creating custom readers/writers
- [Secret Management](SECRET_MANAGEMENT.md) - Managing credentials
