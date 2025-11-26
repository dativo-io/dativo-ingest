# Data Catalog Integration

Dativo supports integration with multiple data catalogs for pushing lineage information and metadata. This enables automatic tracking of data flows and governance metadata in your data catalog.

## Supported Catalogs

- **OpenMetadata** - Open-source metadata management platform
- **AWS Glue** - AWS data catalog service
- **Databricks Unity Catalog** - Databricks unified data governance
- **Nessie** - Git-like versioning for data lakes (via Iceberg table properties)

## Configuration

Add an optional `catalog` block to your job configuration:

```yaml
tenant_id: acme
source_connector: stripe
source_connector_path: connectors/stripe.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: stripe_customers
asset_path: assets/stripe/v1.0/customers.yaml

# Catalog integration (optional)
catalog:
  type: openmetadata
  api_url: http://localhost:8585/api
  auth_token: ${OPENMETADATA_AUTH_TOKEN}  # Optional

source:
  objects: [customers]

target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
      prefix: "raw/stripe/customers"
```

## Catalog Types

### OpenMetadata

```yaml
catalog:
  type: openmetadata
  api_url: http://localhost:8585/api  # OpenMetadata API URL
  auth_token: ${OPENMETADATA_AUTH_TOKEN}  # Optional: Bearer token
```

**Environment Variables:**
- `OPENMETADATA_API_URL` - OpenMetadata API URL (default: `http://localhost:8585/api`)
- `OPENMETADATA_AUTH_TOKEN` - Optional authentication token

### AWS Glue

```yaml
catalog:
  type: aws_glue
  region: us-east-1  # AWS region
```

**Environment Variables:**
- `AWS_REGION` - AWS region (default: `us-east-1`)
- AWS credentials via standard AWS SDK methods (environment variables, IAM role, etc.)

### Databricks Unity Catalog

```yaml
catalog:
  type: databricks
  workspace_url: https://your-workspace.cloud.databricks.com
  token: ${DATABRICKS_TOKEN}
```

**Environment Variables:**
- `DATABRICKS_WORKSPACE_URL` - Databricks workspace URL
- `DATABRICKS_TOKEN` - Databricks personal access token

### Nessie

```yaml
catalog:
  type: nessie
```

**Note:** Nessie lineage and metadata are handled via Iceberg table properties. The Nessie catalog configuration is primarily for consistency with other catalog integrations. Nessie connection details are configured in `target.connection.nessie`.

## What Gets Pushed

### Lineage

When a catalog is configured, Dativo automatically pushes lineage information showing:
- **Source entities**: The source systems/tables from which data is extracted
- **Target entity**: The destination table where data is written
- **Relationships**: Edges connecting sources to targets

### Metadata

The following metadata is pushed to the catalog:

- **Tags**: Derived from asset definition, job config, and source system
  - Classification tags (field-level and table-level)
  - Governance tags (domain, data product, retention, etc.)
  - FinOps tags (cost center, business tags, project, environment)
  - Asset tags from asset definition

- **Owners**: Extracted from asset definition (`team.owner`) or job config overrides

- **Descriptions**: Purpose and usage information from asset definition

- **Domain and Data Product**: Organizational metadata for data governance

## Tag Hierarchy

Tags follow a three-level hierarchy (later overrides earlier):

1. **Source system tags** (LOWEST priority) - From connector metadata
2. **Asset definition tags** (MEDIUM priority) - From schema, compliance, finops
3. **Job configuration tags** (HIGHEST priority) - From classification_overrides, finops, governance_overrides

## Example: Complete Job with Catalog

```yaml
tenant_id: acme
source_connector: stripe
source_connector_path: connectors/stripe.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: stripe_customers
asset_path: assets/stripe/v1.0/customers.yaml

# Catalog integration
catalog:
  type: openmetadata
  api_url: http://openmetadata:8585/api
  auth_token: ${OPENMETADATA_AUTH_TOKEN}

# Source configuration
source:
  objects: [customers]
  incremental:
    lookback_days: 1

# Target configuration
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
      prefix: "raw/stripe/customers"

# Metadata overrides
classification_overrides:
  email: "pii"
  amount: "financial"

finops:
  cost_center: "FIN-001"
  business_tags: ["payments", "revenue"]

governance_overrides:
  owner: "finance-team@acme.com"
```

## Error Handling

Catalog integration failures are logged as warnings but do not fail the job. This ensures that:
- Data ingestion continues even if catalog push fails
- Catalog issues don't block critical data pipelines
- Errors are logged for debugging and monitoring

## Testing

### Unit Tests

Run unit tests for catalog integration:

```bash
pytest tests/test_catalog_integration.py -v
```

### Smoke Tests

Run smoke tests with mocked requests:

```bash
pytest tests/test_catalog_integration_smoke.py -v
```

### Integration Tests

For integration tests with a real OpenMetadata instance:

1. Start OpenMetadata locally:
```bash
docker run -d -p 8585:8585 openmetadata/openmetadata-server:latest
```

2. Run integration tests:
```bash
OPENMETADATA_API_URL=http://localhost:8585/api pytest tests/integration/test_catalog_openmetadata_integration.py -v --run-openmetadata
```

## Troubleshooting

### OpenMetadata Connection Issues

- Verify OpenMetadata is running: `curl http://localhost:8585/api/v1/system/version`
- Check authentication token if required
- Verify API URL format (should end with `/api`)

### AWS Glue Issues

- Ensure AWS credentials are configured
- Verify table exists in Glue catalog
- Check IAM permissions for Glue table updates

### Databricks Issues

- Verify workspace URL format
- Check token permissions (needs Unity Catalog access)
- Ensure table exists in Unity Catalog

### General Issues

- Check job logs for catalog push errors
- Verify catalog configuration format
- Ensure catalog type is supported

## See Also

- [Tag Propagation Documentation](TAG_PROPAGATION.md) - How tags flow through the system
- [Configuration Reference](CONFIG_REFERENCE.md) - Complete configuration options
- [Asset Definitions](MINIMAL_ASSET_EXAMPLE.md) - Asset definition structure
