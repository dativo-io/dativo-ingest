# Metrics and Observability

Dativo-Ingest provides comprehensive metrics export for monitoring job execution, performance, and reliability. Metrics are emitted in both oneshot and orchestrated modes, supporting Prometheus and OpenTelemetry backends.

## Overview

The metrics system tracks:

- **Counters**: Records extracted, bytes written, API calls, retries, errors
- **Timers**: Extraction duration, batch processing time, total job runtime
- **Gauges**: Job running status, last success timestamp
- **Summaries**: Records per batch (percentiles)

## Supported Backends

### Prometheus (Default)

Prometheus metrics are enabled by default and collected in-memory. In orchestrated mode, an HTTP endpoint exposes metrics for scraping.

### OpenTelemetry (Optional)

OpenTelemetry metrics can be enabled to push metrics to an OTLP collector (Grafana Agent, OTEL Collector, etc.).

## Configuration

### Environment Variables

```bash
# Prometheus configuration
DATIVO_METRICS_PROMETHEUS=true          # Enable Prometheus metrics (default: true)
DATIVO_METRICS_PORT=9400                # Metrics HTTP port (default: 9400)
DATIVO_METRICS_HOST=0.0.0.0            # Metrics HTTP host (default: 0.0.0.0)

# OpenTelemetry configuration
DATIVO_METRICS_OTEL=false               # Enable OTEL metrics (default: false)
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317  # OTLP endpoint
OTEL_EXPORTER_OTLP_INSECURE=false      # Disable TLS for OTLP (default: false)
DATIVO_ENVIRONMENT=production          # Environment label (default: production)
```

## Available Metrics

### Counters

| Metric | Description | Labels |
|--------|-------------|--------|
| `dativo_records_extracted_total` | Total records extracted | job_name, tenant_id, connector_type |
| `dativo_records_valid_total` | Total valid records after validation | job_name, tenant_id, connector_type |
| `dativo_records_invalid_total` | Total invalid records filtered | job_name, tenant_id, connector_type |
| `dativo_bytes_written_total` | Total bytes written to storage | job_name, tenant_id, connector_type |
| `dativo_files_written_total` | Total files written | job_name, tenant_id, connector_type |
| `dativo_api_calls_total` | Total API calls made | job_name, tenant_id, connector_type, api_type |
| `dativo_job_runs_total` | Total job runs by status | job_name, tenant_id, connector_type, status |
| `dativo_retries_total` | Total retries attempted | job_name, tenant_id, connector_type |
| `dativo_errors_total` | Total errors by type | job_name, tenant_id, connector_type, error_type |

### Histograms

| Metric | Description | Labels | Buckets (seconds) |
|--------|-------------|--------|-------------------|
| `dativo_extraction_duration_seconds` | Time spent extracting data | job_name, tenant_id, connector_type | 1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600 |
| `dativo_job_duration_seconds` | Total job execution time | job_name, tenant_id, connector_type | 1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600 |
| `dativo_batch_processing_seconds` | Time to process a batch | job_name, tenant_id, connector_type | 0.1, 0.5, 1, 2, 5, 10, 30, 60 |

### Gauges

| Metric | Description | Labels |
|--------|-------------|--------|
| `dativo_job_running` | Whether job is running (1=running, 0=not running) | job_name, tenant_id, connector_type |
| `dativo_last_success_timestamp_seconds` | Unix timestamp of last successful run | job_name, tenant_id, connector_type |

### Summaries

| Metric | Description | Labels |
|--------|-------------|--------|
| `dativo_records_per_batch` | Distribution of records per batch | job_name, tenant_id, connector_type |

## Usage

### Oneshot Mode

Metrics are collected automatically but not exposed via HTTP. They appear in structured logs:

```bash
dativo ingest --config jobs/stripe.yaml
```

```json
{
  "message": "Job execution metrics",
  "level": "INFO",
  "event_type": "metrics_complete",
  "status": "success",
  "execution_time_seconds": 45.2,
  "records_extracted": 10000,
  "records_valid": 9998,
  "records_invalid": 2,
  "files_written": 5,
  "bytes_written": 104857600
}
```

### Orchestrated Mode

In orchestrated mode, metrics are exposed via HTTP endpoint for Prometheus scraping:

```bash
# Start orchestrated mode (metrics server starts automatically)
dativo start orchestrated --runner-config configs/runner.yaml
```

