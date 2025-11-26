# Data Catalog Integration

Dativo supports integration with multiple data catalogs for lineage tracking and metadata management. This enables you to:

- Track data lineage from source to target
- Push table metadata (schema, description, tags, owners)
- Maintain data governance across your data platform
- Integrate with your organization's existing catalog infrastructure

## Supported Catalogs

1. **OpenMetadata** - Open-source metadata platform
2. **AWS Glue Data Catalog** - AWS native data catalog
3. **Databricks Unity Catalog** - Databricks unified governance solution
4. **Nessie** - Git-like data catalog for data lakehouse

## Configuration

Add a `catalog` block to your job configuration:

```yaml
catalog:
  type: openmetadata  # or aws_glue, databricks_unity, nessie
  connection:
    # Catalog-specific connection parameters
    host_port: "http://localhost:8585/api"
  enabled: true
  push_lineage: true
  push_metadata: true
```

## Catalog Types

### OpenMetadata

OpenMetadata is an open-source metadata platform with rich lineage and governance features.

**Configuration:**

```yaml
catalog:
  type: openmetadata
  connection:
    host_port: "http://openmetadata:8585/api"
    service_name: "dativo_iceberg_service"
    # Optional: JWT token for authentication
    jwt_token: "${OPENMETADATA_JWT_TOKEN}"
  enabled: true
  push_lineage: true
  push_metadata: true
```

**Requirements:**
- OpenMetadata server running and accessible
- Install: `pip install 'openmetadata-ingestion[metadata]>=0.13.0'`

**Features:**
- Full lineage tracking with visual graph
- Rich metadata management (tags, owners, descriptions)
- Data quality and profiling integration
- Team and role management

### AWS Glue Data Catalog

AWS Glue Data Catalog is AWS's native metadata repository.

**Configuration:**

```yaml
catalog:
  type: aws_glue
  connection:
    region: us-east-1
    # Optional: explicit credentials (can use IAM roles instead)
    aws_access_key_id: "${AWS_ACCESS_KEY_ID}"
    aws_secret_access_key: "${AWS_SECRET_ACCESS_KEY}"
  enabled: true
  push_lineage: true
  push_metadata: true
```

**Requirements:**
- AWS account with Glue permissions
- boto3 installed (included in base dependencies)

**Features:**
- Native AWS integration
- IAM-based access control
- Integration with Athena, EMR, and other AWS services
- Lineage stored as table properties

**Limitations:**
- No native lineage visualization (stored as table properties)
- Limited tagging capabilities compared to OpenMetadata

### Databricks Unity Catalog

Unity Catalog is Databricks' unified governance solution for lakehouses.

**Configuration:**

```yaml
catalog:
  type: databricks_unity
  connection:
    host: "https://your-workspace.cloud.databricks.com"
    token: "${DATABRICKS_TOKEN}"
    catalog: main
  enabled: true
  push_lineage: true
  push_metadata: true
```

**Requirements:**
- Databricks workspace with Unity Catalog enabled
- Install: `pip install databricks-sdk>=0.18.0`

**Features:**
- Fine-grained access control
- Data lineage tracking
- Data quality monitoring
- Multi-cloud support

**Limitations:**
- Requires Unity Catalog enabled workspace
- Lineage stored as table properties (limited native API)

### Nessie

Nessie provides Git-like operations for data lakehouses with Iceberg.

**Configuration:**

```yaml
catalog:
  type: nessie
  connection:
    uri: "http://nessie:19120"
    branch: main
    warehouse: "s3://lake/"
    catalog_name: nessie
    # Optional S3 configuration
    s3_endpoint: "${S3_ENDPOINT}"
    s3_access_key_id: "${AWS_ACCESS_KEY_ID}"
    s3_secret_access_key: "${AWS_SECRET_ACCESS_KEY}"
    s3_region: us-east-1
  enabled: true
  push_lineage: true
  push_metadata: true
```

**Requirements:**
- Nessie server running
- PyIceberg installed (included in base dependencies)

**Features:**
- Git-like branching for data
- Time-travel queries
- Atomic multi-table transactions
- Built for Iceberg tables

**Limitations:**
- Lineage stored as table properties
- No built-in UI (use Nessie UI separately)

## What Gets Tracked

### Table Metadata

