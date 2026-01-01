# External Connector Catalogs

This directory contains external connector catalog files that extend the Dativo connector registry with metadata from external sources like Airbyte, Singer, and Meltano.

## Overview

Catalogs are **optional** - the system operates normally without them. When present, they provide:

- Automatic Docker image resolution
- Version defaults
- External connector IDs
- Capability metadata
- Documentation URLs

## Catalog Files

### `airbyte.json`

Sample Airbyte connector catalog with popular connectors:
- Stripe (payment processing)
- HubSpot (CRM)
- Postgres (database)
- MySQL (database)
- Google Sheets (spreadsheets)
- Google Drive (file storage)
- File/CSV (file connector)

## Adding Catalogs

### Option 1: Manual File Placement

1. Create or download a catalog JSON file
2. Place it in this directory
3. Ensure it follows a supported format (see below)
4. File name (without .json) becomes the catalog name

### Option 2: Using CLI

```bash
# Copy from local file
dativo connectors sync --catalog-file /path/to/catalog.json

# Verify it loaded
dativo connectors sync --verbose
```

## Supported Formats

### Airbyte Format

```json
{
  "sources": [
    {
      "sourceDefinitionId": "unique-id",
      "name": "Connector Name",
      "dockerRepository": "airbyte/source-name",
      "dockerImageTag": "1.0.0",
      "documentationUrl": "https://...",
      "supportLevel": "certified"
    }
  ]
}
```

### Generic Format

```json
{
  "connectors": [
    {
      "name": "connector_name",
      "external_id": "external-id",
      "docker_image_default": "registry/image:tag",
      "version_default": "1.0.0",
      "capabilities": ["incremental", "cdc"],
      "metadata": {}
    }
  ]
}
```

## Catalog Resolution

When resolving a connector, the system uses this priority:

1. **Job-level overrides** (highest)
2. **Catalog entries** (if engine matches)
3. **Registry defaults** (from connectors.yaml)

Example:
```python
from dativo_ingest.registry import ConnectorRegistry

registry = ConnectorRegistry()

# Resolves docker_image from airbyte.json
resolved = registry.resolve_connector("stripe", engine="airbyte")
print(resolved.docker_image)  # airbyte/source-stripe:4.0.0
```

## CLI Commands

```bash
# List all connectors with catalog data
dativo connectors list --verbose

# Inspect specific connector
dativo connectors inspect stripe

# Show loaded catalogs
dativo connectors sync
```

## File Requirements

- Must be valid JSON
- Must follow one of the supported formats
- File name becomes catalog name (e.g., `airbyte.json` → catalog name: `airbyte`)

## Error Handling

Invalid or corrupted catalog files are:
- Logged as warnings
- Skipped during loading
- Do not prevent system startup

The system continues to operate using registry defaults.

## Maintenance

### Updating Catalogs

To update a catalog:
1. Download new version or update the JSON
2. Replace the file in this directory
3. Restart the service or re-run CLI

### Checking Catalog Status

```bash
# Show loaded catalogs
dativo connectors sync --verbose

# Check specific connector resolution
dativo connectors inspect <name> --json
```

## Security

- Catalogs are loaded from the local filesystem at runtime
- Optional CLI sync can download and cache catalogs (headless, deterministic cache file)
- Job-level overrides can override any catalog value
- Docker images are not validated or pulled automatically

## Performance

- Catalogs loaded once at startup
- O(1) connector lookup after initial load
- Minimal memory overhead (~1KB per connector)
- Typical catalog size: 50-200 connectors

## Documentation

For more information, see:
- [CONNECTOR_REGISTRY_V2.md](../../docs/CONNECTOR_REGISTRY_V2.md) - Complete feature guide
- [CHANGELOG.md](../../CHANGELOG.md) - Version history

## Examples

### Example: Airbyte Connector Resolution

```python
# Without catalog (manual specification required)
# connector_recipe.yaml
default_engine:
  type: airbyte
  options:
    airbyte:
      docker_image: "airbyte/source-stripe:4.0.0"

# With catalog (automatic resolution)
# connector_recipe.yaml  
default_engine:
  type: airbyte
  # docker_image resolved from airbyte.json!
```

### Example: Multi-Catalog Support

```
catalogs/
├── airbyte.json      # Official Airbyte
├── singer.json       # Singer taps
└── custom.json       # Internal connectors
```

Resolution searches all catalogs automatically.

## Troubleshooting

**Catalog not loading:**
- Check JSON validity: `cat airbyte.json | python3 -m json.tool`
- Check file permissions: `ls -la`
- Run: `dativo connectors sync --verbose`

**Wrong version used:**
- Check priority: job > catalog > registry
- Inspect: `dativo connectors inspect <name>`
- Verify catalog entry exists

**Connector not found:**
- List connectors: `dativo connectors list`
- Check catalog name matches
- Verify connector name in catalog