The metrics endpoint is available at: `http://0.0.0.0:9400/metrics`

#### Querying Metrics

```bash
# View all metrics
curl http://localhost:9400/metrics

# View specific metric
curl http://localhost:9400/metrics | grep dativo_job_runs_total

# Sample output:
# dativo_job_runs_total{connector_type="stripe",job_name="stripe_payments",status="success",tenant_id="acme"} 42.0
# dativo_job_runs_total{connector_type="postgres",job_name="orders",status="success",tenant_id="acme"} 38.0
```

## Prometheus Integration

### Prometheus Configuration

Add Dativo-Ingest as a scrape target in `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'dativo-ingest'
    static_configs:
      - targets: ['dativo-ingest:9400']
    scrape_interval: 30s
    scrape_timeout: 10s
```

### Docker Compose Example

```yaml
version: '3.8'

services:
  dativo-ingest:
    image: dativo/dativo-ingest:latest
    command: dativo start orchestrated
    environment:
      - DATIVO_METRICS_PROMETHEUS=true
      - DATIVO_METRICS_PORT=9400
    ports:
      - "9400:9400"

  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
```

### Example Prometheus Queries

```promql
# Job success rate over last hour
rate(dativo_job_runs_total{status="success"}[1h])
/ rate(dativo_job_runs_total[1h])

# Average job duration by connector type
avg(dativo_job_duration_seconds) by (connector_type)

# Records processed per second
rate(dativo_records_extracted_total[5m])

# Error rate by error type
rate(dativo_errors_total[5m]) by (error_type)

# Jobs currently running
sum(dativo_job_running) by (tenant_id)

# Time since last successful run
time() - dativo_last_success_timestamp_seconds

# 95th percentile batch processing time
histogram_quantile(0.95, rate(dativo_batch_processing_seconds_bucket[5m]))
```

## OpenTelemetry Integration

### Installation

Install OpenTelemetry dependencies:

```bash
pip install dativo-ingest[otel]
```

Or install manually:

```bash
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc
```

### Configuration

Enable OpenTelemetry and configure the OTLP endpoint:

```bash
export DATIVO_METRICS_OTEL=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
export DATIVO_ENVIRONMENT=production
```

### OTEL Collector Example

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
    loglevel: debug

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [prometheus, logging]
```

### Docker Compose with OTEL Collector

```yaml
version: '3.8'

services:
  dativo-ingest:
    image: dativo/dativo-ingest:latest
    environment:
      - DATIVO_METRICS_OTEL=true
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
      - OTEL_EXPORTER_OTLP_INSECURE=true
    depends_on:
      - otel-collector

  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    command: ["--config=/etc/otel-collector-config.yaml"]
    volumes:
      - ./otel-collector-config.yaml:/etc/otel-collector-config.yaml
    ports:
      - "4317:4317"  # OTLP gRPC
      - "8889:8889"  # Prometheus exporter
