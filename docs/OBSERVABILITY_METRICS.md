## Metrics Export (Prometheus + OpenTelemetry)

This project exposes **job execution metrics** for monitoring and alerting in both **oneshot** and **orchestrated** modes.

### Install

Metrics export uses `prometheus-client` and OpenTelemetry metrics (OTLP/HTTP). They are installed with the package:

```bash
pip install dativo-ingest
```

### What gets exported

- **Counters**
  - `dativo_ingest_records_total{phase=...}`: records processed (`extracted`, `written`, `invalid`)
  - `dativo_ingest_bytes_total{phase=...}`: bytes processed (`written`, `committed`)
  - `dativo_ingest_retries_total`: retries performed (orchestrated retries)
  - `dativo_ingest_api_calls_total{api_type=...}`: API calls performed (when instrumented)
- **Timers (histograms)**
  - `dativo_ingest_extract_seconds`
  - `dativo_ingest_load_seconds`
  - `dativo_ingest_runtime_seconds`

All metrics include labels:
- `tenant_id`
- `job_name`
- `connector_type`
- `mode`

---

## Prometheus (pull)

### Orchestrated mode (recommended)

Start orchestrated mode and expose a Prometheus endpoint (default `:9400/metrics`):

```bash
export DATIVO_METRICS_ENABLED=true
export DATIVO_METRICS_PROMETHEUS_ENABLED=true
export DATIVO_METRICS_PROMETHEUS_PORT=9400

# Optional (recommended): shared directory for multi-process aggregation
export DATIVO_PROMETHEUS_MULTIPROC_DIR=.local/prometheus

dativo start orchestrated --runner-config configs/runner.yaml
```

Then scrape:

```bash
curl -s http://localhost:9400/metrics | head
```

### Notes on subprocess execution

In orchestrated mode, jobs are executed in subprocesses. Prometheus metrics are aggregated using **Prometheus multiprocess mode** (`PROMETHEUS_MULTIPROC_DIR`) so the single `/metrics` endpoint reflects recent job activity.

---

## OpenTelemetry (push)

### One-shot jobs (recommended)

Enable OTLP/HTTP export by setting an endpoint:

```bash
export DATIVO_OTEL_METRICS_ENDPOINT=http://otel-collector:4318/v1/metrics

dativo ingest --config jobs/acme/stripe_customers_to_iceberg.yaml --mode self_hosted
```

You can also use the standard OTEL environment variable:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
```

---

## Disabling metrics

Disable all metrics:

```bash
export DATIVO_METRICS_ENABLED=false
```

