# Observability: Metrics Export

Dativo-Ingest exposes job execution metrics via Prometheus and OpenTelemetry.

## Quick Start

### Orchestrated Mode

```yaml
# runner.yaml
metrics:
  prometheus:
    enabled: true
    port: 9400
```

```bash
dativo start orchestrated --runner-config runner.yaml

# Access metrics
curl http://localhost:9400/metrics
```

### Oneshot Mode

Metrics are logged internally only (no HTTP server):

```bash
dativo ingest --config jobs/example.yaml
```

## Configuration

### Runner Configuration (Orchestrated)

```yaml
# runner.yaml
metrics:
  enabled: true
  
  prometheus:
    enabled: true
    host: "0.0.0.0"
    port: 9400
  
  otel:
    enabled: false
    endpoint: http://otel-collector:4317
```

### Job Configuration (Optional Override)

```yaml
# jobs/my-job.yaml
tenant_id: acme
source_connector_path: connectors/stripe.yaml
target_connector_path: connectors/iceberg.yaml
asset_path: assets/payments.yaml

# Override metrics for this specific job
metrics:
  enabled: true
  otel:
    enabled: true
    endpoint: http://custom-collector:4317
```

**Config Precedence:** job config > runner config > defaults

## Available Metrics

### Counters
- `dativo_ingest_records_total{phase}` - Records processed (extracted/written/invalid)
- `dativo_ingest_bytes_total{phase}` - Bytes processed
- `dativo_ingest_retries_total` - Retry attempts *(may be zero)*
- `dativo_ingest_api_calls_total{api_type}` - API calls *(may be zero)*

### Histograms
- `dativo_ingest_extract_seconds` - Extraction duration
- `dativo_ingest_load_seconds` - Load/commit duration
- `dativo_ingest_runtime_seconds` - Total job runtime

### Gauges
- `dativo_ingest_job_running` - Job status (0/1)
- `dativo_ingest_last_success_timestamp_seconds` - Last success time

**Labels:** job_name, tenant_id, connector_type, mode

## Example Output

```
# HELP dativo_ingest_records_total Total records processed
# TYPE dativo_ingest_records_total counter
dativo_ingest_records_total{connector_type="stripe",job_name="payments",mode="orchestrated",phase="extracted",tenant_id="acme"} 1000.0

# HELP dativo_ingest_runtime_seconds Job runtime
# TYPE dativo_ingest_runtime_seconds histogram
dativo_ingest_runtime_seconds_sum{connector_type="stripe",job_name="payments",mode="orchestrated",status="success",tenant_id="acme"} 8.5
dativo_ingest_runtime_seconds_count{connector_type="stripe",job_name="payments",mode="orchestrated",status="success",tenant_id="acme"} 1.0
```

## Prometheus Setup

### Scrape Configuration

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'dativo-ingest'
    static_configs:
      - targets: ['dativo-ingest:9400']
    scrape_interval: 30s
```

### Example Queries

```promql
# Records per second
rate(dativo_ingest_records_total{phase="extracted"}[5m])

# 95th percentile job duration
histogram_quantile(0.95, rate(dativo_ingest_runtime_seconds_bucket[5m]))

# Success rate
rate(dativo_ingest_runtime_seconds_count{status="success"}[5m])
```

## OpenTelemetry Setup

### Enable OTEL

```yaml
metrics:
  otel:
    enabled: true
    endpoint: http://otel-collector:4317
```

### OTEL Collector Config

```yaml
# otel-collector-config.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

exporters:
  prometheus:
    endpoint: "0.0.0.0:8889"

service:
  pipelines:
    metrics:
      receivers: [otlp]
      exporters: [prometheus]
```

## Behavior

- **Orchestrated mode:** HTTP server on port 9400, metrics from all jobs
- **Oneshot mode:** No HTTP server, metrics logged only
- **OTEL failures:** Never crash jobs, warning logged

## Limitations (MVP)

- `retries_total` and `api_calls_total` may remain zero (require manual instrumentation)
- Prometheus multiprocess cleanup not automated
- Per-API-call instrumentation not automatic

## Troubleshooting

### No metrics showing

```bash
# Check server (orchestrated mode)
curl http://localhost:9400/metrics

# Check logs
docker logs dativo-ingest | grep metrics
```

### OTEL failures

OTEL export failures are logged but don't crash jobs. Check logs:

```bash
docker logs dativo-ingest | grep otel
```

### Port already in use

If port 9400 is busy, the server won't start but jobs continue. Check logs for:

```
metrics_server_bind_failed
```

Change port in runner.yaml:

```yaml
metrics:
  prometheus:
    port: 9401
```

## See Also

- [Configuration Reference](CONFIG_REFERENCE.md) - Full config options
- [Runner & Orchestration](RUNNER_AND_ORCHESTRATION.md) - Dagster setup
