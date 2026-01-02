# Connector Registry v2 - External Catalog Support

**Version:** 0.5  
**Status:** Implemented  
**Date:** 2025-12-10

## Overview

Connector Registry v2 extends Dativo-Ingest with support for external connector catalogs (Airbyte, Singer, Meltano), enhanced connector resolution logic, and a new CLI for managing connector metadata.

## Features

### 1. External Connector Catalog Support

The system can now load connector metadata from external JSON catalogs stored in `/registry/catalogs/`. This enables automatic resolution of Docker images, versions, and capabilities from external sources like Airbyte's connector catalog.

#### ⚠️ Important: Catalogs are for Resolution, Not Registration

**Key Distinction:**
- **Registration**: Connectors must be defined in `registry/connectors.yaml` to be available in the system
- **Resolution**: Catalogs provide metadata (Docker images, versions, capabilities) for connectors that are **already registered**

**What this means:**
- Running `dativo connectors sync --catalog-url <URL>` downloads and saves catalog metadata locally
- This does **NOT** add new connectors to your registry
- To use a new connector, you must first add it to `connectors.yaml`
- The catalog then helps automatically resolve Docker images and versions for that connector

**Example Workflow:**
```yaml
# Step 1: Register connector in connectors.yaml
# registry/connectors.yaml
stripe:
  roles: [source]
  default_engine: airbyte
  engines_supported: [airbyte]

# Step 2: Sync catalog (provides metadata only)
# dativo connectors sync --catalog-url https://connectors.airbyte.com/...
# This creates registry/catalogs/airbyte.json with metadata for registered connectors

# Step 3: Resolution happens automatically
# When you use "stripe" connector in a job, system resolves:
# - docker_image from catalog: airbyte/source-stripe:4.0.0
# - version from catalog: 4.0.0
# - capabilities from catalog: ["incremental", "certified"]
```

**Without catalog:** You must manually specify Docker images in job configs  
**With catalog:** Docker images are automatically resolved from catalog metadata

#### Supported Catalog Formats

**Airbyte Format:**
```json
{
  "sources": [
    {
      "sourceDefinitionId": "e094cb9a-26de-4645-8761-65c0c425d1de",
      "name": "Stripe",
      "dockerRepository": "airbyte/source-stripe",
      "dockerImageTag": "4.0.0",
      "documentationUrl": "https://docs.airbyte.com/integrations/sources/stripe",
      "supportLevel": "certified"
    }
  ]
}
```

**Generic Format:**
```json
{
  "connectors": [
    {
      "name": "stripe",
      "external_id": "airbyte/source-stripe",
      "docker_image_default": "airbyte/source-stripe:4.0.0",
      "version_default": "4.0.0",
      "capabilities": ["incremental", "certified"]
    }
  ]
}
```

### 2. Extended Connector Registry Schema

The `connectors.yaml` registry now supports additional optional fields:

```yaml
hubspot:
  roles: [source]
  category: crm
  default_engine: airbyte
  engines_supported: [airbyte, singer, native]
  
  # New optional fields (v0.5+)
  external_id: "airbyte/source-hubspot"
  docker_image_default: "airbyte/source-hubspot:2.0.0"
  version_default: "2.0.0"
  source_of_truth: airbyte  # native | airbyte | singer | meltano
  
  allowed_in_cloud: true
  supports_incremental: true
  incremental_strategy_default: updated_after
```

**New Fields:**
- `external_id`: External connector identifier (e.g., Airbyte sourceDefinitionId)
- `docker_image_default`: Default Docker image for the connector
- `version_default`: Default version to use
- `source_of_truth`: Indicates primary source (native, airbyte, singer, meltano)

### 3. Enhanced Connector Resolution

Connector resolution follows a clear, centralized precedence order:

1. **Job-level overrides** (highest priority)
   - Docker image, version, engine specified in job config or connector recipe
2. **External catalog entries**
   - If engine is `airbyte`/`singer`/`meltano` and matching catalog entry exists
3. **Registry defaults**
   - Fallback to `connectors.yaml` values (`docker_image_default`, `version_default`)
4. **No resolution** (lowest priority)
   - Returns None for missing values

The resolution logic is implemented in a single, testable helper function (`resolve_image_and_version`) to ensure consistency across all code paths.

#### Resolution Example

