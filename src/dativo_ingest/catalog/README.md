# Data Catalog Integration Module

This module provides integration with multiple data catalog systems for lineage tracking and metadata management.

## Architecture

```
catalog/
├── __init__.py              # Module exports
├── base.py                  # Base classes and interfaces
├── factory.py               # Client factory for creating catalog instances
├── lineage_tracker.py       # Lineage tracking and metadata management
├── openmetadata_client.py   # OpenMetadata integration
├── glue_client.py          # AWS Glue Data Catalog integration
├── unity_client.py         # Databricks Unity Catalog integration
└── nessie_client.py        # Nessie catalog integration
```

## Usage

### Basic Usage

```python
from dativo_ingest.catalog.factory import CatalogClientFactory
from dativo_ingest.catalog.base import CatalogConfig

# Create configuration
config = CatalogConfig(
    type="openmetadata",
    connection={"host_port": "http://localhost:8585/api"},
    push_lineage=True,
    push_metadata=True,
)

# Create and connect client
client = CatalogClientFactory.create_client(config)
client.connect()

# Use client operations
# ... (see examples below)

# Close connection
client.close()
```

### With Lineage Tracker

```python
from dativo_ingest.catalog.factory import CatalogClientFactory
from dativo_ingest.catalog.lineage_tracker import LineageTracker
from dativo_ingest.catalog.base import CatalogConfig

# Create client
config = CatalogConfig(type="openmetadata", connection={...})
client = CatalogClientFactory.create_client(config)
client.connect()

# Create tracker
tracker = LineageTracker(client)
tracker.start_tracking()

# Push table metadata
metadata = tracker.build_table_metadata(
    asset_definition=asset,
    target_config=target_config,
)
tracker.push_table_metadata(metadata)

# Execute pipeline...

# Push lineage
tracker.end_tracking()
lineage = tracker.build_lineage_info(
    source_fqn="source.table",
    target_fqn="target.table",
    pipeline_name="my_pipeline",
    records_written=1000,
)
tracker.push_lineage(lineage)

client.close()
```

## Supported Catalogs

1. **OpenMetadata** - Full-featured open-source metadata platform
2. **AWS Glue** - AWS native data catalog
3. **Databricks Unity Catalog** - Unified governance for Databricks
4. **Nessie** - Git-like catalog for Iceberg

## Testing

```bash
# Unit tests
pytest tests/unit/catalog/ -v

# Integration tests (requires OpenMetadata)
pytest tests/integration/catalog/ -v

# Smoke tests (auto-starts OpenMetadata)
pytest tests/smoke/test_catalog_smoke.py -v -s
```

## Documentation

See [CATALOG_INTEGRATION.md](../../../../docs/CATALOG_INTEGRATION.md) for comprehensive documentation.
