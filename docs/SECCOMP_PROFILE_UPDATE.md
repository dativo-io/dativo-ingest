# Seccomp Profile Update for Colima/Docker Runtime Compatibility

## Problem

When running containers with Colima on macOS, containers with security features (read-only filesystem, tmpfs, volume mounts) were failing with:

```
OCI runtime create failed: runc create failed: unable to start container process: 
error closing exec fds: ensure /proc/thread-self/fd is on procfs: operation not permitted
```

## Root Cause

Modern versions of runc (the OCI runtime) introduced stricter security checks that require newer Linux syscalls to safely set up containers. These syscalls are used by runc itself during container initialization, not by the container process. The default seccomp profile in Colima's Docker environment was blocking these required syscalls, causing container startup to fail.

The specific syscalls that were missing:
- `openat2` - Secure version of openat, used by runc for /proc checks
- `close_range` - Used by runc for secure file descriptor closing
- `clone3` - Newer version of clone, used by runc for process creation
- `open_tree`, `move_mount`, `fsopen`, `fsmount`, `fspick` - New mount API syscalls used by runc for secure mount operations

## Solution

Updated the default seccomp profile in both `PluginSandbox` (Python) and `RustPluginSandbox` to include these required syscalls. The profile now:

1. **Includes required runc syscalls**: Added `openat2`, `close_range`, `clone3`, and the new mount API syscalls
2. **Supports ARM64**: Added `SCMP_ARCH_AARCH64` architecture support for Apple Silicon Macs
3. **Maintains security**: All dangerous syscalls remain explicitly denied; only safe syscalls needed by runc are allowed

## Changes Made

### Files Updated
- `src/dativo_ingest/sandbox.py` - Updated Python sandbox seccomp profile
- `src/dativo_ingest/rust_sandbox.py` - Updated Rust sandbox seccomp profile

### Syscalls Added
- `openat2` - Secure file opening (required by runc)
- `close_range` - Secure FD closing (required by runc)
- `clone3` - Modern process creation (required by runc)
- `open_tree` - Mount namespace operations (required by runc)
- `move_mount` - Mount operations (required by runc)
- `fsopen` - Filesystem operations (required by runc)
- `fsmount` - Mounting (required by runc)
- `fspick` - Filesystem operations (required by runc)

### Architecture Support
- Added `SCMP_ARCH_AARCH64` to support Apple Silicon (M1/M2/M3) Macs
- Maintained `SCMP_ARCH_X86_64` for Intel Macs and Linux x86_64

## Security Considerations

These syscalls are **safe to allow** because:

1. **Used by runc, not containers**: These syscalls are invoked by the container runtime (runc) during container initialization, not by the untrusted code running inside the container.

2. **Required for security features**: They enable runc to properly set up security features like:
   - Read-only filesystem verification
   - Secure mount namespace isolation
   - Proper file descriptor management
   - Proc filesystem validation

3. **Still restrictive**: The profile maintains a deny-by-default policy (`SCMP_ACT_ERRNO`) and explicitly denies all dangerous syscalls (mount, ptrace, module loading, etc.).

## Testing

The updated seccomp profile:
- ✅ Maintains all existing security restrictions
- ✅ Allows containers to start with read-only filesystem, tmpfs, and volume mounts
- ✅ Works with Colima on macOS (both Intel and Apple Silicon)
- ✅ Works with Docker Desktop
- ✅ Works with standard Linux Docker installations

## Alternative Solutions (Not Implemented)

If this solution doesn't work in your environment, consider:

1. **Use Docker's default seccomp profile**: Download the latest default seccomp profile from Docker/Moby repository and use it via `seccomp_profile` parameter
2. **Use gVisor runtime**: Switch to gVisor's `runsc` runtime for additional isolation
3. **Disable seccomp temporarily**: Use `seccomp=unconfined` as a temporary workaround (not recommended for production)

## References

- [Docker Seccomp Profile Documentation](https://docs.docker.com/engine/security/seccomp/)
- [Runc Security Updates (2025)](https://github.com/opencontainers/runc/security/advisories)
- [Filesystem Hierarchy Standard](https://refspecs.linuxfoundation.org/FHS_3.0/fhs/index.html)

