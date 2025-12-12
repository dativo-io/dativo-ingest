# Quick Start Guide: Connector Registry v2 (v0.5)

**For:** Developers and operators using Dativo-Ingest v0.5+  
**Time to read:** 5 minutes

## What's New in v0.5?

✨ **External connector catalogs** - Automatic Docker image resolution  
✨ **Enhanced connector metadata** - Version, external IDs, capabilities  
✨ **New CLI commands** - List, inspect, and sync connectors  
✨ **Priority-based resolution** - Job > Catalog > Registry  

## Quick Examples

### 1. List All Connectors

```bash
# Basic list
dativo connectors list

# With details
dativo connectors list --verbose

# JSON output
dativo connectors list --json
```

### 2. Inspect a Connector

```bash
# Show all metadata
dativo connectors inspect stripe

# With specific engine
dativo connectors inspect stripe --engine airbyte

# JSON output
dativo connectors inspect stripe --json
```

### 3. Check Catalog Status

```bash
# Show loaded catalogs
dativo connectors sync

# Verbose details
dativo connectors sync --verbose
```

### 4. Add a Catalog

```bash
# Option 1: Copy from file
dativo connectors sync --catalog-file /path/to/airbyte-catalog.json

# Option 2: Manual placement
cp my-catalog.json /app/registry/catalogs/
# or in repo:
cp my-catalog.json registry/catalogs/
```

## Python API

```python
from dativo_ingest.registry import ConnectorRegistry

# Initialize
registry = ConnectorRegistry()

# List connectors
connectors = registry.list_connectors()
print(f"Found {len(connectors)} connectors")

# Resolve connector
resolved = registry.resolve_connector("stripe", engine="airbyte")

# Access properties
print(f"Docker image: {resolved.docker_image}")
print(f"Version: {resolved.version}")
print(f"Capabilities: {resolved.capabilities}")

# Get as dict
data = resolved.to_dict()
```

## Resolution Priority

When resolving Docker images and versions:

1. **Job config** (highest) - Specified in job YAML or connector recipe
2. **Catalog** - From external catalog (Airbyte, Singer, etc.)
3. **Registry** - From `connectors.yaml`
4. **None** (lowest) - Not specified

## Common Tasks

### Task: Add New Connector to Registry

Edit `registry/connectors.yaml`:

```yaml
my_connector:
  roles: [source]
  category: api
  default_engine: airbyte
  engines_supported: [airbyte, native]
  
  # Optional v0.5 fields
  external_id: "airbyte/source-my-connector"
  docker_image_default: "airbyte/source-my-connector:1.0.0"
  version_default: "1.0.0"
  source_of_truth: airbyte
  
  allowed_in_cloud: true
  supports_incremental: true
  incremental_strategy_default: updated_after
```

### Task: Use Automatic Docker Image Resolution

Before (v0.4):
```yaml
# connector_recipe.yaml
default_engine:
  type: airbyte
  options:
    airbyte:
      docker_image: "airbyte/source-stripe:4.0.0"  # Manual
```

After (v0.5):
```yaml
# connector_recipe.yaml
default_engine:
  type: airbyte
  # docker_image resolved automatically from catalog!
```

### Task: Override Connector Version

In your job config or connector recipe:

```yaml
default_engine:
  type: airbyte
  options:
    airbyte:
      docker_image: "airbyte/source-stripe:5.0.0"  # Override
```

Job overrides always take precedence.

## Catalog Formats

### Airbyte Format
```json
{
  "sources": [
    {
      "sourceDefinitionId": "uuid",
      "name": "Connector Name",
      "dockerRepository": "airbyte/source-name",
      "dockerImageTag": "1.0.0"
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
      "docker_image_default": "registry/image:1.0.0",
      "version_default": "1.0.0"
    }
  ]
}
```

## Troubleshooting

### Connector not resolving Docker image

```bash
# Check connector exists
dativo connectors list | grep my_connector

# Inspect resolution
dativo connectors inspect my_connector --verbose

# Check catalogs loaded
dativo connectors sync --verbose
```

### Catalog not loading

```bash
# Validate JSON
cat registry/catalogs/my-catalog.json | python3 -m json.tool

# Check file location
ls -la registry/catalogs/

# Reload
dativo connectors sync --verbose
```

### Wrong version being used

```bash
# Check resolution priority
dativo connectors inspect my_connector --json

# Look for:
# - job_overrides (highest priority)
# - catalog_entry (from external catalog)
# - registry_entry (from connectors.yaml)
```

## File Locations

### In Container
- Registry: `/app/registry/connectors.yaml`
- Catalogs: `/app/registry/catalogs/*.json`
- Logs: Check Dativo logs for registry loading messages

### In Repository
- Registry: `registry/connectors.yaml`
- Catalogs: `registry/catalogs/*.json`
- Docs: `docs/CONNECTOR_REGISTRY_V2.md`

## Integration with Existing Code

✅ **No changes required to existing code!**

- Job configs work as-is
- Connector recipes unchanged
- Factory and engine config transparently enhanced
- Optional feature - works without catalogs

## CLI Reference

```bash
# List commands
dativo connectors list [--role {source,target}] [--json] [--verbose]

# Inspect command
dativo connectors inspect NAME [--engine ENGINE] [--json]

# Sync command  
dativo connectors sync [--catalog-file PATH] [--json] [--verbose]
```

## Further Reading

- **Complete Guide:** `docs/CONNECTOR_REGISTRY_V2.md`
- **Catalog Usage:** `registry/catalogs/README.md`
- **Implementation Details:** `IMPLEMENTATION_SUMMARY_V0.5.md`
- **Changelog:** `CHANGELOG.md` (v0.5.0 section)
- **Tests:** `tests/test_registry.py`

## Support

Questions? Check:
1. This quick start guide
2. `docs/CONNECTOR_REGISTRY_V2.md` for details
3. `dativo connectors inspect <name>` for runtime info
4. Test examples in `tests/test_registry.py`

## Migration from v0.4

✅ **No migration needed!** v0.5 is fully backward compatible.

Optional enhancements:
- Add catalog files for automatic resolution
- Use new CLI commands for inspection
- Update registry with new metadata fields

---

**Version:** 0.5.0  
**Status:** Production Ready  
**Backward Compatibility:** 100%  
**Documentation:** Complete
