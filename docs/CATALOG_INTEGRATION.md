# Data Catalog Integration

Dativo supports integration with data catalogs for automatic lineage tracking and metadata management. When a catalog is configured in a job, lineage information (source → target relationships) and metadata (tags, owners, descriptions) are automatically pushed to the catalog.

## Supported Catalogs

- **OpenMetadata** - Open-source metadata management platform (recommended for local testing)
- **AWS Glue** - AWS data catalog service
- **Databricks Unity Catalog** - Databricks' unified catalog
- **Nessie** - Git-like data catalog (lineage via Iceberg table properties)

## Configuration

Add an optional `catalog` block to your job configuration:

```yaml
tenant_id: acme
source_connector_path: connectors/csv.yaml
target_connector_path: connectors/iceberg.yaml
asset_path: assets/csv/v1.0/employee.yaml

source:
  files:
    - path: data/employees.csv

target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"

# Catalog configuration (optional)
catalog:
  type: openmetadata  # or aws_glue, databricks_unity, nessie
  connection:
    api_url: "${OPENMETADATA_API_URL:-http://localhost:8585/api}"
    auth_token: "${OPENMETADATA_AUTH_TOKEN}"
  database: acme_data
  push_lineage: true
  push_metadata: true
```

### Catalog Configuration Fields

- `type` (required): Catalog type (`openmetadata`, `aws_glue`, `databricks_unity`, `nessie`)
- `connection` (required): Connection configuration (varies by catalog type)
- `database` (optional): Database/schema name in catalog (defaults to asset domain)
- `table_name` (optional): Table name override (defaults to asset name)
- `push_lineage` (optional): Whether to push lineage (default: `true`)
- `push_metadata` (optional): Whether to push metadata (default: `true`)

## Catalog-Specific Configuration

### OpenMetadata

```yaml
catalog:
  type: openmetadata
  connection:
    api_url: "http://localhost:8585/api"
    auth_token: "${OPENMETADATA_AUTH_TOKEN}"
  database: my_database
```

**Environment Variables:**
- `OPENMETADATA_API_URL`: OpenMetadata API URL (default: `http://localhost:8585/api`)
- `OPENMETADATA_AUTH_TOKEN`: Authentication token

**Features:**
- Full lineage support with source → target relationships
- Rich metadata support (tags, owners, descriptions, custom properties)
- Automatic table creation if not exists

### AWS Glue

```yaml
catalog:
  type: aws_glue
  connection:
    region: "${AWS_REGION}"
    aws_access_key_id: "${AWS_ACCESS_KEY_ID}"
    aws_secret_access_key: "${AWS_SECRET_ACCESS_KEY}"
  database: my_database
```

**Environment Variables:**
- `AWS_REGION`: AWS region
- `AWS_ACCESS_KEY_ID`: AWS access key
- `AWS_SECRET_ACCESS_KEY`: AWS secret key

