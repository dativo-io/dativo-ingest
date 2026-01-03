# Observability: Metrics Export

Dativo-Ingest exposes detailed job execution metrics via Prometheus and OpenTelemetry for monitoring, alerting, and integration with observability stacks.

## Quick Start

### Orchestrated Mode (Metrics Server Enabled)

```bash
# Start orchestrated mode
docker run -p 9400:9400 dativo/dativo-ingest:latest \
  dativo start orchestrated --runner-config /app/configs/runner.yaml

# Access metrics
curl http://localhost:9400/metrics
```

### Oneshot Mode (Metrics in Logs Only)

```bash
# Run a single job
dativo ingest --config jobs/example.yaml

# Metrics appear in structured logs
# {"message": "Job execution metrics", "runtime_seconds": 45.2, ...}
```

## Configuration

### Runner Configuration (Orchestrated Mode)

```yaml
# runner.yaml
mode: orchestrated

orchestrator:
  type: dagster
  schedules: [...]

# Metrics configuration
metrics:
  enabled: true
  
  prometheus:
    enabled: true
    host: "0.0.0.0"
    port: 9400
    multiproc_dir: /tmp/prometheus_multiproc  # Required for subprocess metrics
    cleanup_on_startup: false  # Optional: cleanup stale db files
  
  otel:
    enabled: false
    protocol: grpc  # or "http"
    endpoint: http://otel-collector:4317
    export_interval_seconds: 60
  
  labels:
    include_tenant_id: false  # High cardinality - use with caution
    include_job_name: false   # High cardinality - use with caution
    include_mode: true        # Low cardinality - safe
    include_env: false        # Optional environment label
```

### Job Configuration (Optional Override)

```yaml
# jobs/example.yaml
tenant_id: acme
source_connector_path: connectors/stripe.yaml
target_connector_path: connectors/iceberg.yaml
asset_path: assets/payments.yaml

# Optional: override metrics for this specific job
metrics:
  prometheus:
    enabled: true
  otel:
    enabled: true
    endpoint: http://custom-collector:4317
```

### Environment Variable Overrides

```bash
# Prometheus
export DATIVO_METRICS_PROMETHEUS=true
export DATIVO_METRICS_PORT=9400
export PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc

# OpenTelemetry
export DATIVO_METRICS_OTEL=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export OTEL_EXPORTER_OTLP_PROTOCOL=grpc
```

**Configuration precedence:** env vars > job config > runner config > defaults

## Available Metrics

### Counters

| Metric | Labels | Description |
|--------|--------|-------------|
| `dativo_ingest_records_total` | phase=extracted\|written\|invalid | Records processed by phase |
| `dativo_ingest_bytes_total` | phase=written\|committed | Bytes processed |
| `dativo_ingest_retries_total` | - | Retry attempts |
| `dativo_ingest_api_calls_total` | api_type | API calls by type |

### Histograms (Timing)

| Metric | Description | Buckets (seconds) |
|--------|-------------|-------------------|
| `dativo_ingest_extract_seconds` | Extraction phase duration | 1, 2, 5, 10, 30, 60, 120, 300, 600, 1800, 3600 |
| `dativo_ingest_load_seconds` | Load/commit phase duration | 1, 2, 5, 10, 30, 60, 120, 300, 600, 1800, 3600 |
| `dativo_ingest_runtime_seconds` | Total job runtime | 1, 2, 5, 10, 30, 60, 120, 300, 600, 1800, 3600 |

### Gauges

| Metric | Description |
|--------|-------------|
| `dativo_ingest_job_running` | Job running status (1=running, 0=not running) |
| `dativo_ingest_last_success_timestamp_seconds` | Unix timestamp of last successful run |

**Standard labels (always present):**
- `connector_type` - Type of connector (stripe, postgres, etc.)
- `mode` - Execution mode (oneshot, orchestrated)

**Optional labels (configurable):**
- `job_name` - Name of the job (high cardinality - disabled by default)
- `tenant_id` - Tenant identifier (high cardinality - disabled by default)
- `environment` - Deployment environment (optional)

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
# Job success rate over last hour
rate(dativo_ingest_runtime_seconds_count{status="success"}[1h])

# Records processed per second
rate(dativo_ingest_records_total{phase="extracted"}[5m])

# 95th percentile job duration
histogram_quantile(0.95, rate(dativo_ingest_runtime_seconds_bucket[5m]))

# Bytes written per minute
rate(dativo_ingest_bytes_total{phase="written"}[1m]) * 60

