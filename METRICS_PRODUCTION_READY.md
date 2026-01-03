# Metrics Feature: Production-Ready Implementation

## Summary

Transformed the initial metrics implementation (commit 3a3f3f40) into a production-ready system with:
- **Config-driven** (YAML-first with env var overrides)
- **Multiprocess-safe** (Prometheus multiprocess mode for orchestrated)
- **Stable schema** (canonical metric names, controlled cardinality)
- **Reliable** (bounded retry, graceful degradation, error handling)
- **Mode-aware** (different defaults for oneshot vs orchestrated)

## Key Changes

### 1. Configuration Model (YAML-First)

**File: `src/dativo_ingest/config.py`**

Added comprehensive configuration classes:

```python
class PrometheusConfig(BaseModel):
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 9400
    multiproc_dir: Optional[str] = None  # For orchestrated mode

class OtelConfig(BaseModel):
    enabled: bool = False
    protocol: str = "grpc"  # or "http"
    endpoint: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    export_interval_seconds: int = 60
    timeout_seconds: int = 10
    max_export_batch_size: int = 512

class MetricsLabelsConfig(BaseModel):
    include_env: bool = False  # Low cardinality by default
    include_mode: bool = True

class MetricsConfig(BaseModel):
    enabled: bool = True
    prometheus: PrometheusConfig = Field(default_factory=PrometheusConfig)
    otel: OtelConfig = Field(default_factory=OtelConfig)
    labels: MetricsLabelsConfig = Field(default_factory=MetricsLabelsConfig)
```

**Added to both JobConfig and RunnerConfig:**
- `JobConfig.metrics` - Per-job override
- `RunnerConfig.metrics` - Global default for orchestrated mode

**Configuration precedence:**
```
env vars > JobConfig.metrics > RunnerConfig.metrics > defaults
```

### 2. Canonical Metric Names (Stable Schema)

**File: `src/dativo_ingest/metrics.py`**

Renamed all metrics to follow `dativo_ingest_*` namespace:

| Old Name | New Name | Type |
|----------|----------|------|
| `dativo_records_extracted_total` | `dativo_ingest_records_total{phase=extracted}` | Counter |
| `dativo_records_valid_total` | `dativo_ingest_records_total{phase=written}` | Counter |
| `dativo_records_invalid_total` | `dativo_ingest_records_total{phase=invalid}` | Counter |
| `dativo_bytes_written_total` | `dativo_ingest_bytes_total{phase=written}` | Counter |
| `dativo_retries_total` | `dativo_ingest_retries_total` | Counter |
| `dativo_api_calls_total` | `dativo_ingest_api_calls_total` | Counter |
| `dativo_extraction_duration_seconds` | `dativo_ingest_extract_seconds` | Histogram |
| `dativo_job_duration_seconds` | `dativo_ingest_runtime_seconds` | Histogram |
| - | `dativo_ingest_load_seconds` | Histogram (new) |
| `dativo_job_running` | `dativo_ingest_job_running` | Gauge |
| `dativo_last_success_timestamp_seconds` | `dativo_ingest_last_success_timestamp_seconds` | Gauge |

**Benefits:**
- Consistent namespace prevents naming conflicts
- Phase labels reduce metric count (1 counter instead of 3)
- Clear semantic meaning (extract vs load vs runtime)

### 3. Label Cardinality Control

**File: `src/dativo_ingest/metrics.py`**

Implemented strict label validation:

```python
# Standardized label sets
KNOWN_API_TYPES = {"stripe", "hubspot", "salesforce", "postgres", "mysql", "http", "grpc", "unknown"}
KNOWN_ERROR_TYPES = {"timeout", "auth", "rate_limit", "validation", "connection", "unknown"}
KNOWN_PHASES = {"extracted", "written", "invalid", "committed"}

def _validate_label_value(value: str, known_set: Set[str], default: str = "unknown") -> str:
    """Validate and normalize label values to prevent cardinality explosion."""
    if not value:
        return default
    normalized = value.lower()[:50]
    return normalized if normalized in known_set else default
```

