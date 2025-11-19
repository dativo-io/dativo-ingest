# Schema Validation Guide

This guide explains how schema validation works in dativo-ingest, including YAML registry validation against JSON schemas and asset schema validation during ingestion.

## Table of Contents

1. [Overview](#overview)
2. [Registry Schema Validation](#registry-schema-validation)
3. [Asset Schema Validation](#asset-schema-validation)
4. [Validation During Ingestion](#validation-during-ingestion)
5. [Additional Resources](#additional-resources)

---

## Overview

Dativo-ingest uses schema validation at multiple levels:

1. **Registry Validation**: Validates connector registry YAML files against JSON schemas
2. **Asset Schema Validation**: Validates data records against asset definitions during ingestion
3. **Configuration Validation**: Validates job configurations against connector capabilities

---

## Registry Schema Validation

The connector registry (`/registry/connectors.yaml`) is validated against a JSON schema to ensure consistency and correctness.

### What We Validate

- `/registry/connectors.yaml` → `/schemas/connectors.schema.json`

The schema ensures:
- All connectors have required fields (roles, category, default_engine, etc.)
- Connector capabilities are properly defined
- Incremental strategies are valid
- Engine configurations are correct

### Local Setup

**Prerequisites:**
- Node.js 18+ (or use nvm)

**Installation:**
```bash
# Install dev dependencies
npm i --include=dev
```

**Validation:**
```bash
# Validate all schemas
make schema-validate
```

This command:
1. Validates `registry/connectors.yaml` against `schemas/connectors.schema.json`
2. Reports any validation errors with line numbers
3. Exits with error code if validation fails

### Schema Structure

The connector registry schema validates:
- **Connector metadata**: name, roles, category
- **Engine configuration**: default_engine, engines_supported
- **Capabilities**: allowed_in_cloud, supports_incremental
- **Incremental strategies**: incremental_strategy_default, objects_supported

---

## Asset Schema Validation

Asset definitions follow the **Open Data Contract Standard (ODCS) v3.0.2** and are validated during job execution.

### Schema Structure

Asset schemas define:
- **Field definitions**: name, type, required flag, classification
- **Governance metadata**: team ownership, compliance, data quality
- **Target configuration**: file format, partitioning, validation mode

**Example Asset Schema:**
```yaml
schema:
  - name: id
    type: string
    required: true
  - name: email
    type: string
    required: true
    classification: PII
  - name: created_at
    type: timestamp
    required: true
```

### Validation Rules

1. **Required Fields**: Fields marked `required: true` must be present
2. **Type Coercion**: Values are coerced to match schema types
3. **Type Validation**: If coercion fails, validation error is raised

For detailed validation rules, see [INGESTION_EXECUTION.md](INGESTION_EXECUTION.md#schema-validation).

---

## Validation During Ingestion

During job execution, records are validated against the asset schema before being written to Parquet files.

### Validation Modes

**Strict Mode (default):**
- Fails job if any record has validation errors
- Only valid records are written
- Exit code: 2 (failure) if errors found

**Warn Mode:**
- Logs validation errors but continues processing
- Invalid records are skipped
- Exit code: 1 (partial success) if errors found, 0 if all valid

**Configuration:**
```yaml
schema_validation_mode: strict  # or warn
```

### Validation Process

1. **Extract**: Records are extracted from source
2. **Validate**: Each record is validated against asset schema
3. **Report**: Validation errors are logged with details
4. **Write**: Only valid records are written to Parquet files

### Error Reporting

Validation errors include:
- Record index
- Field name
- Error type (missing_required, type_mismatch, etc.)
- Error message
- Original value (if applicable)

For detailed execution flow, see [INGESTION_EXECUTION.md](INGESTION_EXECUTION.md).

---

## Additional Resources

- [SETUP_AND_ONBOARDING.md](SETUP_AND_ONBOARDING.md) - Comprehensive setup guide
- [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) - Configuration reference
- [INGESTION_EXECUTION.md](INGESTION_EXECUTION.md) - Execution flow and validation details
- [SETUP_AND_TESTING.md](SETUP_AND_TESTING.md) - Testing and validation setup

