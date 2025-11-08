# Enhanced Orchestration (v1.3.0)

This document describes the enhanced orchestration features introduced in version 1.3.0, including retry policies, schedule management, and observability improvements. The same schedule definitions can now be consumed by either the bundled Dagster engine or exported as Airflow DAGs (`orchestrator.type: airflow`).

## Overview

Version 1.3.0 enhances the Dagster orchestration layer with production-ready features:

- **Retry Policies**: Intelligent retry with exponential backoff
- **Schedule Management**: Dynamic schedule enable/disable, interval-based scheduling, timezone support
- **Observability**: Metrics collection, distributed tracing, enhanced metadata
- **Tenant Isolation**: Proper tenant tagging and isolation

## Retry Policies

### Configuration

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

### Retry Behavior

- **Exit Code 0**: Success - no retry
- **Exit Code 1**: Partial success - retryable (if configured)
- **Exit Code 2**: Failure - retryable (if configured)

Retries use exponential backoff:
- Attempt 1: Wait `initial_delay_seconds`
- Attempt 2: Wait `initial_delay_seconds * backoff_multiplier`
- Attempt 3: Wait `initial_delay_seconds * backoff_multiplier^2`
- ... capped at `max_delay_seconds`

### Example

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

## Schedule Management

### Schedule Configuration

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
        max_concurrent_runs: 1        # Max concurrent runs
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

### Schedule Features

- **Enable/Disable**: Set `enabled: false` to disable a schedule without removing it
- **Timezone Support**: Specify timezone for schedule execution (e.g., "America/New_York", "UTC")
- **Interval Scheduling**: Use `interval_seconds` as an alternative to cron expressions
- **Concurrency Control**: Set `max_concurrent_runs` to limit parallel executions
- **Custom Tags**: Add tags for filtering and organization

### Cron Expression Format

Standard cron format: `minute hour day month weekday`

Examples:
- `"0 * * * *"` - Every hour at minute 0
- `"0 2 * * *"` - Daily at 2:00 AM
- `"*/15 * * * *"` - Every 15 minutes
- `"0 9 * * 1-5"` - Weekdays at 9:00 AM

## Tenant Isolation

### Tenant Tagging

All assets and jobs are automatically tagged with tenant information:

- `tenant`: Tenant ID (e.g., "acme")
- `job_name`: Schedule name
- `connector_type`: Source connector type

Custom tags from schedule configuration are also included.

### Concurrency Control

Tenant-level serialization ensures only one job runs per tenant at a time:

```yaml
runner:
  orchestrator:
    concurrency_per_tenant: 1  # Only one job per tenant concurrently
```

This prevents Nessie commit conflicts and ensures data consistency.

## Observability

### Metrics Collection

Metrics are automatically collected and emitted as structured log events:

- **Extraction Metrics**: Records extracted, files processed
- **Validation Metrics**: Valid/invalid records, validation rate
- **Writing Metrics**: Files written, bytes written, file sizes
- **API Call Metrics**: API calls made (for API connectors)
- **Error Metrics**: Error types and counts
- **Retry Metrics**: Retry attempts and exit codes
- **Execution Metrics**: Execution time, records per second

### Metrics Example

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

### Distributed Tracing

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

### Enhanced Metadata

Dagster assets emit enhanced metadata:

- `tenant_id`: Tenant identifier
- `connector_type`: Source connector type
- `execution_time_seconds`: Job execution time
- `status`: Job status (success, partial, failure)

Metadata is visible in the Dagster UI for monitoring and debugging.

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

## See Also

- [RUNNER_AND_ORCHESTRATION.md](RUNNER_AND_ORCHESTRATION.md) - Basic orchestration documentation
- [INGESTION_EXECUTION.md](INGESTION_EXECUTION.md) - Execution flow details
- [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) - Configuration reference

