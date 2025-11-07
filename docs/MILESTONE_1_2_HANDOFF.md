# Milestone 1.2 - Handoff Document

## Context for Next Agent

This document provides context for implementing Milestone 1.2, building on the foundation established in Milestone 1.1.

## What's Already Done (M1.1)

### ✅ Complete Framework
- Configuration architecture (connectors, assets, jobs)
- Validation system (connectors, schemas, environment, infrastructure)
- Observability foundation (structured logging)
- Secrets management
- Infrastructure validation
- Startup sequence orchestration
- State management
- Markdown-KV storage support (parser, transformer, asset definitions)
- Testing infrastructure (unit tests, smoke tests)

### ✅ Key Capabilities
- Load and validate job configurations
- Load and validate connector recipes
- Load and validate asset definitions (ODCS v3.0.2)
- Validate environment variables
- Validate infrastructure dependencies
- Load secrets from storage
- Initialize state directories
- Parse Markdown-KV format
- Transform data to Markdown-KV format

## What's NOT Done (Deferred to M1.2+)

### ❌ Actual Data Ingestion
- No data extraction from sources yet
- No data loading to targets yet
- Jobs can be validated but not executed

### ❌ Parquet Writing
- No Parquet file generation yet
- No batch processing logic

### ❌ Iceberg/Nessie Integration
- No Nessie catalog commits yet
- No Iceberg table creation/updates

### ❌ Metrics & Tracing
- No metrics collection
- No distributed tracing

## Architecture Overview

### Configuration Flow
```
Job Config (YAML)
  ├─> Loads Source Connector Recipe
  ├─> Loads Target Connector Recipe
  ├─> Loads Asset Definition (ODCS)
  ├─> Merges source/target configs
  └─> Validates against registry
```

### Current Execution Flow
```
CLI Command
  ├─> startup_sequence()
  │   ├─> Load jobs from directory
  │   ├─> Initialize logging
  │   ├─> Load secrets
  │   ├─> Validate environment variables
  │   ├─> Validate infrastructure
  │   ├─> Initialize state management
  │   └─> Validate job configurations
  └─> _execute_single_job() [PLACEHOLDER - not implemented]
```

## Key Design Patterns

### 1. Config-Driven Architecture
- Everything is defined in YAML
- No hardcoded logic
- Connectors are reusable recipes
- Assets define schemas and governance
- Jobs compose connectors + assets

### 2. Validation-First Approach
- Extensive validation before execution
- Fail fast with clear error messages
- Warnings for non-critical issues (secrets, infrastructure)

### 3. Tenant Isolation
- All jobs belong to a tenant
- State directories are tenant-specific
- Secrets are tenant-specific
- Logging includes tenant_id

### 4. Incremental Sync Support
- State tracking per object/file
- File modified time tracking
- Lookback days support
- Skip unchanged files

## Important Code Locations

### Configuration Loading
- `src/dativo_ingest/config.py`:
  - `JobConfig.from_yaml()`: Load job config
  - `JobConfig.load_jobs_from_directory()`: Load multiple jobs
  - `SourceConnectorRecipe.from_yaml()`: Load source connector
  - `TargetConnectorRecipe.from_yaml()`: Load target connector
  - `AssetDefinition.from_yaml()`: Load asset definition
  - `JobConfig.get_source()`: Get merged source config
  - `JobConfig.get_target()`: Get merged target config

### Validation
- `src/dativo_ingest/validator.py`:
  - `ConnectorValidator.validate_job()`: Validate job against registry
  - `ConnectorValidator.validate_connector_type()`: Validate connector exists
  - `ConnectorValidator.validate_mode_restriction()`: Check cloud/self-hosted
  - `IncrementalStateManager`: State tracking for incremental syncs

### Startup Sequence
- `src/dativo_ingest/cli.py`:
  - `startup_sequence()`: Complete startup orchestration
  - `initialize_state_directory()`: Create state directories
  - `_execute_single_job()`: **PLACEHOLDER** - needs implementation

### Markdown-KV
- `src/dativo_ingest/markdown_kv.py`:
  - `parse_markdown_kv()`: Main parser
  - `parse_to_row_per_kv()`: Row-per-KV pattern
  - `parse_to_document_level()`: Document-level pattern
  - `transform_to_markdown_kv()`: Transform structured data to Markdown-KV

## Configuration Examples

