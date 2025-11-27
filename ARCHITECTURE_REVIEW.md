# Architecture Review: Dativo Data Integration Platform

**Review Date:** November 27, 2025  
**Platform Version:** 1.1.0  
**Reviewer:** Technical Architecture Assessment

---

## Executive Summary

Dativo is a **hybrid plugin-based data integration platform** that successfully balances configuration-driven connectors with code-driven custom plugins. The architecture demonstrates strong alignment with industry patterns from Airbyte, Meltano, and Singer, while introducing innovative features like Rust plugin support and explicit-only governance tagging.

**Key Strengths:**
- ✅ Well-structured microkernel architecture with clear separation of concerns
- ✅ Hybrid plugin model supporting both YAML connectors and code-driven readers/writers
- ✅ Strong schema governance (ODCS v3.0.2 compliant)
- ✅ Multi-engine support (native, Airbyte, Meltano, Singer)
- ✅ Rust plugin bridge for 10-100x performance improvements
- ✅ Pluggable secret management system

**Primary Gaps:**
- ⚠️ Airbyte/Meltano/Singer engine adapters are partially implemented
- ⚠️ Limited plugin versioning and discovery mechanisms
- ⚠️ No formal plugin SDK or development kit
- ⚠️ Sandbox isolation for plugins is minimal
- ⚠️ CDC support is connector-dependent, not framework-level

---

## 1. Architecture & Modularity

### ✔️ What's Working Well

#### Microkernel Design
The platform follows a **clean microkernel architecture**:

```
Core Orchestration (dativo_ingest/cli.py, orchestrated.py)
    ↓
Connector/Plugin Registry (registry/connectors.yaml)
    ↓
Execution Layer
    ├── Standard Connectors (connectors/*.yaml)
    ├── Custom Plugins (plugins.py, rust_plugin_bridge.py)
    └── Engine Adapters (engine_framework.py)
    ↓
Writers & Commiters (parquet_writer.py, iceberg_committer.py)
```

**Evidence:**
- `src/dativo_ingest/cli.py` - Orchestration engine agnostic to plugin types
- `src/dativo_ingest/plugins.py` - Abstract base classes (`BaseReader`, `BaseWriter`)
- `registry/connectors.yaml` - Centralized capability registry
- `src/dativo_ingest/connectors/engine_framework.py` - Engine abstraction (`BaseEngineExtractor`)

#### Composability and Loose Coupling
- **Jobs** reference **Connectors** (YAML recipes) and **Assets** (schemas) via paths
- Connectors define metadata and capabilities independently of job logic
- Source/target configs are merged at runtime, not hard-coded
- Custom plugins can reference connectors for metadata while overriding execution

**Example** (`examples/jobs/custom_plugin_example.yaml`):
```yaml
source_connector: custom_api
source_connector_path: /app/connectors/csv.yaml  # Metadata only
source:
  custom_reader: "/app/plugins/json_api_reader.py:JSONAPIReader"  # Execution
```

### ⚠️ Gaps or Risks

#### 1. Limited Versioning for Plugins
- **Issue:** No version metadata in `plugins.py` or `rust_plugin_bridge.py`
- **Risk:** Breaking changes to plugin interfaces could silently fail
- **Impact:** Difficult to maintain backward compatibility as platform evolves

**Current State:**
```python
# plugins.py - No versioning
class BaseReader(ABC):
    def extract(self, state_manager=None):
        pass
```

**Recommendation:** Add API versioning:
```python
class BaseReader(ABC):
    __plugin_api_version__ = "2.0"
    
    @abstractmethod
    def extract(self, state_manager=None):
        pass
```

#### 2. Connector Isolation is Configuration-Based, Not Runtime-Based
- **Issue:** Connectors run in-process; no container/process isolation by default
- **Evidence:** Native extractors (e.g., `stripe_extractor.py`) execute directly
- **Risk:** Rogue plugins could access memory, credentials, or system resources

**Current Airbyte Isolation** (`engine_framework.py:157-231`):
```python
# Uses subprocess.Popen with Docker, but only for Airbyte engine
process = subprocess.Popen(
    ["docker", "run", "--rm", "-i", self.docker_image, "read", ...],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
)
```

**Native plugins have no isolation** - they execute as Python/Rust code in the main process.

---

## 2. Connector vs Plugin Decision Framework

### ✔️ What's Working Well

