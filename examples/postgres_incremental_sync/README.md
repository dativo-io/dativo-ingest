# Example: PostgreSQL Incremental Sync

This example demonstrates incremental syncing of PostgreSQL tables to S3 with cursor-based state tracking.

## Overview

**What this does:**
- Extracts data from PostgreSQL database tables
- Uses cursor field (e.g., `updated_at`) for incremental sync
- Validates against ODCS v3.0.2 schema
- Writes Parquet files to S3/MinIO
- Tracks last cursor value in state file

**Use case:**
- Incremental sync of operational database to data lake
- Daily updates with cursor-based tracking
- Minimal data transfer (only new/updated records)

## Prerequisites

1. **PostgreSQL database** - Running PostgreSQL instance with read access
2. **S3/MinIO bucket** - Writable S3 bucket or MinIO instance
3. **Cursor field** - Table must have a sortable field (timestamp, integer ID, etc.)
4. **Dativo setup** - Local development environment

## Quick Start

### 1. Set Up Secrets

Create a secrets file for PostgreSQL credentials:

```bash
mkdir -p secrets/acme
```

**secrets/acme/postgres.json:**
```json
{
  "host": "localhost",
  "port": 5432,
  "database": "analytics",
  "user": "readonly_user",
  "password": "your_password_here"
}
```

### 2. Configure Environment

**Set S3/MinIO credentials:**
```bash
export AWS_ACCESS_KEY_ID="your_access_key"
export AWS_SECRET_ACCESS_KEY="your_secret_key"
export S3_BUCKET="your-bucket-name"
export S3_ENDPOINT="http://localhost:9000"  # For MinIO
```

### 3. Run the Job

**First run (full sync):**
```bash
dativo run --config examples/postgres_incremental_sync/job.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted
```

**Subsequent runs (incremental):**
```bash
# Same command - automatically continues from last cursor
dativo run --config examples/postgres_incremental_sync/job.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted
```

### Expected Output

**First run:**
```
[INFO] Starting job execution: acme/postgres_orders
[INFO] No previous state found - performing full sync
[INFO] Extracting data from PostgreSQL: orders
[INFO] Retrieved 10,000 rows (cursor: 2025-11-30 10:00:00)
[INFO] Validating records against schema
[INFO] Writing Parquet files to s3://your-bucket/raw/postgres/orders/
[INFO] Wrote 5 files (128.4 MB) to S3
[INFO] Updated state: last_cursor=2025-11-30 10:00:00
[SUCCESS] Job completed in 45.2s
```

**Incremental run:**
```
[INFO] Starting job execution: acme/postgres_orders
[INFO] Found previous state: last_cursor=2025-11-30 10:00:00
[INFO] Extracting incremental data from PostgreSQL: orders
[INFO] Retrieved 234 new rows (cursor: 2025-11-30 12:30:15)
[INFO] Validating records against schema
[INFO] Writing Parquet files to s3://your-bucket/raw/postgres/orders/
[INFO] Wrote 1 file (12.3 MB) to S3
[INFO] Updated state: last_cursor=2025-11-30 12:30:15
[SUCCESS] Job completed in 8.7s
```

### What Gets Created

**S3 Structure:**
```
s3://your-bucket/
  raw/postgres/orders/
    ingest_date=2025-11-30/
      data_001.parquet  # First run
      data_002.parquet  # Incremental updates
      data_003.parquet
```

**State File:**
```
state/acme/postgres_orders.json
{
  "last_cursor_value": "2025-11-30T12:30:15",
  "last_sync_timestamp": "2025-11-30T12:35:00Z",
  "records_synced": 234
}
```

## File Structure

```
postgres_incremental_sync/
├── README.md                        # This file
├── job.yaml                         # Job configuration
├── connector_postgres.yaml          # PostgreSQL connector definition
├── connector_iceberg.yaml           # Iceberg target definition
└── asset_postgres_orders.yaml       # ODCS schema for orders table
```

## Configuration Files

### job.yaml

```yaml
tenant_id: acme
source_connector: postgres
source_connector_path: examples/postgres_incremental_sync/connector_postgres.yaml
target_connector: iceberg
target_connector_path: examples/postgres_incremental_sync/connector_iceberg.yaml
asset: postgres_orders
asset_path: examples/postgres_incremental_sync/asset_postgres_orders.yaml

source:
  objects: [orders]
  incremental:
    cursor_field: updated_at  # Must exist in table and be sortable
    lookback_days: 1          # Optional: re-sync last day for updates
  engine:
    options:
      batch_size: 1000        # Rows per batch

target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
      endpoint: "${S3_ENDPOINT}"
      prefix: "raw/postgres/orders"
```

### connector_postgres.yaml

```yaml
type: postgres
mode: self_hosted  # Postgres only works in self-hosted mode
capabilities:
  incremental: true
  cursor_based: true
  batch_size: 1000
  supports_tables: ["*"]  # All tables
engine:
  type: psycopg2
  connection_timeout: 30
```

### asset_postgres_orders.yaml

```yaml
$schema: ../../schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: postgres_orders
version: "1.0"
source_type: postgres
object: orders

schema:
  - name: order_id
    type: integer
    required: true
    description: Primary key
  - name: customer_id
    type: integer
    required: true
    description: Foreign key to customers table
  - name: order_total
    type: float
    required: true
    description: Total order amount
  - name: order_date
    type: date
    required: true
    description: Date order was placed
  - name: updated_at
    type: datetime
    required: true
    description: Last update timestamp (cursor field)

target:
  file_format: parquet
  partitioning: [ingest_date]

metadata:
  owner: data-engineering@acme.com
  domain: ecommerce
  tags: [postgres, orders, transactional]
```

## How Incremental Sync Works

