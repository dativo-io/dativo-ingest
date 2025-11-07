# Milestone 1.3 - Handoff Document

## Context for Next Agent

This document provides context for implementing Milestone 1.3, building on the foundation established in Milestones 1.1 and 1.2.

## What's Already Done

### ✅ M1.1 - Core Framework (Complete)
- Configuration architecture (connectors, assets, jobs)
- Validation system (connectors, schemas, environment, infrastructure)
- Observability foundation (structured logging)
- Secrets management
- Infrastructure validation
- Startup sequence orchestration
- State management
- Markdown-KV storage support

### ✅ M1.2 - Parquet + Iceberg Commit Path (Complete)
- Schema validator with `required: true` + type enforcement
- Parquet writer with industry-standard paths
- CSV extractor (native Python)
- Iceberg/Nessie integration (optional catalog)
- Complete ETL pipeline orchestration
- Error handling and exit codes
- Incremental sync support
- Comprehensive metadata propagation

**See**: `docs/MILESTONE_1_2_COMPLETE.md` for full details

## What M1.3 Should Implement

Based on the original plan (`docs/milestones.md`), M1.3 focuses on:

### 1. OSS Connector Wrappers

Implement wrappers for open-source connectors to support additional data sources:

**Priority Sources**:
1. **Stripe** - Payment data extraction
2. **HubSpot** - CRM data extraction
3. **Google Drive CSV** - File-based extraction from GDrive
4. **Google Sheets** - Spreadsheet data extraction
5. **Postgres** - Database extraction (self-hosted only)
6. **MySQL** - Database extraction (self-hosted only)

**Connector Execution Strategy**:
- **Native Python** (preferred for simple sources like CSV - already done)
- **Airbyte** (Docker containers or Python SDK)
- **Singer** (Python taps)
- **Meltano** (Python plugins)
- **Direct API** (for SaaS sources like Stripe, HubSpot)

### 2. State Tracking & Cursor Handling

**Incremental Sync Strategies**:
- **Timestamp-based** (`created`, `updated`): Track cursor field values
- **Incremental append**: Track last processed record ID
- **Full refresh**: Clear state and re-sync all data
- **Lookback days**: Support for backfilling historical data

**State Management**:
- Per-object state tracking (already implemented)
- Cursor field tracking
- Last sync timestamp
- Error state tracking (for retries)

### 3. Dagster Schedules & Retries

**Schedule Integration**:
- Map job configurations to Dagster schedules
- Support for cron-based schedules
- Support for interval-based schedules
- Tenant-level schedule isolation

**Retry Logic**:
- Map job exit codes to Dagster retries:
  - Exit code 0: Success (no retry)
  - Exit code 1: Partial success (optional retry)
  - Exit code 2: Failure (retry with backoff)
- Configurable retry attempts and backoff
- Retryable error classification

### 4. Enhanced Error Handling

**Per-Connector Error Handling**:
- Connector-specific error classification
- Transient vs. permanent errors
- Rate limiting handling
- API quota management
- Connection timeout handling

**Error Reporting**:
- Structured error logs
- Error summaries per connector
- Failed record tracking
- Error notification hooks (future)

## Key Integration Points

### 1. Connector Execution Framework

**Location**: `src/dativo_ingest/connectors/`

**Pattern to Follow**:
```python
class ConnectorExtractor:
    def __init__(self, source_config, asset_definition, state_manager):
        self.source_config = source_config
        self.asset_definition = asset_definition
        self.state_manager = state_manager
    
    def extract(self):
        """Yield batches of records"""
        # 1. Check incremental state
        # 2. Extract data from source
        # 3. Update state after successful extraction
        # 4. Yield batches
        pass
```

**Existing Example**: `src/dativo_ingest/connectors/csv_extractor.py`

### 2. Connector Recipe Structure

**Source Connector Recipe** (`connectors/sources/*.yaml`):
```yaml
name: stripe
type: stripe
description: "Stripe payment data extraction"
default_engine:
  type: native  # or: airbyte, singer, meltano
  options:
    native:
      library: "stripe"
      api_version: "2023-10-16"
    airbyte:
      image: "airbyte/source-stripe:latest"
      config:
        start_date: "${START_DATE}"
credentials:
  api_key: "${STRIPE_API_KEY}"
connection_template:
  api_key: "${STRIPE_API_KEY}"
  account_id: "${STRIPE_ACCOUNT_ID}"
incremental:
  strategy: created
  cursor_field: created
  lookback_days: 7
```

### 3. State Management Integration

**IncrementalStateManager** (`src/dativo_ingest/validator.py`):
- Already supports file-based incremental syncs
- Need to extend for cursor-based syncs:
  - `get_cursor(object_name)`: Get last cursor value
  - `update_cursor(object_name, cursor_value)`: Update cursor
  - `should_sync(object_name, cursor_field)`: Check if sync needed