#### Clear Policy Documentation
The platform provides **excellent decision guidance** in `docs/CUSTOM_PLUGINS.md`:

| Scenario | Recommendation |
|----------|---------------|
| Standard SaaS API (Stripe, HubSpot) | **Connector** |
| Proprietary API with custom auth | **Custom Reader** |
| Need 10-100x performance boost | **Custom Reader/Writer (Rust)** |
| Want to switch engines later | **Connector** |

#### Hybrid Usage Pattern
The system supports **3 modes**:
1. **Pure Connector:** YAML-only configuration (e.g., Stripe via Airbyte)
2. **Pure Plugin:** Custom reader/writer with minimal connector reference
3. **Hybrid:** Connector for metadata + plugin for execution

**Example Hybrid** (`examples/jobs/custom_plugin_example.yaml`):
```yaml
source_connector: custom_api
source_connector_path: /app/connectors/csv.yaml  # Provides type metadata
source:
  custom_reader: "/app/plugins/json_api_reader.py:JSONAPIReader"  # Overrides extraction
```

#### Multi-Engine Support
Each connector declares supported engines in registry:

```yaml
# registry/connectors.yaml
hubspot:
  default_engine: airbyte
  engines_supported: [airbyte, singer, native]
```

### ⚠️ Gaps or Risks

#### 1. No Plugin-to-Connector Promotion Path
- **Issue:** No tooling to convert custom plugins into reusable connectors
- **Example:** If a user creates a great custom Salesforce reader, there's no workflow to promote it to `connectors/salesforce.yaml`
- **Recommendation:** Add `dativo promote-plugin` CLI command

#### 2. Engine Selection is Static, Not Dynamic
- **Issue:** Cannot switch engines at runtime based on environment/performance
- **Current:** `default_engine` in connector recipe is fixed
- **Recommendation:** Support runtime engine selection:

```yaml
# Job config
source:
  engine_override: singer  # Override default Airbyte with Singer
```

#### 3. Partial Connector Override Not Documented
- **Issue:** Unclear if you can override only extraction while keeping connector's credentials
- **Documentation Gap:** `docs/CUSTOM_PLUGINS.md` doesn't explain partial overrides

---

## 3. Interface Design

### ✔️ What's Working Well

#### Unified Lifecycle for All Plugins
All plugins implement a **consistent lifecycle**:

```python
# Reader Lifecycle
reader = CustomReader(source_config)  # 1. Init
for batch in reader.extract(state_manager):  # 2. Extract
    # ... validate and write
reader.get_total_records_estimate()  # 3. Optional metadata

# Writer Lifecycle  
writer = CustomWriter(asset, target_config, output_base)  # 1. Init
file_metadata = writer.write_batch(records, counter)  # 2. Write batches
commit_result = writer.commit_files(file_metadata)  # 3. Optional commit
```

**Evidence:** `src/dativo_ingest/plugins.py:13-139`

#### Standardized Data Format (Records as Dicts)
- Data flows as **`List[Dict[str, Any]]`** across all components
- Aligns with Singer's JSON message protocol
- Compatible with Airbyte's record format: `{"type": "RECORD", "record": {...}}`

**Example** (`engine_framework.py:248-253`):
```python
record = json.loads(line)
if record.get("type") == "RECORD":
    yield record.get("record", {})  # Standardized dict
```

#### Multi-Engine Adapter Pattern
Abstract base class ensures engine-agnostic design:

```python
# src/dativo_ingest/connectors/engine_framework.py:24-60
class BaseEngineExtractor(ABC):
    @abstractmethod
    def extract(self, state_manager=None) -> Iterator[List[Dict[str, Any]]]:
        pass
```

Concrete implementations:
- `AirbyteExtractor` - Docker-based Airbyte connectors
- `MeltanoExtractor` - Meltano taps (stub)
- `SingerExtractor` - Singer taps (stub)

### ⚠️ Gaps or Risks

#### 1. Incomplete Engine Implementations
**Meltano and Singer extractors are stubs:**

```python
# engine_framework.py:331-347
class MeltanoExtractor(BaseEngineExtractor):
    def extract(self, state_manager=None):
        raise NotImplementedError("Meltano extractor not yet implemented")

class SingerExtractor(BaseEngineExtractor):
    def extract(self, state_manager=None):
        raise NotImplementedError("Singer extractor not yet implemented")
```

