# GitHub Actions Workflows

This directory contains CI/CD workflows for the Dativo ETL platform.

## Workflows

### 1. `ci.yml` - Complete CI Test Suite

**Triggers:**
- Push to `main` or `develop` branches
- Pull requests to `main` or `develop`
- Manual workflow dispatch

**Jobs:**
1. **Linting** - Code quality checks (black, isort, flake8)
2. **Core Tests** - Core unit tests (config, validator, state)
3. **Plugin Tests** - Plugin system tests (unit + integration)
4. **Rust Plugins** - Build and test Rust plugins
5. **Integration Tests** - Master test suite
6. **Build Status** - Final status check

**Status Badge:**
```markdown
[![CI](https://github.com/YOUR_ORG/YOUR_REPO/workflows/CI/badge.svg)](https://github.com/YOUR_ORG/YOUR_REPO/actions)
```

### 2. `plugin-tests.yml` - Plugin System Tests

**Triggers:**
- Push/PR affecting plugin-related files
- Manual workflow dispatch

**Jobs:**
1. **Python Plugin Tests**
   - Matrix: Python 3.10, 3.11
   - Unit tests with coverage
   - Integration tests
   
2. **Default Extractors Tests**
   - CSV extractor tests
   - Default reader/writer tests
   
3. **Rust Plugin Tests**
   - Matrix: Ubuntu, macOS
   - Build Rust plugins
   - Run Rust unit tests
   - Verify exports
   - Test Python integration
   
4. **Master Test Suite**
   - Run complete test suite
   - All tests together
   
5. **Test Summary**
   - Final status report

**Status Badge:**
```markdown
[![Plugin Tests](https://github.com/YOUR_ORG/YOUR_REPO/workflows/Plugin%20System%20Tests/badge.svg)](https://github.com/YOUR_ORG/YOUR_REPO/actions)
```

## Test Coverage

### Python Tests

| Component | Coverage |
|-----------|----------|
| Core (config, validator, state) | pytest with coverage |
| Plugin system | pytest with coverage |
| Integration | Shell-based tests |

### Rust Tests

| Component | Coverage |
|-----------|----------|
| CSV reader | cargo test |
| Parquet writer | cargo test |
| Build verification | symbol checks |
| Python integration | detection tests |

## Caching

Workflows use caching for faster builds:

**Python:**
- pip packages: `~/.cache/pip`

**Rust:**
- Cargo registry: `~/.cargo/registry`
- Cargo git: `~/.cargo/git`
- Build artifacts: `target/`

## Artifacts

Rust plugin binaries are uploaded as artifacts:
- Retention: 7 days
- Available for: Ubuntu, macOS
- Includes: CSV reader, Parquet writer

## Local Testing

Before pushing, run tests locally:

```bash
# All tests
./tests/run_all_plugin_tests.sh

# Specific suites
pytest tests/test_plugins.py -v
./tests/test_plugin_integration.sh
cd examples/plugins/rust && ./test_rust_plugins.sh
```

## Matrix Testing

### Python Versions
- Python 3.10 (primary)
- Python 3.11 (compatibility)

### Operating Systems
- Ubuntu Latest (Linux)
- macOS Latest (Darwin)
- Windows (future)

## Workflow Configuration

### Required Secrets

No secrets required for basic tests.

For full integration tests (optional):
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `POSTGRES_PASSWORD`
- Database connection strings

### Environment Variables

All workflows set:
```yaml
env:
  PYTHONPATH: ${{ github.workspace }}/src
```

## Troubleshooting

### Workflow Fails on Plugin Tests

1. Check Python version compatibility
2. Verify all dependencies in `requirements.txt`
3. Check test file permissions (executable)

### Rust Build Fails

1. Check Rust toolchain version
2. Verify Cargo.toml dependencies
3. Check for platform-specific issues

### Cache Issues

Clear cache by:
1. Update cache key in workflow
2. Or manually clear in GitHub Actions UI

## Adding New Tests

### To Core Tests

Add test files to `tests/test_*.py` and they'll be picked up automatically.

### To Plugin Tests

1. Add to `tests/test_plugins.py` for unit tests
2. Add to `tests/test_plugin_integration.sh` for integration
3. Add to `examples/plugins/rust/test_rust_plugins.sh` for Rust

### To Workflows

Update workflow files to include new test paths in triggers:

```yaml
on:
  push:
    paths:
      - 'path/to/new/file.py'
```

## Performance

### Average Run Times

| Workflow | Duration | Jobs |
|----------|----------|------|
| CI (complete) | ~8-10 min | 6 |
| Plugin Tests | ~6-8 min | 5 |

### Optimization

- Caching reduces build time by 50%
- Matrix runs in parallel
- Rust builds cached between runs

## Status Checks

Required status checks for merge:
- ✅ Core Tests (Python 3.10)
- ✅ Plugin Tests
- ✅ Rust Plugin Build

Optional checks:
- Linting (non-blocking)
- Python 3.11 compatibility

## Continuous Deployment

Workflows are designed to support CD:
- Tagged releases trigger builds
- Artifacts available for deployment
- Rust plugins ready for distribution

## Support

For workflow issues:
1. Check workflow run logs in GitHub Actions
2. Run tests locally first
3. Review test documentation in `tests/PLUGIN_TESTING.md`
