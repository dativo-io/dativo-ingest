# Colima Configuration for Plugin Sandboxing

## Issue

When running plugin sandboxing with Colima on macOS, you may encounter errors like:

```
unable to apply bounding set: operation not permitted
```

or

```
error closing exec fds: ensure /proc/thread-self/fd is on procfs: operation not permitted
```

These errors occur because Colima's Docker daemon uses an outdated seccomp profile that doesn't include newer syscalls required by modern runc versions.

## Root Cause

Modern versions of runc (the OCI runtime) require newer Linux syscalls (openat2, close_range, clone3, etc.) for secure container initialization. Colima's Docker daemon may be using a seccomp profile that blocks these syscalls, causing container startup to fail.

## Automatic Fallback (Already Implemented)

The sandbox code automatically handles this by:
1. First trying with the updated seccomp profile (includes new syscalls)
2. If that fails, retrying with `seccomp=unconfined` (allows all syscalls)
3. If that also fails, retrying without seccomp entirely

This ensures containers can start even if Colima's seccomp configuration is problematic.

## Long-Term Solution: Update Colima's Docker Seccomp Profile

For production use, you should update Colima's Docker daemon to use an updated seccomp profile. This maintains security while allowing the required syscalls.

### Step 1: Get Updated Seccomp Profile

Download Docker's latest default seccomp profile:

```bash
# Option 1: From Docker/Moby repository
curl -o /tmp/seccomp.json https://raw.githubusercontent.com/moby/moby/master/profiles/seccomp/default.json

# Option 2: From containers-common (if available in Colima VM)
colima ssh -- cat /usr/share/containers/seccomp.json > /tmp/seccomp.json
```

### Step 2: Copy Profile to Colima VM

```bash
# Copy the profile into Colima VM
colima ssh -- sudo mkdir -p /etc/docker
colima ssh -- sudo tee /etc/docker/seccomp.json < /tmp/seccomp.json
```

### Step 3: Configure Docker Daemon

Edit Colima configuration:

```bash
colima start --edit
```

Add to the `docker:` section:

```yaml
docker:
  seccomp-profile: "/etc/docker/seccomp.json"
```

Or manually edit `~/.colima/default/colima.yaml`:

```yaml
docker:
  seccomp-profile: "/etc/docker/seccomp.json"
```

### Step 4: Restart Colima

```bash
colima stop
colima start
```

### Step 5: Verify Configuration

```bash
docker info | grep -i seccomp
# Should show the custom profile path
```

## Alternative: Use Unconfined Seccomp (Quick Fix)

If updating the profile is not feasible, you can configure Colima to use unconfined seccomp:

```bash
colima start --edit
```

Add:

```yaml
docker:
  seccomp-profile: "unconfined"
```

**Note:** This disables syscall filtering, reducing security. Only use as a temporary workaround.

## Verification

After configuration, test that containers start successfully:

```bash
docker run --rm --read-only --tmpfs /tmp:size=100m python:3.10 echo "test"
```

This should succeed without errors.

## References

- [Docker Seccomp Profile Documentation](https://docs.docker.com/engine/security/seccomp/)
- [Moby Seccomp Profile](https://github.com/moby/moby/blob/master/profiles/seccomp/default.json)
- [Colima Configuration](https://github.com/abiosoft/colima/blob/main/docs/CONFIG.md)