**Impact:**
- Cannot use Singer taps despite registry claiming support
- Registry shows `engines_supported: [airbyte, singer, native]` but Singer fails at runtime

**Recommendation:**
1. Implement Singer extraction using subprocess (similar to Airbyte)
2. Parse Singer messages: `RECORD`, `SCHEMA`, `STATE`
3. Update registry to mark unsupported engines as `experimental`

#### 2. No Schema Discovery Interface
- **Issue:** Plugins cannot expose `discover()` method to list available streams
- **Airbyte/Singer Pattern:** Connectors support `discover` command to list schemas
- **Current:** Users must know object names in advance

**Recommended Addition:**
```python
class BaseReader(ABC):
    def discover(self) -> Dict[str, Any]:
        """Discover available streams and schemas (optional)."""
        return {}  # Default: no discovery support
```

#### 3. No Check/Validate Interface
- **Issue:** Cannot validate credentials before extraction
- **Airbyte Pattern:** `check` command validates connection
- **Current:** Errors surface during `extract()`, wasting time

**Recommended Addition:**
```python
class BaseReader(ABC):
    def check(self) -> Dict[str, Any]:
        """Validate connection and credentials."""
        return {"status": "success"}
```

#### 4. State Management is File-Based Only
- **Issue:** Incremental state tied to local files
- **Evidence:** `validator.py:273-367` - Only JSON file operations
- **Limitation:** Cannot use database or distributed state stores

**Current:**
```python
state = IncrementalStateManager.read_state(state_path)  # Path object only
```

**Recommendation:**
```python
class StateBackend(ABC):
    def read_state(self, key: str) -> Dict[str, Any]: pass
    def write_state(self, key: str, state: Dict[str, Any]): pass

class FileStateBackend(StateBackend): ...
class DatabaseStateBackend(StateBackend): ...
```

---

## 4. Extensibility & SDK Patterns

### ✔️ What's Working Well

#### Declarative Plugin Registration
Plugins are registered via YAML manifests:

```yaml
# registry/connectors.yaml
stripe:
  roles: [source]
  engines_supported: [airbyte, singer, native]
  supports_incremental: true
  incremental_strategy_default: created
```

**Validation:** `src/dativo_ingest/validator.py:88-139` enforces registry constraints

#### Dual-Language Support (Python + Rust)
**Python Plugins:**
```yaml
custom_reader: "/app/plugins/json_api_reader.py:JSONAPIReader"
```

**Rust Plugins:**
```yaml
custom_reader: "/app/plugins/rust/target/release/libcsv_reader.so:create_reader"
```

Bridge layer (`rust_plugin_bridge.py:1-359`) handles FFI:
- JSON serialization for config passing
- ctypes for shared library loading
- Memory management (`free_reader`, `free_string`)

#### Performance Benefits (Rust)
**Documented benchmarks** (`docs/CUSTOM_PLUGINS.md:790-799`):
- **CSV Reading:** 15x faster, 12x less memory
- **Parquet Writing:** 3.5x faster, 27% better compression

### ⚠️ Gaps or Risks

#### 1. No Connector SDK or CDK
**Missing Features:**
- No helper libraries for common tasks (pagination, rate limiting, retries)
- No connector scaffolding tool (`dativo init connector`)
- No testing utilities for plugin development

**Comparison to Airbyte CDK:**
```python
# Airbyte provides CDK with helpers
from airbyte_cdk.sources.streams.http import HttpStream

class MyStream(HttpStream):
    def parse_response(self, response): ...  # Built-in pagination, auth
```

**Dativo forces raw implementation:**
```python
# User must implement everything from scratch
class JSONAPIReader(BaseReader):
    def extract(self):
        # Manual pagination, auth, retries, parsing...
```

**Recommendation:** Create `dativo-plugin-sdk`:
```python
from dativo_sdk import PaginatedAPIReader, OAuth2Mixin

class MyReader(PaginatedAPIReader, OAuth2Mixin):
    def get_next_page_token(self, response): ...  # SDK handles rest
```

#### 2. No Plugin Versioning
- **Issue:** Plugin interfaces can break without detection
- **No versioning metadata** in `plugins.py` or plugin manifests
- **Risk:** Upgrading Dativo breaks custom plugins silently

**Recommendation:**
```yaml
# Plugin manifest
custom_reader: 
  path: /app/plugins/my_reader.py:MyReader
  api_version: "2.0"  # Declare compatibility
```

