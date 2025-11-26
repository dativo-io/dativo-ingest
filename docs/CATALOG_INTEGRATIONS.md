# Data Catalog Integrations

Dativo supports integration with multiple data catalogs for lineage tracking and metadata management. When a catalog is configured in a job definition, lineage information and metadata (tags, owners, descriptions, etc.) are automatically pushed to the catalog.

## Supported Catalogs

- **AWS Glue** - Amazon's data catalog service
- **Databricks Unity Catalog** - Databricks' unified data catalog
- **Nessie** - Git-like versioning for data lakes (via Iceberg table properties)
- **OpenMetadata** - Open-source metadata platform (recommended for local testing)

## Configuration

Add an optional `catalog` block to your job configuration:

```yaml
catalog:
  type: openmetadata  # Options: aws_glue, databricks_unity, nessie, openmetadata
  enabled: true
  connection:
    # Catalog-specific connection settings
    api_url: "http://localhost:8585/api"  # For OpenMetadata
    auth_token: "${OPENMETADATA_TOKEN}"  # Optional authentication
    service_name: "dativo_service"  # Optional service name
```

## Catalog-Specific Configuration

### OpenMetadata

```yaml
catalog:
  type: openmetadata
  enabled: true
  connection:
    api_url: "http://localhost:8585/api"
    auth_token: "${OPENMETADATA_TOKEN}"  # Optional
    service_name: "dativo_service"  # Optional, defaults to "dativo_service"
    timeout: 30  # Optional, request timeout in seconds
```

**Local Testing**: OpenMetadata can be started using docker-compose:
```bash
docker-compose -f docker-compose.dev.yml up -d openmetadata
```

### AWS Glue

```yaml
catalog:
  type: aws_glue
  enabled: true
  connection:
    region: "us-east-1"
    aws_access_key_id: "${AWS_ACCESS_KEY_ID}"  # Optional, uses default credentials if not provided
    aws_secret_access_key: "${AWS_SECRET_ACCESS_KEY}"  # Optional
```

### Databricks Unity Catalog

```yaml
catalog:
  type: databricks_unity
  enabled: true
  connection:
    host: "https://your-workspace.cloud.databricks.com"
    token: "${DATABRICKS_TOKEN}"  # Personal access token
```

### Nessie

```yaml
catalog:
  type: nessie
  enabled: true
  connection:
    # Nessie integration leverages existing Iceberg committer
    # Lineage is stored in table properties
```

## What Gets Pushed

When a catalog is configured, the following information is automatically pushed:

### Lineage
- Source entities (tables, files, API endpoints)
- Target entities (tables, datasets)
- Operation type (e.g., "ingest")

### Metadata
- **Tags**: From asset definition, classification, FinOps, and governance
- **Owners**: From asset definition team configuration
- **Description**: From asset definition description fields
- **Schema**: Column definitions with types and constraints
- **Compliance**: Classification, retention policies
- **FinOps**: Cost center, business tags, project, environment

## Example

See `examples/jobs/catalog_integration_example.yaml` for a complete example.

## Testing

### Unit Tests

Run unit tests for catalog integrations:
```bash
pytest tests/test_catalog_integrations.py -v
```

### Smoke Tests (OpenMetadata)

For local smoke tests with OpenMetadata:

1. Start OpenMetadata:
```bash
docker-compose -f docker-compose.dev.yml up -d openmetadata
```

2. Wait for service to be ready (may take a few minutes)

3. Run smoke tests:
```bash
pytest tests/integration/test_catalog_smoke.py -v -m smoke
```

Or set environment variables:
```bash
export OPENMETADATA_URL=http://localhost:8585/api
export OPENMETADATA_TOKEN=your-token-if-needed
pytest tests/integration/test_catalog_smoke.py -v
```

## Implementation Details

### Catalog Manager

The `CatalogManager` class routes to the appropriate catalog implementation based on the `type` field in the job configuration. It provides a unified interface for:

- `ensure_entity_exists()` - Creates or updates entities in the catalog
- `push_metadata()` - Pushes tags, owners, descriptions, etc.
- `push_lineage()` - Pushes lineage relationships

### Base Catalog Interface

All catalog implementations extend `BaseCatalog`, which provides:

- Automatic extraction of source entities from job configuration
- Automatic extraction of target entities from asset definition
- Automatic extraction of metadata from asset definition and job config

### Integration Points

Catalog operations are integrated into the job execution flow:

1. **Entity Creation**: After job validation, entities are ensured to exist in the catalog
2. **Metadata Push**: Initial metadata is pushed when entity is created
3. **Lineage Push**: After successful file commit, lineage is pushed to the catalog

## Error Handling

Catalog operations are designed to be non-blocking:

- If catalog initialization fails, a warning is logged and the job continues
- If metadata/lineage push fails, a warning is logged but the job continues
- This ensures that catalog issues don't prevent data ingestion

## Future Enhancements

Potential future enhancements:

- Support for additional catalogs (e.g., Apache Atlas, DataHub)
- Incremental lineage updates
- Schema evolution tracking
- Data quality metrics integration
