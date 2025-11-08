# Runner & Orchestration

This doc describes how the **self‑service Docker image** runs jobs in two modes: **orchestrated** (Dagster or Airflow) and **oneshot**.

## Modes

### Orchestrated (default)
- Supports both **Dagster** and **Airflow** orchestrators.
- Reads schedules from `runner.yaml`.
- Ensures **serial per‑tenant** execution to avoid Nessie commit conflicts.

#### Dagster Orchestrator (default)

**Example `runner.yaml`:**
```yaml
runner:
  mode: orchestrated
  orchestrator:
    type: dagster  # Default orchestrator
    schedules:
      - name: stripe_customers_hourly
        config: /app/jobs/acme/stripe_customers_to_iceberg.yaml
        cron: "0 * * * *"
      - name: hubspot_contacts_daily
        config: /app/jobs/acme/hubspot_contacts_to_iceberg.yaml
        cron: "15 2 * * *"
    concurrency_per_tenant: 1
```

#### Airflow Orchestrator

**Example `runner_airflow.yaml`:**
```yaml
runner:
  mode: orchestrated
  orchestrator:
    type: airflow  # Use Airflow instead of Dagster
    schedules:
      - name: stripe_customers_hourly
        config: /app/jobs/acme/stripe_customers_to_iceberg.yaml
        cron: "0 * * * *"
        enabled: true
        timezone: "UTC"
        max_concurrent_runs: 1
        tags:
          environment: "production"
          priority: "high"
      - name: hubspot_contacts_daily
        config: /app/jobs/acme/hubspot_contacts_to_iceberg.yaml
        interval_seconds: 21600  # 6 hours
        enabled: true
        timezone: "America/New_York"
    concurrency_per_tenant: 1
```

**Start Dagster:**
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

**Start Airflow:**
```bash
# Start with Airflow configuration
docker run --rm -p 8080:8080 \
  -v $(pwd)/connectors:/app/connectors:ro \
  -v $(pwd)/assets:/app/assets:ro \
  -v $(pwd)/jobs:/app/jobs \
  -v $(pwd)/configs:/app/configs \
  -v $(pwd)/secrets:/app/secrets \
  -v $(pwd)/state:/app/state \
  our-registry/ingestion:1.0 start orchestrated --runner-config /app/configs/runner_airflow.yaml

# Then start Airflow services (in separate terminals or as background processes):
# 1. Initialize Airflow database
airflow db init

# 2. Start Airflow webserver
airflow webserver --port 8080

# 3. Start Airflow scheduler
airflow scheduler
```

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