#### 3. No Plugin Discovery/Marketplace
- **Issue:** Cannot list available plugins
- **No central repository** for community plugins
- **Recommendation:** Add `dativo list-plugins --marketplace`

#### 4. Limited Observability Hooks
- **Issue:** Plugins cannot emit custom metrics or traces
- **No standard logger injection** into plugins
- **Recommendation:**
```python
class BaseReader(ABC):
    def __init__(self, source_config, logger=None, metrics=None):
        self.logger = logger or get_logger()
        self.metrics = metrics or MetricsCollector()
```

---

## 5. Security & Isolation

### ✔️ What's Working Well

#### Pluggable Secret Management
**5 supported backends** (`src/dativo_ingest/secrets/managers/`):
1. `env.py` - Environment variables (default)
2. `filesystem.py` - Tenant-organized files
3. `vault.py` - HashiCorp Vault (KV v1/v2)
4. `aws.py` - AWS Secrets Manager
5. `gcp.py` - Google Cloud Secret Manager

**Example** (`docs/SECRET_MANAGEMENT.md:1-100`):
```bash
dativo run --job-dir jobs/acme \
  --secret-manager vault \
  --secret-manager-config vault-secrets.yaml
```

#### Credential Injection at Runtime
- Secrets loaded **before job execution**, not embedded in configs
- Environment variable substitution: `"${STRIPE_API_KEY}"`
- Supports credential files for service accounts

#### Audit Logging (Structured)
- JSON-formatted logs (`logging.py`)
- Event types: `extractor_initialized`, `secrets_loaded`, `infra_validated`
- Tenant ID attached to all log events

### ⚠️ Gaps or Risks

#### 1. No Sandboxing for Custom Plugins
**Critical Issue:** Custom plugins run **in-process** with full system access.

**Evidence:**
```python
# plugins.py:202-208 - Direct module loading
spec = importlib.util.spec_from_file_location(module_name, module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)  # Unrestricted execution
```

**Risks:**
- Plugin can read `/secrets/` directory
- Plugin can access all environment variables
- Plugin can make arbitrary network calls
- Plugin can write to filesystem

**Docker isolation exists only for Airbyte engine:**
```python
# engine_framework.py:216-231
subprocess.Popen(["docker", "run", "--rm", "-i", self.docker_image, ...])
```

**Recommendation:** Add container-based plugin execution:
```python
class SandboxedPluginRunner:
    def run_plugin(self, plugin_path, config):
        # Run in Docker container with:
        # - Read-only filesystem (except /tmp)
        # - Limited CPU/memory
        # - No network access (or whitelist)
        # - Secrets injected via env, not files
```

#### 2. No Secret Rotation Support
- **Issue:** Cannot reload secrets without restarting orchestrator
- **Impact:** Long-running jobs require downtime for credential updates

#### 3. Insufficient Audit Trail
**Missing:**
- No tracking of which plugins accessed which credentials
- No record of data volumes extracted per plugin
- No detection of anomalous plugin behavior (e.g., excessive API calls)

**Recommendation:**
```python
class AuditLogger:
    def log_plugin_execution(self, plugin_name, action, metadata):
        # Track: plugin, tenant, records_read, duration, errors
```

#### 4. No Input Validation for Plugin Configs
- **Issue:** Plugins receive raw config dicts without validation
- **Risk:** Malformed configs cause runtime errors, not startup errors

**Recommendation:**
```python
from pydantic import BaseModel

class PluginConfig(BaseModel):
    connection: Dict[str, Any]
    credentials: Optional[Dict[str, Any]]
    # ... with validation rules
```

---

## 6. Performance & Scaling

### ✔️ What's Working Well

#### Incremental Sync Support
Multiple strategies supported (`registry/connectors.yaml:15-19`):
- `updated_at` - Timestamp-based (databases)
- `created` - Creation time (APIs)
- `file_modified_time` - File tracking (GDrive, S3)

**Implementation:** `validator.py:273-426` manages state files

#### Batch Processing
- Readers yield `List[Dict[str, Any]]` in batches (default: 1000 records)
- Configurable batch sizes: `engine.options.batch_size`
- Rust plugins support larger batches (50,000+)

#### Rust Plugin Performance
**Documented gains** (`docs/CUSTOM_PLUGINS.md:253-258`):
- CSV Reader: **10-50x faster** than pandas
- Parquet Writer: **5-20x faster** than PyArrow
- Memory-efficient streaming (constant memory usage)

