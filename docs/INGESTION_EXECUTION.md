# Ingestion Execution Guide

This document describes how the Dativo ingestion platform executes jobs, from data extraction through schema validation, Parquet writing, and Iceberg commits.

## Table of Contents

1. [Execution Flow](#execution-flow)
2. [Schema Validation](#schema-validation)
3. [Parquet File Writing](#parquet-file-writing)
4. [Iceberg/Nessie Integration](#icebergnessie-integration)
5. [Incremental Syncs](#incremental-syncs)
6. [Error Handling](#error-handling)
7. [Performance Considerations](#performance-considerations)
8. [Monitoring](#monitoring)
9. [Example Execution](#example-execution)
10. [Troubleshooting](#troubleshooting)

---

## Execution Flow

The ingestion pipeline follows these steps:

1. **Extract**: Read data from source (CSV, API, database, etc.)
2. **Validate**: Validate records against asset schema
3. **Write**: Write validated records to Parquet files
4. **Commit**: Commit Parquet files to Iceberg table via Nessie
5. **Update State**: Update incremental sync state (if applicable)

---

## Schema Validation

During execution, records are validated against the asset schema before being written to Parquet files.

**Validation Modes:**
- **Strict Mode** (default): Fails job if any record has validation errors
- **Warn Mode**: Logs errors but continues processing

**Configuration:**
```yaml
schema_validation_mode: strict  # or warn
```

For detailed validation rules, error reporting, and configuration options, see [SCHEMA_VALIDATION.md](SCHEMA_VALIDATION.md).

---

## Parquet File Writing

### File Sizing

Parquet files are written with a target size of 128-200 MB (configurable).

**Configuration:**
```yaml
target:
  parquet_target_size_mb: 150  # Target file size in MB
```

The writer:
1. Estimates file size based on sample records
2. Batches records to approximate target size
3. Writes files when batch size is reached
4. Handles remaining records in final file

### Partitioning

Parquet files can be partitioned by one or more columns:

**Configuration:**
```yaml
target:
  partitioning: [ingest_date, region]
```

Common partition columns:
- `ingest_date`: Automatically set to current date
- Custom columns: Values from record data

Partitioned files are organized in directories:
```
s3://bucket/table_name/ingest_date=2024-01-01/region=us/file.parquet
```

### Schema Evolution

The Parquet writer:
- Creates files matching asset schema
- Handles missing optional fields (null values)
- Supports schema changes between runs (via Iceberg)

---

## Iceberg/Nessie Integration

### Branch Management

Tables are committed to Nessie branches:
- **Default**: Branch name matches `tenant_id`
- **Override**: Specify custom branch in target config

**Configuration:**
```yaml
target:
  branch: acme  # Defaults to tenant_id if not specified
```

### Table Creation

Tables are automatically created if they don't exist:
- Schema derived from asset definition
- Partitioning spec from target config
- Created in namespace (domain) from asset definition

### Commit Process

1. Upload Parquet files to S3/MinIO storage
2. Register files in Iceberg table metadata
3. Commit metadata changes to Nessie branch
4. Return commit ID and file count

### Connection Configuration

**Nessie:**
```yaml
target:
  connection:
    nessie:
      uri: "http://nessie.example.com:19120/api/v1"
```

**S3/MinIO:**
```yaml
target:
  connection:
    s3:
      endpoint: "http://s3.example.com:9000"
      bucket: "data-lake"
      access_key_id: "${AWS_ACCESS_KEY_ID}"
      secret_access_key: "${AWS_SECRET_ACCESS_KEY}"
      region: "us-east-1"
```

---

## Incremental Syncs

### File-Based Incremental

For CSV and file-based sources:

**Configuration:**
```yaml
source:
  files:
    - path: /data/customers.csv
      object: customers
  incremental:
    strategy: file_modified_time
    lookback_days: 1
    state_path: .local/state/tenant/csv.customers.state.json
```

The system:
1. Tracks file modified time in state file
2. Skips unchanged files (if `lookback_days: 0`)
3. Processes files modified within lookback window
4. Updates state after successful processing

### State Management

State files are stored at (default for development):
```
.local/state/{tenant_id}/{connector_type}.{object_name}.state.json
```

**Environment-specific locations:**
- **Development**: `.local/state/` (default, gitignored)
- **Testing/CI**: `/tmp/dativo-state/` (temporary, cleaned after tests)
- **Production**: Set `STATE_DIR` environment variable to:
  - Database path (future: database backend)
  - S3 path: `s3://bucket/state/` (future: S3 backend)
  - Custom path: Any writable directory

**Note:** State files are runtime data and should not be committed to version control. The `.local/` directory is automatically gitignored.

State format:
```json
{
  "file_/path/to/file.csv": {
    "last_modified": "2024-01-01T00:00:00Z",
    "file_id": "/path/to/file.csv"
  }
}
```

---

## Error Handling

### Exit Codes

- **0**: Success - all records processed successfully
- **1**: Partial success - some records had errors (warn mode)
- **2**: Failure - job failed (validation errors in strict mode, or other errors)

### Retry Configuration

**Configuration:**
```yaml
retry_config:
  max_retries: 3
  retry_delay_seconds: 5
  retryable_errors:
    - "ConnectionError"
    - "TimeoutError"
```

Retries are applied to:
- Transient network errors
- Temporary storage failures
- Nessie catalog connection issues

### Error Logging

All errors are logged with:
- Error type and message
- Tenant ID and job context
- Stack traces for debugging
- Event type for filtering

---

## Performance Considerations

### Batch Processing

- Records are processed in batches (configurable chunk size)
- Parquet files are written when batch size reaches target
- Multiple files can be written per job run

### Memory Management

- CSV files are read in chunks (default: 10,000 rows)
- Parquet files are written incrementally
- Large datasets are handled without loading entire file into memory

### Parallelization

- Current implementation processes files sequentially
- Future: Support for parallel file processing
- Future: Parallel batch validation

---

## Monitoring

### Log Events

Key events logged during execution:
- `job_started`: Job execution begins
- `extractor_initialized`: Source extractor ready
- `validator_initialized`: Schema validator ready
- `writer_initialized`: Parquet writer ready
- `committer_initialized`: Iceberg committer ready
- `table_ensured`: Iceberg table exists
- `batch_written`: Batch written to Parquet
- `validation_errors`: Validation errors found
- `commit_success`: Files committed to Iceberg
- `job_finished`: Job execution complete

### Metrics (Future)

Planned metrics:
- Records processed per second
- Validation error rate
- File write throughput
- Commit latency
- Storage usage

---

## Example Execution

### Running a Job

```bash
# Run a CSV ingestion job
dativo_ingest run \
  --config jobs/acme/csv_person_to_iceberg.yaml \
  --mode self_hosted
```

**Job Configuration:**
```yaml
tenant_id: acme
source_connector_path: connectors/sources/csv.yaml
target_connector_path: connectors/targets/iceberg.yaml
asset_path: assets/csv/v1.0/person.yaml

source:
  files:
    - path: /data/person.csv
      object: person
  incremental:
    strategy: file_modified_time
    lookback_days: 1

target:
  branch: acme
  warehouse: s3://lake/acme/
  partitioning: [ingest_date]
  connection:
    nessie:
      uri: "${NESSIE_URI}"
    s3:
      endpoint: "${S3_ENDPOINT}"
      bucket: acme-data-lake

schema_validation_mode: strict
```

**Execution Output:**
```
INFO: Starting job execution (connector_type=csv, tenant_id=acme)
INFO: Asset definition loaded (asset_name=csv_person)
INFO: Extractor initialized (source_type=csv)
INFO: Schema validator initialized (validation_mode=strict)
INFO: Parquet writer initialized (output_base=s3://lake/acme/csv_person)
INFO: Iceberg committer initialized (branch=acme)
INFO: Iceberg table ensured (table_name=csv_person)
INFO: Wrote batch: 1000 records, 1 files
INFO: Files committed to Iceberg (files_added=1, commit_id=abc123)
INFO: Job execution completed (total_records=1000, valid_records=1000, exit_code=0)
```

---

## Troubleshooting

### Common Issues

1. **Validation Errors in Strict Mode**
   - Check asset schema matches source data
   - Verify required fields are present
   - Check type compatibility

2. **File Not Found**
   - Verify file paths in source config
   - Check file permissions
   - Ensure files exist before job run

3. **Nessie Connection Failed**
   - Verify Nessie URI is correct
   - Check network connectivity
   - Ensure Nessie service is running

4. **S3 Upload Failed**
   - Verify S3 credentials
   - Check bucket exists and is accessible
   - Verify endpoint URL for MinIO

5. **Table Creation Failed**
   - Check branch exists in Nessie
   - Verify schema is valid
   - Check namespace permissions

---

## Additional Resources

- [SETUP_AND_ONBOARDING.md](SETUP_AND_ONBOARDING.md) - Setup and onboarding guide
- [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) - Configuration reference
- [SCHEMA_VALIDATION.md](SCHEMA_VALIDATION.md) - Schema validation guide
- [CATALOG_LIMITATIONS.md](CATALOG_LIMITATIONS.md) - Catalog limitations and workarounds