```python
from dativo_ingest.registry import ConnectorRegistry

# Recommended: use from_default_paths() for standard usage
registry = ConnectorRegistry.from_default_paths()

# Basic resolution
resolved = registry.resolve_connector("stripe")
print(resolved.docker_image)  # From registry or catalog

# With engine override
resolved = registry.resolve_connector("stripe", engine="airbyte")
print(resolved.docker_image)  # airbyte/source-stripe:4.0.0 (from catalog)

# With job overrides (highest priority)
overrides = {"docker_image": "custom/stripe:5.0.0"}
resolved = registry.resolve_connector("stripe", job_overrides=overrides)
print(resolved.docker_image)  # custom/stripe:5.0.0
```

### 4. Connector Management CLI

Three new CLI commands are available for managing connectors:

#### `dativo connectors list`

List all registered connectors with their metadata.

```bash
# Basic list
dativo connectors list

# Filter by role
dativo connectors list --role source
dativo connectors list --role target

# JSON output
dativo connectors list --json

# Verbose output (includes docker images, versions, capabilities)
dativo connectors list --verbose
```

**Example Output:**
```
Registered Connectors (16):
================================================================================

csv
  Roles: source, target
  Default Engine: native
  Engines Supported: native

hubspot
  Roles: source
  Default Engine: airbyte
  Engines Supported: airbyte, singer, native

stripe
  Roles: source
  Default Engine: airbyte
  Engines Supported: airbyte, singer, native
```

#### `dativo connectors inspect <name>`

Show detailed information about a specific connector.

```bash
# Inspect connector
dativo connectors inspect stripe

# Inspect with engine override
dativo connectors inspect stripe --engine airbyte

# JSON output
dativo connectors inspect stripe --json
```

**Example Output:**
```
Connector: stripe
================================================================================
Type: stripe
Roles: source
Category: payments

Engine Configuration:
  Default Engine: airbyte
  Supported Engines: airbyte, singer, native

Runtime Configuration:
  Docker Image: airbyte/source-stripe:4.0.0
  Version: 4.0.0
  External ID: airbyte/source-stripe
  Source of Truth: airbyte

Capabilities:
  Allowed in Cloud: ✓
  Supports Incremental: ✓
  Incremental Strategy: created
  Additional: incremental, certified

External Catalog Entry:
  Catalog: airbyte
  External ID: e094cb9a-26de-4645-8761-65c0c425d1de
  Docker Image: airbyte/source-stripe:4.0.0
  Version: 4.0.0
  Metadata: {'documentation_url': '...', 'support_level': 'certified'}
```

#### `dativo connectors sync`

Sync external connector catalogs.

**Currently Supported:**
- `--catalog-file <path>`: Copy a local JSON catalog file to the catalogs directory
- `--catalog-url <url>`: Download catalog JSON from a remote URL (e.g., Airbyte OSS registry)

```bash
# Show current catalogs
dativo connectors sync

# Copy catalog from local file
dativo connectors sync --catalog-file /path/to/airbyte-catalog.json

# Download catalog from URL
dativo connectors sync --catalog-url https://connectors.airbyte.com/files/registries/v0/oss_registry.json

# JSON output
dativo connectors sync --json

# Verbose output
dativo connectors sync --verbose
```

**Error Handling:**
- Returns exit code 0 on success
- Returns exit code 2 on errors (missing file, invalid arguments, etc.)
- Error messages are clear and consistent, with JSON output when `--json` is used

**Example Output:**
```
Loaded Catalogs (1):
  - airbyte: 7 connectors

To add a catalog, place a JSON file in: /app/registry/catalogs/
```

### Strict Mode vs Fallback

**Strict Mode (Default):**
- If a connector is configured to use an external engine (Airbyte, etc.), the system REQUIRES resolving a valid Docker image and version.
- If resolution fails (missing catalog entry, missing fields in catalog, no job override), the validator/runtime will raise an error.
- Suggested fix: Run `dativo connectors sync <engine>` or provide `docker_image` in job config.

**Fallback Behavior:**
- (Internal/Legacy) If strict mode is disabled, the system might proceed if partial metadata is available, but this is not recommended for production.

### Security / Governance Guardrail

Optional security feature to restrict Docker images to allowed registries.

**Configuration:**
- `DATIVO_ALLOW_CUSTOM_IMAGES`: Set to `false` (default) to restrict images to allowed prefixes (`airbyte/`, `meltano/`, `singer/`). Set to `true` to allow any image.

**Behavior:**
- If `false`, job validation fails if a connector tries to use a Docker image that doesn't start with an allowed prefix.
- If `true`, any Docker image can be used (useful for private registries or custom builds).

### 5. Catalog Normalization and Adapters

The system includes adapters to normalize external catalog formats into a standard internal representation.

