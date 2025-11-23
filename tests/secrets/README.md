# Secrets Management Test Suite

This directory contains comprehensive tests for the secrets management system, organized to match the module structure and focus on testing **dativo-ingest code logic**, not third-party libraries.

## Test Organization

```
tests/secrets/
├── __init__.py
├── README.md
├── test_parsers.py          # Tests for payload parsing utilities
├── test_validation.py       # Tests for secret validation logic
├── test_factory.py          # Tests for factory/registry functions
└── managers/
    ├── __init__.py
    ├── test_env.py          # Environment variable manager tests
    ├── test_filesystem.py  # Filesystem manager tests
    ├── test_vault.py        # HashiCorp Vault manager tests
    ├── test_aws.py          # AWS Secrets Manager tests
    └── test_gcp.py          # GCP Secret Manager tests
```

## Testing Philosophy

### What We Test
- **Our parsing logic**: How we parse JSON, .env, and text formats
- **Our filtering logic**: How we filter and match environment variables
- **Our path resolution**: How we resolve templates and merge paths
- **Our validation logic**: How we validate required secrets
- **Our factory logic**: How we instantiate managers from configuration
- **Our error handling**: How we handle edge cases and errors

### What We Don't Test
- **Third-party libraries**: We mock boto3, hvac, and GCP SDK clients
- **Network calls**: All external API calls are mocked
- **Authentication flows**: We test our auth configuration, not the actual auth

## Running Tests

Run all secrets tests:
```bash
pytest tests/secrets/
```

Run specific test modules:
```bash
pytest tests/secrets/test_parsers.py
pytest tests/secrets/managers/test_env.py
```

Run with coverage:
```bash
pytest tests/secrets/ --cov=src/dativo_ingest/secrets
```

## Test Coverage

### Parsers (`test_parsers.py`)
- Environment variable blob parsing
- JSON payload parsing
- Text payload parsing
- Auto-detection logic
- Environment variable expansion

### Validation (`test_validation.py`)
- Connector-specific secret requirements
- File template validation
- Missing secret detection
- Partial name matching

### Factory (`test_factory.py`)
- Manager instantiation
- Registry lookups
- Configuration passing
- Alias support
- Error handling

### Managers
Each manager test file focuses on:
- **Template resolution**: How tenant IDs are substituted
- **Path merging**: How multiple paths are combined
- **Format parsing**: How secrets are parsed based on format hints
- **Error handling**: How errors are handled gracefully
- **Configuration**: How manager-specific config is applied

## Mocking Strategy

All external dependencies are mocked:
- **AWS**: `MagicMock` for boto3 client
- **GCP**: `SimpleNamespace` for GCP client responses
- **Vault**: `MagicMock` for hvac client
- **Filesystem**: `tmp_path` fixture for file operations
- **Environment**: `monkeypatch` for environment variables

This ensures tests:
- Run fast (no network calls)
- Are reliable (no external dependencies)
- Focus on our code (not third-party bugs)

