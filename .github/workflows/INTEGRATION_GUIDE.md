# GitHub Actions Integration Guide

## Overview

The Dativo ETL project now has comprehensive CI/CD workflows that include the new plugin system tests alongside existing tests.

## Workflow Structure

### Existing Workflows (Maintained)
1. **`tests.yml`** - Original test suite
2. **`smoke-tests.yml`** - Smoke tests
3. **`schema-validate.yml`** - Schema validation

### New Workflows (Added for Plugin System)
4. **`ci.yml`** - Complete CI pipeline including plugin tests
5. **`plugin-tests.yml`** - Dedicated plugin system tests

## How They Work Together

### On Every PR/Push

**All workflows run in parallel:**

```
PR/Push
├── tests.yml (existing tests)
├── smoke-tests.yml (smoke tests)
├── schema-validate.yml (schema validation)
├── ci.yml (complete CI + plugins)
└── plugin-tests.yml (detailed plugin testing)
```

### Workflow Coordination

**`ci.yml`** is the main workflow that:
- Runs linting
- Runs core tests
- **Runs plugin tests** (new)
- **Builds Rust plugins** (new)
- Runs integration tests
- Reports overall status

**`plugin-tests.yml`** provides detailed plugin testing:
- Python plugin tests (3.10, 3.11)
- Rust plugin tests (Ubuntu, macOS)
- Integration tests
- Detailed test summary

### Why Two Plugin Workflows?

1. **`ci.yml`** - Fast, comprehensive, gates merges
2. **`plugin-tests.yml`** - Detailed, cross-platform, optional

This allows:
- Fast feedback on PRs (ci.yml)
- Detailed analysis when needed (plugin-tests.yml)
- Flexibility in required checks

## Required Status Checks

### Recommended Configuration

**Branch Protection Rules for `main`:**

Required checks:
- ✅ `tests` (from tests.yml)
- ✅ `Core Tests` (from ci.yml)
- ✅ `Plugin Tests` (from ci.yml)
- ✅ `Rust Plugins` (from ci.yml)

Optional checks:
- `Linting` (from ci.yml) - informational
- `Python Plugin Tests` (from plugin-tests.yml) - detailed
- `Rust Plugin Tests (Ubuntu)` (from plugin-tests.yml) - detailed
- `Rust Plugin Tests (macOS)` (from plugin-tests.yml) - detailed

## Configuration

### Setting Up Required Checks

1. **Go to Repository Settings**
2. **Branches → Branch Protection Rules**
3. **Add rule for `main` (or `develop`)**
4. **Enable "Require status checks to pass"**
5. **Select checks:**
   ```
   - tests
   - Core Tests (Python 3.10)
   - Plugin Tests
   - Rust Plugins
   ```

### GitHub UI Steps

```
Settings > Branches > Add Rule
├── Branch name pattern: main
├── ✓ Require status checks to pass before merging
│   ├── ✓ tests
│   ├── ✓ Core Tests (Python 3.10)
│   ├── ✓ Plugin Tests  
│   └── ✓ Rust Plugins
├── ✓ Require branches to be up to date before merging
└── Create
```

## Testing Locally Before CI

### Quick Pre-Push Check

```bash
# Run the master test suite
./tests/run_all_plugin_tests.sh
```

This runs the same tests that CI will run.

### Specific Components

```bash
# Python tests only
pytest tests/test_plugins.py -v

# Integration tests only
./tests/test_plugin_integration.sh

# Rust tests only
cd examples/plugins/rust && ./test_rust_plugins.sh
```

## Monitoring CI

### Viewing Results

**All Workflows:**
```
https://github.com/YOUR_ORG/YOUR_REPO/actions
```

**Specific Workflow:**
```
https://github.com/YOUR_ORG/YOUR_REPO/actions/workflows/ci.yml
https://github.com/YOUR_ORG/YOUR_REPO/actions/workflows/plugin-tests.yml
```

### Status Badges

Add to README:

```markdown
[![CI](https://github.com/YOUR_ORG/YOUR_REPO/workflows/CI/badge.svg)](https://github.com/YOUR_ORG/YOUR_REPO/actions)
[![Plugin Tests](https://github.com/YOUR_ORG/YOUR_REPO/workflows/Plugin%20System%20Tests/badge.svg)](https://github.com/YOUR_ORG/YOUR_REPO/actions)
```

## Troubleshooting

### CI Fails But Local Tests Pass

**Check:**
1. Python version (CI uses 3.10, 3.11)
2. Missing dependencies in requirements.txt
3. File permissions on test scripts
4. Environment variables

**Debug:**
```bash
# Run with same Python version as CI
python3.10 -m pytest tests/test_plugins.py -v

# Check script permissions
ls -la tests/*.sh
chmod +x tests/*.sh
```

### Rust Build Fails in CI