- **Airbyte Adapter**: Fully implemented. Normalizes Airbyte catalog JSON into Dativo's format.
- **Singer/Meltano Adapters**: Stubs provided for future implementation.

**Normalized Catalog Schema:**
See `schemas/external_catalog.schema.json` for the strict schema definition.

## Architecture

### Module Structure

```
src/dativo_ingest/registry/
├── __init__.py              # Public API exports
├── catalog_loader.py        # External catalog loading
└── connector_registry.py    # Enhanced registry with resolution

registry/
├── connectors.yaml          # Main connector registry
└── catalogs/                # External catalog JSON files
    ├── airbyte.json        # Airbyte connector catalog
    └── .gitkeep
```

### Key Classes

#### `CatalogLoader`

Loads and manages external connector catalogs.

```python
from dativo_ingest.registry import CatalogLoader

loader = CatalogLoader()

# Check if catalogs are loaded
if loader.has_catalogs():
    print(f"Loaded catalogs: {loader.get_catalog_names()}")

# Get specific connector
connector = loader.get_connector("stripe", catalog_name="airbyte")

# List all connectors
connectors = loader.list_connectors()
```

#### `ConnectorRegistry`

Enhanced registry with catalog support and resolution logic.

**Recommended Usage:**
```python
from dativo_ingest.registry import ConnectorRegistry

# Use from_default_paths() for standard usage
registry = ConnectorRegistry.from_default_paths()

# Resolve connector with catalog lookup
resolved = registry.resolve_connector(
    connector_name="stripe",
    engine="airbyte",
    job_overrides={"version": "5.0.0"}
)

# Access resolved properties
print(resolved.docker_image)  # Resolved with precedence: job > catalog > registry
print(resolved.version)       # Resolved with precedence: job > catalog > registry
print(resolved.allowed_in_cloud)
print(resolved.to_dict())
```

**Error Handling:**
```python
from dativo_ingest.registry import ConnectorRegistry, RegistryNotFoundError, RegistryLoadError

try:
    registry = ConnectorRegistry.from_default_paths()
except RegistryNotFoundError as e:
    # Registry file not found in any default location
    print(f"Registry not found: {e}")
except RegistryLoadError as e:
    # Registry file exists but cannot be loaded/parsed
    print(f"Failed to load registry: {e}")
```

**Advanced Usage (for testing):**
```python
# For testing, you can provide explicit paths
from pathlib import Path
registry = ConnectorRegistry(registry_path=Path("/custom/path/connectors.yaml"))
```

#### `ResolvedConnector`

Represents a fully resolved connector with merged metadata.

```python
resolved = registry.resolve_connector("stripe")

# Properties follow resolution priority
print(resolved.docker_image)      # Job > Catalog > Registry
print(resolved.version)            # Job > Catalog > Registry
print(resolved.external_id)        # Catalog > Registry
print(resolved.source_of_truth)    # Registry
print(resolved.capabilities)       # Merged from registry + catalog

# Check catalog entry
if resolved.catalog_entry:
    print(f"From catalog: {resolved.catalog_entry.source_of_truth}")
```

## Integration with Existing Code

### Connector Factory Integration

The connector factory (`connectors/factory.py`) continues to work without changes. The enhanced registry is integrated transparently.

### Engine Configuration Integration

The `EngineConfigParser` (`connectors/engine_config.py`) now uses registry resolution for Docker images:

```python
parser = EngineConfigParser(source_config, connector_recipe, tenant_id)

# Automatically resolves from registry + catalog
# Falls back gracefully if registry is missing (backward compatibility)
docker_image = parser.get_docker_image()
```

The registry integration is encapsulated in a simple helper method (`_resolve_airbyte_image_from_registry`) that handles errors gracefully, logging warnings for expected errors (missing registry) and re-raising unexpected errors.

### Validator Integration

The `ConnectorValidator` (`validator.py`) now uses the enhanced registry internally while maintaining backward compatibility. It uses `ConnectorRegistry.from_default_paths()` and raises clear errors (`RegistryNotFoundError`, `RegistryLoadError`) when the registry cannot be loaded.

**Error Handling:**
- Validation errors are printed exactly once (no duplicate messages)
- Mode restriction errors (e.g., cloud mode blocking) are handled by `ConnectorRegistry.validate_connector()` which prints clear error messages and exits with code 2
- All validation methods delegate error handling to the registry to ensure consistent error messages

## Backward Compatibility

✅ **Full backward compatibility maintained:**

