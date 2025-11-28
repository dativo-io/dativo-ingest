# Mount Points Standardization Summary

## Changes Made

All mount points have been standardized to align with industry standards (FHS - Filesystem Hierarchy Standard).

### Standardized Mount Points

| Component | Old Path | New Path | Status |
|-----------|----------|----------|--------|
| **Python Plugins** | `/usr/local/plugins` | `/usr/local/plugins` | ✅ Already correct |
| **Python Source** | `/usr/local/src` | `/usr/local/src` | ✅ Already correct |
| **Rust Plugins** | `/app/plugins` | `/usr/local/plugins` | ✅ **Updated** |
| **Rust Working Dir** | `/app/plugins` | `/usr/local/plugins` | ✅ **Updated** |

### Files Modified

1. **`src/dativo_ingest/rust_sandbox.py`**
   - Changed mount point from `/app/plugins` → `/usr/local/plugins`
   - Updated working directory to `/usr/local/plugins`
   - Updated plugin path reference in container

2. **`docker/rust-plugin-runner/Dockerfile`**
   - Changed directory creation from `/app/plugins` → `/usr/local/plugins`
   - Updated WORKDIR to `/usr/local/plugins`
   - Updated ownership to match new path

3. **`tests/test_rust_sandbox.py`**
   - Updated assertions to check for `/usr/local/plugins`

4. **`docs/MOUNT_POINTS_ANALYSIS.md`** (new)
   - Comprehensive analysis of mount points
   - Industry standards comparison
   - Recommendations and rationale

## Benefits

✅ **FHS Compliance**: All paths follow Filesystem Hierarchy Standard
✅ **Consistency**: Same mount points across Python and Rust sandboxes
✅ **Base Image Compatibility**: `/usr/local` exists in all standard base images
✅ **Read-Only Support**: Works correctly with read-only root filesystem
✅ **Industry Alignment**: Matches practices used by Kubernetes, Docker, and similar systems

## Current Mount Point Configuration

### Python Sandbox
```python
volumes = {
    plugin_dir: {
        "bind": "/usr/local/plugins",  # FHS-compliant
        "mode": "ro"
    },
    source_dir: {
        "bind": "/usr/local/src",     # FHS-compliant
        "mode": "ro"
    }
}
```

### Rust Sandbox
```python
volumes = {
    plugin_dir: {
        "bind": "/usr/local/plugins",  # FHS-compliant (standardized)
        "mode": "ro"
    }
}
```

## Testing

All tests have been updated to reflect the new mount points. The changes maintain backward compatibility at the API level - only internal mount paths have changed.

## Documentation

- See `docs/MOUNT_POINTS_ANALYSIS.md` for detailed analysis and rationale
- All mount points now follow industry best practices
- Consistent with FHS and container standards

