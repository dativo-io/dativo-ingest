## 📌 `IMPLEMENTATION_PLAN.md`

```markdown
# Implementation Plan – Ingestion Platform (v1.1)

## 🏁 Summary
Phased implementation plan for the ingestion platform MVP and v1.1, incorporating OSS connector wrapping, schema enforcement, Iceberg/Nessie commits, metadata emission, tenant isolation, and FinOps/governance observability.

---

## 📐 Milestones & Timeline

### ✅ M1.1 – Core Framework (COMPLETE)
- ✅ Repo scaffolding, Docker build
- ✅ Config loader + validator using static connector catalog
- ✅ **Bundled Dagster orchestrator scaffold** with `runner.yaml` (default orchestrated mode) and oneshot mode
- ✅ **Assets‑as‑code** under `/assets/**` with ODCS v3.0.2 compliance
- ✅ Decoupled architecture (connectors, assets, jobs)
- ✅ Structured logging with secret redaction
- ✅ Secrets management
- ✅ Infrastructure validation
- ✅ Startup sequence orchestration
- ✅ State management for incremental syncs
- ✅ Markdown-KV storage support (three patterns)
- ✅ Industry-standard test structure
- ✅ CLI-first smoke tests

**See**: `docs/MILESTONE_1_1_COMPLETE.md` for full details

### ✅ M2 – Parquet + Iceberg Commit Path (Weeks 2–3)
- Schema validator with `required: true` + type enforcement
- Parquet writer + Nessie commit logic
- Validate `asset_path` against asset definition (enable strict mode)

### ✅ M3 – OSS Connector Wrappers (Weeks 3–5)
- Stripe, HubSpot, GDrive CSV, GSheets, Postgres/MySQL (self‑hosted only)
- State tracking, cursor handling, error retries
- Dagster schedules & retries mapped to job exit codes

### ✅ M4 – Governance + FinOps + Metadata (Weeks 5–6)
- `asset` supports `governance` + `business` tags
- Run metadata includes: `cpu_time_sec`, `api_calls`, `tags`, lineage

### ✅ M5 – Local Dev + Validator (Week 6–7)
- Dev stack: MinIO + Nessie (via Compose)
- Add microbatch mode and lookback
- SaaS‑mode DB validation block

### ✅ M6 – End‑to‑End Tests & Acceptance (Weeks 7–8)
- Integration tests: schema enforcement, incremental, commit idempotency
- Metadata validation (against schema), logs, FinOps stats

---

## 📤 Deliverables
- Docker image: `ingestion:<semver>`
- Volumes: `/configs`, `/specs` (ro), `/secrets`, `/state`, `/logs`
- /registry/connectors.yaml (types & defaults), /schemas/*.json (CI validation).
- Examples: YAMLs, metadata payload, asset definitions, `runner.yaml`

---
```