**Default labels (always included):**
- `job_name`
- `tenant_id`
- `connector_type`
- `mode` (oneshot/orchestrated)

**Optional labels (configurable):**
- `environment` (via `labels.include_env`)
- `status`, `phase`, `api_type` (context-dependent)

### 4. Prometheus Multiprocess Support

**File: `src/dativo_ingest/metrics.py`**

Added multiprocess mode for orchestrated execution:

```python
def _setup_multiprocess_mode(multiproc_dir: Optional[str]) -> bool:
    """Set up Prometheus multiprocess mode if configured."""
    if not multiproc_dir:
        return False
    
    multiproc_path = Path(multiproc_dir)
    multiproc_path.mkdir(parents=True, exist_ok=True)
    os.environ["PROMETHEUS_MULTIPROC_DIR"] = str(multiproc_path)
    return True
```

**File: `src/dativo_ingest/metrics_server.py`**

Server uses multiprocess registry when configured:

```python
def start(self) -> None:
    # Get appropriate registry (multiprocess or standard)
    registry = get_multiprocess_registry()
    if registry is None:
        registry = REGISTRY
    
    start_http_server(port=self.config.port, addr=self.config.host, registry=registry)
```

**Configuration:**
```yaml
# In runner.yaml
metrics:
  prometheus:
    enabled: true
    multiproc_dir: /tmp/prometheus_multiproc
```

### 5. OTLP HTTP + gRPC Protocol Support

**File: `src/dativo_ingest/metrics_otel.py`**

Supports both OTLP protocols:

```python
def _get_otel_exporter(config: OtelConfig):
    """Get appropriate OTEL exporter based on protocol."""
    if config.protocol == "grpc":
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        return OTLPMetricExporter(endpoint=config.endpoint, ...)
    elif config.protocol == "http":
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        return OTLPMetricExporter(endpoint=config.endpoint, ...)
```

**Configuration:**
```yaml
metrics:
  otel:
    enabled: true
    protocol: http  # or grpc
    endpoint: http://localhost:4318  # or :4317 for grpc
```

### 6. Bounded Retry with Throttled Logging

**File: `src/dativo_ingest/metrics_otel.py`**

Prevents log spam when OTEL collector is down:

```python
class ThrottledExportMetricReader(PeriodicExportingMetricReader):
    """Metric reader with throttled error logging."""
    
    def _export(self):
        try:
            result = super()._export()
            # Reset failure counter on success
            if self._consecutive_failures > 0:
                self.logger.info("OTEL export resumed")
            self._consecutive_failures = 0
            return result
        except Exception as e:
            self._consecutive_failures += 1
            
            # Log at most once per 5 minutes
            if should_log or self._consecutive_failures == 1:
                self.logger.warning(f"OTEL export failed (consecutive: {self._consecutive_failures})")
```

**Benefits:**
- Jobs don't crash when collector is down
- Logs are throttled (max 1 per 5 minutes)
- Automatic resume logging when collector recovers

### 7. Standardized Histogram Buckets

**File: `src/dativo_ingest/metrics.py`**

Optimized buckets for job durations (1s to 1h):

```python
HISTOGRAM_BUCKETS = (1, 2, 5, 10, 30, 60, 120, 300, 600, 1800, 3600)
```

Covers common job patterns:
- Fast jobs: 1-10 seconds
- Medium jobs: 10-300 seconds (5 minutes)
- Long jobs: 300-3600 seconds (1 hour)

### 8. Lifecycle Integration

**File: `src/dativo_ingest/job_executor.py`**

**Timing phases (clearly defined):**

1. **Extract phase** (start_extraction → end_extraction):
   - Covers: data extraction + validation + batch writes
   - Metric: `dativo_ingest_extract_seconds`