**Features:**
- Table creation and metadata updates
- Lineage stored in table parameters (Glue doesn't have native lineage)
- Tags and owners stored in table parameters

### Databricks Unity Catalog

```yaml
catalog:
  type: databricks_unity
  connection:
    workspace_url: "${DATABRICKS_WORKSPACE_URL}"
    access_token: "${DATABRICKS_ACCESS_TOKEN}"
    catalog: "${DATABRICKS_CATALOG}"
    warehouse_id: "${DATABRICKS_WAREHOUSE_ID}"
  database: my_schema
```

**Environment Variables:**
- `DATABRICKS_WORKSPACE_URL`: Databricks workspace URL
- `DATABRICKS_ACCESS_TOKEN`: Personal access token or service principal token
- `DATABRICKS_CATALOG`: Catalog name (default: `main`)
- `DATABRICKS_WAREHOUSE_ID`: SQL warehouse ID for table creation

**Features:**
- Table creation via SQL API
- Metadata updates (tags, owners, descriptions)
- Lineage stored in table properties (Unity Catalog lineage is typically managed through workflows)

### Nessie

```yaml
catalog:
  type: nessie
  connection:
    uri: "${NESSIE_URI:-http://localhost:19120}"
  database: my_database
```

**Environment Variables:**
- `NESSIE_URI`: Nessie server URI (default: `http://localhost:19120`)

**Features:**
- Lineage stored in Iceberg table properties
- Metadata handled by IcebergCommitter (tags, owners, etc.)
- Git-like versioning through Nessie branches

## What Gets Pushed

### Lineage

Lineage information tracks the flow of data from sources to targets:

- **Source entities**: Extracted from job source configuration
  - Database tables: `database.schema.table`
  - Files: `file://path/to/file.csv`
  - APIs: `api://source_type/object`
- **Target entity**: Extracted from job target configuration
  - Table: `database.schema.table`
  - Location: S3 path where data is stored
- **Operation**: Type of operation (e.g., `ingest`, `transform`)

### Metadata

Metadata includes governance and operational information:

- **Tags**: Extracted from asset definition and job config
  - Asset tags
  - Domain tags
  - Data product tags
  - Source type tags
  - Compliance classification tags
  - FinOps tags (cost center, business tags)
- **Owners**: Extracted from asset team definition
  - Primary owner
  - Team role members
- **Description**: Extracted from asset description
  - Purpose
  - Usage
  - Limitations
- **Custom Properties**:
  - Source type
  - Asset version
  - Tenant ID

## Example: Complete Job with Catalog

```yaml
tenant_id: acme
source_connector_path: connectors/csv.yaml
target_connector_path: connectors/iceberg.yaml
asset_path: assets/csv/v1.0/employee.yaml

source:
  files:
    - path: data/employees.csv
      object: Employee

target:
  connection:
    s3:
      bucket: acme-data-lake
      prefix: raw/acme/employees

catalog:
  type: openmetadata
  connection:
    api_url: "http://openmetadata.acme.internal:8585/api"
    auth_token: "${OPENMETADATA_AUTH_TOKEN}"
  database: acme_data
  push_lineage: true
  push_metadata: true

schema_validation_mode: strict
logging:
  level: INFO
```

## Testing with OpenMetadata

For local testing, you can run OpenMetadata using Docker:

```bash
# Start OpenMetadata server
docker run -d \
  --name openmetadata \
  -p 8585:8585 \
  openmetadata/openmetadata-server:latest

# Get auth token (after server starts)
# Access UI at http://localhost:8585
# Create a user and generate an access token
export OPENMETADATA_AUTH_TOKEN="your-token-here"
export OPENMETADATA_API_URL="http://localhost:8585/api"

# Run job with catalog
dativo run --config jobs/acme/employees_with_catalog.yaml
```

## Error Handling

Catalog operations are **non-blocking**. If catalog push fails:

- Job execution continues normally
- Data is still written to storage
- Warning is logged with error details
- Exit code is not affected

This ensures that catalog issues don't block data ingestion.

## Best Practices

1. **Start with OpenMetadata** for local development and testing
2. **Use environment variables** for sensitive credentials
3. **Test catalog connectivity** before production deployment
4. **Monitor catalog push logs** to ensure metadata is being updated
5. **Use descriptive database names** that match your data organization
6. **Enable both lineage and metadata** for complete catalog coverage

## Troubleshooting

### Catalog Push Fails

- Check catalog server connectivity
- Verify authentication credentials
- Check catalog logs for detailed error messages
- Ensure database/schema exists in catalog (some catalogs require pre-creation)

### Lineage Not Showing

- Verify `push_lineage: true` in catalog config
- Check that source entities are correctly extracted
- For catalogs without native lineage (Glue, Unity), check table properties

### Metadata Not Updating

- Verify `push_metadata: true` in catalog config
- Check that asset definition has required fields (team.owner, tags, etc.)
- Verify catalog permissions for metadata updates

## See Also

- [Configuration Reference](CONFIG_REFERENCE.md) - Complete job configuration guide
- [Catalog Limitations](CATALOG_LIMITATIONS.md) - Known limitations and workarounds
- [Examples](../examples/jobs/) - Example job configurations with catalog