### Job Configuration
```yaml
tenant_id: acme
source_connector_path: connectors/sources/stripe.yaml
target_connector_path: connectors/targets/iceberg.yaml
asset_path: assets/stripe/v1.0/customers.yaml

source:
  objects: [customers]
  incremental:
    strategy: created
    cursor_field: created
    lookback_days: 1

target:
  branch: acme
  warehouse: s3://lake/acme/
  connection:
    nessie:
      uri: "${NESSIE_URI}"
    s3:
      endpoint: "${S3_ENDPOINT}"
      bucket: acme-bucket
      access_key_id: "${AWS_ACCESS_KEY_ID}"
      secret_access_key: "${AWS_SECRET_ACCESS_KEY}"
      region: "${AWS_REGION}"
```

### Asset Definition (ODCS v3.0.2)
```yaml
$schema: schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
id: <uuid>
name: stripe_customers
version: "1.0"
status: active
domain: payments
dataProduct: stripe
tenant: acme

schema:
  - name: id
    type: string
    required: true
  - name: email
    type: string
    required: false

team:
  owner: data-team@company.com

data_quality:
  monitoring:
    enabled: true
    oncall_rotation: data-ops@company.com

compliance:
  classification: [PII]
  retention_days: 90
```

## Registry Structure

### `registry/connectors.yaml`
Contains connector capabilities only (not full configs):
- `category`: Type of connector (payments, database, files)
- `default_engine`: Default extraction/loading engine
- `engines_supported`: List of supported engines
- `allowed_in_cloud`: Whether allowed in cloud mode
- `supports_incremental`: Whether supports incremental sync
- `incremental_strategy_default`: Default incremental strategy
- `file_formats`: Supported file formats (for targets)

## State Management

### State File Structure
```json
{
  "file_file_123": {
    "last_modified": "2024-01-01T00:00:00Z"
  },
  "object_customers": {
    "cursor": "2024-01-01T00:00:00Z",
    "last_sync": "2024-01-01T00:00:00Z"
  }
}
```

### State Directory
- Path: `/state/{tenant_id}/{job_name}/state.json`
- Created by `initialize_state_directory()`
- Used by `IncrementalStateManager`

## Secrets Structure

### Directory Layout
```
/secrets/
  {tenant_id}/
    gsheets.json          # JSON secrets
    iceberg.env           # Environment variables
    api_key.txt           # Plain text secrets
```

### Loading
- `load_secrets(tenant_id, secrets_dir)` loads all files
- Returns dict keyed by filename (without extension)
- Supports JSON, .env, and plain text
- Environment variables expanded in values

## Infrastructure Validation

### Checks Performed
1. **Nessie**: HTTP connectivity check
2. **S3/MinIO**: Endpoint connectivity check
3. **Database Ports**: TCP port connectivity (for database sources)

### Implementation
- `validate_infrastructure(job_config)` in `infrastructure.py`
- Checks based on target type and source type
- Logs warnings (not errors) for failures
- Allows jobs to proceed even if infrastructure checks fail

## Testing Strategy

### Unit Tests
- Test individual functions/modules in isolation
- Fast execution
- Located in `tests/test_*.py`

### Smoke Tests
- Run actual CLI commands with test fixtures
- True E2E validation
- No pytest wrappers - just CLI invocations

### Test Fixtures
- `tests/fixtures/jobs/`: Job configurations
- `tests/fixtures/assets/`: Asset definitions
- `tests/fixtures/seeds/`: Test data files
- `tests/fixtures/secrets/`: Test secrets

## What M1.2 Should Implement

Based on the original plan, M1.2 should focus on:

### 1. Parquet + Iceberg Commit Path
- Schema validator with `required: true` + type enforcement
- Parquet writer + Nessie commit logic
- Validate `asset_path` against asset definition (enable strict mode)

### 2. Actual Data Extraction
- Implement connector execution logic
- Extract data from sources (Stripe, HubSpot, CSV, etc.)
- Handle incremental syncs
- Process data according to asset schema

### 3. Data Loading
- Write Parquet files
- Commit to Iceberg via Nessie
- Handle partitioning
- Support different file formats

### 4. Error Handling & Retries
- Retry logic for transient failures
- Error reporting and logging
- Exit codes (0=success, 1=partial, 2=failure)

## Key Integration Points

### Where to Add Ingestion Logic

