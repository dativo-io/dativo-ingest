# Test Asset Definitions

This directory contains asset definitions (ODCS v3.0.2 YAML schemas) specifically for smoke tests. These define the **structure and governance** of data, not the data itself.

## Distinction from Test Data

- **Asset Definitions** (this directory): YAML files that define schema, governance, compliance rules
- **Test Data** (`../seeds/`): CSV files containing actual sample data rows

For example:
- `assets/csv/v1.0/person.yaml` - Defines the schema for Person data (what fields exist, their types, governance)
- `../seeds/adventureworks/Person.csv` - Contains actual person records (the data itself)

## Structure

- `csv/v1.0/` - Asset definitions for CSV source connectors used in smoke tests

## ODCS Alignment

All asset definitions:
- Follow ODCS v3.0.2 flat structure (no nested `asset:` wrapper)
- Reference the extended schema via `$schema: schemas/odcs/dativo-odcs-3.0.2-extended.schema.json`
- Include `apiVersion: v3.0.2` to indicate ODCS version
- Extend ODCS with dativo-specific fields: `source_type`, `object`, `target`, `compliance`, `change_management`

## Governance Requirements

All asset definitions satisfy the following governance requirements:

1. **Strong Ownership**: `team.owner` is required (not optional)
2. **Regulatory Compliance**: `compliance` section with regulations, security, access control, user consent, data retention
3. **Data Quality Monitoring**: `data_quality.monitoring.enabled` with `oncall_rotation` (required if monitoring enabled)
4. **Change Management**: `change_management` section with policy, approval, notifications, version history

## Asset Definitions

### AdventureWorks Assets
- `person.yaml` - Person/contact data schema
- `sales_order_header.yaml` - Sales order header schema
- `product.yaml` - Product catalog schema

### Music Listening Assets
- `listening_history.yaml` - Music listening history schema

### Employee Assets
- `employee.yaml` - Employee dataset schema (includes PII and SENSITIVE classification)

## Usage

These asset definitions are used by smoke tests. They are separate from production asset definitions to ensure test isolation. Smoke tests run the CLI directly with test fixtures.

The tests use these asset definitions together with the corresponding CSV data files from `../seeds/` to perform end-to-end ingestion tests.

## Schema Reference

Each asset definition explicitly references the extended ODCS schema:
```yaml
$schema: schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
```

The extended schema (`schemas/odcs/dativo-odcs-3.0.2-extended.schema.json`) extends the base ODCS 3.0.2 schema (`schemas/odcs/odcs-3.0.2.schema.json`) with dativo-specific fields.
