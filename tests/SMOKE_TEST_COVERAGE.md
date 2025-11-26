# Smoke Test Coverage Documentation

## Overview

This document provides a comprehensive overview of smoke test coverage for the Dativo ingestion system. Smoke tests are end-to-end tests that run actual CLI commands with test fixtures to verify the full pipeline works correctly.

## Test Coverage Matrix

### Connector Coverage

| Connector | Role | Engine | Status | Test Fixture |
|-----------|------|--------|--------|--------------|
| hubspot | source | airbyte | ✅ | `hubspot_contacts_to_iceberg.yaml` |
| hubspot | source | airbyte | ✅ (error) | `hubspot_invalid_credentials.yaml` |
| stripe | source | airbyte | ✅ | `stripe_customers_to_iceberg.yaml` |
| gdrive_csv | source | native | ✅ | `gdrive_csv_to_iceberg.yaml` |
| gdrive_csv | source | airbyte | ✅ | `gdrive_csv_airbyte_to_iceberg.yaml` |
| google_sheets | source | native | ✅ | `google_sheets_to_iceberg.yaml` |
| google_sheets | source | airbyte | ✅ | `google_sheets_airbyte_to_iceberg.yaml` |
| google_sheets | target | native | ✅ | `iceberg_to_google_sheets.yaml` |
| csv | source | native | ✅ | `csv_employee_to_iceberg.yaml` |
| csv | source | native | ✅ | `csv_product_to_minio.yaml` |
| csv | source | native | ✅ (error) | `csv_malformed_data.yaml` |
| csv | source | native | ✅ (strict) | `csv_product_strict_validation.yaml` |
| csv | source | native | ✅ (state) | `csv_employee_state_persistence.yaml` |
| markdown_kv | source | native | ✅ | `markdown_kv_source_to_iceberg.yaml` |
| markdown_kv | target | native | ✅ | `postgres_*_to_iceberg_markdown_kv.yaml` |
| postgres | source | native/meltano | ✅ | `postgres_*_to_iceberg_markdown_kv.yaml` |
| postgres | source | native/meltano | ✅ (error) | `postgres_connection_failure.yaml` |
| mysql | source | native/meltano | ✅ | `mysql_*_to_iceberg_markdown_kv.yaml` |
| iceberg | target | native | ✅ | All `*_to_iceberg.yaml` jobs |
| minio | target | native | ✅ | `csv_product_to_minio.yaml` |
| s3 | target | native | ✅ | `csv_person_to_s3.yaml` |

### Engine Type Coverage

| Engine Type | Connectors Tested | Status |
|-------------|-------------------|--------|
| native | csv, gdrive_csv, google_sheets, postgres, mysql, markdown_kv | ✅ |
| airbyte | hubspot, stripe, gdrive_csv, google_sheets | ✅ |
| meltano | postgres, mysql (default, implicit) | ⚠️ |
| singer | None | ❌ |

### Incremental Sync Strategies

| Strategy | Connectors Tested | Status |
|----------|-------------------|--------|
| updated_after | hubspot | ✅ |
| created | stripe | ✅ |
| file_modified_time | csv, gdrive_csv, markdown_kv | ✅ |
| spreadsheet_modified_time | google_sheets | ✅ |
| updated_at | postgres, mysql | ✅ |

### Target Connectors

| Target | Format | Status | Test Fixtures |
|--------|--------|--------|---------------|
| iceberg | parquet | ✅ | All `*_to_iceberg.yaml` |
| iceberg | markdown_kv | ✅ | `postgres_*_to_iceberg_markdown_kv.yaml` |
| minio | parquet | ✅ | `csv_product_to_minio.yaml` |
| s3 | parquet | ✅ | `csv_person_to_s3.yaml` |
| google_sheets | native | ✅ | `iceberg_to_google_sheets.yaml` |

### Feature Coverage