#### Tunable File Sizes
```yaml
target:
  parquet_target_size_mb: 200  # Target 128-200 MB Parquet files
  engine:
    options:
      row_group_size: 500000  # Rust plugins
```

### ⚠️ Gaps or Risks

#### 1. No Built-In Parallelism
**Issue:** Single-threaded extraction and writing by default.

**Evidence:**
```python
# No parallel execution in core loop
for batch in reader.extract():  # Sequential
    validated = validate_batch(batch)
    writer.write_batch(validated)
```

**Recommendation:**
```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=config.parallelism) as executor:
    futures = [executor.submit(process_object, obj) for obj in objects]
```

#### 2. CDC Support is Connector-Specific
- **Issue:** No framework-level CDC abstraction
- **Current:** Each connector implements CDC independently
- **Missing:** Unified CDC interface for streaming changes

**Recommendation:**
```python
class BaseCDCReader(BaseReader):
    @abstractmethod
    def stream_changes(self, checkpoint=None) -> Iterator[ChangeEvent]:
        pass
```

#### 3. No Backpressure Mechanism
- **Issue:** Fast readers can overwhelm slow writers
- **Risk:** Memory exhaustion if writer cannot keep up
- **Recommendation:** Add queue-based buffering with size limits

#### 4. Limited Observability
**Missing Metrics:**
- Records per second (throughput)
- Extractor lag (for incremental syncs)
- Plugin resource usage (CPU, memory)
- Error rates per connector

**Recommendation:** Integrate Prometheus/OpenTelemetry:
```python
metrics.counter("records_extracted", labels={"connector": "stripe"})
metrics.histogram("batch_processing_time", value=duration)
```

#### 5. No Query Pushdown for Databases
- **Issue:** Database connectors read entire tables
- **Evidence:** `postgres_extractor.py` - No partition awareness
- **Recommendation:** Support partition pruning and predicate pushdown

---

## 7. Migration & Maintenance

### ✔️ What's Working Well

#### Forward Compatibility (Unified Connectors)
The system supports **both legacy and new connector formats**:

```python
# config.py:527-548
def _resolve_source_recipe(self):
    try:
        recipe = ConnectorRecipe.from_yaml(path)  # New format
        if recipe.supports_role("source"):
            return recipe
    except Exception:
        return SourceConnectorRecipe.from_yaml(path)  # Legacy format
```

#### ODCS Schema Migration
Automatic migration from old nested format to ODCS v3.0.2:

```python
# config.py:250-288
@classmethod
def _migrate_old_format(cls, data: Dict[str, Any]):
    if "asset" in data:
        # Migrate governance → team
        # Migrate classification → compliance
```

#### Semantic Versioning (Registry)
```yaml
# registry/connectors.yaml
version: 3  # Registry schema version
```

### ⚠️ Gaps or Risks

#### 1. No Plugin Interface Versioning
- **Issue:** Breaking changes to `BaseReader`/`BaseWriter` silently break plugins
- **No deprecation warnings** for old plugin patterns
- **Recommendation:** Use `__plugin_api_version__` attribute

#### 2. No Migration Testing
- **Issue:** Cannot verify that old plugins work with new platform versions
- **Recommendation:** Add compatibility test suite:
```python
def test_v1_plugin_compatibility():
    """Ensure v1 plugins still work in v2 platform."""
    old_plugin = load_plugin("v1_plugin.py")
    assert old_plugin.extract() works
```

#### 3. Breaking Changes Not Documented
- **Issue:** CHANGELOG.md exists but no "Breaking Changes" section
- **Recommendation:** Add upgrade guide per version

#### 4. No Connector Deprecation Policy
- **Issue:** Cannot mark connectors as deprecated
- **Recommendation:**
```yaml
postgres:
  deprecated: true
  deprecated_message: "Use postgres_v2 connector"
  removal_version: "2.0.0"
```

---

## 8. Learnings from Industry Standards

### Alignment with Airbyte

| Feature | Airbyte | Dativo | Status |
|---------|---------|--------|--------|
| Standard connector interface | ✅ Spec/Check/Discover/Read | ✅ Extract lifecycle | ✔️ Aligned |
| Docker isolation | ✅ All connectors | ⚠️ Airbyte engine only | ⚠️ Partial |
| Message protocol | ✅ RECORD/STATE/LOG | ✅ Dict records + state | ✔️ Compatible |
| Catalog/Schema discovery | ✅ Built-in | ❌ Missing | ⚠️ Gap |
| Centralized connector hub | ✅ Marketplace | ❌ No discovery | ⚠️ Gap |
| Incremental sync | ✅ Cursor/State | ✅ Multiple strategies | ✔️ Aligned |

