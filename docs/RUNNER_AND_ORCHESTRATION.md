# Runner and Orchestration Guide

This guide describes how the dativo-ingest Docker image runs jobs in two execution modes: **orchestrated** (Dagster) and **oneshot**.

## Table of Contents

1. [Overview](#overview)
2. [Execution Modes](#execution-modes)
3. [Runner Configuration](#runner-configuration)
4. [Logging and Exit Codes](#logging-and-exit-codes)
5. [Docker Deployment](#docker-deployment)
6. [Additional Resources](#additional-resources)

---

## Overview

Dativo-ingest supports two execution modes:

1. **Orchestrated Mode**: Long-running service with Dagster orchestrator for scheduled jobs
2. **Oneshot Mode**: Single job execution that exits after completion

Both modes use the same Docker image and configuration structure, but differ in how jobs are triggered and managed.

---

## Execution Modes

### Orchestrated Mode (Default)

Orchestrated mode bundles a lightweight Dagster instance that:
- Reads job schedules from `runner.yaml`
- Executes jobs on cron schedules
- Ensures **serial per-tenant** execution to avoid Nessie commit conflicts
- Provides a web UI for monitoring (default port: 3000)

**Key Features:**
- Scheduled execution via cron expressions
- Tenant-level serialization (one job per tenant at a time)
- Automatic retries on failure
- Web UI for job monitoring

### Oneshot Mode

Oneshot mode runs a single job and exits:
- Executes one job configuration
- No scheduling or orchestration
- Ideal for manual runs, testing, and CI/CD pipelines
- Returns exit code based on job result

**Use Cases:**
- Manual job execution
- Testing and development
- CI/CD pipeline integration
- One-time data migrations

---

## Runner Configuration

### Runner Configuration File

The `runner.yaml` file defines schedules and orchestration settings:

```yaml
runner:
  mode: orchestrated
  orchestrator:
    type: dagster
    schedules:
      - name: stripe_customers_hourly
        config: /app/jobs/acme/stripe_customers_to_iceberg.yaml
        cron: "0 * * * *"  # Every hour at minute 0
      - name: hubspot_contacts_daily
        config: /app/jobs/acme/hubspot_contacts_to_iceberg.yaml
        cron: "15 2 * * *"  # Daily at 2:15 AM
    concurrency_per_tenant: 1  # Serial execution per tenant
```

### Configuration Fields

**Required:**
- `mode`: Execution mode (`orchestrated` or `oneshot`)
- `orchestrator.type`: Orchestrator type (currently `dagster`)
- `schedules`: List of scheduled jobs

**Optional:**
- `concurrency_per_tenant`: Maximum concurrent jobs per tenant (default: 1)
- `retry_config`: Retry configuration for failed jobs

### Cron Expression Format

Cron expressions use standard 5-field format:
```
┌───────────── minute (0 - 59)
│ ┌───────────── hour (0 - 23)
│ │ ┌───────────── day of month (1 - 31)
│ │ │ ┌───────────── month (1 - 12)
│ │ │ │ ┌───────────── day of week (0 - 6) (Sunday to Saturday)
│ │ │ │ │
* * * * *
```

**Examples:**
- `"0 * * * *"` - Every hour at minute 0
- `"15 2 * * *"` - Daily at 2:15 AM
- `"0 0 * * 0"` - Weekly on Sunday at midnight
- `"*/15 * * * *"` - Every 15 minutes

---

## Logging and Exit Codes

### Structured JSON Logging

All execution modes use structured JSON logging:
- Logs include event types, tenant IDs, and job context
- Secret redaction enabled when `logging.redaction: true` in job config
- Logs can be consumed by log aggregation systems (ELK, Splunk, etc.)

**Log Event Types:**
- `job_started`: Job execution begins
- `job_finished`: Job execution completes
- `job_error`: Job execution fails
- `tenant_inferred`: Tenant ID determined
- `secrets_loaded`: Secrets loaded successfully
- `infra_validated`: Infrastructure validation complete

### Exit Codes

- **0**: Success - all records processed successfully
- **1**: Partial success - some records had errors (warn mode)
- **2**: Failure - job failed (validation errors in strict mode, or other errors)

---

## Docker Deployment

### Orchestrated Mode

Start the orchestrator service:

```bash
docker run --rm -p 3000:3000 \
  -v $(pwd)/connectors:/app/connectors:ro \
  -v $(pwd)/assets:/app/assets:ro \
  -v $(pwd)/jobs:/app/jobs \
  -v $(pwd)/configs:/app/configs \
  -v $(pwd)/secrets:/app/secrets \
  -v $(pwd)/state:/app/state \
  dativo:1.1.0 start orchestrated --runner-config /app/configs/runner.yaml
```

**Access Web UI:**
- URL: `http://localhost:3000`
- View job schedules, execution history, and logs

### Oneshot Mode

Run a single job:

```bash
docker run --rm \
  -v $(pwd)/connectors:/app/connectors:ro \
  -v $(pwd)/assets:/app/assets:ro \
  -v $(pwd)/jobs:/app/jobs \
  -v $(pwd)/configs:/app/configs \
  -v $(pwd)/secrets:/app/secrets \
  -v $(pwd)/state:/app/state \
  dativo:1.1.0 run --config /app/jobs/acme/stripe_customers_to_iceberg.yaml --mode self_hosted
```

**Volume Mounts:**
- `connectors`: Connector recipes (read-only)
- `assets`: Asset definitions (read-only)
- `jobs`: Job configurations
- `configs`: Runner and policy configurations
- `secrets`: Secrets storage (tenant-organized)
- `state`: Incremental sync state (per tenant)

---

---

## Enhanced Features (v1.3.0+)

### Retry Policies

Retry policies provide intelligent retry with exponential backoff for failed jobs.

#### Configuration

Retry policies are configured in job configuration files:

```yaml
retry_config:
  max_retries: 3                    # Maximum number of retry attempts
  initial_delay_seconds: 5          # Initial delay before first retry
  max_delay_seconds: 300            # Maximum delay between retries (5 minutes)
  backoff_multiplier: 2.0           # Exponential backoff multiplier
  retryable_exit_codes: [1, 2]      # Exit codes that trigger retries
  retryable_error_patterns:         # Regex patterns for error messages (optional)
    - "ConnectionError"
    - "TimeoutError"
    - "Rate limit exceeded"
```

#### Retry Behavior

- **Exit Code 0**: Success - no retry
- **Exit Code 1**: Partial success - retryable (if configured)
- **Exit Code 2**: Failure - retryable (if configured)

Retries use exponential backoff:
- Attempt 1: Wait `initial_delay_seconds`
- Attempt 2: Wait `initial_delay_seconds * backoff_multiplier`
- Attempt 3: Wait `initial_delay_seconds * backoff_multiplier^2`
- ... capped at `max_delay_seconds`

#### Example

```yaml
tenant_id: acme
source_connector: stripe
target_connector: iceberg
asset: stripe_customers

retry_config:
  max_retries: 3
  initial_delay_seconds: 10
  max_delay_seconds: 60
  backoff_multiplier: 2.0
  retryable_exit_codes: [1, 2]
  retryable_error_patterns:
    - "API rate limit"
    - "Connection timeout"
```

### Enhanced Schedule Management

Schedules support additional features for production use:

#### Schedule Configuration

Schedules can be configured with cron expressions or intervals:

```yaml
runner:
  orchestrator:
    schedules:
      # Cron-based schedule
      - name: stripe_customers_hourly
        config: /app/jobs/acme/stripe_customers_to_iceberg.yaml
        cron: "0 * * * *"           # Every hour
        enabled: true                # Enable/disable without deployment
        timezone: "UTC"              # Timezone for execution
        max_concurrent_runs: 1       # Max concurrent runs
        tags:                        # Custom tags
          environment: "production"
      
      # Interval-based schedule
      - name: hubspot_contacts_daily
        config: /app/jobs/acme/hubspot_contacts_to_iceberg.yaml
        interval_seconds: 21600      # Every 6 hours
        enabled: true
        timezone: "America/New_York"
      
      # Disabled schedule
      - name: maintenance_job
        config: /app/jobs/acme/maintenance.yaml
        cron: "0 2 * * *"
        enabled: false               # Won't run until enabled
```

#### Schedule Features

- **Enable/Disable**: Set `enabled: false` to disable a schedule without removing it
- **Timezone Support**: Specify timezone for schedule execution (e.g., "America/New_York", "UTC")
- **Interval Scheduling**: Use `interval_seconds` as an alternative to cron expressions
- **Concurrency Control**: Set `max_concurrent_runs` to limit parallel executions
- **Custom Tags**: Add tags for filtering and organization

### Tenant Isolation

#### Tenant Tagging

All assets and jobs are automatically tagged with tenant information:

- `tenant`: Tenant ID (e.g., "acme")
- `job_name`: Schedule name
- `connector_type`: Source connector type

Custom tags from schedule configuration are also included.

#### Concurrency Control

Tenant-level serialization ensures only one job runs per tenant at a time:

```yaml
runner:
  orchestrator:
    concurrency_per_tenant: 1  # Only one job per tenant concurrently
```

This prevents Nessie commit conflicts and ensures data consistency.

### Observability

#### Metrics Collection

Metrics are automatically collected and emitted as structured log events:

- **Extraction Metrics**: Records extracted, files processed
- **Validation Metrics**: Valid/invalid records, validation rate
- **Writing Metrics**: Files written, bytes written, file sizes
- **API Call Metrics**: API calls made (for API connectors)
- **Error Metrics**: Error types and counts
- **Retry Metrics**: Retry attempts and exit codes
- **Execution Metrics**: Execution time, records per second

#### Metrics Example

```json
{
  "event_type": "metrics_complete",
  "job_name": "stripe_customers_hourly",
  "tenant_id": "acme",
  "status": "success",
  "execution_time_seconds": 45.2,
  "records_extracted": 1000,
  "records_valid": 995,
  "records_invalid": 5,
  "files_written": 2,
  "total_bytes": 52428800,
  "records_per_second": 22.1
}
```

#### Distributed Tracing

Basic OpenTelemetry tracing support is available (optional):

```python
from dativo_ingest.tracing import trace_job_execution, trace_phase

with trace_job_execution("stripe_customers", "acme", "stripe"):
    with trace_phase("extract"):
        # Extraction logic
        pass
    with trace_phase("validate"):
        # Validation logic
        pass
```

**Note**: OpenTelemetry is optional. If not installed, tracing is gracefully disabled.

#### Enhanced Metadata

Dagster assets emit enhanced metadata:

- `tenant_id`: Tenant identifier
- `connector_type`: Source connector type
- `execution_time_seconds`: Job execution time
- `status`: Job status (success, partial, failure)

Metadata is visible in the Dagster UI for monitoring and debugging.

---

## Troubleshooting

### Retries Not Working

1. **Check retry configuration**: Ensure `retry_config` is present in job config
2. **Verify exit codes**: Check that exit code is in `retryable_exit_codes`
3. **Check error patterns**: If using `retryable_error_patterns`, verify regex matches
4. **Review logs**: Look for `retry_attempt` events in logs

### Schedules Not Running

1. **Check enabled status**: Verify `enabled: true` in schedule config
2. **Validate cron/interval**: Ensure either `cron` or `interval_seconds` is set
3. **Check timezone**: Verify timezone is correct for your schedule
4. **Review Dagster logs**: Check orchestrator logs for schedule registration

### Tenant Isolation Issues

1. **Verify tenant tags**: Check that tenant_id is correctly set in job config
2. **Check concurrency**: Ensure `concurrency_per_tenant` is set appropriately
3. **Review run queue**: Check Dagster UI for run queue status

### Metrics Not Appearing

1. **Check logging level**: Ensure logging level is INFO or lower
2. **Verify event types**: Look for `metrics_*` events in logs
3. **Check structured logging**: Ensure JSON logging is enabled

---

## Best Practices

### Retry Configuration

- Set `max_retries` based on error recovery time
- Use `retryable_error_patterns` for transient errors only
- Adjust `backoff_multiplier` based on API rate limits
- Set `max_delay_seconds` to prevent excessive wait times

### Schedule Management

- Use cron for time-based schedules (e.g., daily at 2 AM)
- Use intervals for frequency-based schedules (e.g., every 6 hours)
- Set `enabled: false` for maintenance windows
- Use timezones consistently across schedules

### Observability

- Monitor `execution_time_seconds` for performance issues
- Track `records_per_second` for throughput monitoring
- Alert on high `retry_count` values
- Use tags for filtering and organization

---

## Migration from v1.2.0

### Backward Compatibility

- Existing `runner.yaml` files remain compatible
- Retry configuration is optional (defaults to no retries)
- Schedule `enabled` field defaults to `true`
- Cron-only schedules continue to work

### Upgrading

1. **Add retry configs** (optional): Add `retry_config` to job configs that need retries
2. **Update schedules** (optional): Add `enabled`, `timezone`, `tags` to schedules
3. **Test thoroughly**: Verify schedules and retries work as expected

---

## Additional Resources

- [SETUP_AND_ONBOARDING.md](SETUP_AND_ONBOARDING.md) - Comprehensive setup and onboarding guide
- [INGESTION_EXECUTION.md](INGESTION_EXECUTION.md) - Execution flow documentation
- [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) - Configuration reference
- [README.md](../README.md) - Project overview and quick start