# API call rate
rate(dativo_ingest_api_calls_total[5m])

# Time since last success
time() - dativo_ingest_last_success_timestamp_seconds
```

### Grafana Dashboard

Basic panel examples:

```promql
# Throughput Panel (Time Series)
rate(dativo_ingest_records_total{phase="extracted"}[5m])

# Job Duration Panel (Heatmap)
histogram_quantile(0.50, rate(dativo_ingest_runtime_seconds_bucket[5m]))
histogram_quantile(0.95, rate(dativo_ingest_runtime_seconds_bucket[5m]))
histogram_quantile(0.99, rate(dativo_ingest_runtime_seconds_bucket[5m]))

# Error Rate Panel (Graph)
rate(dativo_ingest_runtime_seconds_count{status="failure"}[5m])

# Data Volume Panel (Gauge)
sum(increase(dativo_ingest_bytes_total{phase="written"}[1h]))
```

## OpenTelemetry Integration

### OTLP gRPC (Default)

```yaml
# runner.yaml
metrics:
  otel:
    enabled: true
    protocol: grpc
    endpoint: http://otel-collector:4317
```

### OTLP HTTP

```yaml
# runner.yaml
metrics:
  otel:
    enabled: true
    protocol: http
    endpoint: http://otel-collector:4318
```

### OTEL Collector Configuration

**For gRPC (port 4317):**

```yaml
# otel-collector-config.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

processors:
  batch:
    timeout: 10s

exporters:
  prometheus:
    endpoint: "0.0.0.0:8889"
  logging:
    loglevel: info

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [prometheus, logging]
```

**For HTTP (port 4318):**

```yaml
# otel-collector-config.yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 10s

exporters:
  prometheus:
    endpoint: "0.0.0.0:8889"

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [prometheus]
```

### Authentication Headers

```yaml
metrics:
  otel:
    enabled: true
    endpoint: https://api.honeycomb.io:443
    headers:
      x-honeycomb-team: "your-api-key-here"
```

## Multiprocess Mode (Orchestrated)

When running jobs in subprocesses (Dagster), use multiprocess mode to aggregate metrics:

```yaml
metrics:
  prometheus:
    enabled: true
    multiproc_dir: /tmp/prometheus_multiproc
    cleanup_on_startup: false  # Set true to delete stale *.db files
```

**Directory requirements:**
- Must be writable by Dativo process
- Should be on fast storage (tmpfs recommended)
- Not shared with other applications

**Cleanup:**
- Set `cleanup_on_startup: true` to remove stale files on startup
- Use with caution - only enable if you control the directory
- Recommended for containerized deployments

## Cardinality Management

**Default configuration uses LOW cardinality** (safe for production):

```yaml
metrics:
  labels:
    include_tenant_id: false   # Disabled by default
    include_job_name: false    # Disabled by default
    include_mode: true         # Enabled (low cardinality)
    include_env: false         # Disabled by default
```

**When disabled, labels use value "disabled"** to keep schema stable.

**Enable high-cardinality labels only if:**
- You have < 100 tenants
- You have < 100 unique jobs
- Your Prometheus can handle the cardinality

**Example with high cardinality enabled:**

```yaml
metrics:
  labels:
    include_tenant_id: true   # ⚠️ Increases series count
    include_job_name: true    # ⚠️ Increases series count
```

**Estimated series count:**
```
Base metrics: ~10
Cardinality multiplier:
  - connector_types: ~10
  - modes: 2 (oneshot, orchestrated)
  - tenant_ids: N (if enabled)
  - job_names: M (if enabled)

