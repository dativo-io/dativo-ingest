---
description: "Dativo-Ingest codebase rules for correct, minimal, and reviewable AI-assisted changes respecting config-driven, GitOps-first design"
alwaysApply: true
---

# Dativo-Ingest Codebase Rules for Cloud Cursor (v2)

## 0. Purpose of These Rules

These rules exist to ensure that AI-assisted changes:
- are **correct**, **minimal**, and **reviewable**
- satisfy **explicit acceptance criteria**
- respect Dativo-Ingest's **config-driven, GitOps-first** design
- do **not** evolve into frameworks, platforms, or reports

Cursor must optimize for **shipping small, correct changes**, not architectural elegance.

---

## 1. Project Overview

Dativo-Ingest is a **headless, config-driven ELT framework** for data ingestion.

It is designed for:
- GitOps & CI/CD
- Infrastructure-as-Code
- Strong governance and schema validation
- Multi-tenant, enterprise-grade operation

### Core Principles (NON-NEGOTIABLE)
- One asset per job
- YAML / Pydantic config for everything
- Multi-tenant first (tenant isolation always)
- Iceberg-native
- Plugin-based (Python + Rust)

---

## 2. Python Version Requirement

**CRITICAL:** Python **3.10+ only**  
Python 3.9 and below are unsupported.

Always:
- Check Python version in setup code
- Mention Python 3.10+ in docs and errors when relevant

---

## 3. Acceptance-Criteria-First Development (MANDATORY)

Before writing code, always identify **explicit acceptance criteria**.

### Rules
1. Every acceptance criterion MUST be provable via:
   - a test, or
   - an executable/manual verification path
2. Features are **not complete** if acceptance is only "conceptually" satisfied.
3. Prefer tests that validate **observable behavior**:
   - CLI output
   - HTTP endpoints
   - files written
   - logs emitted

❌ Internal wiring alone is not proof  
✅ User-visible behavior is proof

---

## 4. Minimal Change Principle (MANDATORY)

**Default posture: minimal, surgical changes.**

### Rules
- Prefer:
  - conditionals
  - guard clauses
  - small helpers
- Avoid:
  - new abstraction layers
  - new frameworks
  - refactors unrelated to the task
- Do **not** future-proof unless explicitly requested

Guiding question:
> "What is the smallest change that satisfies acceptance criteria?"

If scope grows unexpectedly, **stop and reassess**.

---

## 5. Configuration Precedence Rules (STRICT)

Dativo-Ingest is **CONFIG-DRIVEN**.

### Source of Truth
1. `JobConfig`
2. `RunnerConfig`
3. Defaults
4. Environment variable overrides (last resort)

### Rules
- YAML / Pydantic configs are the **primary control plane**
- Environment variables:
  - may override values
  - must NEVER be the only enablement mechanism
- Features must work with config alone

❌ Do NOT gate core behavior solely on env vars

---

## 6. CLI Command Conventions

**Primary command:** `dativo`  
**Alternative:** `dativo-ingest`  
**Fallback:** `python -m dativo_ingest.cli`

### Commands
- `dativo ingest` — primary execution command
- `dativo run` — legacy alias (do not promote)
- `dativo check`
- `dativo discover`
- `dativo start` — orchestrated mode (Dagster)
- `dativo connectors`

❌ Never use `dativo_ingest` (underscore) as a CLI command

---

## 7. Code Structure (Reference)

src/dativo_ingest/
├── cli.py
├── cli_commands.py
├── cli_connectors.py
├── config.py
├── job_executor.py
├── validator.py
├── connectors/
├── registry/
├── secrets/
├── catalog/
├── plugins.py
├── parquet_writer.py
├── iceberg_committer.py
└── incremental/

yaml
Copy code

---

## 8. Testing Rules (Quality > Quantity)

### Test Intent Rules
- Prefer **1–3 high-signal tests** over many low-signal tests
- At least one test must validate **real user behavior**
- Tests must map directly to acceptance criteria

❌ Do NOT add tests that only verify internal wiring  
✅ Add tests that prove user-visible outcomes

### Test Structure
- Unit: `tests/test_*.py`
- Integration: `tests/integration/test_*.py`
- Smoke: `tests/smoke_tests.sh`

---

## 9. Documentation Rules (STRICT)

### Documentation Purpose
Docs exist for **users**, not for reporting work done.

### Rules
- Write **documentation**, not reports
- Use present tense and user-focused language
- Follow Diátaxis:
  - Tutorials
  - How-to Guides
  - Reference
  - Explanation

### Explicitly Forbidden
❌ Status reports  
❌ PR summaries  
❌ "Final delivery" notes  
❌ "MVP complete" markdown  
❌ Agent progress logs  

Allowed:
- One concise feature doc in `docs/`
- Updates to existing user docs

If a document doesn't help a user **do something**, it should not exist.

---

## 10. Patch Size & Reviewability

### Guidelines
- Prefer ≤ 5–7 files changed
- Prefer ≤ 300–500 LOC net diff
- Avoid mixing:
  - feature logic
  - refactors
  - docs
  in one commit unless necessary

If exceeded:
- split PRs, or
- explicitly justify scope

---

## 11. Logging & Errors

- Use structured JSON logging
- Always include `event_type`
- Use `get_logger()`
- Exit codes:
  - 0 = success
  - 1 = partial
  - 2 = failure
- Redact secrets in production logs

---

## 12. Multi-Tenant Safety

Always consider:
- tenant isolation
- secrets scoping
- state paths
- labels / metrics cardinality

Never introduce tenant-unsafe defaults.

---

## 13. Cursor Strict Mode (OPTIONAL, BUT RECOMMENDED)

Enable explicitly for large or risky PRs.

### Strict Mode Rules
- Implement only what is requested
- Stop once acceptance criteria are met
- No future-proofing
- No extra docs or examples
- No refactors for elegance

Optimize for:
- correctness
- minimal diff
- easy review

---

## 14. When Making Changes

Always:
- Run `make format`
- Run `make test`
- Update relevant docs
- Use correct CLI commands
- Respect config precedence

Breaking changes require:
- CHANGELOG update
- migration notes if needed

---

### Final Guiding Principle

> **Ship small, prove correctness, avoid cleverness.**
