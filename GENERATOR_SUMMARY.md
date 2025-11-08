# Job & Asset Generator - Summary

## What Was Created

A comprehensive interactive CLI tool for generating Dativo job configurations and asset definitions, integrated into the main `dativo` CLI as the `generate` command.

## Key Features

### 1. **Connector Registry Integration**
- Reads from `/workspace/registry/connectors.yaml` to understand connector capabilities
- Knows which connectors support incremental sync, their default strategies, supported objects, etc.
- Validates connector compatibility (cloud vs self-hosted, source vs target roles)

### 2. **Intelligent Configuration Suggestions**
- Suggests appropriate schema fields based on connector type:
  - API connectors (Stripe, HubSpot): `id` (string), timestamps
  - Database connectors (Postgres, MySQL): `id` (bigint), `updated_at` (timestamp)
- Auto-detects PII/SENSITIVE fields based on field names
- Suggests incremental sync settings when supported
- Provides connector-specific defaults (cursor fields, lookback days, etc.)

### 3. **Complete Schema Definition**
- Interactive field builder with type selection
- Required/optional flags
- Classification markers (PII, SENSITIVE)
- Governance configuration (owner, tags, retention)
- Target configuration (file format, partitioning, schema evolution mode)

### 4. **Full Job Configuration**
- Source configuration based on connector type:
  - API: objects list
  - Database: tables with cursor fields and connection params
  - Files: paths and incremental settings
- Target configuration:
  - Connector selection
  - Branch and warehouse paths
  - S3/MinIO settings
  - Catalog configuration (Nessie for Iceberg)
- Logging and environment settings

### 5. **Files Generated**
- **Asset Definition**: `/workspace/assets/{connector}/v1.0/{name}.yaml`
- **Job Configuration**: `/workspace/jobs/{tenant}/{name}_to_{target}.yaml`

## Usage

### Command Line
```bash
# Using the installed CLI command
dativo generate

# Or using Python module directly
python3 -m src.dativo_ingest.cli generate

# Or using the convenience script
./generate_job.sh
```

### Integration Points

#### 1. Main CLI (`src/dativo_ingest/cli.py`)
- Added `generate` subcommand
- Updated help text with examples
- Integrated with existing CLI structure

#### 2. Generator Module (`src/dativo_ingest/generator.py`)
- `ConnectorRegistry`: Loads and queries connector capabilities
- `ConnectorRecipeLoader`: Reads full connector configurations
- `InteractiveGenerator`: Main interactive workflow

#### 3. Documentation
- **`docs/GENERATOR_CLI.md`**: Complete reference documentation with examples
- **`README.md`**: Updated with quick start section
- **`GENERATOR_SUMMARY.md`**: This summary document

## Architecture

```
┌─────────────────────────────────────────┐
│         User runs `dativo generate`     │
└───────────────┬─────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────┐
│      InteractiveGenerator.run()         │
│  - Prompts for tenant, connector, etc.  │
└───────────────┬─────────────────────────┘
                │
        ┌───────┴────────┐
        │                │
        ▼                ▼
┌──────────────┐  ┌──────────────────┐
│  Connector   │  │   Connector      │
│  Registry    │  │   Recipe Loader  │
│              │  │                  │
│ - Roles      │  │ - Credentials    │
│ - Features   │  │ - Connection     │
│ - Defaults   │  │ - Engine opts    │
└──────┬───────┘  └────────┬─────────┘
       │                   │
       └─────────┬─────────┘
                 │
                 ▼
    ┌────────────────────────┐
    │  Generate Asset        │
    │  - Schema fields       │
    │  - Governance          │
    │  - Target config       │
    └───────────┬────────────┘
                │
                ▼
    ┌────────────────────────┐
    │  Generate Job          │
    │  - Source config       │
    │  - Target config       │
    │  - Logging             │
    └───────────┬────────────┘
                │
                ▼
    ┌────────────────────────┐
    │  Save YAML Files       │
    │  - assets/{conn}/v1.0/ │
    │  - jobs/{tenant}/      │
    └────────────────────────┘
```

