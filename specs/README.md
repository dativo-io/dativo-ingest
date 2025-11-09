# Dativo Data Contracts (`specs/`)

This directory contains production-aligned data contracts expressed in ODCS v3.0.2 with dativo extensions. Contracts govern schema, lineage, governance, FinOps metadata, and AI context generation for each source system supported by Dativo Ingest.

## Layout

```
specs/
├── <connector>/               # Connector key (csv, hubspot, postgres, …)
│   └── vMAJOR.MINOR/          # Semantic version family for the contract
│       └── <contract>.yaml    # Individual contract (semver MAJOR.MINOR.PATCH inside)
└── README.md
```

Example:
```
specs/
  csv/v1.0/person.yaml
  hubspot/v1.0/contacts.yaml
  stripe/v1.0/customers.yaml
```

## Authoring Guidelines

Every contract MUST:
- Reference `schemas/odcs/dativo-odcs-3.0.2-extended.schema.json`
- Include `apiVersion: v3.0.2`, `kind: DataContract`, and a globally unique `id`
- Specify `team.owner`, `compliance.classification`, `compliance.retention_days`, and `finops.cost_center`
- Provide `lineage` entries with `from_asset`, `to_asset`, and `contract_version`
- Maintain an `audit` trail with `author`, `timestamp`, and SHA-256 `hash`

Semantic versioning rules:
- PATCH (`x.y.z+1`) for backward-compatible field additions or metadata tweaks
- MINOR (`x.y+1.0`) for additive changes requiring downstream awareness
- MAJOR (`x+1.0.0`) for breaking schema changes (field removals, type changes, stricter requirements)

## Workflow

1. Draft or update the contract under `specs/<source>/vMAJOR.MINOR/<name>.yaml`.
2. Run validation (see `tests/test_config.py`) to ensure ODCS compliance.
3. Update any job configs referencing the contract.
4. Record the change in the contract’s `audit` section with a fresh hash.

Contracts power three downstream artifacts:
- **ODCS JSON** for catalog exchange
- **dbt YAML** (sources/models/exposures) via transformation utilities
- **AI context payloads** exposed through `/api/v1/metadata/ai_context`

Refer to `docs/CONFIG_REFERENCE.md` and `docs/MARKDOWN_KV_STORAGE.md` for practical examples.
