# Airflow Support

This document describes how to use Apache Airflow as an alternative orchestrator to Dagster in the Dativo ingestion platform.

## Overview

The platform now supports two orchestrators:
- **Dagster** (default) - Lightweight orchestrator bundled with the Docker image
- **Airflow** - Industry-standard workflow orchestration platform

Both orchestrators support the same schedule configuration format and provide equivalent functionality for running Dativo ingestion jobs.

## Configuration

### Specifying Airflow as Orchestrator

To use Airflow instead of Dagster, set `orchestrator.type: airflow` in your runner configuration:

```yaml
runner:
  mode: orchestrated
  orchestrator:
    type: airflow  # Use 'dagster' for Dagster (default)
    schedules:
      - name: my_job
        config: /app/jobs/tenant/job.yaml
        cron: "0 * * * *"
        enabled: true
    concurrency_per_tenant: 1
```

### Example Configuration

See `/app/configs/runner_airflow.yaml` for a complete example:

```yaml
runner:
  mode: orchestrated
  orchestrator:
    type: airflow
    schedules:
      # Cron-based schedule
      - name: stripe_customers_hourly
        config: /app/jobs/acme/stripe_customers_to_iceberg.yaml
        cron: "0 * * * *"
        enabled: true
        timezone: "UTC"
        max_concurrent_runs: 1
        tags:
          environment: "production"
          priority: "high"
      
      # Interval-based schedule (every 6 hours)
      - name: hubspot_contacts_daily
        config: /app/jobs/acme/hubspot_contacts_to_iceberg.yaml
        interval_seconds: 21600
        enabled: true
        timezone: "America/New_York"
        tags:
          environment: "production"
```

## Schedule Configuration

Both orchestrators support the same schedule properties:

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `name` | string | Yes | Unique schedule identifier |
| `config` | string | Yes | Path to job configuration file |
| `cron` | string | No* | Cron expression for schedule |
| `interval_seconds` | integer | No* | Interval in seconds (alternative to cron) |
| `enabled` | boolean | No | Enable/disable schedule (default: true) |
| `timezone` | string | No | Timezone for execution (default: UTC) |
| `max_concurrent_runs` | integer | No | Max concurrent runs (default: 1) |
| `tags` | object | No | Custom tags for filtering |

\* Either `cron` or `interval_seconds` must be specified, but not both.

## Starting the Orchestrator

### Airflow Setup

1. **Configure runner with Airflow type:**
   ```bash
   # In runner_airflow.yaml
   orchestrator:
     type: airflow
   ```

2. **Initialize Airflow database:**
   ```bash
   export AIRFLOW_HOME=/path/to/airflow
   airflow db init
   ```

3. **Create admin user (optional):**
   ```bash
   airflow users create \
     --username admin \
     --firstname Admin \
     --lastname User \
     --role Admin \
     --email admin@example.com
   ```

4. **Start Airflow webserver:**
   ```bash
   airflow webserver --port 8080
   ```

5. **Start Airflow scheduler (in separate terminal):**
   ```bash
   airflow scheduler
   ```

6. **Access Airflow UI:**
   Open http://localhost:8080 in your browser

### Docker Deployment

```bash
docker run --rm -p 8080:8080 \
  -v $(pwd)/connectors:/app/connectors:ro \
  -v $(pwd)/assets:/app/assets:ro \
  -v $(pwd)/jobs:/app/jobs \
  -v $(pwd)/configs:/app/configs \
  -v $(pwd)/secrets:/app/secrets \
  -v $(pwd)/state:/app/state \
  -e AIRFLOW_HOME=/app/airflow \
  our-registry/ingestion:1.0 start orchestrated \
    --runner-config /app/configs/runner_airflow.yaml
```

## DAG Generation

The Airflow orchestrator automatically generates DAGs from your runner configuration:

1. Each schedule in `runner.yaml` becomes a separate Airflow DAG
2. DAG IDs match the schedule name
3. Tags are automatically added:
   - `dativo` - Platform identifier
   - `tenant:{tenant_id}` - Tenant identifier
   - `connector:{connector_type}` - Connector type
   - Custom tags from schedule configuration

## Features

### Tenant-Level Serialization

Both orchestrators enforce tenant-level serialization through `concurrency_per_tenant`:
- Ensures only one job runs per tenant at a time
- Prevents Nessie commit conflicts
- Configurable per-tenant concurrency

### Retry Support

Airflow respects retry configuration from job configs:
- `max_retries` - Number of retry attempts
- `initial_delay_seconds` - Initial retry delay
- `backoff_multiplier` - Exponential backoff multiplier
- `retryable_exit_codes` - Exit codes that trigger retries

### Schedule Management

Both orchestrators support:
- **Cron expressions** - Standard cron syntax
- **Interval-based schedules** - Run every N seconds
- **Enable/disable toggles** - Enable/disable without redeployment
- **Timezone support** - Execute schedules in specific timezones
- **Max concurrent runs** - Limit concurrent executions

## Monitoring and Logs

### Airflow UI

Access the Airflow web interface at http://localhost:8080 to:
- View DAG status and execution history
- Monitor task execution and logs
- Trigger manual DAG runs
- View execution metrics and statistics

### Structured Logging

All jobs log structured JSON output with:
- `job_name` - Schedule name
- `tenant_id` - Tenant identifier
- `connector_type` - Source connector type
- `event_type` - Event classification
- `execution_time_seconds` - Job duration
- Additional context fields

## Comparison: Dagster vs Airflow

| Feature | Dagster | Airflow |
|---------|---------|---------|
| **Setup Complexity** | Low (bundled) | Medium (separate services) |
| **UI** | Modern, asset-centric | Traditional, task-centric |
| **Community** | Growing | Mature, large ecosystem |
| **Resource Usage** | Lightweight | Heavier (webserver + scheduler) |
| **Production Ready** | Yes | Yes |
| **Learning Curve** | Lower | Higher |

## Migration

### From Dagster to Airflow

1. Update `orchestrator.type` from `dagster` to `airflow`
2. Keep all schedule configurations unchanged
3. Start Airflow services (webserver + scheduler)
4. Verify DAGs appear in Airflow UI

### From Airflow to Dagster

1. Update `orchestrator.type` from `airflow` to `dagster`
2. Keep all schedule configurations unchanged
3. Start Dagster webserver
4. Verify assets and schedules in Dagster UI

## Troubleshooting

### DAGs Not Appearing

1. Check Airflow logs for errors
2. Verify runner config path is correct
3. Ensure Airflow scheduler is running
4. Check AIRFLOW_HOME environment variable

### Jobs Failing

1. Check Airflow task logs in UI
2. Verify job configuration is valid
3. Check secrets and environment variables
4. Validate connector configuration

### Permission Issues

1. Ensure state directory is writable
2. Check volume mounts in Docker
3. Verify file permissions on configs

## Best Practices

1. **Use Dagster for simplicity** - If you don't need Airflow's ecosystem, Dagster is simpler
2. **Use Airflow for integration** - If you have existing Airflow infrastructure, use Airflow
3. **Test locally first** - Validate configuration with oneshot mode before orchestration
4. **Monitor execution** - Use the orchestrator UI to monitor job health
5. **Version control configs** - Keep runner configs in version control

## Resources

- [Airflow Documentation](https://airflow.apache.org/docs/)
- [Dagster Documentation](https://docs.dagster.io/)
- [Dativo Runner & Orchestration](./RUNNER_AND_ORCHESTRATION.md)
- [Example Configs](../configs/)
