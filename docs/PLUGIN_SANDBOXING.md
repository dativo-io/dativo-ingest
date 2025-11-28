# Plugin Sandboxing and Security

This document outlines security considerations and sandboxing strategies for custom plugins in the Dativo platform.

## ✅ Current Implementation Status

**Plugin sandboxing is now implemented and enabled by default in cloud mode.**

### Features Implemented

- ✅ **Docker-based sandboxing** for Python plugins
- ✅ **Docker-based sandboxing** for Rust plugins (via Rust plugin runner)
- ✅ **Automatic sandboxing** in cloud mode
- ✅ **Configurable sandboxing** via job configuration
- ✅ **Resource limits** (CPU, memory)
- ✅ **Network isolation** (disabled by default)
- ✅ **Timeout enforcement**
- ✅ **Seccomp profiles** for syscall restrictions

### Usage

Sandboxing is automatically enabled in `cloud` mode and can be configured per-job:

```yaml
plugins:
  sandbox:
    enabled: true  # Explicitly enable (default in cloud mode)
    cpu_limit: 0.5  # Limit to 50% of one CPU core
    memory_limit: "512m"  # Limit to 512MB
    network_disabled: true  # Disable network access
    timeout: 300  # 5 minute timeout
```

In `self_hosted` mode, sandboxing is disabled by default but can be enabled via configuration.

## ⚠️ Security Warning

**Custom plugins run with the same privileges as the Dativo process in self_hosted mode without sandboxing.** Before enabling custom plugins in production, especially in multi-tenant environments, implement appropriate sandboxing and security measures.

## Threat Model

### Risks from Untrusted Plugins

1. **Code Execution**
   - Arbitrary code execution on host
   - Access to filesystem
   - Network access
   - Environment variables

2. **Data Exfiltration**
   - Access to all tenant data
   - Credentials and secrets
   - API tokens

3. **Resource Exhaustion**
   - CPU consumption
   - Memory exhaustion
   - Disk space
   - Network bandwidth

4. **Privilege Escalation**
   - Container escape
   - Host access
   - Cross-tenant access

## Sandboxing Strategies

### Level 1: Process Isolation (Minimal)

**Status:** Not implemented (roadmap item)

Run plugins in separate processes with limited privileges.

```yaml
plugins:
  sandbox:
    mode: "process"
    user: "dativo-plugin"  # Non-root user
    group: "dativo-plugin"
    nice: 10  # Lower priority
```

**Pros:**
- Simple implementation
- Basic isolation

**Cons:**
- Minimal security
- Same filesystem access
- Same network access

### Level 2: Container Isolation (✅ Implemented)

**Status:** ✅ **Implemented and enabled by default in cloud mode**

Run plugins in Docker containers with restricted capabilities. This is the default behavior for all plugins in cloud mode.

```yaml
plugins:
  sandbox:
    mode: "docker"
    image: "dativo-plugin-runner:1.0"
    resources:
      cpu_limit: "1.0"
      memory_limit: "512M"
    security:
      capabilities_drop: ["ALL"]
      capabilities_add: ["NET_BIND_SERVICE"]
      read_only_rootfs: true
      no_new_privileges: true
```

**Implementation:**

```bash
# Create plugin runner image
FROM python:3.10-slim
RUN useradd -m -u 1000 plugin
USER plugin
WORKDIR /workspace
COPY plugin.py .
CMD ["python", "plugin.py"]
```

**Docker Compose:**

```yaml
services:
  plugin-runner:
    image: dativo-plugin-runner:1.0
    user: "1000:1000"
    read_only: true
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
    networks:
      - plugin-network
    volumes:
      - ./plugins:/plugins:ro
      - plugin-tmp:/tmp
    environment:
      - PLUGIN_CONFIG=/plugins/config.yaml
    resources:
      limits:
        cpus: '1.0'
        memory: 512M
```

**Pros:**
- Strong isolation
- Resource limits
- Network isolation
- Seccomp profiles

**Cons:**
- Requires Docker
- Higher latency
- More complex setup

### Level 3: VM Isolation (Maximum Security)

**Status:** Roadmap item for SaaS deployments

Run plugins in lightweight VMs (e.g., Firecracker, gVisor).

```yaml
plugins:
  sandbox:
    mode: "firecracker"
    kernel: "vmlinux"
    rootfs: "plugin-rootfs.ext4"
    vcpus: 1
    memory: 512
    timeout: 300
```

**Pros:**
- Maximum isolation
- Kernel-level security
- True multi-tenancy

**Cons:**
- Complex setup
- Higher resource usage
- Requires specialized infrastructure

## Security Best Practices

### For Plugin Authors

#### 1. Minimize Dependencies
```python
# ✅ Good - minimal dependencies
from dativo_ingest import BaseReader

# ❌ Bad - unnecessary dependencies
import numpy, pandas, tensorflow
```

