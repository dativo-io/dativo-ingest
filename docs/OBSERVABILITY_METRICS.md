# Observability: Metrics Export

Dativo-Ingest exposes job execution metrics via Prometheus and OpenTelemetry.

## Prometheus Metrics

### Enable Prometheus in runner.yaml

```yaml
# runner.yaml
metrics:
  prometheus:
    enabled: true
    port: 9400
```

Start orchestrated mode:

```bash
dativo start orchestrated --runner-config runner.yaml
```

Access metrics:

```bash
curl http://localhost:9400/metrics
```

## OpenTelemetry Metrics

### Enable OTEL in job.yaml

```yaml
# jobs/my-job.yaml
tenant_id: acme
source_connector_path: connectors/stripe.yaml
target_connector_path: connectors/iceberg.yaml
asset_path: assets/payments.yaml

metrics:
  otel:
    enabled: true
    endpoint: http://otel-collector:4317
```

## Limitations

Retry-level and per-API metrics may be added later.