- **Schema**: Column names, types, descriptions, constraints
- **Description**: Table purpose and documentation
- **Owner**: Team or individual responsible for the table
- **Tags**: Domain, data product, classification, compliance tags
- **Properties**: Source type, object, version, location

### Lineage Information

- **Source**: Fully qualified name of source system/table
- **Target**: Fully qualified name of target table
- **Pipeline**: Pipeline name and description
- **Metrics**: Records read/written, bytes written
- **Timing**: Start time, end time, duration
- **Status**: Success, failed, or running

### Tags and Governance

Tags are automatically derived from:
- Asset definition tags
- Domain and data product
- Compliance classifications
- Regulations (GDPR, HIPAA, etc.)
- Custom job-level tags

## Examples

### Complete Job with OpenMetadata

```yaml
tenant_id: acme
source_connector: postgres
source_connector_path: connectors/postgres.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: customers
asset_path: assets/postgres/v1.0/customers.yaml

source:
  tables:
    - name: customers

target:
  connection:
    s3:
      bucket: "data-lake"

catalog:
  type: openmetadata
  connection:
    host_port: "http://openmetadata:8585/api"
    service_name: "acme_data_platform"
  enabled: true
  push_lineage: true
  push_metadata: true

logging:
  level: INFO
```

## Testing Catalog Integration

### Unit Tests

Run unit tests for catalog clients:

```bash
pytest tests/unit/catalog/ -v
```

### Integration Tests

Run integration tests with OpenMetadata (requires OpenMetadata running):

```bash
# Start OpenMetadata
docker-compose -f docker-compose.catalog.yml up -d

# Run integration tests
pytest tests/integration/catalog/ -v
```

### Smoke Tests

Run smoke tests with automatic OpenMetadata setup:

```bash
pytest tests/smoke/test_catalog_smoke.py -v -s
```

## Troubleshooting

### OpenMetadata Connection Issues

**Error**: "Failed to connect to OpenMetadata"

**Solutions**:
1. Check OpenMetadata is running: `curl http://localhost:8585/api/v1/system/version`
2. Verify `host_port` in configuration
3. Check authentication if enabled
4. Review OpenMetadata logs: `docker logs openmetadata-server`

### AWS Glue Permission Issues

**Error**: "Access Denied" when creating tables

**Solutions**:
1. Ensure IAM role/user has Glue permissions:
   - `glue:CreateDatabase`
   - `glue:CreateTable`
   - `glue:UpdateTable`
   - `glue:GetTable`
2. Check AWS credentials are properly configured
3. Verify region is correct

### Databricks Token Issues

**Error**: "Authentication failed"

**Solutions**:
1. Generate new token in Databricks workspace
2. Verify token has necessary permissions
3. Check workspace URL is correct (include https://)

### Catalog Operations Fail but Pipeline Continues

This is expected behavior. Catalog operations are optional and non-blocking. The pipeline will log warnings but continue execution if catalog operations fail.

To make catalog operations required, handle the logs and implement custom error handling in your orchestration layer.

## Best Practices

1. **Use Environment Variables**: Store credentials in environment variables or secret managers
2. **Enable Selectively**: Start with `push_metadata: true` and `push_lineage: false` to verify metadata works
3. **Monitor Catalog Performance**: Catalog operations add latency; monitor impact on pipeline performance
4. **Tag Consistently**: Use consistent tagging across your organization for better discoverability
5. **Document Owners**: Always specify owners in asset definitions for clear accountability
6. **Test in Dev**: Test catalog integration in development before production deployment

## Performance Considerations

- Catalog operations are synchronous and add to pipeline execution time
- OpenMetadata typically adds 1-3 seconds per pipeline run
- AWS Glue typically adds 2-5 seconds per pipeline run
- Consider disabling catalog for high-frequency pipelines (< 1 minute intervals)
- Catalog operations are retried on transient failures

## Future Enhancements

Planned enhancements for catalog integration:

- Async catalog operations for better performance
- Batch lineage updates for multiple pipelines
- Data quality metrics integration
- Schema evolution tracking
- Column-level lineage
- Cost attribution tracking

## Support

For issues or questions about catalog integration:

1. Check this documentation first
2. Review test cases in `tests/integration/catalog/`
3. Check catalog-specific documentation
4. Open an issue on GitHub with logs and configuration
