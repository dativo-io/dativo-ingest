# Run Summary Artifacts (Ingestion Facts Envelope)

Dativo-Ingest generates a structured JSON summary after each job execution. These summaries enable FinOps, catalog sync, debugging, and auditability.

**This artifact is a stable external-facing contract.**

## Core Principles

*   **Observed Facts Only**: Contains ingestion facts only. Interpretation, quality judgements, and semantic meaning are out of scope.
*   **Immutable**: Written once per run. Never mutated. Corrections happen via new runs.
*   **Mechanical Domains**: Fields are grouped by mechanical responsibility.
*   **Forward Compatible**: Includes placeholders for future features like replay (v1.2).

## Location

The summary artifacts are stored in the state directory:

```
state/<tenant>/<job>/runs/run-<timestamp>.json
```

## Format

The summary is a JSON file structured by domain:

### Example

```json
{
  "run": {
    "id": "20240101T120000Z",
    "type": "incremental",
    "start_time": "2024-01-01T12:00:00Z",
    "end_time": "2024-01-01T12:05:30Z",
    "tenant_id": "acme",
    "job_name": "customers",
    "environment": "prod",
    "triggered_by": "orchestrated",
    "replay_reason": null
  },
  "ingestion": {
    "status": "success",
    "duration_seconds": 330.5,
    "exit_code": 0,
    "error": null
  },
  "volume": {
    "records_extracted": 50000,
    "records_written": 49950,
    "records_invalid": 50,
    "files_written": 5,
    "bytes_written": 10485760,
    "retries": 0
  },
  "time": {
    "event_time_field": "updated_at",
    "watermark": {
        "customers.updated_at": {
            "last_value": "2024-01-01T12:00:00Z"
        }
    },
    "replay_range_start": null,
    "replay_range_end": null
  },
  "schema": {
    "version": "1.0.0",
    "enforcement_mode": "strict"
  },
  "storage": {
    "format": "parquet",
    "target_type": "iceberg",
    "commit_id": "834758934758934",
    "files_added": 5,
    "branch": "main",
    "partition_stats": {
        "summary": "..."
    }
  },
  "resources": {
    "cpu_seconds": null,
    "memory_mb": null,
    "api_calls": null
  },
  "cost": {
    "estimated_usd": null
  },
  "asset": {
    "id": "urn:dativo:asset:customers",
    "name": "customers",
    "version": "1.0.0"
  },
  "metadata": {}
}
```

## Field Groups

| Group | Description |
| :--- | :--- |
| **run** | Identity and timing of the execution (ID, type, start/end). |
| **ingestion** | Operational status and outcome (success/failure, duration). |
| **volume** | Quantifiable data volume metrics (records, bytes, files). |
| **time** | Temporal context (watermarks, event time fields, replay ranges). |
| **schema** | Schema version and enforcement applied. |
| **storage** | Output storage details (format, commit IDs, location). |
| **resources** | Computational resources consumed (CPU, memory). |
| **cost** | Financial impact estimates. |
| **asset** | Identification of the asset being ingested. |

## Error Handling

If a run fails, the `ingestion.status` will be `failure` (or `partial`), and `ingestion.error` will contain details:

```json
"ingestion": {
  "status": "failure",
  "error": {
    "has_errors": true,
    "error_message": "Failed to connect to source database",
    "error_type": "ConnectionError"
  }
}
```