#### 2. Validate All Inputs
```python
def extract(self, state_manager=None):
    # ✅ Validate configuration
    if not self.source_config.connection.get("api_key"):
        raise InvalidCredentialsError("API key required")
    
    # ✅ Validate data
    if not isinstance(self.source_config.objects, list):
        raise ConfigurationError("objects must be a list")
```

#### 3. Handle Secrets Securely
```python
# ✅ Good - use environment variables
import os
api_key = os.environ.get("API_KEY")

# ❌ Bad - hardcoded secrets
api_key = "sk-1234567890abcdef"

# ❌ Bad - log secrets
logger.info(f"Using API key: {api_key}")
```

#### 4. Implement Resource Limits
```python
# ✅ Good - streaming with limits
MAX_BATCH_SIZE = 10000

def extract(self, state_manager=None):
    batch = []
    for record in self.stream_records():
        batch.append(record)
        if len(batch) >= MAX_BATCH_SIZE:
            yield batch
            batch = []
```

#### 5. Use Standard Error Codes
```python
from dativo_ingest import (
    NetworkError,
    AuthenticationError,
    ConnectionTestResult
)

def check_connection(self):
    try:
        self.client.ping()
        return ConnectionTestResult(True, "Connected")
    except AuthenticationError as e:
        return ConnectionTestResult(
            False, 
            str(e), 
            error_code="AUTH_FAILED"
        )
    except NetworkError as e:
        return ConnectionTestResult(
            False,
            str(e),
            error_code="NETWORK_ERROR"
        )
```

### For Platform Operators

#### 1. Plugin Review Process

Before deploying custom plugins:

- [ ] **Code Review**: Manual inspection of plugin code
- [ ] **Dependency Audit**: Check all dependencies for vulnerabilities
- [ ] **Static Analysis**: Run security linters (bandit, safety)
- [ ] **Testing**: Test plugin in sandboxed environment
- [ ] **Signing**: Sign approved plugins with GPG

#### 2. Runtime Monitoring

Monitor plugin execution:

```yaml
monitoring:
  plugins:
    - metric: cpu_usage
      threshold: 80%
      action: throttle
    - metric: memory_usage
      threshold: 90%
      action: kill
    - metric: network_bytes_out
      threshold: 1GB
      action: alert
```

#### 3. Audit Logging

Log all plugin activities:

```python
# Automatic logging of plugin operations
logger.info(
    "Plugin executed",
    extra={
        "plugin_name": "custom_reader",
        "plugin_version": "1.0.0",
        "tenant_id": "acme",
        "records_extracted": 1000,
        "duration_seconds": 45.2,
        "event_type": "plugin_execution"
    }
)
```

#### 4. Network Policies

Restrict network access:

```yaml
# Kubernetes NetworkPolicy example
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: plugin-network-policy
spec:
  podSelector:
    matchLabels:
      app: dativo-plugin
  policyTypes:
  - Egress
  egress:
  - to:
    - namespaceSelector:
        matchLabels:
          name: external-apis
    ports:
    - protocol: TCP
      port: 443
```

#### 5. Secret Scanning

Scan plugins for leaked secrets:

```bash
# Pre-commit hook
#!/bin/bash
if git diff --cached | gitleaks detect --no-git -v; then
    echo "✓ No secrets detected"
else
    echo "✗ Secrets detected in plugin code"
    exit 1
fi
```

## Implementation Roadmap

### Phase 1: Foundation (Current)
- ✅ Plugin interface versioning
- ✅ Standardized error handling
- ✅ Connection testing
- ✅ Discovery interface
- ✅ Documentation

### Phase 2: Basic Security (Next Quarter)
- [ ] Process isolation
- [ ] Resource limits (CPU, memory)
- [ ] Timeout enforcement
- [ ] Plugin signatures
- [ ] Audit logging

### Phase 3: Container Sandbox (✅ Completed)
- [x] Docker-based sandboxing
- [x] Seccomp profiles
- [x] Network policies (network_disabled option)
- [x] Read-only filesystems
- [x] Capability dropping

### Phase 4: VM Isolation (Q3-Q4)
- [ ] Firecracker integration
- [ ] gVisor support
- [ ] Kernel-level isolation
- [ ] True multi-tenancy

## Docker Sandbox Example (Self-Hosted)

### Step 1: Create Plugin Runner Image

```dockerfile
# Dockerfile.plugin-runner
FROM python:3.10-slim

# Install only necessary dependencies
RUN pip install --no-cache-dir dativo-ingest==1.1.0

# Create non-root user
RUN useradd -m -u 1000 -U plugin && \
    mkdir -p /workspace /tmp/plugin && \
    chown -R plugin:plugin /workspace /tmp/plugin

# Security hardening
RUN chmod 700 /home/plugin && \
    chmod 1777 /tmp/plugin

USER plugin
WORKDIR /workspace

# Set resource limits
ENV PYTHONUNBUFFERED=1
ENV PYTHONHASHSEED=random

# Entrypoint
ENTRYPOINT ["python", "-m", "dativo_ingest.cli"]
```

### Step 2: Build and Run

