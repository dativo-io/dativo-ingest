# Data Catalog Integration - Quick Start

Get started with data catalog integration in 5 minutes using OpenMetadata.

## Prerequisites

- Docker and Docker Compose installed
- Dativo ingestion platform set up

## Step 1: Start OpenMetadata

```bash
# Start OpenMetadata and dependencies
docker-compose -f docker-compose.dev.yml up -d openmetadata

# Wait for services to be ready (2-3 minutes)
docker-compose -f docker-compose.dev.yml logs -f openmetadata

# Check health
curl http://localhost:8585/api/v1/health
```

## Step 2: Add Catalog Configuration to Your Job

Add a `catalog` block to your job configuration:

```yaml
# my_job.yaml
tenant_id: my_tenant
source_connector_path: connectors/csv.yaml
target_connector_path: connectors/s3.yaml
asset_path: assets/csv/v1.0/my_asset.yaml

source:
  files:
    - path: data/my_data.csv

target:
  connection:
    bucket: my-bucket
    endpoint: http://localhost:9000

# Add this catalog block
catalog:
  type: openmetadata
  config:
    uri: "http://localhost:8585"
  metadata:
    owners:
      - your-email@company.com
    tags:
      tier: bronze
      environment: dev
    description: "My test dataset"
  lineage:
    enabled: true
```

## Step 3: Run Your Job

```bash
# Set required environment variables
export S3_ENDPOINT=http://localhost:9000
export AWS_ACCESS_KEY_ID=minioadmin
export AWS_SECRET_ACCESS_KEY=minioadmin
export OPENMETADATA_URI=http://localhost:8585

# Run the job
dativo run --config my_job.yaml --mode self_hosted
```

## Step 4: Verify in OpenMetadata UI

1. Open http://localhost:8585 in your browser
2. Login with default credentials: `admin` / `admin`
3. Navigate to **Tables** → Search for your table
4. View:
   - **Schema**: Column definitions and types
   - **Lineage**: Visual data flow diagram
   - **Tags**: Applied tags and classifications
   - **Owners**: Assigned owners
   - **Activity**: Execution history

## What Gets Synced?

### Table Metadata
- Table name and database
- Schema (columns, types, descriptions)
- Storage location
- Execution metrics (records written, files created)

### Lineage
- Source system and object
- Target table and location
- Job execution details
- Upstream and downstream relationships

### Tags
- Asset definition tags
- Domain and data product tags
- Custom catalog tags
- Compliance classifications

### Ownership
- Team owners from asset definition
- Additional owners from catalog config

## Next Steps

### Try Other Catalogs

**AWS Glue:**
```yaml
catalog:
  type: aws_glue
  config:
    region: us-east-1
    database: my_database
```

**Databricks Unity Catalog:**
```yaml
catalog:
  type: databricks_unity
  config:
    workspace_url: "https://your-workspace.databricks.com"
    token: "${DATABRICKS_TOKEN}"
    catalog: main
```

**Nessie:**
```yaml
catalog:
  type: nessie
  config:
    uri: "http://localhost:19120"
    branch: main
```

### Configure Lineage

```yaml
lineage:
  enabled: true
  upstream_tables:
    - source_system.schema.source_table
  downstream_tables:
    - warehouse.schema.target_table
    - analytics.schema.aggregate_table
```

### Add Rich Metadata

```yaml
metadata:
  owners:
    - data-platform@company.com
    - analytics-team@company.com
  tags:
    tier: gold
    domain: sales
    pii: "true"
    retention_days: "365"
  description: |
    Comprehensive sales data aggregated from multiple sources.
    Updated daily at 2 AM UTC.
    
    Usage: Analytics dashboards and ML models.
```

## Common Issues

### Issue: OpenMetadata not accessible

**Solution:**
```bash
# Check if services are running
docker-compose -f docker-compose.dev.yml ps

# Restart if needed
docker-compose -f docker-compose.dev.yml restart openmetadata
```

### Issue: Table not appearing in UI

**Solution:**
- Check job logs for catalog sync errors
- Verify OpenMetadata URI is correct
- Wait 30 seconds and refresh the UI

### Issue: Lineage not showing

**Solution:**
- Ensure upstream tables exist in catalog
- Use fully qualified table names
- Check that lineage is enabled in config

## Testing

Run unit tests:
```bash
pytest tests/test_data_catalog.py -v
```

Run integration tests (requires OpenMetadata):
```bash
export RUN_OPENMETADATA_TESTS=1
export OPENMETADATA_URI=http://localhost:8585
pytest tests/integration/test_catalog_openmetadata_integration.py -v
```

## Resources

- **Full Documentation**: [CATALOG_INTEGRATION.md](CATALOG_INTEGRATION.md)
- **Example Jobs**: [examples/jobs/acme/](../examples/jobs/acme/)
- **OpenMetadata Docs**: https://docs.open-metadata.org/

## Cleanup

```bash
# Stop OpenMetadata
docker-compose -f docker-compose.dev.yml stop openmetadata elasticsearch openmetadata-db

# Remove data (optional)
docker-compose -f docker-compose.dev.yml down -v
```
