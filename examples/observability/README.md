# Dativo-Ingest Observability Examples

This directory contains working examples for monitoring Dativo-Ingest with Prometheus, OpenTelemetry, and Grafana.

## Files

### Configuration Files
- `runner-with-metrics.yaml` - Runner config with metrics enabled
- `job-with-metrics.yaml` - Job config with metrics override
- `prometheus.yml` - Prometheus scrape configuration
- `otel-collector-config.yaml` - OpenTelemetry Collector configuration
- `alerts.yml` - Prometheus alerting rules

### Stack Files
- `docker-compose.yml` - Complete observability stack
- `grafana-datasources.yml` - Grafana datasource provisioning
- `grafana-dashboards.yml` - Grafana dashboard provisioning
- `grafana-dashboard.json` - Pre-built dashboard

## Quick Start

### 1. Start the Stack

```bash
cd examples/observability
docker-compose up -d
```

This starts:
- **Dativo-Ingest** - Metrics on port 9400
- **Prometheus** - UI on port 9090
- **Grafana** - UI on port 3000
- **OTEL Collector** - OTLP on ports 4317 (gRPC) and 4318 (HTTP)
- **MinIO** - S3-compatible storage
- **Nessie** - Iceberg catalog

### 2. Verify Metrics

**Check metrics endpoint:**
```bash
curl http://localhost:9400/metrics
```

Expected output:
```
# HELP dativo_ingest_records_total Total number of records processed
# TYPE dativo_ingest_records_total counter
dativo_ingest_records_total{connector_type="stripe",mode="orchestrated",phase="extracted"} 1000.0
...
```

**Check OTEL Collector health:**
```bash
curl http://localhost:13133
```

### 3. Access Services

| Service | URL | Credentials |
|---------|-----|-------------|
| **Metrics Endpoint** | http://localhost:9400/metrics | - |
| **Prometheus** | http://localhost:9090 | - |
| **Grafana** | http://localhost:3000 | admin / admin |
| **OTEL Collector** | http://localhost:13133 (health) | - |
| **MinIO Console** | http://localhost:9001 | minioadmin / minioadmin |

### 4. Explore Metrics in Prometheus

Visit http://localhost:9090/graph and try these queries:

```promql
# Records processed per second
rate(dativo_ingest_records_total{phase="extracted"}[5m])

# Job success rate
rate(dativo_ingest_runtime_seconds_count{status="success"}[5m])

# 95th percentile job duration
histogram_quantile(0.95, rate(dativo_ingest_runtime_seconds_bucket[5m]))

# Bytes written per minute
rate(dativo_ingest_bytes_total{phase="written"}[1m]) * 60

# Jobs currently running
sum(dativo_ingest_job_running)
```

### 5. View Grafana Dashboard

1. Open http://localhost:3000
2. Login: **admin / admin**
3. Navigate to **Dashboards → Browse**
4. Open **"Dativo-Ingest Monitoring"**

Dashboard includes:
- Job success rate
- Records processed
- Job duration percentiles
- Data volume
- Error rates

## Standalone Setup

### Prometheus Only

```bash
# Start Dativo-Ingest with metrics
docker run -d \
  -p 9400:9400 \
  -e DATIVO_METRICS_PROMETHEUS=true \
  --name dativo-ingest \
  dativo/dativo-ingest:latest \
  dativo start orchestrated

# Start Prometheus
docker run -d \
  -p 9090:9090 \
  -v $(pwd)/prometheus.yml:/etc/prometheus/prometheus.yml \
  --name prometheus \
  prom/prometheus:latest
```

### OpenTelemetry Collector

```bash
# Start OTEL Collector
docker run -d \
  -p 4317:4317 \
  -p 8889:8889 \
  -v $(pwd)/otel-collector-config.yaml:/etc/otel-collector-config.yaml \
  --name otel-collector \
  otel/opentelemetry-collector-contrib:latest \
  --config=/etc/otel-collector-config.yaml

# Start Dativo-Ingest with OTEL
docker run -d \
  -e DATIVO_METRICS_OTEL=true \
  -e OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317 \
  --link otel-collector \
  --name dativo-ingest \
  dativo/dativo-ingest:latest \
  dativo start orchestrated
```