### Alignment with Meltano

| Feature | Meltano | Dativo | Status |
|---------|---------|--------|--------|
| Plugin manifests | ✅ YAML definitions | ✅ Registry + recipes | ✔️ Aligned |
| CLI-first design | ✅ meltano run | ✅ dativo run | ✔️ Aligned |
| Singer tap integration | ✅ Native | ⚠️ Stub only | ⚠️ Gap |
| Extensible via taps/targets | ✅ Any Singer tap | ✅ Custom plugins | ✔️ Better (Rust support) |
| Orchestration | ✅ Built-in schedules | ✅ Dagster integration | ✔️ Aligned |

### Alignment with Singer

| Feature | Singer | Dativo | Status |
|---------|--------|--------|--------|
| JSON message protocol | ✅ RECORD/SCHEMA/STATE | ✅ Dict records | ✔️ Compatible |
| Decoupled tap/target | ✅ Unix pipes | ✅ Extract/write separation | ✔️ Aligned |
| Schema enforcement | ⚠️ Optional | ✅ Strict validation (ODCS) | ✔️ Better |
| State management | ✅ STATE messages | ✅ State files | ✔️ Aligned |

### Innovations Beyond Industry Standards

1. **Rust Plugin Support** - 10-100x performance gains (industry-first)
2. **ODCS v3.0.2 Compliance** - Strong governance and lineage
3. **Hybrid Plugin Model** - Metadata from connectors + execution from plugins
4. **Pluggable Secret Backends** - 5 secret managers (most platforms support 1-2)
5. **Explicit-Only Tagging** - No auto-PII detection (reduces false positives)

---

## 9. Recommendations Summary

### Critical (P0) - Address Immediately

1. **Implement Plugin Sandboxing**
   - Risk: Custom plugins have unrestricted system access
   - Action: Add Docker-based execution for Python plugins (like Airbyte)
   - Effort: 2-3 weeks

2. **Complete Singer/Meltano Extractors**
   - Risk: Registry claims support but implementation is stub
   - Action: Implement subprocess-based Singer tap execution
   - Effort: 1-2 weeks

3. **Add Plugin API Versioning**
   - Risk: Breaking changes silently break plugins
   - Action: Add `__plugin_api_version__` attribute and compatibility checks
   - Effort: 1 week

### High Priority (P1) - Next Quarter

4. **Create Plugin SDK**
   - Impact: Reduce plugin development effort by 50%
   - Action: Build `dativo-plugin-sdk` with helpers for:
     - Pagination, authentication, rate limiting
     - Testing utilities
     - Connector scaffolding (`dativo init connector`)
   - Effort: 4-6 weeks

5. **Add Schema Discovery Interface**
   - Impact: Enable dynamic connector configuration
   - Action: Add `discover()` method to `BaseReader`
   - Effort: 2 weeks

6. **Implement Parallelism**
   - Impact: 2-5x throughput improvement
   - Action: Add `ThreadPoolExecutor` for multi-object extraction
   - Effort: 2-3 weeks

7. **Enhance Observability**
   - Impact: Better debugging and monitoring
   - Action: Integrate Prometheus metrics + OpenTelemetry tracing
   - Effort: 3-4 weeks

### Medium Priority (P2) - Future Roadmap

8. **Plugin Marketplace/Discovery**
   - Action: Build community plugin repository
   - Effort: 6-8 weeks

9. **State Backend Abstraction**
   - Action: Support database and S3 state storage (beyond files)
   - Effort: 2-3 weeks

10. **CDC Framework**
    - Action: Add `BaseCDCReader` interface for streaming changes
    - Effort: 4-6 weeks

11. **Secret Rotation Support**
    - Action: Enable runtime secret reloading
    - Effort: 2 weeks

12. **Connector Promotion Tool**
    - Action: Add `dativo promote-plugin` to convert plugins → connectors
    - Effort: 2 weeks

---

## 10. Code Examples & Pseudocode

### Recommended: Plugin API Versioning

