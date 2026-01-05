# Observability: Metrics Export (MVP)

Dativo-Ingest exposes job execution metrics via Prometheus and OpenTelemetry.

> **Note**: This is a minimal metrics MVP. Per-API-call and retry-level metrics may be added later.

## Quick Start

### Orchestrated Mode

```yaml
# runner.yaml
mode: orchestrated

metrics:
  enabled: true
  prometheus:
    enabled: true
    port: 9400
  otel:
    enabled: false
    endpoint: http://otel-collector:4317
```

```bash
dativo start orchestrated --runner-config runner.yaml

# Access metrics
curl http://localhost:9400/metrics
```

### Oneshot Mode

```bash
# No HTTP server started (metrics in logs only)
dativo ingest --config jobs/example.yaml
```

## Configuration

### In runner.yaml (orchestrated)

```yaml
metrics:
  enabled: true
  prometheus:
    enabled: true
    host: "0.0.0.0"
    port: 9400
  otel:
    enabled: false
    endpoint: http://localhost:4317
```

### In job.yaml (optional override)

```yaml
# jobs/example.yaml
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

**Precedence:** job config > runner config > defaults

## Available Metrics

### Counters
- `dativo_ingest_records_total{phase}` - Records processed (extracted/written/invalid)
- `dativo_ingest_bytes_total{phase}` - Bytes processed (written/committed)
- `dativo_ingest_retries_total` - Retry attempts
- `dativo_ingest_api_calls_total{api_type}` - API calls by type

### Histograms (Timing)
- `dativo_ingest_extract_seconds` - Extraction phase duration
- `dativo_ingest_load_seconds` - Load/commit phase duration
- `dativo_ingest_runtime_seconds` - Total job runtime

### Gauges
- `dativo_ingest_job_running` - Job running status
- `dativo_ingest_last_success_timestamp_seconds` - Last successful run timestamp

**Labels:** job_name, tenant_id, connector_type, mode

## Example Metrics Output

```
# HELP dativo_ingest_records_total Total records processed
# TYPE dativo_ingest_records_total counter
dativo_ingest_records_total{connector_type="stripe",job_name="payments",mode="orchestrated",phase="extracted",tenant_id="acme"} 1000.0

# HELP dativo_ingest_runtime_seconds Job runtime in seconds
# TYPE dativo_ingest_runtime_seconds histogram
dativo_ingest_runtime_seconds_bucket{connector_type="stripe",job_name="payments",mode="orchestrated",status="success",tenant_id="acme",le="10.0"} 1.0
dativo_ingest_runtime_seconds_sum{connector_type="stripe",job_name="payments",mode="orchestrated",status="success",tenant_id="acme"} 8.5
dativo_ingest_runtime_seconds_count{connector_type="stripe",job_name="payments",mode="orchestrated",status="success",tenant_id="acme"} 1.0
```

## Prometheus Integration

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
# Records processed per second
rate(dativo_ingest_records_total{phase="extracted"}[5m])

# 95th percentile job duration
histogram_quantile(0.95, rate(dativo_ingest_runtime_seconds_bucket[5m]))

# Job success rate
rate(dativo_ingest_runtime_seconds_count{status="success"}[5m])
```

## OpenTelemetry Integration

### Enable OTEL Export

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

### Safety

OTEL export failures **never crash jobs**. If the collector is unreachable, a warning is logged and the job continues.

## Behavior

### Orchestrated Mode
- ✅ HTTP server started on port 9400
- ✅ `/metrics` endpoint exposed
- ✅ Metrics from all jobs

### Oneshot Mode
- ✅ NO HTTP server started
- ✅ Metrics recorded internally
- ✅ Metrics logged as structured JSON
- ✅ OTEL export if configured

## Troubleshooting

### No metrics showing

```bash
# Check if server is running (orchestrated mode only)
curl http://localhost:9400/metrics

# Check logs
docker logs dativo-ingest | grep metrics_initialized
```

### OTEL export failures

OTEL failures are logged but **do not crash jobs**. Check logs:

```bash
docker logs dativo-ingest | grep otel
```

## Limitations (MVP)

This is a minimal metrics MVP. The following are **NOT YET SUPPORTED**:

- Prometheus multiprocess cleanup
- Automatic retry-level instrumentation
- Per-API-call automatic instrumentation

These may be added in future releases based on user feedback.

## See Also

- [Runner & Orchestration](RUNNER_AND_ORCHESTRATION.md) - Dagster setup
- [Configuration Reference](CONFIG_REFERENCE.md) - Full config options
