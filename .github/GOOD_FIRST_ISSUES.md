# Good First Issues - Ideas

This document contains ideas for "good first issue" labels to help new contributors get started.

## Documentation Improvements

### 1. Add Architecture Diagram

**Title:** Create visual architecture diagram for README

**Description:**
We need a clear visual representation of Dativo's architecture showing the flow from sources → Dativo → S3/Iceberg.

**What to do:**
1. Create a diagram (PNG or SVG) showing:
   - Data sources (Stripe, Postgres, etc.)
   - Dativo components (CLI, Dagster, connectors, etc.)
   - Targets (S3, MinIO, Iceberg)
   - Data flow arrows
2. Save to `assets/architecture-diagram.png`
3. Add to README.md in the Architecture section
4. Ensure it's accessible (alt text, clear labels)

**Skills needed:** Diagramming (draw.io, Excalidraw, etc.), basic understanding of data pipelines

**Estimated effort:** 2-3 hours

**Good for:** First-time contributors, designers, technical writers

---

### 2. Add Connector Comparison Matrix

**Title:** Create detailed connector comparison table

**Description:**
Add a comprehensive comparison matrix showing capabilities of each connector (incremental sync, rate limiting, batch size, etc.)

**What to do:**
1. Create a markdown table in `docs/CONNECTOR_COMPARISON.md`
2. Columns: Connector, Type, Incremental Sync, Batch Size, Rate Limiting, Auth Methods, Self-hosted/Cloud
3. Fill in for all existing connectors (Stripe, HubSpot, Postgres, CSV, etc.)
4. Link from README and docs/INDEX.md

**Skills needed:** Research, markdown tables, basic understanding of connectors

**Estimated effort:** 2-3 hours

**Good for:** First-time contributors, technical writers

---

### 3. Add Troubleshooting Guide

**Title:** Create comprehensive troubleshooting guide

**Description:**
Consolidate common errors and solutions into a single troubleshooting guide.

**What to do:**
1. Create `docs/TROUBLESHOOTING.md`
2. Sections: Connection errors, Schema validation errors, S3/MinIO errors, Plugin errors
3. For each error: symptom, cause, solution, prevention
4. Include common CLI commands for debugging
5. Link from docs/INDEX.md and README

**Skills needed:** Technical writing, basic understanding of the platform

**Estimated effort:** 3-4 hours

**Good for:** Users who've encountered issues and want to help others

---

## Code Improvements

### 4. Add `dativo version` Command

**Title:** Implement `dativo version` command to show version info

**Description:**
Currently `dativo --version` might not work as expected. We need a proper version command.

**What to do:**
1. Update `src/dativo_ingest/cli.py` to add version command
2. Show: version number (from pyproject.toml), Python version, platform
3. Add test in `tests/test_cli.py`
4. Update README with example output

**Skills needed:** Python, CLI development (Click/argparse), pytest

**Estimated effort:** 1-2 hours

**Good for:** Python developers new to the codebase

**Files to modify:**
- `src/dativo_ingest/cli.py`
- `tests/test_cli.py`
- `README.md`

---

### 5. Add Progress Bar for Large Extractions

**Title:** Add progress bar for data extraction

**Description:**
When extracting large datasets, users have no visibility into progress. Add a progress bar using `tqdm`.

**What to do:**
1. Add `tqdm` to `pyproject.toml` dependencies
2. Wrap extraction loops in CSV extractor with progress bar
3. Show: current batch, total records, estimated time remaining
4. Make it optional (disable in CI/non-TTY environments)
5. Add tests

**Skills needed:** Python, CLI development, testing

**Estimated effort:** 2-3 hours

**Good for:** Python developers comfortable with CLI tools

**Files to modify:**
- `pyproject.toml`
- `src/dativo_ingest/connectors/csv_extractor.py`
- Tests

---

### 6. Improve Error Messages for Missing Secrets

**Title:** Better error messages when secrets are not found

**Description:**
When secrets are missing, the error message is generic. We should provide actionable guidance.

**What to do:**
1. Update secret managers to provide specific error messages
2. Include: which secret is missing, expected location, how to create it
3. Example: "Secret 'stripe' not found for tenant 'acme'. Expected at: secrets/acme/stripe.json. See docs/SECRET_MANAGEMENT.md"
4. Add tests for error scenarios

**Skills needed:** Python, error handling, testing

**Estimated effort:** 2-3 hours

**Good for:** Python developers interested in UX improvements

