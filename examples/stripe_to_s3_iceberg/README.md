# Example: Stripe to S3/Iceberg

This example demonstrates ingesting Stripe customer data into S3 as Iceberg-backed Parquet tables.

## Overview

**What this does:**
- Extracts customer data from Stripe API
- Validates against ODCS v3.0.2 schema
- Writes Parquet files to S3/MinIO
- Commits to Iceberg catalog (optional)
- Tracks incremental sync state

**Use case:**
- Daily sync of Stripe customers for analytics
- Incremental sync with 1-day lookback
- Partitioned by ingestion date

## Prerequisites

1. **Stripe API key** - Get from https://dashboard.stripe.com/apikeys
2. **S3/MinIO bucket** - Writable S3 bucket or MinIO instance
3. **Dativo setup** - Local development environment (see [SETUP_AND_TESTING.md](../../docs/SETUP_AND_TESTING.md))

## Quick Start

### 1. Set Up Secrets

Create a secrets file for Stripe credentials:

```bash
mkdir -p secrets/acme
```

**secrets/acme/stripe.json:**
```json
{
  "api_key": "sk_test_your_stripe_api_key_here"
}
```

### 2. Configure Environment

**Set S3/MinIO credentials:**
```bash
export AWS_ACCESS_KEY_ID="your_access_key"
export AWS_SECRET_ACCESS_KEY="your_secret_key"
export S3_BUCKET="your-bucket-name"
export S3_ENDPOINT="http://localhost:9000"  # For MinIO, omit for AWS S3
```

### 3. Run the Job

```bash
dativo run --config examples/stripe_to_s3_iceberg/job.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted
```

### Expected Output

```
[INFO] Starting job execution: acme/stripe_customers
[INFO] Extracting data from Stripe API: customers
[INFO] Retrieved 1,234 customers
[INFO] Validating records against schema
[INFO] Writing Parquet files to s3://your-bucket/raw/stripe/customers/
[INFO] Wrote 2 files (45.3 MB) to S3
[INFO] Committed to Iceberg table: acme.stripe_customers
[INFO] Updated state: last_sync=2025-11-30T10:23:45Z
[SUCCESS] Job completed in 23.4s
```

### What Gets Created

**S3 Structure:**
```
s3://your-bucket/
  raw/stripe/customers/
    ingest_date=2025-11-30/
      data_001.parquet
      data_002.parquet
```

**State File:**
```
state/acme/stripe_customers.json
{
  "last_sync_timestamp": "2025-11-30T10:23:45Z",
  "records_synced": 1234
}
```

## File Structure

```
stripe_to_s3_iceberg/
├── README.md                    # This file
├── job.yaml                     # Job configuration
├── connector_stripe.yaml        # Stripe connector definition
├── connector_iceberg.yaml       # Iceberg target definition
└── asset_stripe_customers.yaml  # ODCS schema for customers
```

## Configuration Files

### job.yaml

```yaml
tenant_id: acme
source_connector: stripe
source_connector_path: examples/stripe_to_s3_iceberg/connector_stripe.yaml
target_connector: iceberg
target_connector_path: examples/stripe_to_s3_iceberg/connector_iceberg.yaml
asset: stripe_customers
asset_path: examples/stripe_to_s3_iceberg/asset_stripe_customers.yaml

source:
  objects: [customers]
  incremental:
    lookback_days: 1

target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
      endpoint: "${S3_ENDPOINT}"  # Optional, for MinIO
      prefix: "raw/stripe/customers"
  catalog:
    type: nessie
    connection:
      api_url: "${NESSIE_API_URL:-http://localhost:19120/api/v1}"
    database: acme
    branch: main
```

### connector_stripe.yaml

```yaml
type: stripe
mode: self_hosted
capabilities:
  incremental: true
  batch_size: 100
  supports_objects: [customers, charges, invoices, subscriptions]
engine:
  type: api
  version: "2023-10-16"
```

