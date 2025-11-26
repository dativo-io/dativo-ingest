# Data Catalog Integration Module

This module provides integration with multiple data catalog systems, enabling automatic registration of datasets, lineage tracking, and metadata propagation.

## Supported Catalogs

- **AWS Glue Data Catalog** - AWS's managed metadata catalog
- **Databricks Unity Catalog** - Databricks' unified governance solution  
- **Nessie** - Git-like catalog for Apache Iceberg
- **OpenMetadata** - Open-source metadata management platform

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Dativo Ingestion Pipeline                 │
│                                                              │
│  Extract → Transform → Write → Commit → Catalog Publishing  │
└─────────────────────────────────────────────────────────────┘
                                            │
                                            ▼
                               ┌──────────────────────┐
                               │  Catalog Factory     │
                               │  (factory.py)        │
                               └──────────────────────┘
                                            │
                     ┌──────────────────────┼──────────────────────┐
                     │                      │                      │
                     ▼                      ▼                      ▼
            ┌────────────────┐    ┌────────────────┐    ┌────────────────┐
            │  Glue Client   │    │ Unity Client   │    │  Nessie Client │
            │  (aws_glue.py) │    │(unity_catalog) │    │(nessie_catalog)│
            └────────────────┘    └────────────────┘    └────────────────┘
                     │                      │                      │
                     ▼                      ▼                      ▼
            ┌────────────────┐    ┌────────────────┐    ┌────────────────┐
            │  AWS Glue      │    │   Databricks   │    │   Nessie       │
            │  Data Catalog  │    │ Unity Catalog  │    │   Server       │
            └────────────────┘    └────────────────┘    └────────────────┘
```

## Module Structure

```
catalogs/
├── __init__.py              # Module exports
├── base.py                  # Base classes and interfaces
├── factory.py               # Catalog client factory
├── aws_glue.py             # AWS Glue implementation
├── unity_catalog.py        # Databricks Unity Catalog implementation
├── nessie_catalog.py       # Nessie implementation
├── openmetadata.py         # OpenMetadata implementation
└── README.md               # This file
```

## Usage

### Basic Example

```python
from dativo_ingest.catalogs.base import CatalogConfig, LineageInfo
from dativo_ingest.catalogs.factory import create_catalog_client
from datetime import datetime

# Create catalog configuration
config = CatalogConfig(
    type="openmetadata",
    enabled=True,
    uri="http://localhost:8585/api",
    push_lineage=True,
    push_schema=True,
    push_metadata=True,
)

# Create catalog client
client = create_catalog_client(config)

# Test connection
if client.test_connection():
    print("✓ Connected to catalog")

# Register dataset
schema = [
    {"name": "id", "type": "string", "required": True},
    {"name": "name", "type": "string"},
]

metadata = {
    "description": "User table",
    "owner": "data-team@example.com",
    "tags": ["production", "pii"],
}

result = client.register_dataset(
    dataset_name="default.users",
    schema=schema,
    metadata=metadata,
)

print(f"Dataset registered: {result}")

# Publish lineage
lineage = LineageInfo(
    source_type="postgres",
    source_dataset="source_db.users",
    target_type="iceberg",
    target_dataset="default.users",
    pipeline_name="postgres_to_iceberg",
    tenant_id="acme",
    records_processed=1000,
    execution_time=datetime.utcnow(),
)

result = client.publish_lineage(lineage)
print(f"Lineage published: {result}")
```

### Job Configuration

```yaml
catalog:
  type: openmetadata
  enabled: true
  uri: "${OPENMETADATA_URI}"
  push_lineage: true
  push_schema: true
  push_metadata: true
