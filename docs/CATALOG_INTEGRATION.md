# Data Catalog Integration

This document describes the data catalog integration feature that allows pushing lineage and metadata to external data catalogs.

## Overview

The catalog integration feature enables automatic pushing of:
- **Lineage information**: Source-to-target data flow relationships
- **Metadata**: Tags, owners, descriptions, schema, and custom properties

## Supported Catalogs

1. **AWS Glue**: AWS Glue Data Catalog
2. **Databricks Unity Catalog**: Databricks Unity Catalog
3. **Nessie**: Nessie catalog (for Iceberg tables)
4. **OpenMetadata**: OpenMetadata catalog (recommended for local testing)

## Configuration

Add an optional `catalog` block to your job configuration:

```yaml
catalog:
  type: openmetadata  # Options: aws_glue, databricks_unity, nessie, openmetadata
  connection:
    api_endpoint: http://localhost:8585/api
    auth_provider: basic
    username: admin
    password: admin
    database_service: default
  database: example_schema  # Optional: database/schema name
  table_name: customers  # Optional: override table name (defaults to asset name)
```

## Catalog-Specific Configuration

### OpenMetadata

```yaml
catalog:
  type: openmetadata
  connection:
    api_endpoint: http://localhost:8585/api
    auth_provider: basic  # or jwt
    username: admin
    password: admin
    database_service: default
  database: schema_name
```

### AWS Glue

```yaml
catalog:
  type: aws_glue
  connection:
    region: us-east-1
    access_key_id: ${AWS_ACCESS_KEY_ID}  # Optional: can use IAM role
    secret_access_key: ${AWS_SECRET_ACCESS_KEY}  # Optional: can use IAM role
  database: database_name
```

### Databricks Unity Catalog

```yaml
catalog:
  type: databricks_unity
  connection:
    workspace_url: https://workspace.cloud.databricks.com
    access_token: ${DATABRICKS_TOKEN}
    catalog: main
  database: schema_name
```

### Nessie

```yaml
catalog:
  type: nessie
  connection:
    uri: http://localhost:19120/api/v1
    branch: main
    auth_token: ${NESSIE_TOKEN}  # Optional
  database: namespace_name
```

## What Gets Pushed

### Metadata

The following metadata is automatically extracted from your asset definition and pushed to the catalog:

- **Name**: Table name (from asset name or `catalog.table_name`)
- **Description**: From `asset.description.purpose`
- **Tags**: From `asset.tags`
- **Owners**: From `asset.team.owner`
- **Schema**: From `asset.schema`
- **Classification**: From `asset.compliance.classification`
- **Cost Center**: From `asset.finops.cost_center`
- **Business Tags**: From `asset.finops.business_tags`
- **Project**: From `asset.finops.project`
- **Environment**: From `job.environment`
- **Custom Properties**: Domain, dataProduct, tenant, source_type

### Lineage

Lineage information is automatically extracted from source configuration:

- **Source Entities**: Detected from source connector configuration
- **Target Entity**: The output table
- **Process Name**: `{tenant_id}_{asset_name}`
- **Process Type**: `etl`

## Execution Flow

1. Job executes normally (extract, transform, load)
2. On successful completion (exit code 0), catalog integration is triggered
3. Metadata is pushed to the catalog
4. Lineage is pushed to the catalog (if source entities are detected)
5. Errors in catalog push are logged as warnings but don't fail the job

## Testing

### Unit Tests

```bash
pytest tests/test_catalog.py -v
```

### OpenMetadata Smoke Tests

Start OpenMetadata locally:

```bash
docker-compose -f docker-compose.openmetadata.yml up -d
```

Run smoke tests:

```bash
pytest tests/test_catalog_openmetadata_smoke.py -v -m smoke
```

## Example

See `examples/jobs/catalog_integration_example.yaml` for a complete example.

## Implementation Details

### Architecture

- **Base Catalog** (`catalog/base.py`): Abstract base class defining the interface
- **Catalog Factory** (`catalog/factory.py`): Factory for creating catalog instances
- **Catalog Integrations**: Individual implementations for each catalog type
- **Integration Helper** (`catalog/integration.py`): Helper function to push metadata and lineage
- **CLI Integration**: Hooked into job execution flow in `cli.py`

### Error Handling

Catalog integration errors are logged as warnings and do not fail the job. This ensures that:
- Catalog connectivity issues don't block data ingestion
- Catalog API changes don't break existing jobs
- Users can monitor catalog push status via logs

### Extensibility

To add a new catalog type:

1. Create a new class in `catalog/` implementing `BaseCatalog`
2. Add the class to `CatalogFactory._catalog_classes`
3. Add tests in `tests/test_catalog.py`
4. Update this documentation

## Limitations

- **Nessie**: Lineage storage requires Iceberg metadata updates (currently logged as warning)
- **AWS Glue**: Lineage is stored in table parameters (not native lineage API)
- **Databricks Unity Catalog**: Lineage is stored in table properties (not native lineage API)
- **OpenMetadata**: Full lineage support via pipeline entities

## Future Enhancements

- Support for additional catalog types
- Native lineage APIs where available
- Incremental metadata updates
- Schema evolution tracking
- Data quality metrics integration