## Kubernetes Deployment

### Deploy with Helm

```bash
# Add Prometheus Helm repo
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Install Prometheus Operator
helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace

# Deploy Dativo-Ingest with ServiceMonitor
kubectl apply -f k8s-servicemonitor.yaml
```

### ServiceMonitor Example

Create `k8s-servicemonitor.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: dativo-ingest-metrics
  namespace: dativo
  labels:
    app: dativo-ingest
spec:
  ports:
    - name: metrics
      port: 9400
      targetPort: 9400
  selector:
    app: dativo-ingest
---
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: dativo-ingest
  namespace: dativo
  labels:
    app: dativo-ingest
spec:
  selector:
    matchLabels:
      app: dativo-ingest
  endpoints:
    - port: metrics
      interval: 30s
      path: /metrics
```

## Configuration Reference

### Environment Variables

```bash
# Prometheus
export DATIVO_METRICS_PROMETHEUS=true    # Enable Prometheus (default: true)
export DATIVO_METRICS_PORT=9400          # Metrics port (default: 9400)
export DATIVO_METRICS_HOST=0.0.0.0      # Bind host (default: 0.0.0.0)

# OpenTelemetry
export DATIVO_METRICS_OTEL=true          # Enable OTEL (default: false)
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export OTEL_EXPORTER_OTLP_INSECURE=true  # Disable TLS
export DATIVO_ENVIRONMENT=production     # Environment label
```

### Prometheus Configuration

Key sections in `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'dativo-ingest'
    static_configs:
      - targets: ['dativo-ingest:9400']
    scrape_interval: 30s
    scrape_timeout: 10s
```

### OTEL Collector Exporters

The collector supports multiple exporters:

```yaml
exporters:
  prometheus:              # Expose metrics for Prometheus scraping
  prometheusremotewrite:   # Push to Grafana Cloud
  awscloudwatch:          # Export to AWS CloudWatch
  datadog:                # Export to DataDog
  logging:                # Log metrics (debugging)
```

## Troubleshooting

### Metrics Not Showing in Prometheus

1. Check Dativo-Ingest metrics endpoint:
   ```bash
   curl http://localhost:9400/metrics
   ```

2. Verify Prometheus can reach Dativo:
   ```bash
   curl http://prometheus:9090/api/v1/targets
   ```

3. Check Prometheus logs:
   ```bash
   docker logs prometheus
   ```

### OTEL Collector Not Receiving Metrics

1. Check OTEL Collector health:
   ```bash
   curl http://localhost:13133
   ```

2. View OTEL logs:
   ```bash
   docker logs otel-collector
   ```

3. Verify connectivity:
   ```bash
   nc -zv otel-collector 4317
   ```

### Grafana Dashboard Not Loading

1. Verify datasource is configured:
   - Navigate to Configuration → Data Sources
   - Test the Prometheus connection

2. Check dashboard provisioning:
   ```bash
   docker exec grafana ls /var/lib/grafana/dashboards
   ```

3. Import dashboard manually:
   - Copy `grafana-dashboard.json`
   - Navigate to Dashboards → Import
   - Paste JSON content

## Production Recommendations

1. **Use persistent storage** for Prometheus and Grafana data
2. **Enable authentication** on metrics endpoints
3. **Configure retention** policies (default: 90 days)
4. **Set up alerting** with Alertmanager or Grafana
5. **Use service discovery** instead of static targets
6. **Enable TLS** for metrics scraping
7. **Monitor cardinality** to avoid performance issues
8. **Set resource limits** on all containers

## See Also

- [Metrics Documentation](../../docs/METRICS.md)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [OpenTelemetry Documentation](https://opentelemetry.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
