# Data Catalog Integration

Dativo ingestion platform supports integration with multiple data catalogs for automatic lineage tracking and metadata management. When configured, lineage information including tags, owners, and governance metadata is automatically pushed to your data catalog after successful job execution.

## Supported Catalogs

- **AWS Glue Data Catalog** - AWS-native metadata management
- **Databricks Unity Catalog** - Unified governance for Databricks
- **Nessie** - Git-like data catalog with branching
- **OpenMetadata** - Open-source metadata and governance platform

## Configuration

Add a `catalog` block to your job configuration:

```yaml
tenant_id: acme
source_connector_path: connectors/postgres.yaml
target_connector_path: connectors/iceberg.yaml
asset_path: assets/postgres/v1.0/customers.yaml

# Data catalog configuration
catalog:
  type: openmetadata  # aws_glue, databricks_unity, nessie, openmetadata
  enabled: true
  connection:
    host_port: http://openmetadata:8585/api
    service_name: dativo_ingestion
  options:
    database: production
    schema: default

source:
  tables:
    - object: customers

target:
  connection:
    s3:
      bucket: data-lake
      # ... connection details
```

## Catalog-Specific Configuration

### AWS Glue Data Catalog

```yaml
catalog:
  type: aws_glue
  enabled: true
  connection:
    region: us-east-1
    database: production_db
    bucket: data-lake-bucket
    # Optional: Override AWS credentials (defaults to environment/IAM)
    aws_access_key_id: ${AWS_ACCESS_KEY_ID}
    aws_secret_access_key: ${AWS_SECRET_ACCESS_KEY}
```

**Features:**
- Automatically creates/updates Glue tables
- Pushes schema and partitioning information
- Stores metadata as table properties
- Integrates with AWS Lake Formation for access control

**Permissions Required:**
- `glue:CreateTable`
- `glue:UpdateTable`
- `glue:GetTable`

### Databricks Unity Catalog

```yaml
catalog:
  type: databricks_unity
  enabled: true
  connection:
    workspace_url: https://your-workspace.cloud.databricks.com
    token: ${DATABRICKS_TOKEN}
    catalog: main
    schema: production
    bucket: data-lake-bucket
```

**Features:**
- Creates tables in Unity Catalog
- Supports three-level namespace (catalog.schema.table)
- Pushes governance metadata and tags
- Integrates with Databricks access policies

**Permissions Required:**
- `CREATE TABLE` on schema
- `USE CATALOG` on catalog
- `USE SCHEMA` on schema

### Nessie

```yaml
catalog:
  type: nessie
  enabled: true
  connection:
    uri: http://nessie:19120/api/v1
    branch: main
    bucket: data-lake-bucket
```

**Features:**
- Git-like branching and versioning
- Isolated data views per branch
- Multi-table transactions
- Time-travel queries

**Configuration Notes:**
- Uses PyNessie client
- Automatically creates branches if they don't exist
- Supports both standalone and integrated Nessie deployments

### OpenMetadata

```yaml
catalog:
  type: openmetadata
  enabled: true
  connection:
    host_port: http://openmetadata:8585/api
    service_name: dativo_ingestion
    # Optional: JWT token for authentication
    jwt_token: ${OPENMETADATA_JWT_TOKEN}
  options:
    database: production
    schema: default
```

**Features:**
- Rich metadata model with data quality, lineage, and profiling
- Automatic entity creation (service, database, schema, table)
- Tag and owner propagation
- Data lineage visualization
- Column-level governance

**Authentication Options:**
- No-auth (local development)
- JWT token (production)

## Metadata Propagation

The catalog integration automatically pushes the following metadata:

### 1. Table Metadata
- Table name and fully qualified name
- Schema/database/catalog hierarchy
- Physical location (S3/storage path)
- File format and partitioning

### 2. Schema Information
- Column names and types
- Required/optional constraints
- Column descriptions
- Column-level tags (PII, sensitive, etc.)

### 3. Governance Metadata
- **Owners**: From `team.owner` in asset definition
- **Tags**: From asset definition `tags` field
- **Classification**: From `compliance.classification`
- **Retention**: From `compliance.retention_days`
- **Regulations**: From `compliance.regulations`