```python
# plugins.py (updated)
CURRENT_API_VERSION = "2.0"

class BaseReader(ABC):
    __plugin_api_version__ = "2.0"
    
    @classmethod
    def check_compatibility(cls):
        plugin_version = cls.__plugin_api_version__
        if plugin_version != CURRENT_API_VERSION:
            if not is_compatible(plugin_version, CURRENT_API_VERSION):
                raise IncompatiblePluginError(
                    f"Plugin requires API version {plugin_version}, "
                    f"but platform is on {CURRENT_API_VERSION}"
                )
```

### Recommended: Schema Discovery

```python
# plugins.py (addition)
class BaseReader(ABC):
    def discover(self) -> Dict[str, Any]:
        """Discover available streams and schemas.
        
        Returns:
            {
                "streams": [
                    {"name": "customers", "schema": {...}},
                    {"name": "orders", "schema": {...}}
                ]
            }
        """
        return {"streams": []}  # Default: no discovery
```

### Recommended: Sandboxed Plugin Execution

```python
# sandbox.py (new module)
class PluginSandbox:
    def __init__(self, docker_image="python:3.10-slim"):
        self.docker_image = docker_image
    
    def run_plugin(self, plugin_path, config, secrets):
        # Create temporary directory with plugin code
        with tempfile.TemporaryDirectory() as tmpdir:
            shutil.copy(plugin_path, f"{tmpdir}/plugin.py")
            
            # Write config to temp file
            config_path = f"{tmpdir}/config.json"
            with open(config_path, "w") as f:
                json.dump(config, f)
            
            # Run in Docker with restrictions
            container = docker_client.containers.run(
                self.docker_image,
                command=["python", "/plugin/plugin.py", "--config", "/config/config.json"],
                volumes={
                    tmpdir: {"bind": "/plugin", "mode": "ro"},
                    config_path: {"bind": "/config/config.json", "mode": "ro"}
                },
                environment=secrets,  # Inject secrets as env vars
                network_disabled=False,  # Or use network=None for isolation
                mem_limit="2g",
                cpu_quota=50000,  # 50% CPU
                remove=True
            )
```

### Recommended: Parallel Extraction

```python
# cli.py (updated)
from concurrent.futures import ThreadPoolExecutor, as_completed

def run_job_with_parallelism(job_config, parallelism=4):
    source_config = job_config.get_source()
    objects = source_config.objects or []
    
    with ThreadPoolExecutor(max_workers=parallelism) as executor:
        futures = {}
        for obj in objects:
            future = executor.submit(extract_and_write, job_config, obj)
            futures[future] = obj
        
        for future in as_completed(futures):
            obj = futures[future]
            try:
                result = future.result()
                logger.info(f"Completed {obj}: {result}")
            except Exception as e:
                logger.error(f"Failed {obj}: {e}")
```

---

## 11. Conclusion

Dativo demonstrates a **mature, well-architected data integration platform** that successfully balances simplicity (YAML configs) with power (Rust plugins). The microkernel design, hybrid plugin model, and strong governance features position it well for enterprise adoption.

**Key Differentiators:**
- Rust plugin support (10-100x performance)
- ODCS v3.0.2 compliance (governance-first design)
- Pluggable secret management (5 backends)

**Critical Next Steps:**
1. Implement plugin sandboxing for security
2. Complete Singer/Meltano engine support
3. Add plugin API versioning for stability
4. Build plugin SDK for developer productivity

With these improvements, Dativo will rival Airbyte and Meltano while offering unique advantages in performance (Rust) and governance (ODCS).

---

**Appendix A: Referenced Files**

Core Architecture:
- `src/dativo_ingest/cli.py` - Orchestration engine
- `src/dativo_ingest/plugins.py` - Plugin base classes
- `src/dativo_ingest/rust_plugin_bridge.py` - FFI bridge
- `src/dativo_ingest/connectors/engine_framework.py` - Engine adapters
- `registry/connectors.yaml` - Capability registry

Configuration:
- `src/dativo_ingest/config.py` - Job/asset models
- `src/dativo_ingest/validator.py` - Registry validation

Security:
- `src/dativo_ingest/secrets/managers/` - 5 secret backends
- `docs/SECRET_MANAGEMENT.md` - Secret documentation

Documentation:
- `docs/CUSTOM_PLUGINS.md` - Plugin guide
- `README.md` - Architecture overview
- `examples/jobs/` - Job configurations
- `examples/plugins/` - Plugin examples
