# Data Catalog Integration Guide

Dativo supports integration with multiple data catalog systems to automatically track lineage, metadata, tags, and ownership information for your data pipelines.

## Supported Data Catalogs

- **AWS Glue Data Catalog** - Native AWS metadata repository
- **Databricks Unity Catalog** - Unified governance for Databricks
- **Nessie** - Git-like data catalog for Iceberg
- **OpenMetadata** - Open-source metadata platform

## Quick Start

Add a `catalog` block to your job configuration to enable catalog integration:

```yaml
catalog:
  type: openmetadata
  config:
    uri: "http://localhost:8585"
    token: "${OPENMETADATA_TOKEN}"
  metadata:
    owners:
      - data-team@company.com
    tags:
      tier: gold
      domain: sales
    description: "Sales data for analytics"
  lineage:
    enabled: true
    upstream_tables:
      - source.raw.sales
    downstream_tables:
      - analytics.sales_enriched
```

## Configuration Reference

### Catalog Block Structure

```yaml
catalog:
  type: <catalog_type>        # Required: aws_glue, databricks_unity, nessie, openmetadata
  config:                      # Required: Catalog-specific configuration
    <catalog_config>
  metadata:                    # Optional: Additional metadata
    owners: []                 # List of data owners
    tags: {}                   # Key-value pairs for tagging
    description: ""            # Table description
    tier: ""                   # Data tier (gold/silver/bronze)
  lineage:                     # Optional: Lineage configuration
    enabled: true              # Enable/disable lineage tracking
    upstream_tables: []        # List of upstream tables
    downstream_tables: []      # List of downstream tables
```

## Catalog-Specific Configuration

### AWS Glue Data Catalog

```yaml
catalog:
  type: aws_glue
  config:
    region: "us-east-1"        # AWS region
    database: "analytics_db"   # Glue database name
  metadata:
    owners:
      - data-engineering@company.com
    tags:
      environment: production
      cost_center: eng-123
    description: "Production analytics data"
```

**Features:**
- Creates/updates Glue tables with schema and metadata
- Stores lineage information in table parameters
- Applies tags using AWS Tagging API
- Stores ownership in table parameters

**Requirements:**
- AWS credentials configured (via environment or IAM role)
- `boto3` installed
- Appropriate IAM permissions for Glue operations

### Databricks Unity Catalog

```yaml
catalog:
  type: databricks_unity
  config:
    workspace_url: "https://your-workspace.databricks.com"
    token: "${DATABRICKS_TOKEN}"
    catalog: "main"            # Unity Catalog name
  metadata:
    owners:
      - data-platform@company.com
    tags:
      tier: gold
      domain: customer
    description: "Customer 360 data"
  lineage:
    enabled: true
    upstream_tables:
      - bronze.raw.customers
      - bronze.raw.transactions
```

**Features:**
- Creates/updates Unity Catalog tables
- Native lineage tracking through Unity Catalog API
- Table properties and tags
- Owner management

**Requirements:**
- Databricks workspace with Unity Catalog enabled
- Personal access token with catalog permissions
- `requests` library

### Nessie Catalog

```yaml
catalog:
  type: nessie
  config:
    uri: "http://nessie-server:19120"
    branch: "main"             # Nessie branch
  metadata:
    owners:
      - data-team@company.com
    tags:
      tier: bronze
      source: kafka
    description: "Real-time event data"
  lineage:
    enabled: true
```

**Features:**
- Updates table metadata in Nessie
- Stores lineage as commit metadata
- Git-like versioning and branching
- Integration with Iceberg tables

**Requirements:**
- Nessie server running
- `requests` library
- `pynessie` package

### OpenMetadata

```yaml
catalog:
  type: openmetadata
  config:
    uri: "http://openmetadata:8585"
    token: "${OPENMETADATA_TOKEN}"  # Optional for local dev
    api_version: "v1"                # Default: v1
  metadata:
    owners:
      - analytics-team@company.com
    tags:
      environment: production
      pii: "true"
    description: "Customer PII data"
    tier: gold
  lineage:
    enabled: true
    upstream_tables:
      - postgres.public.customers
      - kafka.events.customer_updates
    downstream_tables:
      - warehouse.dim_customers
```

**Features:**
- Full metadata management (tables, schemas, descriptions)
- Visual lineage tracking with edge details
- Rich tagging and classification
- Owner and team management
- Data quality integration

**Requirements:**
- OpenMetadata server running (v1.3+)
- `requests` library
- Optional: JWT token for authentication

