# Runner & Orchestration

This doc describes how the **self‑service Docker image** runs jobs in two modes: **orchestrated** (Dagster) and **oneshot**.

## Modes

### Orchestrated (default)
- Bundles a lightweight Dagster instance.
- Reads schedules from `runner.yaml`.
- Ensures **serial per‑tenant** execution to avoid Nessie commit conflicts.

**Example `runner.yaml`:**
```yaml
runner:
  mode: orchestrated
  orchestrator:
    type: dagster
    schedules:
      - name: stripe_hourly
        config: /app/configs/examples/stripe.yaml
        cron: "0 * * * *"
      - name: hubspot_daily
        config: /app/configs/examples/hubspot.yaml
        cron: "15 2 * * *"
    concurrency_per_tenant: 1
```

**Start:**
```bash
docker run --rm -p 3000:3000   -v $(pwd)/configs:/app/configs   -v $(pwd)/specs:/app/specs:ro   our-registry/ingestion:1.0 start orchestrated --runner-config /app/configs/runner.yaml
```

### One‑shot
Run a single job and exit:
```bash
docker run --rm   -v $(pwd)/configs:/app/configs   -v $(pwd)/specs:/app/specs:ro   our-registry/ingestion:1.0 run --config /app/configs/examples/stripe.yaml --mode self_hosted
```

## Logs & Exit Codes
- Structured JSON logs; secret redaction enabled when `logging.redaction: true`.
- Exit codes: `0=success`, `1=partial`, `2=failure`.

## Notes
- **No service adapters** included in MVP; outbound integrations can be added later.
- /registry/connectors.yaml provides default engines and capability flags. YAML **engine** blocks are optional overrides.