- Existing job configs work without changes
- Connectors without catalog entries continue to work
- System operates normally without any catalog files
- All existing connector behaviors preserved
- Legacy registry formats still supported

## Adding New Catalogs

**Note:** Adding a catalog provides metadata for connectors that are already registered in `connectors.yaml`. It does not add new connectors to your registry.

### Option 1: Manual File Placement

1. Download or create a catalog JSON file
2. Place it in `/registry/catalogs/` (or `registry/catalogs/` in the repo)
3. Name it descriptively (e.g., `airbyte.json`, `singer.json`)
4. Restart or re-run the CLI command

### Option 2: Using CLI

```bash
# Copy from local file
dativo connectors sync --catalog-file /path/to/catalog.json

# Or download from URL
dativo connectors sync --catalog-url https://connectors.airbyte.com/...

# Verify it was loaded
dativo connectors sync --verbose
```

**What happens:**
- Catalog file is saved to `registry/catalogs/`
- Metadata is loaded for connectors that match names in your `connectors.yaml`
- No new connectors are added to the registry

### Catalog File Requirements

- Must be valid JSON
- Must follow one of the supported formats (Airbyte or generic)
- File name (without .json) becomes the catalog name

## Use Cases

### 1. Automatic Docker Image Resolution

Without catalog:
```yaml
# connector_recipe.yaml
default_engine:
  type: airbyte
  options:
    airbyte:
      docker_image: "airbyte/source-stripe:4.0.0"  # Must specify manually
```

With catalog:
```yaml
# connector_recipe.yaml
default_engine:
  type: airbyte
  # docker_image automatically resolved from catalog!
```

### 2. Version Management

Use the CLI to check which versions are available:

```bash
dativo connectors inspect stripe
# Shows: Version: 4.0.0 (from catalog)

dativo connectors inspect hubspot
# Shows: Version: 2.0.0 (from catalog)
```

### 3. Connector Discovery

List all available connectors (registered in `connectors.yaml`) and their metadata (from catalogs):

```bash
# See all source connectors
dativo connectors list --role source --verbose

# Find connectors with incremental support
dativo connectors list --verbose | grep "Incremental: ✓"
```

**Note:** This lists connectors that are already registered in `connectors.yaml`. Catalogs provide additional metadata (Docker images, versions, capabilities) for these connectors.

### 4. Multi-Catalog Support

Load catalogs from multiple sources:

```
registry/catalogs/
├── airbyte.json      # Official Airbyte catalog
├── singer.json       # Singer taps catalog
└── custom.json       # Internal custom connectors
```

Resolution automatically searches all catalogs.

## Testing

Comprehensive test coverage in `tests/test_registry.py`:

- Catalog loading (Airbyte and generic formats)
- Connector resolution with priority handling
- Job override precedence
- Registry validation
- Integration tests with real registry

Run tests:
```bash
pytest tests/test_registry.py -v
```

## Schema Validation

The registry schema (`schemas/connectors.schema.json`) has been updated to include the new optional fields. Existing CI validation continues to pass.

Validate your registry:
```bash
# JSON schema validation (if using validation tools)
jsonschema -i registry/connectors.yaml schemas/connectors.schema.json
```

## Future Enhancements

Potential future improvements:

1. **Catalog Versioning**: Track catalog versions and updates
2. **Connector Templates**: Enhanced templates with catalog metadata
3. **Multi-Source Aggregation**: Merge multiple catalogs intelligently
4. **Capability Matching**: Match job requirements to connector capabilities

## Migration Guide

### From v0.4.x to v0.5

No migration required! v0.5 is fully backward compatible.

**Optional enhancements:**

1. Add catalog files to `/registry/catalogs/` for automatic resolution
2. Update `connectors.yaml` entries with new optional fields
3. Use new CLI commands for connector inspection

**Example update:**

```yaml
# Before (v0.4.x) - still works
stripe:
  roles: [source]
  default_engine: airbyte
  engines_supported: [airbyte]

# After (v0.5+) - enhanced metadata
stripe:
  roles: [source]
  default_engine: airbyte
  engines_supported: [airbyte]
  external_id: "airbyte/source-stripe"
  docker_image_default: "airbyte/source-stripe:4.0.0"
  version_default: "4.0.0"
  source_of_truth: airbyte
```

## Troubleshooting

### Catalog not loading

**Problem:** Catalog file in `/registry/catalogs/` but not detected.

**Solutions:**
1. Check file is valid JSON: `cat registry/catalogs/airbyte.json | python3 -m json.tool`
2. Check file permissions: `ls -la registry/catalogs/`
3. Check logs for parsing errors
4. Run: `dativo connectors sync --verbose`

