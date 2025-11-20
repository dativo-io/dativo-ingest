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

## Additional Resources

- [SETUP_AND_ONBOARDING.md](SETUP_AND_ONBOARDING.md) - Comprehensive setup and onboarding guide
- [INGESTION_EXECUTION.md](INGESTION_EXECUTION.md) - Execution flow documentation
- [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) - Configuration reference
- [README.md](../README.md) - Project overview and quick start
