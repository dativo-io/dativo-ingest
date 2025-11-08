# Integration Tests

This directory contains integration tests that verify system-wide functionality.

## Test Files

### `test_tag_derivation_integration.py`
**Purpose:** Validates the tag derivation module integration  
**What it tests:**
- Module structure and imports
- Explicit classification (no auto-detection)
- IcebergCommitter signature
- Config extensions (FinOps, classification_overrides)

**Run:**
```bash
PYTHONPATH=src python3 tests/integration/test_tag_derivation_integration.py
```

---

### `test_complete_integration.py`
**Purpose:** End-to-end integration verification  
**What it tests:**
- Module imports
- Tag derivation patterns
- Asset definition structure
- Job configuration examples
- IcebergCommitter integration
- CLI integration
- Documentation presence

**Run:**
```bash
PYTHONPATH=src python3 tests/integration/test_complete_integration.py
```

---

### `test_odcs_compliance.py`
**Purpose:** ODCS v3.0.2 compliance validation  
**What it tests:**
- Asset definitions against ODCS schema
- Required sections (source_type, object, schema, team)
- Extended sections (finops, compliance)
- Schema validation with jsonschema

**Run:**
```bash
PYTHONPATH=src python3 tests/integration/test_odcs_compliance.py
```

---

## Running All Integration Tests

### Via Make
```bash
make test-integration
```

### Via GitHub Actions
Integration tests run automatically on:
- Push to `main`, `master`, or `develop` branches
- Pull requests
- Manual workflow trigger

### Manually
```bash
# Set PYTHONPATH
export PYTHONPATH=src

# Run each test
python3 tests/integration/test_tag_derivation_integration.py
python3 tests/integration/test_complete_integration.py
python3 tests/integration/test_odcs_compliance.py
```

---

## CI/CD Integration

### GitHub Actions Workflows

#### `.github/workflows/integration-tests.yml`
Runs all integration tests on every push and PR.

**Jobs:**
- Tag derivation integration
- Complete system integration
- ODCS compliance validation

**Trigger:**
```bash
# Manual trigger
gh workflow run integration-tests.yml
```

#### `.github/workflows/schema-validate.yml`
Validates schemas including ODCS compliance.

**Jobs:**
- Connector registry validation
- ODCS compliance validation

---

## Test Categories

| Category | Tests | CI Workflow |
|----------|-------|-------------|
| **Unit Tests** | `tests/test_*.py` | `tests.yml` |
| **Integration Tests** | `tests/integration/test_*.py` | `integration-tests.yml` |
| **Schema Validation** | ODCS, connectors | `schema-validate.yml` |
| **Smoke Tests** | CLI E2E | `smoke-tests.yml` |

---

## Adding New Integration Tests

1. **Create test file:** `tests/integration/test_your_feature.py`
2. **Follow pattern:**
```python
#!/usr/bin/env python3
"""Integration test for your feature."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

def test_your_feature():
    """Test your feature integration."""
    # Your test code
    return True

def main():
    """Run all tests."""
    print("Testing your feature...\n")
    
    tests = [
        ("Your feature", test_your_feature),
    ]
    
    # Run tests...
    
if __name__ == "__main__":
    main()
```

3. **Add to Makefile:**
```makefile
test-integration:
    @PYTHONPATH=src python3 tests/integration/test_your_feature.py
```

4. **Add to GitHub Actions:**
```yaml
- name: Run your feature tests
  run: |
    echo "🔍 Testing your feature..."
    PYTHONPATH=src python3 tests/integration/test_your_feature.py
```

---

## Debugging

### View CI Logs
```bash
# List recent workflow runs
gh run list --workflow=integration-tests.yml

# View specific run
gh run view <run-id>

# Download artifacts
gh run download <run-id>
```

### Local Debugging
```bash
# Run with verbose output
PYTHONPATH=src python3 -v tests/integration/test_tag_derivation_integration.py

# Run with debugging
PYTHONPATH=src python3 -m pdb tests/integration/test_complete_integration.py
```

---

## Notes

- **PYTHONPATH:** Always set `PYTHONPATH=src` when running integration tests
- **Dependencies:** Some tests require `pyyaml` and `jsonschema`
- **Fast:** Integration tests should complete in < 10 minutes
- **Isolated:** Tests should not depend on external services
- **Idempotent:** Tests should be repeatable without side effects

---

_See also: `/workspace/tests/README.md` for overall test strategy_
