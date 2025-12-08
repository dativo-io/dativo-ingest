# WAL (Write-Ahead Log) / Checkpointing Architecture

> **Note**: This document provides detailed technical documentation for WAL checkpointing. For configuration reference, see [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md). For execution flow details, see [INGESTION_EXECUTION.md](INGESTION_EXECUTION.md).

## Overview

The WAL (Write-Ahead Log) / checkpointing system enables jobs to resume extraction within a single run at page/offset/chunk boundaries. This complements the existing incremental state mechanism, which tracks cross-run logical cursors (e.g., `last_updated_at`).

## Two-Layer State Architecture

### 1. Incremental State (Cross-Run)
- **Purpose**: Track logical cursors across job runs
- **Scope**: High-water marks (e.g., `last_updated_at`, `last_created`)
- **Persistence**: JSON files in state directory
- **Update Frequency**: Only after successful Iceberg/Nessie commit
- **Lifecycle**: Persists across runs, updated on success

### 2. WAL / Checkpoints (Intra-Run)
- **Purpose**: Enable resume within a single run
- **Scope**: Page numbers, offsets, chunk boundaries, record counts
- **Persistence**: JSON files in WAL directory (separate from state)
- **Update Frequency**: After each chunk/page/batch processed
- **Lifecycle**: Created at job start, updated during extraction, finalized/removed on success

## Design Principles

1. **Separation of Concerns**: WAL and incremental state are independent
2. **Idempotency**: WAL must not break idempotency guarantees
3. **Atomic Commits**: WAL never exposes partial data (Iceberg/Nessie rules apply)
4. **Backward Compatibility**: All changes are opt-in via configuration
5. **Extractor Agnostic**: Works with native, Airbyte, and Meltano/Singer extractors

## WAL Manager Architecture

### Core Components

```
WALManager
├── create_wal()          # Initialize WAL file for job run
├── load_wal()            # Load existing WAL if resuming
├── update_checkpoint()   # Record progress after chunk/page
├── finalize_wal()        # Mark WAL as complete (on success)
├── cleanup_wal()         # Remove WAL file (after finalization)
└── get_resume_point()    # Extract checkpoint for extractor
```

### WAL File Structure

**Location**: `{wal_base_dir}/{tenant_id}/{job_name}/{run_id}.wal.json`

**Format**: JSON with flexible schema per connector type

```json
{
  "version": "1.0",
  "job_name": "stripe_customers",
  "tenant_id": "acme",
  "run_id": "2024-01-15T10:30:00",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:35:00Z",
  "status": "in_progress",
  "checkpoints": {
    "stream_name": {
      "type": "page_based",
      "last_page": 42,
      "last_offset": 1000,
      "records_processed": 42000,
      "last_checkpoint_time": "2024-01-15T10:35:00Z"
    }
  },
  "metadata": {
    "extractor_type": "airbyte",
    "connector_type": "stripe"
  }
}
```

### Checkpoint Types

Different extractors use different checkpoint strategies:

1. **Page-Based**: For paginated APIs (Stripe, HubSpot)
   ```json
   {
     "type": "page_based",
     "last_page": 42,
     "last_offset": 1000
   }
   ```

2. **Offset-Based**: For database queries with LIMIT/OFFSET
   ```json
   {
     "type": "offset_based",
     "last_offset": 50000,
     "last_id": "abc123"
   }
   ```

3. **Chunk-Based**: For file-based extractors (CSV)
   ```json
   {
     "type": "chunk_based",
     "file_id": "file_123",
     "chunk_number": 15,
     "records_in_chunk": 10000
   }
   ```

4. **State-Based**: For Airbyte/Meltano (STATE messages)
   ```json
   {
     "type": "state_based",
     "airbyte_state": {
       "streams": [
         {
           "stream_descriptor": {"name": "customers"},
           "stream_state": {"created": 1705315200}
         }
       ]
     }
   }
   ```

## Integration Points

### Job Executor Flow

