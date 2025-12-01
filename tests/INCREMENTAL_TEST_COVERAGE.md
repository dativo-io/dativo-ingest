# Incremental Sync Test Coverage Analysis

## Current Test Coverage

### ✅ Existing Tests

1. **CSV Extractor** (`test_csv_extractor.py`)
   - ✅ `test_extract_with_incremental_disabled_by_default` - Tests default behavior
   - ✅ `test_extract_with_incremental_enabled` - Tests `file_modified_time` strategy
   - ❌ **Missing**: Tests for `cursor_field` strategy in CSV

2. **State Management** (`test_state.py`)
   - ✅ Tests for `IncrementalStateManager` (old API)
   - ❌ **Missing**: Tests for new unified strategy framework

3. **Integration Tests** (`test_state_persistence.sh`)
   - ✅ End-to-end state persistence test
   - ⚠️ Uses old API, may not test new unified framework

4. **Config Tests** (`test_config.py`)
   - ✅ Tests for incremental config merging
   - ✅ Tests for incremental strategy validation

### ❌ Missing Tests

#### 1. **Unified Strategy Framework Tests** (CRITICAL)
   - No tests for `IncrementalStrategy` base class
   - No tests for `FileModifiedTimeStrategy`
   - No tests for `CursorFieldStrategy`
   - No tests for `SpreadsheetModifiedTimeStrategy`
   - No tests for `IncrementalStrategyFactory`
   - No tests for `create_incremental_strategy()` helper

#### 2. **CSV Extractor - Cursor Field Strategy** (HIGH PRIORITY)
   - No tests for `cursor_field` strategy in CSV extractor
   - No tests for filtering records by cursor value
   - No tests for state updates with cursor values

#### 3. **Database Extractors - Incremental Sync** (HIGH PRIORITY)
   - No tests for Postgres extractor with `cursor_field` strategy
   - No tests for MySQL extractor with `cursor_field` strategy
   - No tests for SQL query building with cursor values
   - No tests for state updates after processing

#### 4. **Google Sheets/GDrive Extractors - Incremental Sync** (MEDIUM PRIORITY)
   - No tests for Google Sheets with `spreadsheet_modified_time` strategy
   - No tests for GDrive CSV with `file_modified_time` strategy
   - No tests for skipping unchanged spreadsheets/files

#### 5. **Integration Tests** (MEDIUM PRIORITY)
   - No integration tests for unified framework end-to-end
   - No tests for strategy auto-detection
   - No tests for strategy switching (file_modified_time → cursor_field)

## Recommended Test Suite

### Unit Tests Needed

#### `tests/test_incremental_strategies.py` (NEW)
```python
class TestFileModifiedTimeStrategy:
    - test_should_process_entity_no_state
    - test_should_process_entity_file_modified
    - test_should_process_entity_file_not_modified
    - test_filter_records_returns_all
    - test_update_state_with_modified_time
    - test_get_state_key

class TestCursorFieldStrategy:
    - test_should_process_entity_always_true
    - test_filter_records_no_state
    - test_filter_records_with_state
    - test_filter_records_missing_cursor_field
    - test_update_state_with_max_cursor
    - test_get_last_cursor_value
    - test_get_state_key

class TestSpreadsheetModifiedTimeStrategy:
    - test_should_process_entity_no_state
    - test_should_process_entity_spreadsheet_modified
    - test_filter_records_returns_all
    - test_update_state_with_modified_time

class TestIncrementalStrategyFactory:
    - test_create_file_modified_time_strategy
    - test_create_cursor_field_strategy
    - test_create_spreadsheet_modified_time_strategy
    - test_create_unsupported_strategy_raises_error
    - test_get_supported_strategies

class TestCreateIncrementalStrategy:
    - test_create_with_explicit_strategy
    - test_auto_detect_cursor_field
    - test_auto_detect_file_modified_time
    - test_create_without_state_path_returns_none
    - test_create_with_invalid_config_returns_none
```

#### `tests/test_csv_extractor_incremental.py` (NEW)
```python
class TestCSVExtractorCursorField:
    - test_extract_with_cursor_field_no_state
    - test_extract_with_cursor_field_with_state
    - test_extract_filters_records_by_cursor
    - test_extract_updates_state_with_max_cursor
    - test_extract_handles_missing_cursor_field
    - test_extract_multiple_files_different_cursors
```

#### `tests/test_postgres_extractor_incremental.py` (NEW)
```python
class TestPostgresExtractorIncremental:
    - test_extract_with_cursor_field_no_state
    - test_extract_with_cursor_field_with_state
    - test_build_query_with_cursor_value
    - test_build_query_without_cursor_value
    - test_extract_updates_state_after_processing
    - test_extract_handles_lookback_days
```

#### `tests/test_mysql_extractor_incremental.py` (NEW)
```python
class TestMySQLExtractorIncremental:
    - test_extract_with_cursor_field_no_state
    - test_extract_with_cursor_field_with_state
    - test_build_query_with_cursor_value
    - test_extract_updates_state_after_processing
```

#### `tests/test_google_sheets_extractor_incremental.py` (NEW)
```python
class TestGoogleSheetsExtractorIncremental:
    - test_extract_with_spreadsheet_modified_time_no_state
    - test_extract_skips_unchanged_spreadsheet
    - test_extract_processes_modified_spreadsheet
    - test_extract_updates_state_after_processing
```

#### `tests/test_gdrive_csv_extractor_incremental.py` (NEW)
```python
class TestGDriveCSVExtractorIncremental:
    - test_extract_with_file_modified_time_no_state
    - test_extract_skips_unchanged_file
    - test_extract_processes_modified_file
    - test_extract_updates_state_after_processing
```

### Integration Tests Needed

#### `tests/integration/test_incremental_e2e.py` (NEW)
```python
class TestIncrementalE2E:
    - test_csv_cursor_field_end_to_end
    - test_csv_file_modified_time_end_to_end
    - test_postgres_cursor_field_end_to_end
    - test_mysql_cursor_field_end_to_end
    - test_google_sheets_end_to_end
    - test_gdrive_csv_end_to_end
    - test_strategy_auto_detection
    - test_state_persistence_across_runs
```

### Smoke Tests Needed

Update existing smoke tests to verify:
- ✅ CSV with `cursor_field` strategy works
- ✅ Postgres/MySQL with `cursor_field` strategy works
- ✅ Google Sheets with `spreadsheet_modified_time` works
- ✅ GDrive CSV with `file_modified_time` works
- ✅ State files are created and updated correctly

## Test Coverage Goals

### Unit Tests
- **Target**: 90%+ coverage for `src/dativo_ingest/incremental/`
- **Target**: 80%+ coverage for incremental logic in extractors

### Integration Tests
- **Target**: All strategies tested end-to-end
- **Target**: All extractors tested with incremental sync

### Smoke Tests
- **Target**: At least one smoke test per strategy type
- **Target**: Verify state persistence works correctly

## Priority Order

1. **CRITICAL**: Create `test_incremental_strategies.py` - Test the unified framework
2. **HIGH**: Add cursor_field tests to CSV extractor
3. **HIGH**: Add incremental tests to Postgres/MySQL extractors
4. **MEDIUM**: Add incremental tests to Google Sheets/GDrive extractors
5. **MEDIUM**: Create integration tests for end-to-end scenarios
6. **LOW**: Update smoke tests to cover new strategies

## Estimated Effort

- Unit tests for strategies: ~4-6 hours
- Unit tests for extractors: ~6-8 hours
- Integration tests: ~4-6 hours
- Smoke test updates: ~2-3 hours
- **Total**: ~16-23 hours

