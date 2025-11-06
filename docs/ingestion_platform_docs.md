# Architecture Overview: Ingestion Platform (v1.1)

> **Updates (2025‑11‑05):** Bundled **Dagster** as the default orchestrator for self‑service runs. Introduced optional `engine` overrides for **sources** and **targets** (registry‑driven defaults). No service adapters are included at this stage.

## 🧱 High‑Level Architecture

The ingestion platform is a **headless, config‑driven ingestion engine** designed for SaaS and self‑hosted modes. It uses standard OSS connectors (Airbyte, Singer, Meltano), and lands validated Parquet files into **Iceberg tables** via **Nessie catalog**. Jobs are Dockerized, one‑shot or orchestrated, and tenant‑isolated.

### 📦 Components
- **Orchestrator (Dagster, bundled)**: optional; schedules/executes jobs defined in `runner.yaml`.
- **Runner Engine (Docker)**: stateless per job; supports **oneshot** or **orchestrated** modes.
- **Connector Plugin Wrapper**: runs OSS taps (Airbyte, Singer) with YAML‑based configs.
- **Schema Validator**: applies strict `asset.schema` typing with `required: true` enforcement (M2).
- **Parquet Writer**: batches records into partitioned Parquet files (128–200 MB) (M2).
- **Iceberg/Nessie Committer**: atomic commit to tenant branch (M2).
- **State Store**: tracks incremental cursor per object (M3).
- **Metadata Emitter**: outputs OpenMetadata‑compatible run record (M4).

### 🧭 Engines (optional overrides)
Default extraction/loader engines come from **/registry/connectors.yaml**; execution metadata and endpoint/pagination hints are in **/registry/templates/<connector>.yaml**.Advanced jobs may override:

```yaml
source:
  type: hubspot
  engine:
    type: airbyte   # airbyte | singer | native | jdbc
    options:
      airbyte:
        docker_image: "airbyte/source-hubspot:1.0.15"

target:
  type: iceberg
  engine:
    type: native    # native | spark | meltano
    options:
      native:
        batch_size_rows: 50000
```
If `engine` is omitted, the registry default is used.

---

## 🧾 Config & Metadata Enhancements

### ✅ Consolidated YAML (Job + Schema reference)
```yaml
tenant_id: acme

source:
  type: gdrive_csv
  files:
    - file_id: 1a2B3cGDRIVEID
      object: deals_daily
  incremental:
    strategy: file_modified_time

target:
  type: iceberg
  catalog: nessie
  branch: acme
  warehouse: s3://lake/acme/
  file_format: parquet

logging:
  redaction: true

asset_definition: /app/specs/gdrive_csv/v1.0/deals_daily.yaml
```

### 🧑‍✈️ Runner Orchestration Config
```yaml
runner:
  mode: orchestrated
  orchestrator:
    type: dagster
    schedules:
      - name: stripe_hourly
        config: /app/configs/examples/stripe.yaml
        cron: "0 * * * *"
    concurrency_per_tenant: 1
```

---

## 🧰 Developer Experience

Mount `/specs` read‑only in local compose and Docker runs.

---

## 🔄 Tenancy, Isolation & FinOps

(unchanged)

---

## 📌 Implementation Notes

- Connector registry (`connectors.json`) includes `default_engine` and `engines_supported` for both **sources** and **targets**.
- Exit codes: `0=success`, `1=partial`, `2=hard fail` (unchanged).

---

## ✅ MVP Complete When
- Orchestrated mode can start and invoke jobs from `runner.yaml` (no schema/commit logic in M1).
- Iceberg path complete in M2; state in M3.