Total series = 10 × 10 × 2 × N × M
Example: 10 tenants, 50 jobs = ~100,000 series
```

## Security Considerations

### Metrics Endpoint

The `/metrics` endpoint is **not authenticated** by default (Prometheus standard).

**Production recommendations:**
1. Use firewall rules to restrict access
2. Deploy behind reverse proxy with authentication
3. Use VPN or private network
4. Enable TLS at reverse proxy

**Example nginx configuration:**

```nginx
server {
    listen 9400 ssl;
    ssl_certificate /etc/nginx/certs/cert.pem;
    ssl_certificate_key /etc/nginx/certs/key.pem;

    # Basic auth
    auth_basic "Metrics";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location /metrics {
        proxy_pass http://dativo-ingest:9400/metrics;
    }
}
```

### Secrets in Metrics

Metrics **never include**:
- Connection strings
- Passwords or API keys
- PII (personal data)
- Business-sensitive values

Only operational metadata is exposed (job names, connector types, timing).

### OTEL Headers

OTEL headers (which may contain API keys) are **never logged**.  
Configuration logs show only: `headers_configured: true`

## Troubleshooting

### Metrics Not Showing

1. **Check server is running (orchestrated mode):**
   ```bash
   curl http://localhost:9400/metrics
   ```

2. **Check configuration:**
   ```bash
   # In orchestrated mode, metrics.prometheus.enabled should be true
   # In oneshot mode, it's false by default
   ```

3. **Check logs for errors:**
   ```bash
   docker logs dativo-ingest 2>&1 | grep metrics
   ```

4. **Verify multiprocess directory (if configured):**
   ```bash
   ls -la /tmp/prometheus_multiproc/
   # Should contain *.db files
   ```

### OTEL Export Failures

1. **Check collector is reachable:**
   ```bash
   nc -zv otel-collector 4317
   ```

2. **Check logs (throttled):**
   - Failures logged at most once per 5 minutes
   - Look for: `"event_type": "otel_export_failed"`

3. **Verify endpoint configuration:**
   ```yaml
   # gRPC uses port 4317
   endpoint: http://collector:4317
   protocol: grpc
   
   # HTTP uses port 4318
   endpoint: http://collector:4318
   protocol: http
   ```

4. **Test with logging exporter:**
   ```yaml
   # otel-collector-config.yaml
   exporters:
     logging:
       loglevel: debug
   ```

### High Cardinality Issues

If Prometheus is slow or running out of memory:

1. **Check series count:**
   ```promql
   count({__name__=~"dativo_ingest_.*"})
   ```

2. **Disable high-cardinality labels:**
   ```yaml
   metrics:
     labels:
       include_tenant_id: false
       include_job_name: false
   ```

3. **Use recording rules for aggregation:**
   ```yaml
   # prometheus-rules.yml
   groups:
     - name: dativo_aggregations
       interval: 60s
       rules:
         - record: job:dativo_ingest_records_total:rate5m
           expr: rate(dativo_ingest_records_total[5m])
   ```

## Operational Best Practices

### For Orchestrated Mode

1. **Always use multiprocess mode:**
   ```yaml
   prometheus:
     multiproc_dir: /tmp/prometheus_multiproc
   ```

2. **Use tmpfs for multiproc directory:**
   ```yaml
   # docker-compose.yml
   volumes:
     - type: tmpfs
       target: /tmp/prometheus_multiproc
   ```

3. **Set resource limits:**
   ```yaml
   # docker-compose.yml
   deploy:
     resources:
       limits:
         memory: 2G
   ```

### For Oneshot Mode

1. **Metrics in logs only (default):**
   - No HTTP server overhead
   - Structured logging for aggregation

2. **Enable server if needed:**
   ```yaml
   # job.yaml
   metrics:
     prometheus:
       enabled: true
   ```

### Scrape Interval

- **Fast jobs (< 5 min):** 15-30 second interval
- **Long jobs (> 30 min):** 60 second interval
- **Very long jobs (> 1 hour):** 120 second interval

### Retention

Configure appropriate retention for metrics:

```bash
prometheus \
  --storage.tsdb.retention.time=90d \
  --storage.tsdb.retention.size=50GB
```

## Migration from Old Metrics

If you're using the initial metrics implementation:

### Metric Name Changes

| Old Name | New Name |
|----------|----------|
| `dativo_records_extracted_total` | `dativo_ingest_records_total{phase="extracted"}` |
| `dativo_records_valid_total` | `dativo_ingest_records_total{phase="written"}` |
| `dativo_records_invalid_total` | `dativo_ingest_records_total{phase="invalid"}` |
| `dativo_bytes_written_total` | `dativo_ingest_bytes_total{phase="written"}` |
| `dativo_extraction_duration_seconds` | `dativo_ingest_extract_seconds` |
| `dativo_job_duration_seconds` | `dativo_ingest_runtime_seconds` |

### Query Migration

**Before:**
```promql
rate(dativo_records_extracted_total[5m])
```

**After:**
```promql
rate(dativo_ingest_records_total{phase="extracted"}[5m])
```

## See Also

- [Examples](/examples/observability/README.md) - Working examples with Docker Compose
- [Configuration Reference](/docs/CONFIG_REFERENCE.md) - Complete config options
- [Prometheus Documentation](https://prometheus.io/docs/) - Official Prometheus docs
- [OpenTelemetry Documentation](https://opentelemetry.io/docs/) - Official OTEL docs