### connector_iceberg.yaml

```yaml
type: iceberg
mode: self_hosted
capabilities:
  formats: [parquet]
  partitioning: true
  catalog: optional
engine:
  type: pyiceberg
  parquet_options:
    compression: snappy
    row_group_size: 100000
```

### asset_stripe_customers.yaml

```yaml
$schema: ../../schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
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
    description: Stripe customer ID
  - name: email
    type: string
    required: false
    description: Customer email address
  - name: created
    type: integer
    required: true
    description: Unix timestamp of creation
  - name: name
    type: string
    required: false
    description: Customer name

target:
  file_format: parquet
  partitioning: [ingest_date]

metadata:
  owner: data-engineering@acme.com
  domain: payments
  tags: [stripe, customers, pii]
```

## Customization

### Change Sync Frequency

**Daily full sync:**
```yaml
source:
  objects: [customers]
  incremental:
    lookback_days: 0  # No lookback, just new records
```

**Weekly backfill:**
```yaml
source:
  objects: [customers]
  incremental:
    lookback_days: 7  # Re-sync last 7 days
```

### Add More Objects

```yaml
source:
  objects: [customers, charges, subscriptions]
```

*Note: You'll need to create separate asset definitions for each object.*

### Change Partitioning

**Partition by year/month/day:**
```yaml
target:
  file_format: parquet
  partitioning: [year, month, day]
```

**No partitioning:**
```yaml
target:
  file_format: parquet
  partitioning: []
```

## Scheduling with Dagster

To run this job on a schedule, create a runner config:

**configs/runner.yaml:**
```yaml
jobs:
  - job_name: stripe_customers_daily
    job_config_path: examples/stripe_to_s3_iceberg/job.yaml
    enabled: true
    schedule:
      type: cron
      cron: "0 2 * * *"  # Daily at 2 AM
      timezone: "UTC"
    retry_config:
      max_retries: 3
      initial_delay_seconds: 60
      max_delay_seconds: 3600
      backoff_multiplier: 2.0
```

**Start the orchestrator:**
```bash
dativo start orchestrated --runner-config configs/runner.yaml
```

## Troubleshooting

### "Connection refused" errors

**Check MinIO/Nessie:**
```bash
cd /workspace
./scripts/setup-dev.sh  # Restart local infrastructure
```

### "Invalid API key" errors

**Verify Stripe credentials:**
```bash
cat secrets/acme/stripe.json
# Should contain valid sk_test_... or sk_live_... key
```

**Test connection:**
```bash
dativo check --config examples/stripe_to_s3_iceberg/job.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --verbose
```

### Schema validation errors

**Common issues:**
- Missing required fields: Check Stripe API response format
- Type mismatches: Update asset schema to match actual data types

**Run in warn mode:**
```yaml
schema_validation_mode: warn  # Log warnings instead of failing
```

### S3/MinIO access errors

**Check credentials:**
```bash
echo $AWS_ACCESS_KEY_ID
echo $S3_BUCKET
```

**Test S3 access:**
```bash
aws s3 ls s3://$S3_BUCKET/ --endpoint-url $S3_ENDPOINT
```

## Next Steps

1. **Add more connectors** - See [CONFIG_REFERENCE.md](../../docs/CONFIG_REFERENCE.md)
2. **Build custom plugins** - See [CUSTOM_PLUGINS.md](../../docs/CUSTOM_PLUGINS.md)
3. **Set up data catalog** - See [CATALOG_INTEGRATION.md](../../docs/CATALOG_INTEGRATION.md)
4. **Schedule with Dagster** - See [RUNNER_AND_ORCHESTRATION.md](../../docs/RUNNER_AND_ORCHESTRATION.md)

## Support

- [Documentation Index](../../docs/INDEX.md)
- [GitHub Issues](https://github.com/dativo-io/dativo-ingest/issues)
- [Contributing Guide](../../.github/CONTRIBUTING.md)