1. **`_execute_single_job()` in `cli.py`**:
   - Currently a placeholder
   - Should orchestrate: extract → transform → load → commit

2. **Connector Execution**:
   - Need to implement actual connector execution
   - Use connector recipes to determine engine
   - Execute Airbyte/Singer/Meltano/Native connectors

3. **Schema Enforcement**:
   - Validate extracted data against asset schema
   - Enforce `required: true` fields
   - Type coercion/validation

4. **Parquet Writing**:
   - Batch records into Parquet files
   - Apply partitioning
   - Handle file size limits

5. **Nessie Commits**:
   - Commit Parquet files to Iceberg
   - Update table metadata
   - Handle branch management

## Dependencies

### Already Installed
- `pydantic>=2.0.0`: Configuration models
- `pyyaml>=6.0`: YAML parsing
- `jsonschema>=4.0.0`: Schema validation
- `requests>=2.28.0`: HTTP requests

### May Need for M1.2
- `pyarrow` or `fastparquet`: Parquet writing
- `pyiceberg`: Iceberg table management
- `pynessie`: Nessie catalog client
- `boto3`: S3/MinIO access
- Airbyte/Singer/Meltano connectors (Docker images or Python packages)

## Important Notes

### 1. Configuration is the Source of Truth
- All behavior driven by YAML configs
- No hardcoded logic
- Connectors are recipes, not code

### 2. Validation is Extensive
- Validate everything before execution
- Fail fast with clear errors
- Warnings for non-critical issues

### 3. Tenant Isolation is Critical
- All operations are tenant-scoped
- State, secrets, logs are tenant-specific
- Nessie branches are tenant-specific

### 4. Incremental Syncs are First-Class
- State tracking is built-in
- Support for multiple incremental strategies
- Lookback days for backfilling

### 5. Markdown-KV is Fully Supported
- Parser and transformer implemented
- Three storage patterns available
- Asset definitions ready

## Questions to Consider for M1.2

1. **Connector Execution**:
   - How to execute Airbyte/Singer/Meltano connectors?
   - Docker containers? Python packages? Subprocess calls?
   - How to handle connector-specific configuration?

2. **Schema Enforcement**:
   - When to validate? During extraction? Before writing?
   - How strict should validation be?
   - What to do with invalid records?

3. **Parquet Writing**:
   - Batch size? File size limits?
   - Compression? Partitioning strategy?
   - How to handle schema evolution?

4. **Nessie Integration**:
   - How to manage branches?
   - How to handle conflicts?
   - How to track commit history?

5. **Error Handling**:
   - What constitutes partial success?
   - How to retry failed operations?
   - How to report errors to users?

## Recommended Next Steps

1. **Start with Parquet Writing**:
   - Implement basic Parquet file generation
   - Test with sample data
   - Validate against asset schemas

2. **Add Nessie Integration**:
   - Set up Nessie client
   - Implement basic commit logic
   - Test with local Nessie instance

3. **Implement CSV Source**:
   - Start with simplest source (CSV)
   - Extract data from CSV files
   - Write to Parquet
   - Commit to Iceberg

4. **Add Schema Enforcement**:
   - Validate data against asset schema
   - Enforce required fields
   - Handle type mismatches

5. **Add Incremental Sync**:
   - Use state management for incremental syncs
   - Track cursor values
   - Skip unchanged data

## Testing Strategy for M1.2

### Unit Tests
- Test Parquet writing
- Test Nessie commits
- Test schema validation
- Test incremental sync logic

### Integration Tests
- Test CSV → Parquet → Iceberg flow
- Test with real Nessie instance
- Test with real S3/MinIO

### Smoke Tests
- Use existing smoke test infrastructure
- Add actual data ingestion tests
- Validate data in Iceberg tables

## Documentation to Update

- `README.md`: Add ingestion execution details
- `docs/CONFIG_REFERENCE.md`: Add execution examples
- `docs/RUNNER_AND_ORCHESTRATION.md`: Add execution details
- Create `docs/INGESTION_EXECUTION.md`: Detailed execution guide

## Success Criteria for M1.2

- ✅ Can extract data from CSV source
- ✅ Can write Parquet files
- ✅ Can commit to Iceberg via Nessie
- ✅ Can validate data against asset schema
- ✅ Can handle incremental syncs
- ✅ Can report success/failure with exit codes
- ✅ Can handle errors gracefully

Good luck with M1.2! The foundation is solid and ready for the next phase.