### 4. FinOps Metadata
- Cost center
- Business tags
- Project attribution
- Environment tags

### 5. Lineage Information
- Source system and object name
- Target system and table name
- Execution timestamp
- Record count and file count
- Data volume (bytes)

## Tag Propagation Hierarchy

Tags are derived using a three-level hierarchy (highest to lowest priority):

1. **Job-level overrides**: `classification_overrides`, `finops`, `governance_overrides`
2. **Asset-level metadata**: Tags, team, compliance from asset YAML
3. **Source-level tags**: Tags from source connector (lowest priority)

Example:

```yaml
# In job config
classification_overrides:
  email: PII
  ssn: PII
finops:
  cost_center: analytics
  project: customer-360
governance_overrides:
  retention_days: 180
```

## Error Handling

Catalog integration uses a fail-safe approach:

- **Job succeeds even if catalog push fails**: Lineage push failures are logged as warnings, not errors
- **Partial failures**: If some metadata can't be pushed, the rest continues
- **Retry logic**: Automatic retries for transient failures
- **Detailed logging**: All catalog operations are logged with context

## Examples

### Example 1: OpenMetadata with Full Governance

```yaml
tenant_id: acme
source_connector_path: connectors/stripe.yaml
target_connector_path: connectors/iceberg.yaml
asset_path: assets/stripe/v1.0/customers.yaml

catalog:
  type: openmetadata
  enabled: true
  connection:
    host_port: http://openmetadata:8585/api
    service_name: dativo_stripe_ingestion
  options:
    database: stripe
    schema: raw

source:
  objects: [customers]

target:
  connection:
    s3:
      bucket: data-lake
      prefix: raw/stripe/customers

# Override governance metadata
classification_overrides:
  email: PII
  phone: PII
  address: PII
finops:
  cost_center: revenue
  business_tags: [stripe, payments]
  project: revenue-analytics
governance_overrides:
  retention_days: 2555  # 7 years for financial data
```

### Example 2: AWS Glue with Multi-Region

```yaml
tenant_id: acme
source_connector_path: connectors/postgres.yaml
target_connector_path: connectors/s3.yaml
asset_path: assets/postgres/v1.0/orders.yaml

catalog:
  type: aws_glue
  enabled: true
  connection:
    region: us-west-2
    database: production_orders
    bucket: acme-data-lake-west
    # Uses IAM role credentials by default

source:
  tables:
    - object: orders

target:
  connection:
    s3:
      bucket: acme-data-lake-west
      region: us-west-2
      prefix: raw/orders
```

### Example 3: Databricks Unity Catalog

```yaml
tenant_id: acme
source_connector_path: connectors/hubspot.yaml
target_connector_path: connectors/iceberg.yaml
asset_path: assets/hubspot/v1.0/contacts.yaml

catalog:
  type: databricks_unity
  enabled: true
  connection:
    workspace_url: https://acme.cloud.databricks.com
    token: ${DATABRICKS_TOKEN}
    catalog: main
    schema: hubspot
    bucket: acme-unity-catalog

source:
  objects: [contacts]

target:
  connection:
    s3:
      bucket: acme-unity-catalog
      prefix: hubspot/contacts
```

## Disabling Catalog Integration

To temporarily disable catalog integration without removing the configuration:

```yaml
catalog:
  type: openmetadata
  enabled: false  # Set to false to disable
  connection:
    # ... configuration preserved
```

Or remove the entire `catalog` block from your job configuration.

## Troubleshooting

### Catalog connection failures

**Symptom**: Job succeeds but shows warning: "Failed to push lineage to catalog"

**Solutions**:
1. Verify catalog service is accessible:
   ```bash
   # OpenMetadata
   curl http://openmetadata:8585/api/v1/system/version
   
   # Nessie
   curl http://nessie:19120/api/v1/trees
   ```

2. Check credentials and permissions:
   ```bash
   # AWS Glue
   aws glue get-database --name production_db
   
   # Databricks
   curl -H "Authorization: Bearer $DATABRICKS_TOKEN" \
        https://workspace.databricks.com/api/2.0/unity-catalog/catalogs
   ```

3. Review logs for detailed error messages:
   ```bash
   dativo run --config job.yaml --mode self_hosted 2>&1 | grep catalog
   ```