```
1. Job Start
   ├── Load incremental state (existing)
   ├── Check for existing WAL (resume scenario)
   └── Create new WAL if no resume point

2. Extraction Loop
   ├── Pass checkpoint context to extractor
   ├── Extractor resumes from checkpoint (if present)
   ├── Process chunk/page/batch
   ├── Update WAL checkpoint after each chunk
   └── Continue until complete

3. Success Path
   ├── Finalize WAL (mark as complete)
   ├── Update incremental state (existing)
   ├── Commit to Iceberg/Nessie (atomic)
   └── Cleanup WAL file

4. Failure Path
   ├── WAL remains (for next retry)
   ├── Incremental state unchanged
   └── Next retry loads WAL and resumes
```

### Extractor Interface

All extractors receive checkpoint context:

```python
def extract(
    self,
    state_manager: Optional[IncrementalStateManager] = None,
    checkpoint_context: Optional[Dict[str, Any]] = None
) -> Iterator[List[Dict[str, Any]]]:
    # checkpoint_context contains:
    # - checkpoint data from WAL
    # - resume instructions
    # - metadata about last processed point
```

## Configuration

### Job Configuration

WAL is opt-in and configured in the job's source configuration:

```yaml
tenant_id: acme
source_connector_path: connectors/examples/stripe.yaml
target_connector_path: connectors/examples/iceberg.yaml
asset_path: assets/examples/stripe/v1.0/customers.yaml

source:
  type: stripe
  object: customers
  incremental:
    enabled: true
    strategy: created
    cursor_field: created
  wal:
    enabled: true  # Opt-in to WAL
    base_dir: "/app/wal"  # Optional, defaults to /app/wal
    run_id: "2024-01-15T10:30:00"  # Optional, auto-generated if not provided
```

**Configuration Options:**
- `enabled`: Boolean to enable/disable WAL (default: false)
- `base_dir`: Base directory for WAL files (default: `/app/wal`)
- `run_id`: Optional run ID for WAL file naming (default: timestamp-based)

### Connector Capabilities

Connectors can declare WAL support in their recipe files (optional metadata):

```yaml
# connectors/examples/stripe.yaml
connector:
  name: stripe
  type: stripe
  roles: [source]
  default_engine:
    type: airbyte
    options:
      airbyte:
        docker_image: airbyte/source-stripe:2.1.5
  # WAL metadata (informational, not required)
  # wal_checkpoint_type: state_based  # For Airbyte connectors
  # wal_resume_strategy: skip_processed
```

**Checkpoint Types:**
- `chunk_based`: For file-based extractors (CSV)
- `offset_based`: For database extractors (Postgres, MySQL)
- `page_based`: For paginated API extractors (Stripe, HubSpot)
- `state_based`: For Airbyte/Meltano extractors (STATE messages)

## Extractor-Specific Integration

### Native Extractors (CSV, Postgres, MySQL, Google Sheets, GDrive CSV)

All native extractors support WAL checkpointing:

1. **CSV Extractor**: Chunk-based checkpoints
   - Resumes from last processed chunk
   - Updates checkpoint after each chunk

2. **Postgres Extractor**: Offset-based checkpoints
   - Resumes using cursor scroll to last offset
   - Updates checkpoint after each batch

3. **MySQL Extractor**: Offset-based checkpoints
   - Similar to Postgres, uses offset-based resume
   - Updates checkpoint after each batch

4. **Google Sheets Extractor**: Spreadsheet-based checkpoints
   - Tracks which spreadsheets have been processed
   - Updates checkpoint after processing each spreadsheet

5. **GDrive CSV Extractor**: Chunk-based checkpoints
   - Similar to CSV extractor, chunk-based resume
   - Updates checkpoint after each chunk

**Resume Logic**: All extractors skip already processed chunks/pages/offsets
**Checkpoint Updates**: After each chunk/page/batch
**State Interaction**: WAL checkpoints complement incremental state

Example (CSV):
```python
# Load WAL checkpoint
checkpoint = checkpoint_context.get("checkpoint") if checkpoint_context else None

if checkpoint and checkpoint.get("type") == "chunk_based":
    # Skip to last processed chunk
    start_chunk = checkpoint.get("chunk_number", 0) + 1
    # Fast-forward file reader to start_chunk
```

### Airbyte Extractors

1. **STATE Messages**: Map Airbyte STATE to/from WAL
2. **Initial State**: Inject incremental state + WAL checkpoint into Airbyte
3. **State Merging**: Merge Airbyte-emitted state with WAL