**State File Structure** (extend):
```json
{
  "file_file_123": {
    "last_modified": "2024-01-01T00:00:00Z"
  },
  "object_customers": {
    "cursor": "2024-01-01T00:00:00Z",
    "last_sync": "2024-01-01T00:00:00Z",
    "cursor_field": "created"
  }
}
```

### 4. Dagster Integration

**Location**: `src/dativo_runner/orchestrated.py`

**Current State**: Scaffold exists, needs implementation

**Required Features**:
- Load jobs from `runner.yaml`
- Create Dagster assets for each job
- Map job schedules to Dagster schedules
- Map job exit codes to Dagster retries
- Tenant-level isolation

**Example**:
```python
@asset(
    key_prefix=["dativo", tenant_id],
    group_name=tenant_id,
    retry_policy=RetryPolicy(max_retries=3, delay=60),
)
def stripe_customers_job(context):
    # Execute job
    exit_code = execute_job(job_config)
    if exit_code == 2:
        raise RetryableException("Job failed, will retry")
    return exit_code
```

## Implementation Strategy

### Phase 1: Stripe Connector (Week 1)

**Why Start Here**:
- Simple API-based source
- Well-documented API
- Common use case
- Good for testing incremental syncs

**Implementation Steps**:
1. Create `connectors/sources/stripe.yaml` recipe
2. Implement `src/dativo_ingest/connectors/stripe_extractor.py`
3. Add Stripe API client integration
4. Implement cursor-based incremental sync
5. Add unit tests
6. Add smoke test

### Phase 2: HubSpot Connector (Week 1-2)

**Similar to Stripe**:
- API-based source
- Cursor-based incremental sync
- Rate limiting considerations

### Phase 3: Google Drive/Sheets (Week 2)

**Implementation Options**:
- **Native Python**: Use Google APIs client library
- **Airbyte**: Use `airbyte/source-google-sheets`
- **Hybrid**: Native for simple cases, Airbyte for complex

**Considerations**:
- OAuth2 authentication
- File discovery and listing
- Incremental sync by modified time

### Phase 4: Database Connectors (Week 2-3)

**Postgres/MySQL**:
- **Self-hosted only** (security requirement)
- Use SQLAlchemy or native database drivers
- Support for:
  - Full table sync
  - Incremental sync by timestamp
  - Incremental sync by ID
  - Custom SQL queries

**Implementation**:
- `src/dativo_ingest/connectors/postgres_extractor.py`
- `src/dativo_ingest/connectors/mysql_extractor.py`
- Connection pooling
- Query result chunking

### Phase 5: Dagster Integration (Week 3)

**Schedule Mapping**:
- Parse `runner.yaml` for schedule definitions
- Create Dagster schedules
- Map to job configurations

**Retry Mapping**:
- Parse job exit codes
- Map to Dagster retry policies
- Handle partial success cases

## Dependencies

### Already Installed
- `pydantic>=2.0.0`: Configuration models
- `pyyaml>=6.0`: YAML parsing
- `pandas>=2.0.0`: Data processing
- `pyarrow>=14.0.0`: Parquet writing
- `boto3>=1.28.0`: S3/MinIO access
- `dagster>=1.5.0`: Orchestration framework

### May Need for M1.3
- `stripe>=7.0.0`: Stripe API client
- `hubspot-api-client`: HubSpot API client
- `google-api-python-client`: Google APIs client
- `google-auth`: Google authentication
- `sqlalchemy>=2.0.0`: Database abstraction
- `psycopg2-binary`: Postgres driver
- `pymysql`: MySQL driver
- `airbyte-cdk`: Airbyte Python SDK (optional)
- `singer-python`: Singer taps (optional)

## Testing Strategy

### Unit Tests
- Test each connector extractor independently
- Mock API responses
- Test incremental sync logic
- Test error handling

### Integration Tests
- Test with real API credentials (use test accounts)
- Test with real databases (use test databases)
- Test state persistence
- Test retry logic

### Smoke Tests
- Add smoke tests for each new connector
- Use test fixtures with sample data
- Verify end-to-end flow

## Configuration Examples

### Stripe Job Configuration
```yaml
tenant_id: acme
source_connector: stripe
source_connector_path: connectors/sources/stripe.yaml
target_connector: iceberg
target_connector_path: connectors/targets/iceberg.yaml
asset: stripe_customers
asset_path: assets/stripe/v1.0/customers.yaml

source:
  objects: [customers, subscriptions]
  incremental:
    strategy: created
    cursor_field: created
    lookback_days: 7

target:
  connection:
    s3:
      endpoint: "${S3_ENDPOINT}"
      bucket: acme-data-lake
```

