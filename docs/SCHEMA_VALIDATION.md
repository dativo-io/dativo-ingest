# docs/SCHEMA_VALIDATION.md

# Dativo – Schema Validation (YAML ↔ JSON Schema)

This repo keeps **YAML** registry files validated against **JSON Schemas**.

## What we validate
- `/registry/connectors.yaml` → `/schemas/connectors.schema.json`

## Local setup

```bash
# 1) Install Node.js 18+ (or use nvm)
# 2) Install dev deps
npm i --include=dev

# 3) Validate everything
make schema-validate