```bash
# Build image
docker build -f Dockerfile.plugin-runner -t dativo-plugin-runner:1.0 .

# Run plugin in sandbox
docker run --rm \
  --user 1000:1000 \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --cpus 1.0 \
  --memory 512m \
  --network plugin-net \
  -v $(pwd)/plugins:/plugins:ro \
  -v plugin-tmp:/tmp \
  -e PLUGIN_CONFIG=/plugins/config.yaml \
  dativo-plugin-runner:1.0 \
  run --config /plugins/job.yaml
```

### Step 3: Add Seccomp Profile

```json
{
  "defaultAction": "SCMP_ACT_ERRNO",
  "architectures": ["SCMP_ARCH_X86_64"],
  "syscalls": [
    {
      "names": [
        "read", "write", "open", "close", "stat",
        "fstat", "lstat", "poll", "lseek", "mmap",
        "mprotect", "munmap", "brk", "rt_sigaction",
        "rt_sigprocmask", "rt_sigreturn", "ioctl",
        "pread64", "pwrite64", "readv", "writev",
        "access", "pipe", "select", "sched_yield",
        "mremap", "msync", "mincore", "madvise",
        "socket", "connect", "accept", "sendto",
        "recvfrom", "sendmsg", "recvmsg", "shutdown",
        "bind", "listen", "getsockname", "getpeername"
      ],
      "action": "SCMP_ACT_ALLOW"
    }
  ]
}
```

```bash
# Run with seccomp profile
docker run --security-opt seccomp=seccomp.json ...
```

## Kubernetes Deployment Example

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dativo-plugin-runner
spec:
  replicas: 3
  selector:
    matchLabels:
      app: dativo-plugin-runner
  template:
    metadata:
      labels:
        app: dativo-plugin-runner
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
        seccompProfile:
          type: RuntimeDefault
      containers:
      - name: plugin-runner
        image: dativo-plugin-runner:1.0
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          capabilities:
            drop: ["ALL"]
        resources:
          limits:
            cpu: "1"
            memory: "512Mi"
          requests:
            cpu: "100m"
            memory: "128Mi"
        volumeMounts:
        - name: plugins
          mountPath: /plugins
          readOnly: true
        - name: tmp
          mountPath: /tmp
      volumes:
      - name: plugins
        configMap:
          name: plugin-configs
      - name: tmp
        emptyDir: {}
```

## Testing Sandbox Security

### 1. Test Resource Limits
```bash
# CPU limit test
stress-ng --cpu 4 --timeout 10s

# Memory limit test
stress-ng --vm 1 --vm-bytes 1G --timeout 10s

# Expected: Container should be throttled/killed
```

### 2. Test Filesystem Access
```bash
# Try to write to read-only filesystem
touch /etc/test.txt

# Expected: Permission denied
```

### 3. Test Network Access
```bash
# Try to access restricted endpoint
curl https://internal-api.example.com

# Expected: Connection refused (network policy)
```

### 4. Test Privilege Escalation
```bash
# Try to become root
sudo su

# Expected: sudo not available
```

## Monitoring and Alerting

### CloudWatch Example (AWS)
```python
import boto3
cloudwatch = boto3.client('cloudwatch')

# Put custom metrics
cloudwatch.put_metric_data(
    Namespace='Dativo/Plugins',
    MetricData=[
        {
            'MetricName': 'PluginExecutionTime',
            'Value': execution_time,
            'Unit': 'Seconds',
            'Dimensions': [
                {'Name': 'PluginName', 'Value': 'custom_reader'},
                {'Name': 'TenantId', 'Value': 'acme'}
            ]
        }
    ]
)
```

### Prometheus Example
```python
from prometheus_client import Counter, Histogram

plugin_executions = Counter(
    'dativo_plugin_executions_total',
    'Total plugin executions',
    ['plugin_name', 'tenant_id', 'status']
)

plugin_duration = Histogram(
    'dativo_plugin_duration_seconds',
    'Plugin execution duration',
    ['plugin_name', 'tenant_id']
)

# Record metrics
with plugin_duration.labels('custom_reader', 'acme').time():
    result = execute_plugin()
    plugin_executions.labels('custom_reader', 'acme', 'success').inc()
```

## Conclusion

**For Self-Hosted Deployments:**
- Start with trusted plugins only
- Implement Docker sandboxing when adding custom plugins
- Use resource limits and network policies
- Regular security audits

**For SaaS/Cloud Deployments:**
- Docker sandboxing is **mandatory**
- Consider VM isolation (Firecracker/gVisor)
- Implement comprehensive monitoring
- Regular penetration testing
- Plugin marketplace with vetting process

**Remember:** Security is a journey, not a destination. Start with trusted plugins and add security layers as you scale.

## Resources

- [Docker Security Best Practices](https://docs.docker.com/engine/security/)
- [Kubernetes Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- [Seccomp Profiles](https://docs.docker.com/engine/security/seccomp/)
- [gVisor Documentation](https://gvisor.dev/docs/)
- [Firecracker Documentation](https://firecracker-microvm.github.io/)
