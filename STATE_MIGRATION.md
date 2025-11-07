# State Directory Migration Guide

## Overview

State files have been moved from `state/` (repo root) to `.local/state/` (hidden, gitignored) to follow modern best practices.

## What Changed

1. **Default location**: `state/` → `.local/state/`
2. **Gitignore**: State directories are now ignored
3. **CI/CD**: Uses `/tmp/dativo-state/` (temporary, cleaned after tests)
4. **Production**: Can override with `STATE_DIR` environment variable

## Migration Steps

### For Local Development

1. **Migrate existing state files** (if any):
   ```bash
   # If you have existing state files in state/
   mkdir -p .local/state
   mv state/* .local/state/ 2>/dev/null || true
   rm -rf state/
   ```

2. **Verify state directory**:
   ```bash
   mkdir -p .local/state/test_tenant
   ```

3. **Run jobs** - they will automatically use `.local/state/`:
   ```bash
   dativo_ingest run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets --mode self_hosted
   ```

### For CI/CD

No changes needed - CI/CD workflows now use `/tmp/dativo-state/` automatically.

### For Production

Set `STATE_DIR` environment variable to your desired location:

```bash
# Example: Use a dedicated directory
export STATE_DIR=/var/lib/dativo/state

# Example: Use S3 (future: when S3 backend is implemented)
export STATE_DIR=s3://dativo-state-bucket/state

# Example: Use database (future: when database backend is implemented)
export STATE_DIR=postgresql://user:pass@host/db
```

## Benefits

1. ✅ **Cleaner repo**: State files no longer clutter the root directory
2. ✅ **Gitignored**: State files won't be accidentally committed
3. ✅ **Environment-aware**: Different locations for dev/test/prod
4. ✅ **CI/CD friendly**: Temporary directories cleaned after tests
5. ✅ **Production-ready**: Can use database or object storage

## Backward Compatibility

- Old `state/` directory will still work if `STATE_DIR=state` is set
- Existing state files can be migrated manually
- No breaking changes to state file format

## Future Enhancements

- Database backend for production (PostgreSQL/MySQL)
- S3 backend for cloud deployments
- State backend abstraction layer
- State migration utilities

