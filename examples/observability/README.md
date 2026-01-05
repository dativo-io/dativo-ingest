# Observability Examples

Example configurations for monitoring Dativo-Ingest with Prometheus and OpenTelemetry.

## Files

- `prometheus.yml` - Prometheus scrape configuration
- `otel-collector-config.yaml` - OpenTelemetry Collector setup
- `docker-compose.yml` - Complete stack (Dativo + Prometheus + Grafana + OTEL)
- `grafana-dashboard.json` - Pre-built Grafana dashboard
- `alerts.yml` - Example Prometheus alerts

## Quick Start

```bash
cd examples/observability
docker-compose up -d

# Access metrics
curl http://localhost:9400/metrics

# Access Grafana
open http://localhost:3000  # admin/admin
```

## Services

| Service | URL | Credentials |
|---------|-----|-------------|
| Metrics Endpoint | http://localhost:9400/metrics | - |
| Prometheus | http://localhost:9090 | - |
| Grafana | http://localhost:3000 | admin/admin |

## Example Queries

See [docs/OBSERVABILITY_METRICS.md](../../docs/OBSERVABILITY_METRICS.md) for more details.