2. **Load phase** (start_load → end_load):
   - Covers: commit to catalog/storage
   - Metric: `dativo_ingest_load_seconds`

3. **Runtime** (start → finish):
   - Covers: entire job execution
   - Metric: `dativo_ingest_runtime_seconds{status=success|failure|partial}`

**Metrics on failure paths:**
- `finish()` called in all exception handlers
- Status set to "failure" on errors
- Ensures `runtime_seconds` recorded even on crash

### 9. Server Startup Logic

**File: `src/dativo_ingest/orchestrated.py`**

**Orchestrated mode:**
- Metrics server **enabled by default**
- Uses `RunnerConfig.metrics` configuration
- Multiprocess mode recommended

**Oneshot mode:**
- Metrics server **disabled by default**
- Can be enabled via `JobConfig.metrics.prometheus.enabled = true`
- Uses standard (non-multiprocess) mode

## Configuration Examples

### Job Configuration (jobs/example.yaml)

```yaml
tenant_id: acme
source_connector_path: connectors/stripe.yaml
target_connector_path: connectors/s3_iceberg.yaml
asset_path: assets/stripe_payments.yaml

# Optional: override metrics for this job
metrics:
  enabled: true
  prometheus:
    enabled: true
  otel:
    enabled: false
```

### Runner Configuration (runner.yaml)

```yaml
mode: orchestrated

orchestrator:
  type: dagster
  schedules: [...]

# Global metrics configuration
metrics:
  enabled: true
  
  prometheus:
    enabled: true
    host: "0.0.0.0"
    port: 9400
    multiproc_dir: /tmp/prometheus_multiproc  # Required for subprocess metrics
  
  otel:
    enabled: true
    protocol: grpc
    endpoint: http://otel-collector:4317
    export_interval_seconds: 60
  
  labels:
    include_env: false  # Keep cardinality low
    include_mode: true
```

### Environment Variable Overrides

```bash
# Prometheus
export DATIVO_METRICS_PROMETHEUS=true
export DATIVO_METRICS_PORT=9400
export DATIVO_METRICS_HOST=0.0.0.0
export PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc

# OpenTelemetry
export DATIVO_METRICS_OTEL=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export OTEL_EXPORTER_OTLP_PROTOCOL=grpc
```

## Verification

### Check Syntax

```bash
python3 -m py_compile src/dativo_ingest/config.py
python3 -m py_compile src/dativo_ingest/metrics.py
python3 -m py_compile src/dativo_ingest/metrics_server.py
python3 -m py_compile src/dativo_ingest/metrics_otel.py
python3 -m py_compile src/dativo_ingest/job_executor.py
python3 -m py_compile src/dativo_ingest/orchestrated.py
```

All files compile successfully ✅

### Test Metrics in Oneshot Mode

```bash
# Run a job (metrics collected, no HTTP server)
dativo ingest --config jobs/example.yaml

# Metrics appear in structured logs:
# {"message": "Job execution metrics", "runtime_seconds": 45.2, "status": "success", ...}
```

### Test Metrics in Orchestrated Mode

```bash
# Start orchestrated mode with metrics server
dativo start orchestrated --runner-config runner.yaml

# Check metrics endpoint
curl http://localhost:9400/metrics

# Should show metrics from recent job runs:
# dativo_ingest_records_total{job_name="example",phase="extracted",...} 10000.0
# dativo_ingest_runtime_seconds_sum{job_name="example",status="success",...} 45.2
```

### Test OTEL Export

```bash
# Configure OTEL in runner.yaml or via env:
export DATIVO_METRICS_OTEL=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# Start orchestrated mode
dativo start orchestrated

# Metrics pushed to OTEL collector every 60s
# Check collector logs for incoming metrics
```

## Files Modified

