# Test Data Contracts

This directory contains ODCS v3.0.2 data contracts used by smoke tests. Each YAML file defines the **structure, governance, compliance, and FinOps metadata** for a dataset – the data itself lives in `../seeds/`.

## Directory Structure

```
tests/fixtures/specs/
├── csv/v1.0/            # Contracts for CSV-based fixtures
├── markdown_kv/v1.0/    # Contracts for Markdown-KV fixtures
└── README.md            # This file
```

## What Lives Here
- **Format**: Open Data Contract Standard (ODCS) v3.0.2 + dativo extensions
- **Content**: Schema fields, classification, retention policies, lineage and audit trails, FinOps cost centers
- **Example**: `csv/v1.0/person.yaml` defines the contract for the `Person.csv` seed dataset

## Relationship to Seeds
- **Contracts (`specs/`)** describe the data _shape_ and governance.
- **Seeds (`../seeds/`)** provide the actual rows used during tests.

Smoke tests load data from `seeds/` and validate it against these contracts to ensure ingestion, schema validation, and governance checks all succeed.

## Contract Requirements
All contracts in this directory:
- Reference the extended schema `schemas/odcs/dativo-odcs-3.0.2-extended.schema.json`
- Specify `apiVersion: v3.0.2` and `kind: DataContract`
- Include `team.owner`, `compliance.classification`, `compliance.retention_days`, and `finops.cost_center`
- Provide lineage edges and an audit trail (`author`, `timestamp`, `hash`)

## Adding a New Fixture
1. Create the dataset under `../seeds/<dataset>/`.
2. Author a contract under `specs/<source>/vMAJOR.MINOR/<name>.yaml`.
3. Reference the contract from a job configuration in `../jobs/`.
4. Update `../datasets.yaml` with mapping details.

This keeps fixtures self-contained and guarantees every smoke test remains ODCS-compliant.