```

## API Reference

### BaseCatalogClient

Abstract base class for all catalog clients.

**Methods:**

- `register_dataset(dataset_name, schema, metadata)` - Register or update a dataset
- `publish_lineage(lineage_info)` - Publish lineage information
- `update_metadata(dataset_name, tags, owner, classification, custom_metadata)` - Update metadata
- `test_connection()` - Test catalog connection
- `get_dataset_fqn(dataset_name, domain, namespace)` - Get fully qualified name

### CatalogConfig

Configuration model for catalog connection.

**Fields:**

- `type: str` - Catalog type (glue, unity, nessie, openmetadata)
- `enabled: bool` - Enable/disable catalog integration
- `uri: str` - Catalog endpoint URI
- `push_lineage: bool` - Push lineage information
- `push_schema: bool` - Register/update schema
- `push_metadata: bool` - Push tags, owners, classifications

**Catalog-Specific Fields:**

- AWS Glue: `aws_region`, `aws_account_id`
- Unity Catalog: `workspace_url`, `token`, `catalog_name`
- Nessie: `branch`, `token`
- OpenMetadata: `server_config`

### LineageInfo

Lineage information model.

**Fields:**

- `source_type: str` - Source system type
- `source_name: str` - Source database/service name
- `source_dataset: str` - Source table/object name
- `source_columns: List[str]` - Source columns
- `target_type: str` - Target system type
- `target_name: str` - Target database/warehouse name
- `target_dataset: str` - Target table/dataset name
- `target_columns: List[str]` - Target columns
- `pipeline_name: str` - Pipeline/job name
- `tenant_id: str` - Tenant ID
- `records_processed: int` - Number of records processed
- `bytes_processed: int` - Number of bytes processed
- `transformation_type: str` - Type of transformation
- `transformation_description: str` - Description of transformation
- `execution_time: datetime` - Execution timestamp

## Implementation Details

### AWS Glue Client

- Uses boto3 to interact with AWS Glue API
- Auto-creates databases if they don't exist
- Stores lineage as table parameters
- Supports AWS resource tags

### Unity Catalog Client

- Uses REST API to interact with Databricks Unity Catalog
- Auto-creates catalogs and schemas
- Supports native lineage API and fallback to table properties
- Token-based authentication

### Nessie Client

- Uses REST API to interact with Nessie server
- Works with Iceberg table properties
- Branch-based metadata management
- Git-like versioning

### OpenMetadata Client

- Uses openmetadata-ingestion library
- Auto-creates services, databases, and schemas
- Native lineage tracking with pipeline references
- Rich metadata support

## Error Handling

All catalog operations are designed to be non-fatal:

- Connection failures are logged as warnings
- Partial failures are handled gracefully
- Pipeline continues even if catalog operations fail

## Testing

### Unit Tests

```bash
pytest tests/test_catalog_glue.py -v
pytest tests/test_catalog_openmetadata.py -v
pytest tests/test_catalog_integration.py -v
```

### Smoke Tests

```bash
# Start OpenMetadata
docker run -d -p 8585:8585 openmetadata/server:latest

# Run smoke tests
RUN_OPENMETADATA_SMOKE_TESTS=true pytest tests/smoke_test_openmetadata.py -v
```

## Extension

To add a new catalog client:

1. Create a new file (e.g., `my_catalog.py`)
2. Implement `BaseCatalogClient` abstract methods
3. Add to `factory.py` catalog type mapping
4. Add tests in `tests/test_catalog_my_catalog.py`
5. Update documentation

Example:

```python
from .base import BaseCatalogClient, CatalogConfig, LineageInfo

class MyCatalogClient(BaseCatalogClient):
    def _validate_config(self) -> None:
        # Validate catalog-specific config
        pass
    
    def register_dataset(self, dataset_name, schema, metadata):
        # Implementation
        pass
    
    def publish_lineage(self, lineage_info):
        # Implementation
        pass
    
    def update_metadata(self, dataset_name, **kwargs):
        # Implementation
        pass
    
    def test_connection(self) -> bool:
        # Implementation
        pass
```

## See Also

- [Data Catalog Integration Guide](../../../docs/DATA_CATALOG_INTEGRATION.md)
- [Config Reference](../../../docs/CONFIG_REFERENCE.md)
- [Tag Derivation](../../../docs/TAG_DERIVATION.md)
