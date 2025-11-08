# Runner & Orchestration

This doc describes how the **self‑service Docker image** runs jobs in two modes: **orchestrated** (Dagster or Airflow) and **oneshot**.

## Modes

### Orchestrated (default)
- Bundles a lightweight Dagster instance when `type: dagster`.
- `type: airflow` generates deployable DAG files for an external Airflow instance.
- Reads schedules from `runner.yaml` (Dagster) or `runner_airflow.yaml` (Airflow example).
- Ensures **serial per‑tenant** execution to avoid Nessie commit conflicts.

**Dagster example `runner.yaml`:**
```yaml
runner:
  mode: orchestrated
  orchestrator:
    type: dagster
    schedules:
      - name: stripe_customers_hourly
        config: /app/jobs/acme/stripe_customers_to_iceberg.yaml
        cron: "0 * * * *"
      - name: hubspot_contacts_daily
        config: /app/jobs/acme/hubspot_contacts_to_iceberg.yaml
        cron: "15 2 * * *"
    concurrency_per_tenant: 1
```

**Start Dagster orchestrator:**
```bash
docker run --rm -p 3000:3000 \
  -v $(pwd)/connectors:/app/connectors:ro \
  -v $(pwd)/assets:/app/assets:ro \
  -v $(pwd)/jobs:/app/jobs \
  -v $(pwd)/configs:/app/configs \
  -v $(pwd)/secrets:/app/secrets \
  -v $(pwd)/state:/app/state \
  our-registry/ingestion:1.0 start orchestrated --runner-config /app/configs/runner.yaml
```

**Airflow example `runner_airflow.yaml`:**
```yaml
runner:
  mode: orchestrated
  orchestrator:
    type: airflow
    airflow:
      dag_output_dir: /app/dags
      dag_file_prefix: dativo_
      catchup: false
    schedules:
      - name: stripe_customers_hourly
        config: /app/jobs/acme/stripe_customers_to_iceberg.yaml
        cron: "0 * * * *"
      - name: hubspot_contacts_daily
        config: /app/jobs/acme/hubspot_contacts_to_iceberg.yaml
        interval_seconds: 21600
    concurrency_per_tenant: 1
```

**Generate Airflow DAGs:**
```bash
docker run --rm \
  -v $(pwd)/connectors:/app/connectors:ro \
  -v $(pwd)/assets:/app/assets:ro \
  -v $(pwd)/jobs:/app/jobs \
  -v $(pwd)/configs:/app/configs \
  -v $(pwd)/secrets:/app/secrets \
  -v $(pwd)/state:/app/state \
  -v $(pwd)/airflow/dags:/app/dags \
  our-registry/ingestion:1.0 start orchestrated --runner-config /app/configs/runner_airflow.yaml
```
Generated DAGs are written to `/app/dags` (mount to Airflow `dags/` directory). Deploy them to Airflow and enable the DAGs there.

### One‑shot
Run a single job and exit:
```bash
docker run --rm \
  -v $(pwd)/connectors:/app/connectors:ro \
  -v $(pwd)/assets:/app/assets:ro \
  -v $(pwd)/jobs:/app/jobs \
  -v $(pwd)/configs:/app/configs \
  -v $(pwd)/secrets:/app/secrets \
  -v $(pwd)/state:/app/state \
  our-registry/ingestion:1.0 run --config /app/jobs/acme/stripe_customers_to_iceberg.yaml --mode self_hosted
```

## Logs & Exit Codes
- Structured JSON logs; secret redaction enabled when `logging.redaction: true`.
- Exit codes: `0=success`, `1=partial`, `2=failure`.

## Notes
- **No service adapters** included in MVP; outbound integrations can be added later.
- /registry/connectors.yaml provides default engines and capability flags. YAML **engine** blocks are optional overrides.