### Postgres Job Configuration
```yaml
tenant_id: acme
source_connector: postgres
source_connector_path: connectors/sources/postgres.yaml
target_connector: iceberg
target_connector_path: connectors/targets/iceberg.yaml
asset: db_orders
asset_path: assets/postgres/v1.0/orders.yaml

source:
  objects: [orders, order_items]
  incremental:
    strategy: updated
    cursor_field: updated_at
    lookback_days: 1
  connection:
    host: "${POSTGRES_HOST}"
    port: 5432
    database: "${POSTGRES_DB}"
    user: "${POSTGRES_USER}"
    password: "${POSTGRES_PASSWORD}"

target:
  connection:
    s3:
      endpoint: "${S3_ENDPOINT}"
      bucket: acme-data-lake
```

### Dagster Runner Configuration
```yaml
# runner.yaml
jobs:
  - name: stripe_customers_sync
    schedule: "0 */6 * * *"  # Every 6 hours
    job_path: jobs/acme/stripe_customers_to_iceberg.yaml
    retry_policy:
      max_retries: 3
      delay_seconds: 60
      backoff_factor: 2
```

## Important Notes

### 1. Connector Execution Patterns

**Native Python** (preferred when possible):
- Direct API calls
- Simple, maintainable
- Good for SaaS APIs (Stripe, HubSpot)

**Airbyte** (for complex sources):
- Use Docker containers
- Or use Airbyte Python SDK
- Good for databases and complex APIs

**Singer** (legacy, but still used):
- Python taps
- Standardized protocol
- Good for existing Singer ecosystem

### 2. Incremental Sync Strategies

**Timestamp-based** (`created`, `updated`):
- Track cursor field value
- Query: `WHERE cursor_field > last_cursor`
- Most common for SaaS APIs

**Incremental append**:
- Track last processed ID
- Query: `WHERE id > last_id`
- Good for databases

**Full refresh**:
- Clear state
- Re-sync all data
- Use for schema changes or backfills

### 3. Error Handling

**Transient Errors** (retry):
- Network timeouts
- Rate limiting (with backoff)
- Temporary API unavailability

**Permanent Errors** (fail fast):
- Authentication failures
- Invalid configuration
- Schema mismatches

### 4. Rate Limiting

**Considerations**:
- API rate limits (Stripe, HubSpot have limits)
- Implement exponential backoff
- Track API call counts (for FinOps)
- Respect rate limit headers

## Success Criteria for M1.3

- ✅ Can extract data from Stripe API
- ✅ Can extract data from HubSpot API
- ✅ Can extract data from Google Drive/Sheets
- ✅ Can extract data from Postgres database
- ✅ Can extract data from MySQL database
- ✅ Can handle cursor-based incremental syncs
- ✅ Can handle rate limiting gracefully
- ✅ Dagster schedules work for jobs
- ✅ Dagster retries work based on exit codes
- ✅ State persistence works across runs
- ✅ All connectors have unit tests
- ✅ All connectors have smoke tests

## Recommended Next Steps

1. **Start with Stripe**:
   - Simplest API-based source
   - Good for testing incremental syncs
   - Well-documented

2. **Add HubSpot**:
   - Similar to Stripe
   - Different API patterns to learn

3. **Add Google Sources**:
   - More complex (OAuth2)
   - Good for testing file-based extraction

4. **Add Database Sources**:
   - Different pattern (SQL queries)
   - Good for testing query-based extraction

5. **Integrate Dagster**:
   - Map schedules
   - Map retries
   - Test orchestration

## Documentation to Update

- `README.md`: Add connector examples
- `docs/CONFIG_REFERENCE.md`: Add connector-specific configs
- `docs/INGESTION_EXECUTION.md`: Add connector execution details
- Create `docs/CONNECTOR_DEVELOPMENT.md`: Guide for adding new connectors

## Key Files Reference

### Existing Files to Extend
- `src/dativo_ingest/connectors/csv_extractor.py`: Reference implementation
- `src/dativo_ingest/validator.py`: IncrementalStateManager
- `src/dativo_ingest/cli.py`: Job execution orchestration
- `connectors/sources/csv.yaml`: Connector recipe example

### New Files to Create
- `src/dativo_ingest/connectors/stripe_extractor.py`
- `src/dativo_ingest/connectors/hubspot_extractor.py`
- `src/dativo_ingest/connectors/gdrive_extractor.py`
- `src/dativo_ingest/connectors/gsheets_extractor.py`
- `src/dativo_ingest/connectors/postgres_extractor.py`
- `src/dativo_ingest/connectors/mysql_extractor.py`
- `connectors/sources/stripe.yaml`
- `connectors/sources/hubspot.yaml`
- `connectors/sources/gdrive_csv.yaml`
- `connectors/sources/google_sheets.yaml`
- `connectors/sources/postgres.yaml`
- `connectors/sources/mysql.yaml`

Good luck with M1.3! The foundation is solid and ready for connector expansion.