**Files to modify:**
- `src/dativo_ingest/secrets/managers/*.py`
- Tests

---

## Testing Improvements

### 7. Add Integration Test for MySQL Connector

**Title:** Create integration tests for MySQL connector

**Description:**
MySQL connector exists but lacks comprehensive integration tests.

**What to do:**
1. Create `tests/integration/test_mysql_integration.py`
2. Use Docker Compose to spin up MySQL instance
3. Test: connection, full sync, incremental sync, schema validation
4. Follow patterns from `test_postgres_integration.py`
5. Add to CI workflow

**Skills needed:** Python, pytest, Docker, MySQL

**Estimated effort:** 3-4 hours

**Good for:** Developers familiar with MySQL and testing

**Files to create:**
- `tests/integration/test_mysql_integration.py`
- `tests/fixtures/mysql/*` (test data)

---

### 8. Add Smoke Test for Rust Plugins

**Title:** Create end-to-end smoke test for Rust plugin pipeline

**Description:**
We have Rust plugins but no automated smoke test for the full pipeline.

**What to do:**
1. Create smoke test script: `tests/smoke_test_rust_pipeline.sh`
2. Build Rust plugins
3. Run job with Rust reader + Rust writer
4. Verify output files and state
5. Add to GitHub Actions workflow

**Skills needed:** Bash scripting, Rust (basic), testing

**Estimated effort:** 2-3 hours

**Good for:** Developers interested in Rust or testing

---

## New Features (Small)

### 9. Add `dativo validate` Command

**Title:** Add command to validate job config without running

**Description:**
Users want to validate their YAML configs without actually running jobs.

**What to do:**
1. Add `dativo validate --config job.yaml` command
2. Check: YAML syntax, required fields, connector/asset paths exist, schema validation
3. Output: clear success/error messages with line numbers for issues
4. Add tests
5. Document in README

**Skills needed:** Python, YAML parsing, validation logic

**Estimated effort:** 3-4 hours

**Good for:** Python developers interested in CLI development

**Files to modify:**
- `src/dativo_ingest/cli.py`
- `src/dativo_ingest/validator.py` (extend)
- Tests

---

### 10. Add Support for .env Files in Secret Manager

**Title:** Support .env files for environment-based secret manager

**Description:**
Currently env secret manager only reads from process environment. Support loading from .env files.

**What to do:**
1. Update `src/dativo_ingest/secrets/managers/env.py`
2. Add optional `--env-file` parameter to CLI
3. Use `python-dotenv` to load .env file
4. Merge with process environment (process env takes precedence)
5. Add tests
6. Document in SECRET_MANAGEMENT.md

**Skills needed:** Python, environment variables, testing

**Estimated effort:** 2-3 hours

**Good for:** Python developers familiar with environment management

**Files to modify:**
- `src/dativo_ingest/secrets/managers/env.py`
- `src/dativo_ingest/cli.py`
- `docs/SECRET_MANAGEMENT.md`
- Tests

---

## How to Use This Document

**For maintainers:**
1. Create GitHub issues from these ideas
2. Add `good first issue` label
3. Add `help wanted` label if appropriate
4. Add specific labels (documentation, testing, enhancement)
5. Reference this document in the issue

**For contributors:**
1. Pick an issue that interests you
2. Comment on the issue to claim it
3. Ask questions if anything is unclear
4. Submit a PR when ready
5. Reference the issue in your PR

**Template for creating GitHub issue:**

```markdown
**Issue Title:** [Copy from above]

**Description:** [Copy from above]

**What to do:** [Copy checklist from above]

**Skills needed:** [Copy from above]

**Estimated effort:** [Copy from above]

**Getting Started:**
1. Fork the repository
2. Read CONTRIBUTING.md
3. Set up your development environment
4. Comment on this issue if you have questions
5. Submit a PR when ready

**Resources:**
- [CONTRIBUTING.md](.github/CONTRIBUTING.md)
- [SETUP_AND_TESTING.md](docs/SETUP_AND_TESTING.md)
- [Documentation Index](docs/INDEX.md)
```

---

## Priority Recommendations

**For first batch of "good first issue" labels:**

1. **Add Architecture Diagram** (high visibility, helps everyone)
2. **Add `dativo version` Command** (small, well-defined, immediate value)
3. **Improve Error Messages for Missing Secrets** (UX improvement, clear scope)

These three provide:
- One documentation improvement
- One small code feature
- One UX enhancement

And they're all achievable in 1-3 hours, perfect for first-time contributors.
