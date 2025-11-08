# Test Job Configurations

This directory contains job configurations for smoke tests.

## Structure

Job configurations can be:
1. **Generated automatically** during smoke test execution (saved here for reference)
2. **Created manually** as example/reference configurations

Each job configuration follows the pattern:

`{dataset_name}_{asset_name}_to_iceberg.yaml`

For example:
- `adventureworks_person_to_iceberg.yaml` (example included)
- `music_listening_listening_history_to_iceberg.yaml`
- `employee_employee_to_iceberg.yaml`

## Example Job

An example job configuration (`adventureworks_person_to_iceberg.yaml`) is included to demonstrate:
- CSV source connector configuration
- Iceberg target connector configuration
- Asset definition reference
- Source and target overrides
- Infrastructure metadata linking to externally managed runtimes (provider, runtime type, resource identifiers, tags)
- Environment variable usage

## Usage

These job configurations demonstrate how to configure CSV to Iceberg ingestion jobs for different datasets.

## Generating Job Configurations

You can generate job configurations in two ways:

### Option 1: Generate from Datasets (Recommended)

Use the helper script to generate jobs for all available datasets:

```bash
python tests/fixtures/jobs/generate_example_jobs.py
```

This script:
- Reads `tests/fixtures/datasets.yaml` to discover available datasets
- Generates job configurations for each asset
- Saves them to `tests/fixtures/jobs/`

### Option 2: Generate Before Running Smoke Tests

Generate job configurations before running smoke tests:

```bash
# Generate all jobs
python tests/fixtures/jobs/generate_example_jobs.py

# Then run smoke tests
dativo_ingest run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets
```

## E2E Smoke Test Startup

For E2E smoke tests, you can run jobs from this directory using:

```bash
# Run a specific job
dativo_ingest run --config tests/fixtures/jobs/adventureworks_person_to_iceberg.yaml --mode self_hosted

# Or use a runner config to load all jobs
dativo_ingest start orchestrated --runner-config tests/fixtures/runner.yaml
```

Note: Before running E2E tests, ensure:
1. Observability is set up (logging, metrics, tracing)
2. Secrets are loaded from secrets storage
3. Required environment variables are set
4. Test infrastructure is available (MinIO, Nessie, etc.)

