# Mount Points Analysis and Industry Standards

## Current Mount Points

### Python Sandbox (`sandbox.py`)
- **Plugin mount**: `/usr/local/plugins` (read-only)
- **Source mount**: `/usr/local/src` (read-only, when dativo_ingest source is found)

### Rust Sandbox (`rust_sandbox.py`)
- **Plugin mount**: `/app/plugins` (read-only)
- **Working directory**: `/app/plugins`
- **Note**: `/app/plugins` is created in the Dockerfile

## Industry Standards Analysis

### Filesystem Hierarchy Standard (FHS) Compliance

According to FHS and container best practices:

| Path | FHS Standard | Use Case | Current Usage | Recommendation |
|------|-------------|----------|---------------|----------------|
| `/usr/local/plugins` | ✅ FHS-compliant | Locally installed optional software | Python plugins | ✅ **Keep** - Good choice |
| `/usr/local/src` | ✅ FHS-compliant | Source code | dativo_ingest source | ✅ **Keep** - Appropriate |
| `/app/plugins` | ❌ Non-standard | Container-specific | Rust plugins | ⚠️ **Standardize** - Not FHS-compliant |
| `/opt/dativo/plugins` | ✅ FHS-compliant | Self-contained application data | N/A | 💡 **Alternative** - More explicit |
| `/var/lib/dativo/plugins` | ✅ FHS-compliant | Variable state data | N/A | ❌ **Not suitable** - For state, not code |

### Industry Best Practices

1. **FHS Compliance**: Use standard directories that exist in base images
2. **Consistency**: Use the same mount points across all sandbox types
3. **Clarity**: Use application-specific paths for better organization
4. **Security**: Mount points should be read-only for plugin code
5. **Compatibility**: Paths should exist in base images (python:3.10, debian:bookworm-slim)

## Recommendations

### Option 1: Standardize on `/usr/local/*` (Recommended)

**Pros:**
- ✅ FHS-compliant
- ✅ Exists in all standard base images
- ✅ Already working for Python sandbox
- ✅ Clear semantic meaning (locally installed software)
- ✅ Works with read-only filesystem

**Changes needed:**
- Update Rust sandbox to use `/usr/local/plugins` instead of `/app/plugins`
- Update `rust-plugin-runner` Dockerfile to create `/usr/local/plugins` instead of `/app/plugins`

**Mount Points:**
```
Python plugins:  /usr/local/plugins
Rust plugins:    /usr/local/plugins
Source code:     /usr/local/src
```

### Option 2: Use `/opt/dativo/*` (More Application-Specific)

**Pros:**
- ✅ FHS-compliant
- ✅ More explicit about application ownership
- ✅ Better for multi-tenant scenarios
- ✅ Clear separation from system software

**Cons:**
- ⚠️ Requires creating directories in base images
- ⚠️ Slightly more verbose paths

**Mount Points:**
```
Python plugins:  /opt/dativo/plugins
Rust plugins:    /opt/dativo/plugins
Source code:     /opt/dativo/src
```

### Option 3: Hybrid Approach (Current + Standardization)

**Keep current Python paths, standardize Rust to match:**

**Mount Points:**
```
Python plugins:  /usr/local/plugins  (keep)
Rust plugins:    /usr/local/plugins  (change from /app/plugins)
Source code:     /usr/local/src      (keep)
```

## Recommended Implementation: Option 1

**Rationale:**
1. `/usr/local/*` is the most widely supported across base images
2. Already proven to work with read-only filesystems
3. FHS-compliant and semantically correct
4. Minimal changes needed (only Rust sandbox)
5. Consistent across all sandbox types

### Implementation Steps

1. **Update Rust sandbox** (`rust_sandbox.py`):
   - Change mount point from `/app/plugins` to `/usr/local/plugins`
   - Update working directory to `/usr/local/plugins`

2. **Update Rust plugin runner Dockerfile**:
   - Change from creating `/app/plugins` to `/usr/local/plugins`
   - Update WORKDIR if needed

3. **Update tests** to reflect new mount points

## Security Considerations

All mount points should:
- ✅ Be read-only (`mode: "ro"`)
- ✅ Use absolute paths from host
- ✅ Exist in base images (no creation needed)
- ✅ Not conflict with system directories
- ✅ Work with read-only root filesystem

## Comparison with Industry Examples

### Kubernetes/Docker Best Practices
- **Plugins/Extensions**: `/usr/local/lib/<app>/plugins` or `/opt/<app>/plugins`
- **Source Code**: `/usr/local/src` or `/opt/<app>/src`
- **Configuration**: `/etc/<app>` (not applicable here)

### Similar Systems
- **Terraform**: Uses `/opt/terraform/plugins`
- **Kubernetes**: Uses `/usr/local/bin` for binaries
- **Docker plugins**: Use `/run/docker/plugins` (runtime) or `/usr/lib/docker/plugins` (system)

## Conclusion

**Recommended**: Standardize on `/usr/local/plugins` and `/usr/local/src` for all sandbox types.

This provides:
- ✅ FHS compliance
- ✅ Base image compatibility
- ✅ Read-only filesystem support
- ✅ Consistency across sandbox implementations
- ✅ Clear semantic meaning