## How It Works

### 1. Job Execution

When a job runs with catalog integration enabled:

1. **Extract and Transform**: Data is extracted from source and validated
2. **Write**: Data is written to target storage (S3, MinIO, etc.)
3. **Catalog Sync**: After successful write, catalog operations are performed:
   - Table metadata is created/updated
   - Lineage is pushed
   - Tags are synchronized
   - Owners are updated

### 2. Metadata Derivation

The catalog manager automatically derives metadata from:

- **Asset Definition**: Schema, domain, data product, compliance info
- **Job Configuration**: Tenant, environment, source/target details
- **Catalog Config**: Custom tags, owners, descriptions
- **Execution Metrics**: Records written, files created, timestamps

### 3. Tag Propagation

Tags are collected from multiple sources (in order of precedence):

1. Catalog-specific tags (highest priority)
2. Asset definition tags
3. Domain and data product tags
4. Compliance classification tags
5. Source system tags (lowest priority)

### 4. Lineage Tracking

Lineage captures:
- **Source**: Connector type and object name
- **Target**: Database, table, and storage location
- **Job Details**: Job ID, tenant, execution time
- **Metrics**: Records processed, files written
- **Upstream/Downstream**: Configured table relationships

## Best Practices

### 1. Use Environment Variables for Credentials

```yaml
catalog:
  type: openmetadata
  config:
    uri: "${OPENMETADATA_URI}"
    token: "${OPENMETADATA_TOKEN}"
```

### 2. Standardize Naming Conventions

```yaml
metadata:
  tags:
    tier: gold              # Use: gold/silver/bronze
    domain: sales           # Business domain
    source: stripe          # Source system
    pii: "true"            # Use string "true"/"false"
```

### 3. Leverage Asset Definitions

Define metadata in asset definitions rather than duplicating in job configs:

```yaml
# Asset definition (assets/stripe/v1.0/customers.yaml)
team:
  owner: payments-team@company.com
tags: [stripe, customers, pii]
compliance:
  classification: [PII, SENSITIVE]
```

### 4. Configure Upstream/Downstream Tables

```yaml
lineage:
  enabled: true
  upstream_tables:
    - source_system.schema.table_name  # Use fully qualified names
  downstream_tables:
    - target_system.schema.table_name
```

### 5. Use Tier Classification

```yaml
metadata:
  tier: gold    # Recommended: gold (curated), silver (cleaned), bronze (raw)
```

## Examples

### Example 1: OpenMetadata for Local Development

```yaml
tenant_id: dev_tenant
source_connector_path: connectors/csv.yaml
target_connector_path: connectors/s3.yaml
asset_path: assets/csv/v1.0/employees.yaml

source:
  files:
    - path: data/employees.csv

target:
  connection:
    bucket: dev-bucket
    endpoint: http://localhost:9000

catalog:
  type: openmetadata
  config:
    uri: "http://localhost:8585"
    # No token needed for local dev
  metadata:
    owners:
      - dev-team@company.com
    tags:
      environment: dev
    tier: bronze
  lineage:
    enabled: true
```

### Example 2: AWS Glue for Production

```yaml
tenant_id: prod_tenant
source_connector_path: connectors/postgres.yaml
target_connector_path: connectors/iceberg.yaml
asset_path: assets/postgres/v1.0/orders.yaml

source:
  tables:
    - name: orders

target:
  connection:
    s3:
      bucket: prod-data-lake
      region: us-east-1

catalog:
  type: aws_glue
  config:
    region: us-east-1
    database: production_analytics
  metadata:
    owners:
      - data-platform@company.com
      - analytics-team@company.com
    tags:
      environment: production
      tier: silver
      domain: orders
      cost_center: eng-456
    description: "Production order data for analytics and reporting"
  lineage:
    enabled: true
    upstream_tables:
      - postgres.public.orders
      - postgres.public.order_items
    downstream_tables:
      - warehouse.fact_orders
      - analytics.orders_summary
```

### Example 3: Databricks Unity Catalog

```yaml
tenant_id: prod_tenant
source_connector_path: connectors/kafka.yaml
target_connector_path: connectors/iceberg.yaml
asset_path: assets/kafka/v1.0/events.yaml

source:
  topics:
    - user_events

target:
  connection:
    s3:
      bucket: prod-data-lake
      region: us-east-1

catalog:
  type: databricks_unity
  config:
    workspace_url: "https://company.cloud.databricks.com"
    token: "${DATABRICKS_TOKEN}"
    catalog: main
  metadata:
    owners:
      - data-engineering@company.com
    tags:
      tier: bronze
      source: kafka
      domain: events
      real_time: "true"
    description: "Real-time user event data from Kafka"
  lineage:
    enabled: true
    upstream_tables:
      - kafka.events.user_events
    downstream_tables:
      - silver.events.enriched_user_events
      - gold.analytics.user_behavior
```

