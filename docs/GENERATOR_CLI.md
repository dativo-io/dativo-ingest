# Job and Asset Generator CLI

The Dativo CLI includes an interactive generator that creates job configurations and asset definitions with intelligent suggestions based on the connector registry.

## Overview

The generator provides:
- **Connector Knowledge**: Queries the connector registry to understand capabilities, supported objects, incremental strategies, and configuration requirements
- **Intelligent Suggestions**: Suggests configuration based on connector type and capabilities
- **Schema Builder**: Interactive schema definition with type suggestions and PII/SENSITIVE detection
- **Complete Configuration**: Generates both asset definitions and job configurations in one flow

## Usage

```bash
# Interactive mode (recommended)
dativo generate

# Or using Python module directly
python -m src.dativo_ingest.cli generate
```

## Workflow

The generator guides you through the following steps:

### 1. Tenant Configuration
- Prompts for tenant ID (e.g., `acme`, `corp`)

### 2. Source Connector Selection
- Lists all available source connectors from the registry
- Shows connector details:
  - Category (crm, payments, database, files)
  - Incremental sync support
  - Supported objects
  - Cloud compatibility

### 3. Asset Definition Generation

#### Basic Information
- Asset name (e.g., `stripe_customers`, `postgres_orders`)
- Object/table name (with suggestions based on connector's supported objects)
- Version (default: `1.0`)

#### Schema Definition
- Interactive field builder with:
  - Field name
  - Type selection (string, integer, bigint, double, boolean, date, timestamp)
  - Required flag
  - Automatic PII/SENSITIVE classification suggestions
- Starter fields suggested based on connector type:
  - API connectors (Stripe, HubSpot): `id` (string), `created` (timestamp)
  - Database connectors (Postgres, MySQL): `id` (bigint), `updated_at` (timestamp)

#### Governance
- Owner email (defaults to `data-team@{tenant}.com`)
- Tags (comma-separated, auto-suggests connector and object names)
- Retention days (default: 90)
- Auto-populates classifications from field-level PII/SENSITIVE markers

#### Target Configuration
- File format (default: parquet)
- Partitioning columns (default: ingest_date)
- Schema evolution mode (strict/merge/relaxed, default: strict)

### 4. Job Configuration Generation

#### Basic Information
- Environment (dev/staging/prod)

#### Source Configuration
Based on connector type:

**API Connectors** (Stripe, HubSpot):
- Objects to sync (comma-separated)
- Incremental sync settings (if supported)

**Database Connectors** (Postgres, MySQL):
- Table name (e.g., `public.orders`)
- Object name
- Cursor field for incremental sync
- Connection parameters (host, port, database)
  - Supports environment variable references (e.g., `${PGHOST}`)

**File Connectors** (CSV, Google Sheets):
- File paths or identifiers
- Incremental sync based on file modification time

#### Target Configuration
- Target connector selection (lists all target-capable connectors)
- Branch (defaults to tenant ID)
- Warehouse path (defaults to `s3://lake/{tenant}/`)
- S3/MinIO configuration:
  - Bucket name
  - Prefix path
- Catalog configuration (for Iceberg):
  - Nessie URI (optional)

#### Logging Configuration
- Log level (DEBUG/INFO/WARNING/ERROR)
- Redaction enabled/disabled

### 5. File Generation
- Saves asset definition to `/workspace/assets/{source_connector}/v1.0/{asset_name}.yaml`
- Saves job configuration to `/workspace/jobs/{tenant_id}/{job_name}.yaml`
- Shows summary and next steps

## Connector Registry Integration

The generator reads from `/workspace/registry/connectors.yaml` to provide:

### Connector Capabilities
```yaml
connectors:
  stripe:
    roles: [source]
    category: payments
    default_engine: airbyte
    allowed_in_cloud: true
    supports_incremental: true
    incremental_strategy_default: created
    objects_supported: ["charges", "customers", "invoices"]
```

### Intelligent Suggestions Based on Registry
- **Incremental sync**: Only offered if `supports_incremental: true`
- **Objects**: Suggests from `objects_supported` list
- **Default strategies**: Uses `incremental_strategy_default` for cursor fields
- **Connection requirements**: Knows if connector needs tables, queries, or API credentials
- **Cloud compatibility**: Warns if connector not allowed in cloud mode

## Connector Recipe Integration

The generator also reads full connector recipes from `/workspace/connectors/{connector}.yaml`:

### Credentials
```yaml
credentials:
  type: api_key
  from_env: STRIPE_API_KEY
```

### Connection Templates
```yaml
connection_template:
  host: "${PGHOST}"
  port: "${PGPORT}"
  database: "${PGDATABASE}"
```

### Engine Options
```yaml
default_engine:
  type: native
  options:
    native:
      library: "pandas"
      chunk_size: 10000
```

## Example Session

```
================================================================================
DATIVO JOB & ASSET GENERATOR
================================================================================

This interactive tool will guide you through creating:
  1. Asset definition (schema, governance, target config)
  2. Job configuration (source, target, scheduling)

--- Tenant Configuration ---
Tenant ID (e.g., acme, corp) [acme]: mycompany

--- Source Connector Selection ---

Available source connectors:

csv:
  Category: files
  Incremental: True
  Objects: file

stripe:
  Category: payments
  Incremental: True
  Objects: charges, customers, invoices

postgres:
  Category: database
  Incremental: True

Select source connector:
  1. csv
  2. gdrive_csv
  3. google_sheets
  4. hubspot
  5. mysql
  6. postgres
  7. stripe

Enter number (1-7): 7

================================================================================
ASSET DEFINITION GENERATION
================================================================================

STRIPE Connector:
  Category: payments
  Roles: source
  Default Engine: airbyte
  Cloud Allowed: True
  Incremental Support: True
  Incremental Strategy: created
  Objects Supported: charges, customers, invoices

--- Basic Information ---
Asset name (e.g., stripe_customers, postgres_orders): stripe_customers
Object/table name [customers]: customers
Version [1.0]: 1.0

--- Schema Definition ---
Define the schema fields for this asset.
Common field types: string, integer, bigint, double, boolean, date, timestamp

Suggested starter fields (you can customize):
Add 'id' field (string, required)? [Y/n]: y

Add additional fields (press Enter with empty name to finish):

Field name: email
Field type:
  1. string
  2. integer
  3. bigint
  4. double
  5. boolean
  6. date
  7. timestamp

Enter number (1-7) [1]: 1
Required? [y/N]: n
Mark as PII? [Y/n]: y

Field name: created
Field type:
  1. string
  2. integer
  3. bigint
  4. double
  5. boolean
  6. date
  7. timestamp

Enter number (1-7) [1]: 7
Required? [y/N]: y

Field name: balance
Field type:
  1. string
  2. integer
  3. bigint
  4. double
  5. boolean
  6. date
  7. timestamp

Enter number (1-7) [1]: 4
Required? [y/N]: n

Field name: 

--- Governance ---
Owner email [data-team@mycompany.com]: 
Tags (comma-separated) [stripe, customers]: 
Retention days [90]: 30

--- Target Configuration ---
File format:
  1. parquet

Enter number (1-1) [1]: 1
Partitioning columns (comma-separated) [ingest_date]: 
Schema evolution mode:
  1. strict
  2. merge
  3. relaxed

Enter number (1-3) [1]: 1

✓ Saved to: /workspace/assets/stripe/v1.0/stripe_customers.yaml

================================================================================
JOB CONFIGURATION GENERATION
================================================================================

--- Basic Information ---
Environment:
  1. dev
  2. staging
  3. prod

Enter number (1-3) [1]: 1

--- Source Configuration ---

Supported objects for stripe: charges, customers, invoices
Objects to sync (comma-separated) [customers]: 

Enable incremental sync? [Y/n]: y
Lookback days [1]: 

--- Target Configuration ---

Available target connectors:
  csv, google_sheets, iceberg, markdown_kv, minio, mysql, postgres, s3

Select target connector:
  * 1. iceberg
    2. s3
    3. minio

Enter number (1-3) [1]: 1
Target branch [mycompany]: 
Warehouse path [s3://lake/mycompany/]: 

Configure target connection? [Y/n]: y
S3/MinIO bucket [mycompany-data-lake]: 
S3 prefix [raw/stripe/stripe_customers]: 
Configure Nessie catalog? [Y/n]: y
Nessie URI [http://nessie.mycompany.internal:19120/api/v1]: 

--- Logging Configuration ---
Log level:
  1. DEBUG
  2. INFO
  3. WARNING
  4. ERROR

Enter number (1-4) [2]: 2
Enable log redaction? [Y/n]: y

✓ Saved to: /workspace/jobs/mycompany/stripe_customers_to_iceberg.yaml

================================================================================
GENERATION COMPLETE!
================================================================================

Asset Definition: /workspace/assets/stripe/v1.0/stripe_customers.yaml
Job Configuration: /workspace/jobs/mycompany/stripe_customers_to_iceberg.yaml

Next steps:
  1. Review and edit the generated files if needed
  2. Run the job: dativo run --config /workspace/jobs/mycompany/stripe_customers_to_iceberg.yaml --mode self_hosted
  3. Or add to orchestration: update configs/runner.yaml with schedule
```

## Generated Files

### Asset Definition Example
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
    - name: created
      type: timestamp
      required: true
    - name: balance
      type: double
      required: false
  governance:
    owner: data-team@mycompany.com
    tags:
      - stripe
      - customers
    classification:
      - PII
    retention_days: 30
  target:
    file_format: parquet
    partitioning:
      - ingest_date
    mode: strict
```

### Job Configuration Example
```yaml
tenant_id: mycompany
environment: dev
source_connector: stripe
source_connector_path: /app/connectors/stripe.yaml
target_connector: iceberg
target_connector_path: /app/connectors/iceberg.yaml
asset: stripe_customers
asset_path: /app/assets/stripe/v1.0/stripe_customers.yaml
source:
  objects:
    - customers
  incremental:
    lookback_days: 1
target:
  branch: mycompany
  warehouse: s3://lake/mycompany/
  connection:
    s3:
      bucket: mycompany-data-lake
      prefix: raw/stripe/stripe_customers
    nessie:
      uri: http://nessie.mycompany.internal:19120/api/v1
logging:
  redaction: true
  level: INFO
```

## Features

### Smart Defaults
- Suggests connector-appropriate field types and names
- Auto-detects PII and SENSITIVE data based on field names
- Provides sensible defaults for all configurations
- Uses tenant ID consistently across configurations

### Connector-Aware
- Only offers features supported by the connector (incremental, objects, tables)
- Configures connection parameters based on connector type
- Suggests appropriate cursor fields for incremental sync
- Handles credential templates from connector recipes

### Complete Workflow
- Generates both asset and job in one session
- Maintains consistency between asset and job references
- Creates proper directory structure
- Provides immediate next steps for testing

### Validation Ready
- Generates files that pass schema validation
- References proper connector paths for runtime resolution
- Uses standard ODCS schema format
- Follows Dativo configuration conventions

## Advanced Usage

### Custom Paths
The generator prompts for directory paths with sensible defaults:
- Assets: `/workspace/assets/{source_connector}/v1.0/`
- Jobs: `/workspace/jobs/{tenant_id}/`

These can be customized during generation.

### Environment Variables
For sensitive configuration (database credentials, API keys), use environment variable references:
```yaml
source:
  connection:
    host: "${PGHOST}"
    port: "${PGPORT}"
    database: "${PGDATABASE}"
```

### Multiple Objects
For connectors supporting multiple objects (HubSpot, Stripe):
```yaml
source:
  objects:
    - customers
    - charges
    - invoices
```

## Next Steps After Generation

1. **Review Generated Files**: Check asset schema and job configuration
2. **Set Up Secrets**: Ensure environment variables or secret files are configured
3. **Test Run**: Execute with `dativo run --config <job_path> --mode self_hosted`
4. **Add to Orchestration**: Update `configs/runner.yaml` with schedule if needed

## Troubleshooting

### Missing Registry
If the connector registry is not found at `/workspace/registry/connectors.yaml`, update the path in `generator.py`:
```python
registry = ConnectorRegistry(registry_path="/custom/path/connectors.yaml")
```

### Missing Connector Recipe
If a connector recipe is not found in `/workspace/connectors/`, the generator will use minimal configuration. Add the missing recipe or configure manually.

### Custom Connector
To add support for a custom connector:
1. Add to `registry/connectors.yaml`
2. Create connector recipe in `connectors/{name}.yaml`
3. Generator will automatically pick it up

## See Also
- [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) - Complete configuration reference
- [SCHEMA_VALIDATION.md](SCHEMA_VALIDATION.md) - Schema validation details
- [repo_layout.md](repo_layout.md) - Repository structure
