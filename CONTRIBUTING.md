# Contributing to Dativo-Ingest

Thank you for your interest in contributing! This guide covers essential validation and workflow requirements.

## Prerequisites

- **Python 3.10+**: Required for running tests and validation
- **Node.js 18+**: Required for schema validation (AJV)
- **Docker**: Required for integration tests

## Schema Validation

All YAML configuration files must pass schema validation before submission.

### Running Schema Validation

```bash
# Validate all schemas (connector registry + ODCS compliance)
make schema-validate
```

This command:
1. Validates `registry/connectors.yaml` against `schemas/connectors.schema.json` using AJV
2. Validates asset definitions for ODCS v3.0.2 compliance
3. Uses `yq` to convert YAML to JSON for AJV validation

**Prerequisites:**
- Node.js 18+ installed (for `npx ajv-cli`)
- Python with `pyyaml` and `jsonschema` packages

**Local Setup:**
```bash
# Install Node.js dependencies
npm i --include=dev

# Install Python dependencies
pip install pyyaml jsonschema
```

See [docs/SCHEMA_VALIDATION.md](docs/SCHEMA_VALIDATION.md) for detailed validation rules.

## Connector Registry Validation

The connector registry (`/registry/connectors.yaml`) and connector templates are validated in CI via `.github/workflows/schema-validate.yml`:

- **Connector Registry**: Validated against JSON schema using AJV
- **ODCS Compliance**: Asset definitions validated for ODCS v3.0.2 structure
- **Automated**: Runs on every push and pull request

**Manual validation:**
```bash
# Validate connector registry only
make schema-connectors

# Validate ODCS compliance only
make schema-odcs
```

## Pull Request Expectations

### Before Submitting

1. **Run Schema Validation**: `make schema-validate` must pass
2. **Format Code**: `make format` and verify with `make format-check`
3. **Run Tests**: Ensure existing tests pass (`make test-unit`)
4. **Update Documentation**: Update relevant docs for configuration or API changes

### PR Checklist

- [ ] Schema validation passes (`make schema-validate`)
- [ ] Code is formatted (`make format-check`)
- [ ] Tests pass (`make test-unit`)
- [ ] Documentation updated (if needed)
- [ ] Commit messages follow conventional format (`feat:`, `fix:`, `docs:`, etc.)

### Code Style

- Follow PEP 8 for Python code
- Use type hints where appropriate
- Add docstrings to functions and classes
- Keep functions focused and small

## CI/CD Validation

All pull requests automatically run:
- Schema validation (connector registry + ODCS)
- Code formatting checks
- Unit tests
- Linting (flake8)

See `.github/workflows/schema-validate.yml` for the complete validation workflow.

## Questions?

- Review [docs/index.md](docs/index.md) for complete documentation
- Check existing issues for similar problems
- Open a discussion for questions

