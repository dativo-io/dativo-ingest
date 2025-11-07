# Test Cleanup Guide

## Overview

After running smoke tests, all temporary files and artifacts are automatically cleaned up to keep the repository and system clean.

## What Gets Cleaned Up

### 1. State Files
- **Location**: `/tmp/dativo-state/` (CI/CD) or `.local/state/` (local dev)
- **What**: Incremental sync state files (`.state.json`)
- **When**: After every test run

### 2. Temporary Parquet Files
- **Location**: `/tmp/dativo_ingest*/` (system temp directory)
- **What**: Parquet files written during processing before upload to S3/MinIO
- **When**: After every test run

### 3. Log Files
- **Location**: Project root and subdirectories
- **What**: Any `.log` files created during test execution
- **When**: After every test run

### 4. Other Temporary Files
- **Location**: Project root
- **What**: `.tmp`, `.temp` files
- **When**: After every test run

### 5. Test Environment Files
- **Location**: `.github/workflows/test.env`
- **What**: Temporary environment configuration files
- **When**: After smoke tests in CI/CD

## Cleanup Methods

### Automatic Cleanup (CI/CD)

In GitHub Actions workflows, cleanup runs automatically after tests:

```yaml
- name: Cleanup test artifacts
  if: always()  # Runs even if tests fail
  run: |
    # Comprehensive cleanup of all temporary files
```

### Manual Cleanup (Local Development)

#### Using Makefile

```bash
# Clean state files only
make clean-state

# Clean temporary files only
make clean-temp

# Clean everything
make clean
```

#### Using Smoke Test Script

The `tests/smoke_tests.sh` script automatically cleans up after execution:

```bash
./tests/smoke_tests.sh
# Cleanup runs automatically via trap on exit
```

#### Manual Cleanup

```bash
# Clean state files
rm -rf .local/state/test_tenant/*.state.json

# Clean temporary Parquet files
rm -rf /tmp/dativo_ingest*

# Clean log files
rm -f *.log
```

## What Doesn't Get Cleaned

### MinIO/S3 Test Data

**By default, MinIO test bucket data is kept** for verification purposes. This allows you to:
- Verify that files were written correctly
- Inspect Parquet file contents
- Debug test failures

To clean MinIO bucket manually:
```bash
mc rm --recursive --force local/test-bucket/
```

Or uncomment the cleanup line in the workflow:
```yaml
# mc rm --recursive --force local/test-bucket/ || true
```

### Docker Volumes

Docker volumes (Postgres, MySQL, MinIO data) persist between test runs. This is intentional to:
- Speed up subsequent test runs
- Preserve test data for debugging

To clean Docker volumes:
```bash
docker-compose -f docker-compose.dev.yml down -v
```

## Cleanup Best Practices

1. **Always run cleanup after tests** - Prevents accumulation of temporary files
2. **Use `if: always()` in CI/CD** - Ensures cleanup even on test failures
3. **Keep MinIO data for verification** - Only clean if you need a fresh start
4. **Document custom cleanup needs** - If you add new temporary files, update cleanup scripts

## Troubleshooting

### Cleanup Not Running

If cleanup doesn't run:
1. Check that `if: always()` is set in CI/CD workflows
2. Verify trap is set in shell scripts: `trap cleanup EXIT`
3. Check file permissions on temp directories

### Files Still Present After Cleanup

Some files may persist if:
- They're in use during cleanup (wait and retry)
- Permissions prevent deletion (check with `ls -la`)
- They're in a different location than expected (check paths)

### Need to Clean Everything

For a complete fresh start:

```bash
# Clean all state
make clean-state

# Clean all temp files
make clean-temp

# Clean MinIO bucket
mc rm --recursive --force local/test-bucket/

# Clean Docker volumes
docker-compose -f docker-compose.dev.yml down -v

# Clean Docker images (optional)
docker-compose -f docker-compose.dev.yml down --rmi all
```