**Common issues:**
1. Cargo.toml dependencies
2. Platform-specific code
3. Missing system libraries

**Debug:**
```bash
# Test Rust build locally
cd examples/plugins/rust
cargo clean
cargo build --release
cargo test --release
```

### Workflow Not Triggering

**Check workflow triggers:**

```yaml
on:
  push:
    paths:
      - 'src/dativo_ingest/**'  # Update these paths
```

**Ensure changed files match paths:**
```bash
git diff --name-only HEAD~1 HEAD
```

## Caching Strategy

### What's Cached

**Python:**
- pip packages → faster dependency install
- Key: `${{ runner.os }}-pip-${{ hashFiles('requirements.txt') }}`

**Rust:**
- Cargo registry → faster downloads
- Cargo git → cached git deps
- Target directory → compiled dependencies
- Key: `${{ runner.os }}-cargo-${{ hashFiles('**/Cargo.lock') }}`

### Cache Invalidation

Cache updates when:
- `requirements.txt` changes (Python)
- `Cargo.lock` changes (Rust)
- Cache key is manually updated

**Manual cache clear:**
1. Update cache key in workflow
2. Or delete cache in GitHub UI

## Performance

### Typical Run Times

| Workflow | Jobs | Duration | Cost |
|----------|------|----------|------|
| ci.yml | 6 | ~8-10 min | Medium |
| plugin-tests.yml | 5 | ~6-8 min | Medium |
| tests.yml | 1 | ~3-5 min | Low |
| smoke-tests.yml | 1 | ~2-3 min | Low |

**Total per PR:** ~15-20 minutes

### Optimization Tips

1. **Use caching** - Already implemented
2. **Limit test scope** - Use path filters
3. **Run in parallel** - Already implemented
4. **Skip optional checks** - Make some non-required

### When to Run Plugin Tests

**Always run:**
- Changes to `src/dativo_ingest/plugins.py`
- Changes to `src/dativo_ingest/rust_plugin_bridge.py`
- Changes to `src/dativo_ingest/cli.py`
- Changes to any plugin code

**Can skip:**
- Documentation-only changes
- README updates
- Comment changes

**Configure with paths:**
```yaml
on:
  push:
    paths-ignore:
      - '**.md'
      - 'docs/**'
```

## Cost Management

### GitHub Actions Minutes

**Free tier:**
- 2,000 minutes/month for public repos
- 500 minutes/month for private repos (multiplied by OS)

**This project uses:**
- ~15-20 minutes per PR
- ~50 PRs/month = ~1,000 minutes

**Recommendations:**
1. Public repos → no issues
2. Private repos → consider:
   - Limiting matrix builds
   - Running detailed tests on-demand
   - Using self-hosted runners

### Self-Hosted Runners

For high-volume private repos:

```yaml
jobs:
  test:
    runs-on: self-hosted  # Instead of ubuntu-latest
```

## Notifications

### Slack Integration

Add to workflow:

```yaml
- name: Notify Slack
  if: failure()
  uses: 8398a7/action-slack@v3
  with:
    status: ${{ job.status }}
    webhook_url: ${{ secrets.SLACK_WEBHOOK }}
```

### Email Notifications

Configured per-user in GitHub settings:
```
Settings > Notifications > Actions
```

## Maintenance

### Updating Workflows

**When to update:**
- New test files added
- New dependencies added
- Python/Rust version updates
- New plugin types added

**Process:**
1. Update workflow files
2. Test locally first
3. Push to feature branch
4. Verify CI runs correctly
5. Merge to main

### Dependabot

Configured in `.github/dependabot.yml` to:
- Update Python dependencies weekly
- Update Rust dependencies weekly
- Update GitHub Actions weekly

**Review PRs from Dependabot:**
- Check test results
- Review CHANGELOG
- Merge if green

## Best Practices

### For Contributors

1. **Run tests locally first**
   ```bash
   ./tests/run_all_plugin_tests.sh
   ```

2. **Check workflow status** before requesting review

3. **Fix CI failures** before marking PR ready

4. **Don't skip tests** unless documented reason

### For Maintainers

1. **Require passing checks** before merge

2. **Review test changes** carefully

3. **Keep workflows updated** with dependencies

4. **Monitor CI performance** and optimize

## Support

### Getting Help

**CI failing?**
1. Check workflow logs in GitHub Actions
2. Run tests locally to reproduce
3. Review test documentation
4. Open issue with:
   - Workflow run URL
   - Error message
   - Local test results

**Need new test coverage?**
1. Add tests locally
2. Update workflow if needed
3. Document in PR description

## References

- **Workflow Files**: `.github/workflows/`
- **Test Scripts**: `tests/`
- **Documentation**: `tests/PLUGIN_TESTING.md`
- **Examples**: `examples/plugins/`
- **Contributing**: `.github/CONTRIBUTING.md`
