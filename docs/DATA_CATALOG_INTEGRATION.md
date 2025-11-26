
# Data Catalog Integration

Dativo supports integration with multiple data catalog systems to automatically register datasets, publish lineage information, and propagate metadata (tags, owners, classifications).

## Supported Catalogs

- **AWS Glue Data Catalog** - AWS's managed metadata catalog
- **Databricks Unity Catalog** - Databricks' unified governance solution
- **Nessie** - Git-like catalog for Apache Iceberg (enhanced integration)
- **OpenMetadata** - Open-source metadata management platform

## Configuration

Add a `catalog` block to your job configuration to enable catalog integration:

```yaml
tenant_id: acme
source_connector: postgres
source_connector_path: connectors/postgres.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: postgres_orders
asset_path: assets/postgres/v1.0/orders.yaml

# Data catalog configuration (optional)
catalog:
  type: openmetadata  # glue, unity, nessie, or openmetadata
  enabled: true
  uri: http://localhost:8585/api
  
  # Control what gets pushed to catalog
  push_lineage: true   # Push lineage information
  push_schema: true    # Register/update dataset schema
  push_metadata: true  # Push tags, owners, classifications
  
source:
  tables:
    - table: orders
      object: orders

target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
      prefix: "warehouse/orders"
```

## Catalog-Specific Configuration

### AWS Glue

```yaml
catalog:
  type: glue
  enabled: true
  aws_region: us-east-1
  aws_account_id: "123456789012"  # Optional, auto-detected if not provided
  push_lineage: true
  push_schema: true
  push_metadata: true
```

**Features:**
- Automatic database creation if doesn't exist
- Table creation/updates with schema
- Lineage stored as table parameters
- Tag support via AWS resource tags
- Metadata stored as table parameters

**Requirements:**
- AWS credentials configured (via environment, IAM role, or AWS CLI)
- `boto3` library (included in dependencies)

### Databricks Unity Catalog

```yaml
catalog:
  type: unity  # or 'unity_catalog' or 'databricks'
  enabled: true
  workspace_url: https://myworkspace.databricks.com
  token: "${DATABRICKS_TOKEN}"
  catalog_name: main  # Unity Catalog name (default: 'main')
  push_lineage: true
  push_schema: true
  push_metadata: true
```

**Features:**
- Automatic catalog and schema creation
- Table registration with full schema
- Lineage tracking (via Unity Catalog lineage API or table properties)
- Tag support via table properties
- Owner and classification metadata

**Requirements:**
- Databricks workspace access token
- `requests` library (included in dependencies)

### Nessie

```yaml
catalog:
  type: nessie
  enabled: true
  uri: http://localhost:19120/api/v1
  branch: main  # Nessie branch (default: 'main')
  token: "${NESSIE_TOKEN}"  # Optional
  push_lineage: true
  push_schema: true
  push_metadata: true
```

**Features:**
- Branch-based catalog management
- Integration with Iceberg table properties
- Lineage stored as table metadata
- Git-like versioning of metadata

**Requirements:**
- Nessie server running
- `requests` library (included in dependencies)

**Note:** Nessie integration works in conjunction with the existing Iceberg committer. Table metadata and lineage are stored as Iceberg table properties.

### OpenMetadata

```yaml
catalog:
  type: openmetadata  # or 'open_metadata'
  enabled: true
  uri: http://localhost:8585/api
  token: "${OPENMETADATA_TOKEN}"  # Optional for local dev
  push_lineage: true
  push_schema: true
  push_metadata: true
  
  # Optional: Custom server configuration
  server_config:
    hostPort: http://localhost:8585/api
    authProvider: no-auth  # or 'openmetadata' for JWT auth
```

**Features:**
- Full schema registration with descriptions
- Native lineage tracking with pipeline references
- Rich metadata support (tags, owners, classifications)
- Service, database, and schema auto-creation
- Column-level lineage support

**Requirements:**
- OpenMetadata server running
- `openmetadata-ingestion>=1.2.0` library (included in dependencies)

## What Gets Published

### Schema Registration (`push_schema: true`)

When schema push is enabled, Dativo registers or updates the dataset in the catalog with:

- **Dataset Name:** Fully qualified name (e.g., `database.schema.table`)
- **Schema:** List of columns with names, types, and descriptions
- **Description:** From asset definition
- **Location:** S3/storage path where data is written
- **Custom Metadata:**
  - Tenant ID
  - Asset version
  - Source type
  - Environment

### Lineage Information (`push_lineage: true`)

Dativo publishes comprehensive lineage information:

- **Source:** Type, name, dataset, and columns
- **Target:** Type, name, dataset, and columns
- **Pipeline:** Name and execution details
- **Statistics:**
  - Records processed
  - Bytes processed