```

## Grafana Dashboards

### Importing Pre-built Dashboard

A Grafana dashboard template is available in `examples/observability/grafana-dashboard.json`.

Import steps:

1. Open Grafana
2. Navigate to Dashboards → Import
3. Upload `grafana-dashboard.json`
4. Select Prometheus data source
5. Click Import

### Key Dashboard Panels

- **Job Success Rate**: Success vs failure rate over time
- **Records Processed**: Total records extracted and validated
- **Throughput**: Records per second by job
- **Error Rate**: Errors by type and job
- **Job Duration**: Execution time percentiles
- **Active Jobs**: Currently running jobs by tenant
- **Data Volume**: Bytes written over time
- **API Calls**: API call rate by connector type

## Alerting

### Example Prometheus Alerts

Create `alerts.yml`:

```yaml
groups:
  - name: dativo_alerts
    interval: 30s
    rules:
      # Job failure alert
      - alert: DativoJobFailureRate
        expr: |
          rate(dativo_job_runs_total{status="failure"}[5m])
          / rate(dativo_job_runs_total[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High job failure rate"
          description: "Job {{ $labels.job_name }} has >10% failure rate"

      # Job not running alert
      - alert: DativoJobNotRunning
        expr: |
          time() - dativo_last_success_timestamp_seconds > 7200
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "Job hasn't run successfully"
          description: "Job {{ $labels.job_name }} hasn't succeeded in 2 hours"

      # High error rate alert
      - alert: DativoHighErrorRate
        expr: |
          rate(dativo_errors_total[5m]) > 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate detected"
          description: "Error rate >10/min for job {{ $labels.job_name }}"

      # Slow job execution alert
      - alert: DativoSlowJobExecution
        expr: |
          histogram_quantile(0.95,
            rate(dativo_job_duration_seconds_bucket[10m])
          ) > 1800
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Job execution is slow"
          description: "95th percentile job duration >30min for {{ $labels.job_name }}"

      # Validation issues alert
      - alert: DativoHighInvalidRecords
        expr: |
          rate(dativo_records_invalid_total[5m])
          / rate(dativo_records_extracted_total[5m]) > 0.05
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "High invalid record rate"
          description: "Job {{ $labels.job_name }} has >5% invalid records"
```

## Best Practices

### 1. Use Labels Effectively

Labels enable filtering and aggregation:

```promql
# Per-tenant metrics
sum(rate(dativo_records_extracted_total[5m])) by (tenant_id)

# Per-connector metrics
avg(dativo_job_duration_seconds) by (connector_type)
```

### 2. Set Appropriate Scrape Intervals

- Short jobs (< 5 min): 15-30 second scrape interval
- Long jobs (> 30 min): 60 second scrape interval

### 3. Monitor Cardinality

High label cardinality can impact Prometheus performance. Dativo-Ingest uses fixed labels to keep cardinality manageable.

### 4. Use Recording Rules

Pre-compute expensive queries:

```yaml
groups:
  - name: dativo_recording_rules
    interval: 30s
    rules:
      - record: job:dativo_success_rate:5m
        expr: |
          rate(dativo_job_runs_total{status="success"}[5m])
          / rate(dativo_job_runs_total[5m])

      - record: job:dativo_throughput:5m
        expr: rate(dativo_records_extracted_total[5m])
```

### 5. Set Up Retention Policies

Configure appropriate retention for metrics:

```bash
prometheus \
  --storage.tsdb.retention.time=90d \
  --storage.tsdb.retention.size=50GB
```

## Troubleshooting

### Metrics Not Appearing

1. **Check Prometheus client is installed**:
   ```bash
   pip show prometheus-client
   ```

2. **Verify metrics endpoint is accessible**:
   ```bash
   curl http://localhost:9400/metrics
   ```

3. **Check environment variables**:
   ```bash
   echo $DATIVO_METRICS_PROMETHEUS  # Should be "true"
   ```

4. **Review logs for metrics initialization**:
   ```bash
   dativo start orchestrated 2>&1 | grep metrics
   ```

### OTEL Export Failures

1. **Verify OTEL dependencies**:
   ```bash
   pip show opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc
   ```

2. **Check OTLP endpoint connectivity**:
   ```bash
   nc -zv otel-collector 4317
   ```

3. **Enable debug logging**:
   ```bash
   export OTEL_LOG_LEVEL=debug
   ```

4. **Verify OTEL collector is running**:
   ```bash
   docker logs otel-collector
   ```

### High Cardinality Issues

If Prometheus is running slow:

1. Check metric cardinality:
   ```promql
   count(dativo_job_runs_total) by (__name__)
   ```

2. Review label values:
   ```promql
   count(dativo_job_runs_total) by (job_name, tenant_id)
   ```

3. Consider aggregating at ingestion time if needed

## Security Considerations

### Metrics Endpoint Security

The metrics endpoint exposes operational data. In production:

1. **Use firewall rules** to restrict access to the metrics port
2. **Use reverse proxy authentication** (nginx, Envoy, etc.)
3. **Enable TLS** for Prometheus scraping
4. **Use network policies** in Kubernetes

Example nginx configuration:

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

### Sensitive Data in Metrics

Metrics labels do not include:
- Connection strings or credentials
- Personal data (PII)
- Business-sensitive values

Only operational metadata is exposed (job names, tenant IDs, connector types).

## See Also

- [Prometheus Documentation](https://prometheus.io/docs/)
- [OpenTelemetry Documentation](https://opentelemetry.io/docs/)
- [Grafana Dashboards](https://grafana.com/docs/grafana/latest/dashboards/)
- [PromQL Tutorial](https://prometheus.io/docs/prometheus/latest/querying/basics/)