### Connector resolution returning None

**Problem:** `resolved.docker_image` is None despite catalog entry.

**Solutions:**
1. **First, ensure connector is registered:** Verify the connector exists in `registry/connectors.yaml` (catalogs don't register connectors)
2. Verify connector name matches catalog: `dativo connectors list --verbose`
3. Check engine matches catalog source: `dativo connectors inspect <name> --engine airbyte`
4. Verify catalog entry has docker_image field
5. Check catalog is loaded: `dativo connectors sync`

### Wrong docker image being used

**Problem:** Getting unexpected docker image for connector.

**Solutions:**
1. Check resolution priority: job overrides > catalog > registry
2. Inspect connector: `dativo connectors inspect <name> --json`
3. Check for job-level overrides in connector recipe
4. Verify catalog entry: look at `catalog_entry` in inspect output

### Validation Error: "Failed to resolve docker image/version"

**Problem:** Job fails validation with error about missing metadata.

**Solutions:**
1. Run `dativo connectors sync airbyte` (or relevant engine)
2. Ensure the connector exists in the synced catalog
3. Provide a manual override in your job config:
   ```yaml
   source:
     type: stripe
     engine:
       type: airbyte
       options:
         airbyte:
           docker_image: "airbyte/source-stripe:4.0.0"
   ```

### Security Violation

**Problem:** "Docker image ... is not allowlisted".

**Solutions:**
1. Use an official image (`airbyte/...`).
2. Set `DATIVO_ALLOW_CUSTOM_IMAGES=true` in environment if using custom images.

## API Reference

### Python API

**Public API (Recommended):**
```python
from dativo_ingest.registry import (
    ConnectorRegistry,
    ResolvedConnector,
    RegistryNotFoundError,
    RegistryLoadError,
)

# Use registry (recommended)
registry = ConnectorRegistry.from_default_paths()
resolved = registry.resolve_connector("stripe", engine="airbyte")

# Access properties
print(resolved.docker_image)  # Resolved with precedence
print(resolved.version)        # Resolved with precedence
print(resolved.allowed_in_cloud)
print(resolved.to_dict())
```

**Internal APIs (for advanced use/testing):**
```python
from dativo_ingest.registry import (
    CatalogLoader,      # Internal catalog loading (not needed for normal use)
    ExternalConnector,  # Internal catalog entry representation
    resolve_image_and_version,  # Resolution helper (used internally)
)
```

**Note:** `CatalogLoader` and related classes are implementation details. For normal usage, you only need `ConnectorRegistry` and `ResolvedConnector`.

### CLI API

```bash
# List connectors
dativo connectors list [--role {source,target}] [--json] [--verbose]

# Inspect connector
dativo connectors inspect <name> [--engine {airbyte,singer,meltano}] [--json]

# Sync catalogs
dativo connectors sync [--catalog-file PATH] [--catalog-url URL] [--json] [--verbose]
```

## Security Considerations

1. **Catalog Integrity**: Catalog files are loaded from local filesystem only
2. **Docker Image Validation**: No automatic downloading or validation of images
3. **Job Override Priority**: Job configs can override any catalog value
4. **Optional Feature**: Catalogs are completely optional - system works without them

## Performance

- Catalog loading: O(n) where n = number of connectors in catalog
- Connector resolution: O(1) lookup after initial load
- Memory overhead: ~1KB per connector entry
- Typical catalog size: 50-200 connectors, ~100-500KB

## Support

For issues or questions:

1. Check this documentation
2. Run `dativo connectors inspect <name> --verbose`
3. Check logs for registry loading errors
4. Verify catalog JSON is valid
5. Consult `tests/test_registry.py` for examples

## Changelog

**v0.5.0 (2025-12-10):**
- Added external connector catalog support
- Extended registry schema with optional fields
- Implemented enhanced connector resolution
- Added connector management CLI commands
- Fixed duplicate error messages in connector validation
- Full backward compatibility maintained
- Comprehensive test coverage added

## Related Documentation

- [CUSTOM_PLUGINS.md](CUSTOM_PLUGINS.md) - Custom plugin development
- [CONNECTOR_VS_PLUGIN_DECISION_TREE.md](CONNECTOR_VS_PLUGIN_DECISION_TREE.md) - Choosing connectors vs plugins
- [RUNNER_AND_ORCHESTRATION.md](RUNNER_AND_ORCHESTRATION.md) - Job execution and orchestration