### Cursor-Based Tracking

**Query on first run:**
```sql
SELECT * FROM orders
ORDER BY updated_at ASC
LIMIT 1000;
```

**Query on subsequent runs:**
```sql
SELECT * FROM orders
WHERE updated_at > '2025-11-30 10:00:00'  -- Last cursor value
ORDER BY updated_at ASC
LIMIT 1000;
```

### Lookback Window

With `lookback_days: 1`, the query becomes:

```sql
SELECT * FROM orders
WHERE updated_at > '2025-11-29 10:00:00'  -- Last cursor - 1 day
ORDER BY updated_at ASC
LIMIT 1000;
```

**Why use lookback?**
- Handles late-arriving updates
- Catches records that were updated after initial sync
- Ensures data consistency

## Customization

### Change Cursor Field

Use any sortable field:

```yaml
source:
  incremental:
    cursor_field: order_id  # Use integer ID instead of timestamp
```

### Disable Incremental Sync (Full Refresh)

```yaml
source:
  objects: [orders]
  # No incremental section = full refresh every time
```

### Sync Multiple Tables

Create separate job configs for each table, or:

```yaml
source:
  objects: [orders, customers, products]
```

*Note: You'll need separate asset definitions for each table.*

### Adjust Batch Size

**Large tables (optimize for speed):**
```yaml
source:
  engine:
    options:
      batch_size: 10000  # Larger batches
```

**Memory-constrained environments:**
```yaml
source:
  engine:
    options:
      batch_size: 100  # Smaller batches
```

## Monitoring and Operations

### Check Sync Status

```bash
cat state/acme/postgres_orders.json
```

**Output:**
```json
{
  "last_cursor_value": "2025-11-30T12:30:15",
  "last_sync_timestamp": "2025-11-30T12:35:00Z",
  "records_synced": 234
}
```

### Reset State (Force Full Sync)

```bash
rm state/acme/postgres_orders.json
dativo run --config examples/postgres_incremental_sync/job.yaml ...
```

### Test Connection

```bash
dativo check --config examples/postgres_incremental_sync/job.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --verbose
```

### Discover Available Tables

```bash
dativo discover --config examples/postgres_incremental_sync/job.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --verbose
```

**Output:**
```
Found 12 table(s):

1. orders
   Schema: {"order_id": "integer", "customer_id": "integer", ...}

2. customers
   Schema: {"customer_id": "integer", "email": "varchar", ...}
```

## Scheduling with Dagster

**Run incremental sync every hour:**

```yaml
# configs/runner.yaml
jobs:
  - job_name: postgres_orders_hourly
    job_config_path: examples/postgres_incremental_sync/job.yaml
    enabled: true
    schedule:
      type: cron
      cron: "0 * * * *"  # Every hour
      timezone: "UTC"
    retry_config:
      max_retries: 3
      initial_delay_seconds: 30
```

**Start orchestrator:**
```bash
dativo start orchestrated --runner-config configs/runner.yaml
```

## Troubleshooting

### "No cursor field found" errors

**Verify cursor field exists:**
```sql
SELECT column_name, data_type 
FROM information_schema.columns
WHERE table_name = 'orders' AND column_name = 'updated_at';
```

**Create cursor field if missing:**
```sql
ALTER TABLE orders ADD COLUMN updated_at TIMESTAMP DEFAULT NOW();
CREATE INDEX idx_orders_updated_at ON orders(updated_at);
```

### "Connection refused" errors

**Check PostgreSQL connection:**
```bash
psql -h localhost -p 5432 -U readonly_user -d analytics
```

**Verify secrets:**
```bash
cat secrets/acme/postgres.json
```

### Slow queries

**Add index on cursor field:**
```sql
CREATE INDEX idx_orders_updated_at ON orders(updated_at);
```

**Reduce batch size:**
```yaml
source:
  engine:
    options:
      batch_size: 500  # Smaller batches
```

### Schema validation errors

**Check actual vs expected schema:**
```bash
dativo discover --config examples/postgres_incremental_sync/job.yaml --verbose
```

**Update asset schema** to match actual database schema.

## Best Practices

### 1. Use Dedicated Read-Only User

```sql
CREATE USER readonly_user WITH PASSWORD 'secure_password';
GRANT CONNECT ON DATABASE analytics TO readonly_user;
GRANT USAGE ON SCHEMA public TO readonly_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;
```

### 2. Add Indexes on Cursor Fields

```sql
CREATE INDEX idx_orders_updated_at ON orders(updated_at);
ANALYZE orders;  -- Update statistics
```

### 3. Use Connection Pooling

For high-frequency syncs, consider using PgBouncer or similar.

### 4. Monitor State Files

```bash
# Backup state files periodically
cp -r state/ state_backup/
```

### 5. Set Appropriate Lookback

**High-update tables:**
```yaml
lookback_days: 1  # Catch late updates
```

**Append-only tables:**
```yaml
lookback_days: 0  # No lookback needed
```

## Next Steps

1. **Transform with Markdown-KV** - Convert to LLM-friendly format: [MARKDOWN_KV_STORAGE.md](../../docs/MARKDOWN_KV_STORAGE.md)
2. **Add data quality checks** - Validate business rules
3. **Set up data catalog** - Track lineage: [CATALOG_INTEGRATION.md](../../docs/CATALOG_INTEGRATION.md)
4. **Build custom transformations** - Use Python plugins: [CUSTOM_PLUGINS.md](../../docs/CUSTOM_PLUGINS.md)

## Support

- [Documentation Index](../../docs/INDEX.md)
- [GitHub Issues](https://github.com/dativo-io/dativo-ingest/issues)
- [PostgreSQL Connector Docs](../../docs/CONFIG_REFERENCE.md#postgresql-connector)