## Connector Knowledge Examples

### From Registry (`registry/connectors.yaml`)
```yaml
stripe:
  roles: [source]
  category: payments
  supports_incremental: true
  incremental_strategy_default: created
  objects_supported: ["charges", "customers", "invoices"]
```

Generator uses this to:
- Show only source connectors when selecting source
- Offer incremental sync option
- Suggest `created` as cursor field
- Provide object list for selection

### From Recipe (`connectors/stripe.yaml`)
```yaml
credentials:
  type: api_key
  from_env: STRIPE_API_KEY
incremental:
  strategy: created
  cursor_field_default: created
  lookback_days_default: 1
```

Generator uses this to:
- Know credentials come from environment variable
- Set default lookback days to 1
- Configure cursor field automatically

## Example Generated Files

### Asset Definition
```yaml
asset:
  name: stripe_customers
  source_type: stripe
  object: customers
  version: "1.0"
  schema:
    - name: id
      type: string
      required: true
    - name: email
      type: string
      required: false
      classification: PII
  governance:
    owner: data-team@acme.com
    tags: [stripe, customers]
    classification: [PII]
    retention_days: 30
  target:
    file_format: parquet
    partitioning: [ingest_date]
    mode: strict
```

### Job Configuration
```yaml
tenant_id: acme
environment: dev
source_connector: stripe
source_connector_path: /app/connectors/stripe.yaml
target_connector: iceberg
target_connector_path: /app/connectors/iceberg.yaml
asset: stripe_customers
asset_path: /app/assets/stripe/v1.0/stripe_customers.yaml
source:
  objects: [customers]
  incremental:
    lookback_days: 1
target:
  branch: acme
  warehouse: s3://lake/acme/
  connection:
    s3:
      bucket: acme-data-lake
      prefix: raw/stripe/stripe_customers
    nessie:
      uri: http://nessie.acme.internal:19120/api/v1
logging:
  redaction: true
  level: INFO
```

## Benefits

1. **Reduces Manual Configuration Effort**: No need to manually write YAML files
2. **Ensures Consistency**: Uses standard patterns and naming conventions
3. **Validates at Creation Time**: Only allows valid configurations based on connector capabilities
4. **Educational**: Shows users what configuration options are available
5. **Reduces Errors**: Auto-detection of PII, proper type selection, etc.
6. **Self-Documenting**: Generated files include all necessary references

## Testing

Verified functionality:
- ✅ CLI help text shows `generate` command
- ✅ `generate --help` displays detailed help
- ✅ `ConnectorRegistry` loads and queries registry correctly
- ✅ Lists all source and target connectors
- ✅ Retrieves connector details with capabilities
- ✅ Module imports work correctly

## Future Enhancements

Potential improvements:
1. **Batch Generation**: Generate multiple assets/jobs in one session
2. **Template Library**: Pre-built templates for common use cases
3. **Validation Preview**: Show validation errors before saving
4. **Test Generation**: Auto-generate test fixtures
5. **Schema Import**: Import schema from existing tables/APIs
6. **Diff View**: Show changes when regenerating existing files
7. **Non-Interactive Mode**: Support command-line arguments for CI/CD
8. **Configuration Profiles**: Save and reuse common configurations

## Related Documentation

- [docs/GENERATOR_CLI.md](docs/GENERATOR_CLI.md) - Complete user guide
- [docs/CONFIG_REFERENCE.md](docs/CONFIG_REFERENCE.md) - Configuration reference
- [registry/connectors.yaml](registry/connectors.yaml) - Connector registry
- [connectors/](connectors/) - Connector recipes
- [assets/](assets/) - Example asset definitions
- [docs/examples/jobs/](docs/examples/jobs/) - Example job configurations
