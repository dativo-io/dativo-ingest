# Run Summary Artifacts

Dativo-Ingest generates a structured JSON summary after each job execution. These summaries enable FinOps, catalog sync, debugging, and auditability.

## Location

The summary artifacts are stored in the state directory:

```
state/<tenant>/<job>/runs/run-<timestamp>.json
```

Where:
- `state` is the configured state directory (defaults to `.local/state`).
- `<tenant>` is the tenant ID.
- `<job>` is the job name (asset name).
- `<timestamp>` is the run start time in `YYYYMMDD-HHMMSS` format (UTC).

## Format

The summary is a JSON file containing the following sections:

- **Run Metadata**: ID, timestamps, duration, status.
- **Asset Info**: Asset ID, name, version.
- **Connector Info**: Source and target types.
- **Metrics**: Record counts, file counts, byte counts.
- **Commit Info**: Iceberg commit details (if applicable).
- **Error Info**: Error details if the run failed.
- **Context**: Run type, environment, trigger source.
- **Watermark**: Incremental state (if applicable).
- **Resource Usage**: CPU/Memory usage and cost estimates (if available).

### Example

```json
{
  "tenant_id": "acme",
  "job_name": "customers",
  "run_id": "20240101T120000Z",
  "start_time": "2024-01-01T12:00:00Z",
  "end_time": "2024-01-01T12:05:30Z",
  "duration_seconds": 330.5,
  "status": "success",
  "exit_code": 0,
  "asset": {
    "id": "urn:dativo:asset:customers",
    "name": "customers",
    "version": "1.0.0"
  },
  "connector": {
    "source_type": "mysql",
    "target_type": "iceberg"
  },
  "context": {
    "run_type": "incremental",
    "environment": "prod",
    "triggered_by": "orchestrated"
  },
  "metrics": {
    "records_extracted": 50000,
    "records_written": 49950,
    "records_invalid": 50,
    "files_written": 5,
    "bytes_written": 10485760,
    "retries": 0
  },
  "watermark": {
    "customers.updated_at": {
        "last_value": "2024-01-01T12:00:00Z",
        "updated_at": "2024-01-01T12:05:00Z"
    }
  },
  "resource_usage": {
    "cpu_seconds": null,
    "memory_mb": null,
    "cost_estimate": null
  },
  "commit": {
    "commit_id": "834758934758934",
    "files_added": 5,
    "table_name": "acme.customers",
    "branch": "main",
    "partition_stats": {
        "summary": "..."
    }
  },
  "error": null,
  "metadata": {}
}
```

## Error Handling

If a run fails, the `status` field will be `failure` (or `partial`), and the `error` object will contain details:

```json
{
  "status": "failure",
  "error": {
    "has_errors": true,
    "error_message": "Failed to connect to source database",
    "error_type": "ConnectionError"
  }
}
```

## Usage

These artifacts can be consumed by:
1. **FinOps Dashboards**: To calculate cost per job/tenant based on `bytes_written` and duration.
2. **Audit Logs**: To track data lineage and job success rates.
3. **Debugging**: To quickly identify why a job failed without parsing raw logs.