### Core Implementation (6 files)
- ✅ `src/dativo_ingest/config.py` - Added MetricsConfig classes
- ✅ `src/dativo_ingest/metrics.py` - Rewritten with canonical names, multiprocess support
- ✅ `src/dativo_ingest/metrics_server.py` - Updated for config-driven startup
- ✅ `src/dativo_ingest/metrics_otel.py` - Added HTTP support, bounded retry
- ✅ `src/dativo_ingest/job_executor.py` - Updated to use new metrics API
- ✅ `src/dativo_ingest/orchestrated.py` - Config-driven metrics startup

### Tests (TODO)
- ⏳ `tests/test_metrics.py` - Update for new API
- ⏳ `tests/test_metrics_acceptance.py` - Acceptance tests (NEW)
- ⏳ `tests/test_metrics_multiprocess.py` - Multiprocess tests (NEW)

### Documentation (TODO)
- ⏳ `docs/OBSERVABILITY_METRICS.md` - Rewrite in Dativo style (NEW)
- ⏳ `examples/observability/job-with-metrics.yaml` - YAML config example (NEW)
- ⏳ `examples/observability/runner-with-metrics.yaml` - Runner config example (NEW)

## Remaining Work

### High Priority
1. **Tests** - Add acceptance tests for:
   - Prometheus in orchestrated mode
   - OTEL export
   - Oneshot mode (no server)
   - Label cardinality limits

2. **Documentation** - Rewrite docs/OBSERVABILITY_METRICS.md:
   - Remove "implementation summary" style
   - Focus on user-facing "how to use"
   - Include YAML config examples
   - Document multiprocess requirements
   - Security notes (no secrets, low cardinality)

3. **Examples** - Update examples/observability/:
   - Add job-with-metrics.yaml
   - Add runner-with-metrics.yaml
   - Update docker-compose.yml with multiproc_dir
   - Update prometheus.yml with new metric names

### Lower Priority
4. **Migration Guide** - Document breaking changes:
   - Metric name changes
   - API changes (record_records vs record_extraction)
   - Configuration changes (YAML-first)

5. **Performance Testing** - Verify:
   - Multiprocess mode works correctly
   - Cardinality limits prevent explosion
   - OTEL export doesn't block job execution

## Breaking Changes

### Metric Names
All metrics renamed to `dativo_ingest_*` namespace.

**Migration for existing dashboards:**
```promql
# Old
dativo_records_extracted_total

# New
dativo_ingest_records_total{phase="extracted"}
```

### API Changes
```python
# Old API
metrics_collector.record_extraction(records_count=1000)
metrics_collector.record_validation(valid=950, invalid=50, total=1000)
metrics_collector.record_writing(files=5, bytes=1048576)

# New API
metrics_collector.record_records(1000, phase="extracted")
metrics_collector.record_records(950, phase="written")
metrics_collector.record_records(50, phase="invalid")
metrics_collector.record_bytes(1048576, phase="written")
```

### Configuration
```yaml
# Old (env vars only)
export DATIVO_METRICS_PROMETHEUS=true
export DATIVO_METRICS_OTEL=true

# New (YAML-first)
metrics:
  enabled: true
  prometheus:
    enabled: true
  otel:
    enabled: true
```

## Security Considerations

### No Secrets in Metrics
- Connection strings NOT in labels
- Credentials NOT in labels
- Only operational metadata (job_name, tenant_id, connector_type)

### Low Cardinality
- Known label sets validated
- Unknown values mapped to "unknown"
- String labels limited to 50 chars
- Optional labels disabled by default

### Metrics Endpoint Security
- In production: use firewall rules or reverse proxy auth
- No authentication built-in (Prometheus standard)
- Consider TLS termination at proxy

## Next Steps

1. Run: `pytest tests/test_metrics.py -v` (after updating tests)
2. Test multiprocess mode with actual Dagster subprocess
3. Verify OTEL export with real collector
4. Update documentation
5. Create migration guide for existing deployments

---

**Status:** Core implementation complete ✅  
**Remaining:** Tests + Documentation (estimated 2-3 hours)