| Feature | Status | Test Fixtures |
|---------|--------|---------------|
| Basic extraction | ✅ | All source connector tests |
| Parquet writing | ✅ | All iceberg/minio/s3 target tests |
| Iceberg commits | ✅ | All `*_to_iceberg.yaml` tests |
| Incremental sync | ✅ | All tests with incremental config |
| State persistence | ✅ | `csv_employee_state_persistence.yaml` + `test_state_persistence.sh` |
| Schema validation (warn) | ✅ | Most tests use warn mode |
| Schema validation (strict) | ✅ | `csv_product_strict_validation.yaml` |
| Error handling | ✅ | Error scenario tests |
| Custom plugins | ✅ | `smoke_test_*.yaml` (separate suite) |
| Markdown-KV transformation | ✅ | `postgres_*_to_iceberg_markdown_kv.yaml` |

### Error Scenario Coverage

| Error Type | Test Fixture | Expected Behavior |
|------------|--------------|------------------|
| Invalid API credentials | `hubspot_invalid_credentials.yaml` | Authentication error, job fails |
| Connection failure | `postgres_connection_failure.yaml` | Connection error, job fails |
| Malformed CSV data | `csv_malformed_data.yaml` | Parse error, handled gracefully |
| Strict validation failure | `csv_product_strict_validation.yaml` | Validation error, job fails |

## Test Execution

### Running All Smoke Tests

```bash
# Run all smoke tests
make test-smoke

# Or directly
./tests/smoke_tests.sh
```

### Running State Persistence Test

```bash
# Run state persistence test separately
./tests/test_state_persistence.sh
```

### Running Custom Plugin Tests

```bash
# Run custom plugin smoke tests
./tests/smoke_tests_custom_plugins.sh
```

### Running Specific Job

```bash
# Run a specific job fixture
PYTHONPATH=src python -m dativo_ingest.cli run \
  --job-dir tests/fixtures/jobs \
  --secrets-dir tests/fixtures/secrets \
  --mode self_hosted \
  --job csv_employee_to_iceberg.yaml
```

## Test Categories

### 1. Core Functionality Tests

These tests verify basic connector functionality:

- **Source connectors**: Extract data from various sources
- **Target connectors**: Write data to various targets
- **Data formats**: Parquet, Markdown-KV
- **Basic pipeline**: Extract → Validate → Write → Commit

**Test Fixtures:**
- `hubspot_contacts_to_iceberg.yaml`
- `stripe_customers_to_iceberg.yaml`
- `gdrive_csv_to_iceberg.yaml`
- `google_sheets_to_iceberg.yaml`
- `csv_employee_to_iceberg.yaml`
- `postgres_*_to_iceberg_markdown_kv.yaml`
- `mysql_*_to_iceberg_markdown_kv.yaml`

### 2. Engine Variant Tests

These tests verify alternative engine types for multi-engine connectors:

- **Airbyte engine**: Docker-based connectors
- **Native engine**: Python-based implementations

**Test Fixtures:**
- `gdrive_csv_airbyte_to_iceberg.yaml`
- `google_sheets_airbyte_to_iceberg.yaml`

**Expected Behavior:**
- Will fail if Docker unavailable (categorized as Docker error)
- Will fail if credentials unavailable (categorized as API error)
- Will pass if Docker and credentials available

### 3. Schema Validation Tests

These tests verify schema validation behavior:

- **Warn mode**: Logs warnings but continues
- **Strict mode**: Fails on validation errors

**Test Fixtures:**
- `csv_product_strict_validation.yaml` (strict mode with invalid data)

**Expected Behavior:**
- Strict mode: Job fails with validation error
- Warn mode: Job completes with warnings logged

### 4. State Persistence Tests

These tests verify incremental sync state management:

- **State file creation**: State written after first run
- **State file reading**: State read on subsequent runs
- **Incremental sync**: Only new/changed records processed

**Test Fixtures:**
- `csv_employee_state_persistence.yaml`
- `tests/test_state_persistence.sh` (dedicated test script)

**Expected Behavior:**
- First run: Processes all records, creates state file
- Second run: Reads state, skips unchanged files

### 5. Error Scenario Tests

These tests verify error handling:

- **Invalid credentials**: Authentication failures
- **Connection failures**: Network/database connection errors
- **Malformed data**: Data parsing errors