## Testing

### Local Testing with OpenMetadata

1. Start OpenMetadata with docker-compose:

```bash
docker-compose -f docker-compose.dev.yml up -d openmetadata
```

2. Wait for services to be healthy (can take 2-3 minutes):

```bash
docker-compose -f docker-compose.dev.yml ps
```

3. Access OpenMetadata UI:
   - URL: http://localhost:8585
   - Default credentials: admin/admin

4. Run integration tests:

```bash
# Set environment variable to enable tests
export RUN_OPENMETADATA_TESTS=1
export OPENMETADATA_URI=http://localhost:8585

# Run tests
pytest tests/integration/test_catalog_openmetadata_integration.py -v
```

### Unit Tests

```bash
# Run all catalog unit tests
pytest tests/test_data_catalog.py -v

# Run specific catalog client tests
pytest tests/test_data_catalog.py::TestOpenMetadataCatalogClient -v
pytest tests/test_data_catalog.py::TestAWSGlueCatalogClient -v
```

## Troubleshooting

### Issue: Catalog sync fails but job succeeds

**Cause**: Catalog operations are non-blocking. Job writes data successfully even if catalog sync fails.

**Solution**: Check logs for catalog-specific errors. Catalog sync failures are logged as warnings.

### Issue: Table not found in catalog

**Cause**: Table must exist in catalog before lineage can be pushed.

**Solution**: The `sync_table_metadata` operation creates tables. Ensure it runs before lineage operations.

### Issue: Authentication failed

**Cause**: Missing or invalid credentials.

**Solution**: 
- AWS Glue: Check AWS credentials and IAM permissions
- Databricks: Verify workspace URL and token
- OpenMetadata: Check token if authentication is enabled
- Nessie: Verify Nessie URI and accessibility

### Issue: Lineage edges not appearing

**Cause**: Upstream/downstream tables don't exist in catalog.

**Solution**: 
1. Create upstream tables in catalog first
2. Use fully qualified table names
3. Check catalog logs for specific errors

## Performance Considerations

- **Non-blocking**: Catalog operations don't block data writing
- **Failure Handling**: Catalog failures are logged but don't fail jobs
- **Async Support**: Consider async catalog updates for high-throughput pipelines
- **Batch Operations**: Multiple jobs can update catalog concurrently

## Security

### Credential Management

Use secret managers for credentials:

```yaml
catalog:
  type: databricks_unity
  config:
    workspace_url: "${DATABRICKS_WORKSPACE_URL}"
    token: "${DATABRICKS_TOKEN}"  # From secret manager
```

### Network Security

- Use private endpoints when available
- Enable TLS/SSL for production
- Restrict catalog API access with firewall rules

### Least Privilege

Grant minimal required permissions:
- AWS Glue: `glue:CreateTable`, `glue:UpdateTable`, `glue:TagResource`
- Databricks: Catalog USE and CREATE permissions
- OpenMetadata: Table create/update permissions

## Monitoring

### Catalog Operation Logs

```json
{
  "event_type": "catalog_sync_started",
  "catalog_type": "openmetadata",
  "timestamp": "2024-01-15T10:30:00Z"
}

{
  "event_type": "catalog_table_synced",
  "result": {"status": "created", "table": "default.sales.customers"},
  "timestamp": "2024-01-15T10:30:01Z"
}

{
  "event_type": "catalog_lineage_pushed",
  "result": {"status": "success", "lineage_pushed": true},
  "timestamp": "2024-01-15T10:30:02Z"
}
```

### Metrics to Track

- Catalog sync success rate
- Catalog operation latency
- Failed lineage pushes
- Tag sync failures

## Future Enhancements

- Data quality metrics integration
- Schema evolution tracking
- Data discovery automation
- Access control synchronization
- Data contract validation

## Additional Resources

- [OpenMetadata Documentation](https://docs.open-metadata.org/)
- [AWS Glue Documentation](https://docs.aws.amazon.com/glue/)
- [Databricks Unity Catalog](https://docs.databricks.com/data-governance/unity-catalog/)
- [Nessie Documentation](https://projectnessie.org/)