Flow:
```
1. Load incremental state (last_created timestamp)
2. Load WAL checkpoint (if resuming)
3. Build Airbyte STATE message combining both
4. Pass STATE to Airbyte container
5. Capture STATE messages from Airbyte output
6. Update WAL with latest STATE
```

### Meltano/Singer Extractors

Similar to Airbyte, using Singer STATE format.

## Behavior & Guarantees

### Resume Behavior

- **Skip Processed**: Default behavior - skip chunks/pages already in WAL
- **Rewind & Reprocess**: Optional - reprocess from checkpoint (for validation)

### Idempotency

- WAL checkpoints are advisory only
- Incremental state is authoritative for cross-run deduplication
- WAL reduces reprocessing but doesn't change logical semantics

### Atomicity

- WAL updates are frequent (per chunk)
- Incremental state updates only on successful commit
- Iceberg/Nessie commits remain atomic
- No partial data exposure

### Failure Handling

- **Mid-Extraction Failure**: WAL persists, next retry resumes
- **Post-Extraction Failure**: WAL persists, but incremental state unchanged
- **Post-Commit Failure**: WAL cleaned up, incremental state updated

## File Layout

```
/app/
├── state/                    # Incremental state (existing)
│   └── {tenant_id}/
│       └── {job_name}.json
└── wal/                      # WAL files (new)
    └── {tenant_id}/
        └── {job_name}/
            └── {run_id}.wal.json      # WAL file (status: "in_progress" or "completed")
```

## Performance Considerations

1. **WAL Update Frequency**: Configurable (default: per chunk/page)
2. **WAL File Size**: Small JSON files, minimal I/O overhead
3. **Resume Overhead**: Minimal - just skip to checkpoint
4. **Storage**: WAL files are temporary, cleaned up on success

## Migration & Backward Compatibility

- WAL is **opt-in** via `source.wal.enabled: true`
- Jobs without WAL config work exactly as before
- Existing incremental state mechanism unchanged
- Connectors without WAL support fall back to full extraction

## Testing Strategy

Comprehensive test coverage includes:

1. **Unit Tests** (`tests/test_wal_manager.py`): 
   - WAL Manager operations (create, load, update, finalize, cleanup)
   - Checkpoint management
   - Resume detection
   - Multiple checkpoint types
   - **13 test cases**

2. **Integration Tests** (`tests/integration/test_wal_integration.py`):
   - WAL with CSV extractor (chunk-based resume)
   - WAL with Postgres extractor (offset-based resume)
   - WAL with MySQL extractor (offset-based resume)
   - WAL with GDrive CSV extractor (chunk-based resume)
   - WAL with Google Sheets extractor (spreadsheet-based resume)
   - WAL with Airbyte extractor (STATE message mapping)
   - Failure scenarios and resume behavior
   - WAL finalization and cleanup
   - **8 test cases**

3. **Infrastructure Tests** (`tests/test_wal_infrastructure.py`):
   - WAL directory creation and permissions
   - File permissions and atomic writes
   - Concurrent access scenarios
   - Multi-tenant and multi-job support
   - Large checkpoint data handling
   - WAL persistence after failures
   - WAL cleanup after success
   - **11 test cases**

4. **Smoke Tests** (`tests/smoke_tests_wal.sh`):
   - End-to-end WAL functionality with real job execution
   - WAL file creation verification
   - Checkpoint update verification
   - Resume scenario testing
   - WAL directory structure validation
   - WAL finalization verification

**Test Execution:**
```bash
# Run all WAL tests
pytest tests/test_wal_manager.py tests/integration/test_wal_integration.py tests/test_wal_infrastructure.py -v

# Run smoke tests
./tests/smoke_tests_wal.sh
```

**Total Test Coverage:**
- **32 test cases** across unit, integration, and infrastructure tests
- All extractors support checkpoint_context parameter
- All extractors update WAL checkpoints during extraction
- Resume scenarios for all checkpoint types
- State interaction (WAL + incremental state)
- Infrastructure robustness (permissions, concurrency, multi-tenancy)

## Usage Examples

### Example 1: CSV Extractor with WAL