### Schema conflicts

**Symptom**: Catalog rejects schema updates

**Solutions**:
1. Ensure schema evolution is compatible
2. For Glue: Check `UpdateBehavior` settings
3. For Unity Catalog: Verify `ALTER TABLE` permissions
4. Consider versioning tables for breaking changes

### Missing metadata

**Symptom**: Some tags or owners not appearing in catalog

**Solutions**:
1. Verify asset definition includes required fields
2. Check tag hierarchy (job overrides > asset > source)
3. Ensure catalog supports the metadata type
4. Review catalog-specific naming restrictions

## Best Practices

### 1. Use Environment-Specific Catalogs

Separate catalogs by environment:

```yaml
# production.yaml
catalog:
  connection:
    database: production

# staging.yaml  
catalog:
  connection:
    database: staging
```

### 2. Consistent Naming Conventions

Follow catalog-specific naming rules:
- AWS Glue: lowercase, underscores
- Databricks Unity: alphanumeric, underscores
- OpenMetadata: flexible but consistent

### 3. Comprehensive Asset Definitions

Include all governance metadata in asset definitions:

```yaml
team:
  owner: data-team@company.com
  roles:
    - name: Data Engineer
      email: engineer@company.com
compliance:
  classification: [PII]
  regulations: [GDPR, CCPA]
  retention_days: 90
tags: [customer-data, analytics]
```

### 4. Monitor Catalog Operations

Track catalog integration health:
- Monitor logs for catalog warnings/errors
- Set up alerts for repeated failures
- Periodically audit catalog metadata accuracy

### 5. Test Before Production

Always test catalog integration in staging:

```bash
# Test catalog connectivity
dativo run --config staging_job.yaml

# Verify metadata in catalog UI/API
# OpenMetadata: http://localhost:8080
# AWS Glue Console: https://console.aws.amazon.com/glue
```

## Performance Considerations

- **Async by default**: Catalog operations don't block data writing
- **Batch updates**: Multiple files pushed in single catalog transaction
- **Caching**: Catalog clients cache connections
- **Timeout**: Catalog operations timeout after 30s by default

## Security

### Credentials Management

Never hardcode credentials. Use one of:

1. **Environment variables**:
   ```yaml
   token: ${DATABRICKS_TOKEN}
   ```

2. **Secret managers**:
   ```bash
   dativo run --secret-manager vault --config job.yaml
   ```

3. **IAM roles** (AWS):
   ```yaml
   # No credentials needed - uses IAM role
   catalog:
     type: aws_glue
     connection:
       region: us-east-1
   ```

### Network Security

- Use private endpoints for cloud catalogs
- Configure VPC peering for Databricks
- Use TLS/SSL for all connections
- Restrict catalog access with IAM/RBAC

## Testing

Run catalog integration tests:

```bash
# Unit tests (mocked)
pytest tests/test_catalog_integrations.py -v

# Integration tests with OpenMetadata
cd tests/integration
docker-compose -f docker-compose-openmetadata.yml up -d
export RUN_OPENMETADATA_TESTS=1
pytest test_openmetadata_smoke.py -v

# Or use convenience script
./tests/integration/run_openmetadata_tests.sh
```

## API Reference

See Python API documentation:

```python
from dativo_ingest.catalog_integrations import (
    create_catalog_client,
    LineageInfo,
    BaseCatalogClient,
)

# Create client
catalog_config = CatalogConfig(type="openmetadata", ...)
client = create_catalog_client(catalog_config)

# Push lineage
lineage_info = LineageInfo(...)
result = client.push_lineage(lineage_info)
```

## Migration Guide

### From No Catalog to Catalog-Enabled

1. Add catalog block to job configs
2. Test in staging environment
3. Verify metadata appears correctly
4. Roll out to production jobs

### Switching Catalog Types

1. Update `catalog.type` in job config
2. Update `catalog.connection` for new catalog
3. Run job to populate new catalog
4. Verify metadata transfer
5. Decommission old catalog (optional)

## Future Enhancements

Planned features:
- Column-level lineage tracking
- Data quality metrics in catalogs
- Automated data profiling
- Schema drift detection
- Multi-catalog synchronization
