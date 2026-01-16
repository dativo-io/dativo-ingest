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

**⚠️ Security Warning**: The Dagster UI does not include built-in authentication. For production deployments:
- **MUST** be placed behind a reverse proxy with authentication (OAuth, SAML, LDAP, or basic auth)
- **MUST** be placed behind a VPN or private network
- **MUST** use HTTPS/TLS encryption
- See [SECURITY.md](../SECURITY.md) and [docs/SECURITY_AUDIT.md](SECURITY_AUDIT.md) for production security guidance

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

## Notification Hooks (v1.4.0+)

Notification hooks provide runner-level, failure-only external notifications via simple command hooks.

### Philosophy

Dativo follows a headless, config-only approach for notifications:

- **No embedded services**: Dativo does not implement Slack, Kafka, PagerDuty, etc. internally
- **User-controlled**: You provide external scripts that integrate with your systems
- **Failure-only**: Hooks are triggered only when jobs fail (exit code = 2)
- **Graceful failure**: Hook failures never affect job outcomes

### Configuration

Add a `notifications` block to your `runner.yaml`:

```yaml
runner:
  mode: orchestrated
  orchestrator:
    type: dagster
    schedules:
      - name: stripe_hourly
        config: /app/jobs/acme/stripe.yaml
        cron: "0 * * * *"
  
  # Notification hooks (optional)
  notifications:
    on_failure:
      command: ["/app/scripts/notify_slack.sh"]
      env:
        SLACK_WEBHOOK_URL: ${SLACK_WEBHOOK_URL}
      timeout_seconds: 15
```

#### Configuration Fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `notifications` | No | - | Top-level notifications block |
| `on_failure` | No | - | Hook configuration for job failures |
| `command` | Yes* | - | Command as argv array (no shell). Required if `on_failure` is present |
| `env` | No | - | Environment variables with `${VAR}` expansion |
| `timeout_seconds` | No | 15 | Hook execution timeout (1-60 seconds) |

### Environment Contract

When a hook executes, these environment variables are always injected by the runner:

| Variable | Description | Example |
|----------|-------------|---------|
| `DATIVO_TENANT_ID` | Tenant identifier | `acme` |
| `DATIVO_JOB_NAME` | Job/schedule name | `stripe_hourly` |
| `DATIVO_RUN_ID` | Unique run identifier | `2026-01-16T10:03:12Z` |
| `DATIVO_SUMMARY_PATH` | Absolute path to summary JSON | `/logs/runs/.../summary.json` |

**Environment Precedence** (highest to lowest):
1. Required `DATIVO_*` variables (always set, override user values)
2. User-provided `env` (after `${VAR}` expansion)
3. Existing process environment

### Summary File

For each failed run, a summary JSON file is written:

```json
{
  "tenant_id": "acme",
  "job_name": "stripe_hourly",
  "run_id": "2026-01-16T10:03:12Z",
  "status": "failure",
  "timestamp": "2026-01-16T10:03:12Z",
  "config_path": "/app/configs/jobs/stripe.yaml",
  "error": {
    "message": "Stripe API timeout",
    "type": "UpstreamError"
  }
}
```

**Rules:**
- Schema is minimal and stable
- Never includes secrets
- Hook scripts may read this file directly

### Example Scripts

Dativo ships example scripts in `examples/scripts/`:

#### Slack Webhook (`notify_slack.sh`)

```yaml
notifications:
  on_failure:
    command: ["/app/scripts/notify_slack.sh"]
    env:
      SLACK_WEBHOOK_URL: ${SLACK_WEBHOOK_URL}
      SLACK_CHANNEL: "#alerts"  # Optional override
```

#### Generic HTTP Webhook (`notify_webhook.sh`)

```yaml
notifications:
  on_failure:
    command: ["/app/scripts/notify_webhook.sh"]
    env:
      WEBHOOK_URL: ${WEBHOOK_URL}
      WEBHOOK_HEADERS: "Authorization: Bearer ${API_TOKEN}"
```

### Oneshot Mode

Notification hooks also work in oneshot mode when you provide the runner config:

```bash
dativo run --config /app/jobs/stripe.yaml --runner-config /app/configs/runner.yaml
```

### Writing Custom Hook Scripts

Requirements:
1. **Executable**: Script must be executable (`chmod +x`)
2. **No shell**: Command is invoked as argv array (no shell interpolation)
3. **Pure shell + curl**: Avoid external dependencies for portability
4. **Graceful**: Handle missing summary file gracefully
5. **Timeout-aware**: Complete within configured timeout

### Explicit Non-Goals

Dativo does **not** ship built-in integrations for:
- Slack, Teams, Discord
- Kafka, RabbitMQ
- PagerDuty, OpsGenie
- Email, SMS

**If you need Kafka**, write a custom hook script:

```bash
#!/bin/sh
# notify_kafka.sh
cat "$DATIVO_SUMMARY_PATH" | \
    kafka-console-producer \
        --broker-list "$KAFKA_BROKERS" \
        --topic "$KAFKA_TOPIC"
```

### Failure & Safety Semantics

Hook execution is designed to fail gracefully:

| Condition | Behavior |
|-----------|----------|
| Command not found | Log error, continue |
| Command not executable | Log error, continue |
| Command times out | Log warning, continue |
| Command exits non-zero | Log warning, continue |

**Key principle**: The ingestion job failed because ingestion failed — not because notification failed.

### Troubleshooting Notification Hooks

#### Script not found

```
ERROR: Hook command not found: /app/scripts/notify_slack.sh
```

- Check that the script exists in your Docker container
- Verify the path is absolute or relative to working directory

#### Permission denied

```
ERROR: Hook command not executable: /app/scripts/notify_slack.sh
```

- Run `chmod +x /app/scripts/notify_slack.sh`
- Ensure the script has a valid shebang (`#!/bin/sh`)

#### Missing environment variables

```
ERROR: SLACK_WEBHOOK_URL environment variable is not set
```

- Add the variable to your `runner.yaml` `env` block
- Ensure the source environment variable is set

#### Webhook errors

- Check HTTP response codes in logs
- 401/403: Authentication issues
- 404: Incorrect URL
- 5xx: Target service issues

#### Finding summary.json

The summary path is logged when hooks are triggered. Default pattern:
```
/logs/runs/{run_id}/summary.json
```

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

### Notification Hooks

- Keep hook scripts simple and fast (< 15 seconds)
- Use pure shell + curl for portability
- Handle missing summary file gracefully
- Test hooks independently before deploying
- Use structured logging in custom scripts
- Never include secrets in logs or error messages

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