**Test Fixtures:**
- `hubspot_invalid_credentials.yaml`
- `postgres_connection_failure.yaml`
- `csv_malformed_data.yaml`

**Expected Behavior:**
- Jobs fail with appropriate error messages
- Errors are categorized correctly in smoke test script
- No unexpected crashes or hangs

### 6. Connector Role Tests

These tests verify bidirectional connector functionality:

- **Source role**: Reading from connectors
- **Target role**: Writing to connectors

**Test Fixtures:**
- `markdown_kv_source_to_iceberg.yaml` (markdown_kv as source)
- `iceberg_to_google_sheets.yaml` (google_sheets as target)

**Expected Behavior:**
- Source role: Data extracted correctly
- Target role: Data written correctly

## Expected Failures

The smoke test script categorizes expected failures:

1. **Database connection errors**: Expected if Postgres/MySQL not running
2. **API credential errors**: Expected if credentials not configured
3. **Docker errors**: Expected if Docker not available
4. **Strict validation errors**: Expected for error scenario tests
5. **Malformed data errors**: Expected for error scenario tests

These failures are counted separately and don't cause the test suite to fail.

## Adding New Tests

### 1. Create Job Fixture

Create a new YAML file in `tests/fixtures/jobs/`:

```yaml
tenant_id: test_tenant
environment: test

source_connector: your_connector
source_connector_path: connectors/your_connector.yaml

target_connector: iceberg
target_connector_path: connectors/iceberg.yaml

asset: your_asset
asset_path: assets/your_connector/v1.0/your_asset.yaml

source:
  # Your source configuration

target:
  # Your target configuration

logging:
  redaction: false
  level: INFO
```

### 2. Create Asset Definition (if needed)

Create asset definition in `assets/your_connector/v1.0/your_asset.yaml` following ODCS v3.0.2 schema.

### 3. Create Test Data (if needed)

Add test data files to `tests/fixtures/seeds/` directory.

### 4. Update Coverage Matrix

Update this document with your new test fixture.

### 5. Run Tests

```bash
# Run all smoke tests
./tests/smoke_tests.sh

# Run specific job
PYTHONPATH=src python -m dativo_ingest.cli run \
  --job-dir tests/fixtures/jobs \
  --secrets-dir tests/fixtures/secrets \
  --mode self_hosted \
  --job your_new_test.yaml
```

## Test Statistics

- **Total Job Fixtures**: 30+
- **Core Functionality Tests**: 15+
- **Engine Variant Tests**: 2
- **Error Scenario Tests**: 3
- **State Persistence Tests**: 1
- **Connector Role Tests**: 2
- **Custom Plugin Tests**: 5 (separate suite)

## Coverage Gaps

### Known Gaps

1. **Meltano engine**: Not explicitly tested (only implicit via postgres/mysql defaults)
2. **Singer engine**: Not tested at all
3. **Azure Blob connector**: No test fixtures
4. **S3/MinIO as source**: Only tested as targets
5. **Multiple objects in single job**: Not tested
6. **Full refresh mode**: Not explicitly tested
7. **Schema evolution**: Not tested

### Future Improvements

1. Add explicit Meltano engine tests
2. Add Singer engine tests (if supported)
3. Add Azure Blob connector tests
4. Add S3/MinIO source tests
5. Add multi-object job tests
6. Add full refresh mode tests
7. Add schema evolution tests

## Maintenance

### Regular Updates

- Update coverage matrix when adding new tests
- Verify all test fixtures are valid YAML
- Ensure test data files are available
- Check that expected failures are categorized correctly

### Troubleshooting

If a test fails unexpectedly:

1. Check job fixture YAML syntax
2. Verify asset definition exists and is valid
3. Check test data files are present
4. Verify environment variables are set
5. Check connector recipes are valid
6. Review error logs for details

## Related Documentation

- [Testing Strategy](tests/README.md)
- [Configuration Reference](docs/CONFIG_REFERENCE.md)
- [Ingestion Execution](docs/INGESTION_EXECUTION.md)
- [Custom Plugins](docs/CUSTOM_PLUGINS.md)

