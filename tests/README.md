# Testing Strategy

Dativo uses a two-tier testing approach:

## 1. Unit Tests (`test_m1_1_cli.py`)

**Purpose**: Test internal functions and modules in isolation

**What they test**:
- Config loading and parsing
- Schema validation logic
- Connector validation
- Incremental state management
- Error handling

**Why we need them**:
- Fast execution
- Isolated testing of individual components
- Easy to debug failures
- Code coverage tracking

**Run with**:
```bash
# Run all unit tests
pytest tests/test_*.py -v

# Run specific test file
pytest tests/test_config.py -v
pytest tests/test_validator.py -v
pytest tests/test_state.py -v

# Or using Makefile
make test-unit
```

## 2. Smoke Tests

**Purpose**: Test the actual CLI execution with real fixtures

**What they test**:
- Full CLI command execution
- Startup sequence (config loading, secrets, infrastructure)
- End-to-end job execution
- Integration with actual connectors

**Why we need them**:
- Verify the CLI works as users would use it
- Test real-world scenarios
- Catch integration issues
- Validate the full pipeline

**Run with**:
```bash
# Direct CLI command (recommended)
dativo_ingest run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets

# Or using Python module
python -m dativo_ingest.cli run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets --mode self_hosted

# Or using Makefile
make test-smoke
```

**Note**: Smoke tests are just running the CLI directly with test fixtures. No special test code needed!

## Why Not Pytest for Smoke Tests?

For a config-driven system, smoke tests should simply run the CLI directly with test fixtures:

1. **Run the actual CLI commands** that users would run
2. **Check exit codes** to verify success/failure
3. **No special test code needed** - just use the CLI

This approach:
- ✅ Tests what users actually do
- ✅ Simpler and more maintainable
- ✅ No need for pytest fixtures for CLI execution
- ✅ Easy to add new test cases

## Adding New Smoke Tests

Simply add new job configurations to `tests/fixtures/jobs/` and run the CLI:

```bash
# Add new job config: tests/fixtures/jobs/new_job.yaml
# Then run:
dativo_ingest run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets
```

## Test Fixtures

All test fixtures are in `tests/fixtures/`:
- `jobs/` - Job configurations
- `specs/` - Data contract definitions
- `seeds/` - Test data files
- `secrets/` - Test secrets (placeholders)

## Running All Tests

```bash
make test  # Runs both unit and smoke tests
```

