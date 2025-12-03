# Testing FinOps Metadata

This guide explains how to test that FinOps metadata from asset definitions is properly stored in Iceberg table properties.

## Overview

FinOps metadata (cost_center, business_tags, project, environment) is written to **Iceberg table properties** when a catalog is configured. When no catalog is configured, FinOps metadata is not written to S3 metadata/tags.

## Prerequisites

1. **Nessie catalog running** (for Iceberg table properties)
   ```bash
   # Using Docker Compose (if available)
   docker-compose up -d nessie
   
   # Or check if Nessie is already running
   curl http://localhost:19120/api/v1/config
   ```

2. **Job with catalog configured** - See example below

## Step 1: Create Job with Catalog Configuration

Create a job file with catalog configuration:

```yaml
# jobs/testcase3/stripe_customers_with_catalog.yaml
tenant_id: testcase3
source_connector: stripe
source_connector_path: connectors/stripe.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: stripe_customers
asset_path: assets/examples/stripe/v1.0/customers.yaml
source:
  objects: [customers]
  incremental:
    enabled: true
    lookback_days: 7
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
# Catalog configuration - enables FinOps metadata in Iceberg table properties
catalog:
  type: nessie
  connection:
    uri: "${NESSIE_URI:-http://localhost:19120/api/v1}"
  database: testcase3
  push_metadata: true
  push_lineage: true
```

## Step 2: Run the Job

```bash
dativo run \
  --config jobs/testcase3/stripe_customers_with_catalog.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets
```

## Step 3: Verify FinOps Metadata

### Option A: Using the Test Script (Recommended)

The test script reads Iceberg metadata.json files directly from S3, avoiding PyIceberg catalog compatibility issues:

```bash
# Set environment variables (optional, defaults provided)
export S3_BUCKET=test-bucket
export TENANT_ID=testcase3
export TABLE_NAME=stripe_customers

# Run the test script
python scripts/test_finops_metadata.py
```

The script will:
- Search for Iceberg metadata.json files in S3
- Read the most recent metadata file
- Extract table properties
- Validate FinOps metadata matches asset definition

### Option B: Reading Iceberg Metadata Files Directly from S3

If PyIceberg catalog connection fails (due to Nessie compatibility), you can read metadata files directly:

```python
import boto3
import json
from io import BytesIO

# Create S3 client
s3_client = boto3.client(
    's3',
    endpoint_url='http://localhost:9000',
    aws_access_key_id='minioadmin',
    aws_secret_access_key='minioadmin'
)

# Find metadata files
bucket = 'test-bucket'
prefix = 'testcase3/stripe_customers/metadata/'
response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)

# Read most recent metadata file
metadata_files = [obj['Key'] for obj in response.get('Contents', []) 
                  if 'metadata-' in obj['Key']]
latest_metadata = sorted(metadata_files, reverse=True)[0]

# Read and parse metadata
obj = s3_client.get_object(Bucket=bucket, Key=latest_metadata)
metadata = json.loads(obj['Body'].read().decode('utf-8'))

# Extract table properties
properties = metadata.get('properties', {})

# Check FinOps properties
print("FinOps Properties:")
for key, value in properties.items():
    if key.startswith('finops.'):
        print(f"  {key} = {value}")
```

### Option C: Using SQL (Trino/Spark)

If you have Trino or Spark connected to Nessie:

```sql
-- Query table properties
SELECT key, value
FROM system.metadata.table_properties
WHERE catalog_name = 'nessie'
  AND schema_name = 'testcase3'
  AND table_name = 'stripe_customers'
  AND key LIKE 'finops.%';
```

Expected output:
```
key                    | value
-----------------------+------------------
finops.cost_center     | FIN-001
finops.business_tags   | payments,revenue
finops.project         | payment-platform
finops.environment     | production
```

## Expected FinOps Properties

Based on the asset definition in `assets/examples/stripe/v1.0/customers.yaml`:

```yaml
finops:
  cost_center: FIN-001
  business_tags: [payments, revenue]
  project: payment-platform
  environment: production
```

The following table properties should be created:

- `finops.cost_center` = `FIN-001`
- `finops.business_tags` = `payments,revenue` (comma-separated)
- `finops.project` = `payment-platform`
- `finops.environment` = `production`

## Troubleshooting

### Table Not Found

If you get "Table not found" error:
1. Verify the job ran successfully
2. Check Nessie is accessible: `curl http://localhost:19120/api/v1/config`
3. Verify namespace and table name match

### FinOps Properties Missing

If FinOps properties are not in table properties:
1. Check asset definition has `finops` section
2. Verify catalog is configured in job
3. Check job logs for catalog errors
4. Ensure `push_metadata: true` in catalog config

### Catalog Connection Issues

If catalog connection fails:
1. Check Nessie is running: `docker ps | grep nessie`
2. Verify `NESSIE_URI` environment variable
3. Check network connectivity to Nessie
4. Review job logs for catalog errors

## Verification Script

The `scripts/test_finops_metadata.py` script provides automated testing:

```bash
# Test with custom parameters
NESSIE_URI=http://localhost:19120/api/v1 \
NAMESPACE=testcase3 \
TABLE_NAME=stripe_customers \
python scripts/test_finops_metadata.py
```

## Summary

✅ **With Catalog**: FinOps metadata → Iceberg table properties  
❌ **Without Catalog**: FinOps metadata → Not stored (only in asset definition)

To test FinOps metadata, you must:
1. Configure a catalog in your job
2. Run the job
3. Query Iceberg table properties via PyIceberg or SQL