- **Transformation:** Type and description
- **Execution Time:** When the pipeline ran

### Metadata (`push_metadata: true`)

Dativo propagates governance metadata from asset definitions:

- **Tags:** From asset definition and job config
- **Owner:** From asset team configuration
- **Classification:** Data classification labels (PII, Sensitive, etc.)
- **Custom Metadata:** FinOps tags, cost center, business tags, etc.

## Metadata Propagation

Dativo follows a three-level tag hierarchy (see [Tag Derivation](TAG_DERIVATION.md)):

1. **Job-level overrides** (highest priority)
2. **Asset definition metadata** (middle priority)
3. **Source system tags** (lowest priority)

This ensures that governance policies can be enforced at the job level while preserving asset-level metadata.

## Example: Complete Workflow

```yaml
tenant_id: acme
environment: production

source_connector: postgres
source_connector_path: connectors/postgres.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: postgres_customers
asset_path: assets/postgres/v1.0/customers.yaml

# Data catalog integration
catalog:
  type: openmetadata
  enabled: true
  uri: "${OPENMETADATA_URI}"
  push_lineage: true
  push_schema: true
  push_metadata: true

# Source configuration
source:
  tables:
    - table: customers
      object: customers

# Target configuration
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
      prefix: "warehouse/customers"

# Metadata overrides (highest priority)
classification_overrides:
  email: PII
  phone: PII

finops:
  cost_center: "CC-12345"
  business_tags:
    - department:sales
    - project:crm

governance_overrides:
  retention_days: 2555  # 7 years
```

## Workflow

When a job runs with catalog integration enabled:

1. **Extract & Transform:** Data is extracted and transformed as usual
2. **Write:** Data is written to Parquet files in S3
3. **Commit:** Files are committed to Iceberg (if catalog configured)
4. **Catalog Publishing** (if catalog block configured):
   a. **Register Dataset:** Create/update dataset with schema and metadata
   b. **Publish Lineage:** Create lineage relationship from source to target
   c. **Update Metadata:** Apply tags, owner, and classification

All catalog operations are **non-fatal** - if they fail, the job continues and data is still written.

## Error Handling

Catalog integration is designed to be resilient:

- **Connection Failures:** Logged as warnings, job continues
- **Registration Failures:** Logged, job continues
- **Partial Failures:** Some operations may succeed (e.g., schema registered but lineage failed)

Check logs for catalog-related events:
- `catalog_publishing` - Starting catalog publish
- `catalog_register_success` - Dataset registered successfully
- `catalog_lineage_success` - Lineage published successfully
- `catalog_metadata_success` - Metadata updated successfully
- `catalog_publish_error` - Catalog operation failed (non-fatal)

## Testing

### Unit Tests

```bash
# Run unit tests for catalog clients
pytest tests/test_catalog_glue.py -v
pytest tests/test_catalog_openmetadata.py -v
pytest tests/test_catalog_integration.py -v
```

### Smoke Tests

OpenMetadata smoke tests verify end-to-end integration with a local OpenMetadata instance:

```bash
# Start OpenMetadata locally (via Docker)
docker run -d -p 8585:8585 openmetadata/server:latest

# Run smoke tests
RUN_OPENMETADATA_SMOKE_TESTS=true pytest tests/smoke_test_openmetadata.py -v -s
```

## Best Practices

1. **Enable Gradually:** Start with `push_schema: true`, then add lineage and metadata
2. **Test Connection:** Use `test_connection()` method to verify catalog access
3. **Monitor Logs:** Watch for catalog-related log events
4. **Use Environment Variables:** Store sensitive credentials in environment variables
5. **Separate Catalogs by Environment:** Use different catalogs for dev/staging/prod
6. **Tag Consistently:** Use consistent tag formats across your organization

## Troubleshooting

### "Failed to connect to catalog"

- Check that the catalog URI is correct
- Verify credentials are properly configured
- Ensure the catalog service is running and accessible

### "Dataset registration failed"

- Verify the dataset name format matches catalog requirements
- Check that required metadata fields are provided
- Ensure permissions to create/update datasets

### "Lineage publication had issues"

- Verify source and target datasets are registered first
- Check that the lineage API is enabled in the catalog
- Some catalogs may store lineage as table properties instead

### "OpenMetadata import errors"

- Ensure `openmetadata-ingestion>=1.2.0` is installed
- Try: `pip install openmetadata-ingestion`

## See Also

- [Tag Derivation](TAG_DERIVATION.md) - Metadata propagation details
- [Config Reference](CONFIG_REFERENCE.md) - Complete job configuration reference
- [Iceberg Committer](ICEBERG_COMMITTER.md) - Iceberg catalog integration