```yaml
# Job configuration
tenant_id: test_tenant
source_connector_path: connectors/examples/csv.yaml
target_connector_path: connectors/examples/iceberg.yaml
asset_path: assets/examples/csv/v1.0/employees.yaml

source:
  type: csv
  files:
    - path: /data/employees.csv
      id: employees_file
  wal:
    enabled: true
```

**Resume Behavior:**
- If job fails after processing chunk 5, WAL contains `chunk_number: 5`
- On retry, CSV extractor skips first 5 chunks and resumes from chunk 6
- Reduces reprocessing time for large files

### Example 2: Postgres Extractor with WAL

```yaml
source:
  type: postgres
  tables:
    - name: public.orders
      object: orders
  incremental:
    enabled: true
    cursor_field: updated_at
  wal:
    enabled: true
```

**Resume Behavior:**
- If job fails after processing 50,000 records, WAL contains `last_offset: 50000`
- On retry, Postgres extractor uses `cursor.scroll(50000)` to skip to offset
- Avoids re-reading already processed records

### Example 3: Airbyte Extractor with WAL

```yaml
source:
  type: stripe
  object: customers
  incremental:
    enabled: true
    cursor_field: created
  wal:
    enabled: true
```

**Resume Behavior:**
- WAL stores Airbyte STATE messages from previous run
- On retry, STATE is injected into Airbyte container via `--state` flag
- Airbyte connector resumes from last checkpoint automatically
- STATE messages are captured and stored in WAL during extraction

## Troubleshooting

### WAL File Not Found on Resume

If a job fails and WAL file is missing on retry:
- Check WAL directory permissions: `/app/wal/{tenant_id}/{job_name}/`
- Verify `run_id` matches between runs (or use auto-detection)
- Check logs for WAL initialization errors

### Checkpoint Not Updating

If checkpoints aren't updating during extraction:
- Verify WAL is enabled in source config: `source.wal.enabled: true`
- Check extractor supports checkpoint updates (native extractors do)
- Review logs for checkpoint update messages

### WAL Cleanup Issues

If WAL files persist after successful runs:
- Verify job completes successfully (exit code 0)
- Check that `wal_manager.cleanup_wal()` is called after commit
- Review logs for cleanup errors

## Implementation Status

### Connector Support

All connectors support WAL checkpointing:

**Native Extractors:**
- ✅ CSV Extractor - Chunk-based checkpoints
- ✅ Postgres Extractor - Offset-based checkpoints
- ✅ MySQL Extractor - Offset-based checkpoints
- ✅ Google Sheets Extractor - Spreadsheet-based checkpoints
- ✅ GDrive CSV Extractor - Chunk-based checkpoints

**Engine-Based Extractors:**
- ✅ Airbyte Extractor - STATE message mapping
- ✅ HubSpot Extractor - Inherits from AirbyteExtractor
- ✅ Stripe Extractor - Inherits from AirbyteExtractor

**Custom Plugins:**
- ✅ All BaseReader implementations accept `checkpoint_context` parameter
- ✅ Sandboxed wrappers pass checkpoint context through

### Test Coverage

Comprehensive test coverage across three categories:

- **Unit Tests**: 13 test cases covering WAL Manager operations
- **Integration Tests**: 8 test cases for extractor integration
- **Infrastructure Tests**: 11 test cases for file system robustness
- **Smoke Tests**: End-to-end validation scenarios

All 32 test cases passing. See [SETUP_AND_TESTING.md](SETUP_AND_TESTING.md#wal-testing) for details.

### Files Modified

**Core Implementation:**
- `src/dativo_ingest/wal_manager.py` (new)
- `src/dativo_ingest/config.py` (added `wal` field to SourceConfig)
- `src/dativo_ingest/job_executor.py` (WAL integration)

**Extractor Updates:**
- All native extractors updated with checkpoint support
- Engine framework updated for Airbyte STATE mapping
- Plugin base classes updated for checkpoint context

## Future Enhancements

1. **Distributed WAL**: For multi-worker scenarios
2. **WAL Compression**: For large checkpoint payloads
3. **WAL Retention**: Configurable retention policies
4. **Metrics**: WAL resume statistics, reprocessing reduction
5. **Checkpoint Validation**: Verify checkpoint consistency before resume

