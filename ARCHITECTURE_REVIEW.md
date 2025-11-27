# Dativo Platform Architecture Review

**Review Date**: November 27, 2025  
**Reviewer**: Platform Architecture Assessment  
**Scope**: Hybrid plugin model combining config-driven connectors and custom code plugins

---

## Executive Summary

The Dativo platform implements a **hybrid plugin architecture** that successfully bridges config-driven connectors (Airbyte/Singer-style) with custom code plugins (Python/Rust). The system demonstrates strong separation of concerns, extensible interfaces, and pragmatic choices for multi-tenant data ingestion. Key strengths include flexible engine support, robust schema validation, and high-performance Rust plugin integration. Primary gaps involve plugin discoverability, versioning, and standardized messaging protocols.

**Overall Assessment**: ✅ **Solid Foundation** with clear opportunities for standardization and ecosystem alignment.

---

## 1. Architecture & Modularity

### ✔️ What's Working Well

**Plugin/Microkernel Architecture**
- Clear separation between **orchestration layer** (Dagster), **execution engine** (CLI runner), and **connector/plugin layer**
- Plugin loading via dynamic import (`PluginLoader`) with support for both Python and Rust plugins
- Orchestration is truly agnostic to plugin implementation:
  ```python
  # src/dativo_ingest/orchestrated.py
  # Orchestrator invokes CLI subprocess - no direct connector coupling
  subprocess.run([sys.executable, "-m", "dativo_ingest.cli", "run", ...])
  ```

**Connector Isolation**
- Connectors defined as **tenant-agnostic YAML recipes** (`connectors/stripe.yaml`, `connectors/iceberg.yaml`)
- Jobs reference connectors by path, enabling versioning and reuse
- Source/target configs merged at runtime without tight coupling:
  ```yaml
  # Job config references connector recipe
  source_connector_path: connectors/stripe.yaml
  source:
    objects: [customers]  # Job-specific overrides
  ```

**Engine Abstraction**
- `BaseEngineExtractor` provides uniform interface across engine types:
  - **Native**: Direct Python implementations
  - **Airbyte**: Docker container execution
  - **Meltano/Singer**: CLI subprocess execution (future)
- Engine selection in connector recipe, not hardcoded:
  ```yaml
  # connectors/stripe.yaml
  default_engine:
    type: airbyte
    options:
      docker_image: "airbyte/source-stripe:2.1.5"
  ```

**Composability**
- Connectors, assets, and jobs are independently versionable
- Asset schemas (ODCS v3.0.2) decoupled from connector implementation
- Hybrid approach: Use connector for metadata + custom plugin for execution

### ⚠️ Gaps and Risks

**Engine Framework Incomplete**
- Meltano/Singer engines referenced but not fully implemented
- Missing protocol adapters for Singer JSON message format
- Risk: Airbyte-heavy implementation may not generalize well

**Cross-Cutting Concerns**
- Secrets management tightly coupled to job execution (not abstracted into middleware)
- Logging/tracing spread across components (no unified observability layer)
- Retry logic implemented in orchestrator, not reusable by CLI runner

**State Management**
- Incremental state tied to filesystem (`IncrementalStateManager`)
- No abstraction for pluggable state backends (database, S3, etc.)
- Risk: Scalability bottleneck for high-frequency syncs

### 💡 Recommendations

1. **Complete Engine Framework**
   - Implement Singer protocol adapter:
     ```python
     class SingerExtractor(BaseEngineExtractor):
         def extract(self):
             # Parse RECORD/STATE/SCHEMA messages
             for line in self._run_singer_tap():
                 msg = json.loads(line)
                 if msg['type'] == 'RECORD':
                     yield [msg['record']]
     ```
   - Add Meltano wrapper for Singer taps/targets

2. **Abstract State Management**
   ```python
   class StateBackend(ABC):
       @abstractmethod
       def read_state(self, key: str) -> Dict[str, Any]: pass
       @abstractmethod
       def write_state(self, key: str, state: Dict[str, Any]): pass
   
   # Implementations: FilesystemStateBackend, S3StateBackend, DBStateBackend
   ```

3. **Extract Cross-Cutting Middleware**
   - Secrets injection middleware
   - Observability middleware (tracing, metrics)
   - Retry middleware (reusable across CLI and orchestrator)

---

## 2. Connector vs Plugin Decision Framework

### ✔️ What's Working Well

**Clear Separation of Concerns**
- **Connectors**: Tenant-agnostic, configuration-driven, reusable across jobs
- **Custom Plugins**: Code-driven, job-specific, performance-optimized
- Excellent documentation in `docs/CUSTOM_PLUGINS.md` explaining when to use each

**Hybrid Model Support**
```yaml
# Job can reference connector for metadata but use custom plugin
source_connector: postgres  # Registry entry + connection template
source_connector_path: connectors/postgres.yaml
source:
  custom_reader: "/app/plugins/high_perf_postgres.py:FastReader"
  connection:
    host: "${DB_HOST}"
```

**Connector Registry**
- `registry/connector_registry.yaml` validates connector types and capabilities
- Supports both unified (`connectors`) and legacy (`sources`/`targets`) formats
- Validates mode restrictions (e.g., databases only in `self_hosted`)

### ⚠️ Gaps and Risks

**No Formal Decision Tree**
- Decision criteria scattered across documentation
- Missing machine-readable policy (e.g., "Use connector if exists in registry, else custom plugin")

**Plugin Registry Missing**
- No centralized registry of available custom plugins
- Cannot discover plugins without filesystem access
- No metadata about plugin capabilities, version, or compatibility

**Hybrid Model Ambiguity**
- When using both connector + custom plugin, unclear which takes precedence
- Connection config merged from recipe + job, but no explicit override rules documented

### 💡 Recommendations

1. **Formalize Decision Framework**
   Create `docs/CONNECTOR_DECISION_MATRIX.md`:
   ```markdown
   | Scenario | Recommendation | Example |
   |----------|----------------|---------|
   | Standard API (registry) | Connector | Stripe, HubSpot |
   | Custom API | Custom Plugin | Internal REST API |
   | Performance critical (>1GB) | Rust Plugin | Large CSV files |
   | Rapid prototyping | Python Plugin | One-off extraction |
   ```

2. **Create Plugin Registry**
   ```yaml
   # registry/plugins.yaml
   plugins:
     high_performance_csv_reader:
       type: reader
       language: rust
       path: examples/plugins/rust/target/release/libcsv_reader_plugin.so
       version: "1.0.0"
       capabilities:
         - streaming
         - incremental
       performance_profile: high_memory_low_latency
   ```

3. **Document Precedence Rules**
   In job config schema:
   ```yaml
   # Precedence: custom_reader > connector engine > default behavior
   source:
     custom_reader: "..."  # Highest priority - bypasses connector engine
     # ... connector engine used if no custom_reader
   ```

---

## 3. Interface Design

### ✔️ What's Working Well

**Shared Plugin Lifecycle**
- Consistent interface across Python/Rust plugins:
  ```python
  class BaseReader(ABC):
      def __init__(self, source_config): ...
      @abstractmethod
      def extract(self, state_manager) -> Iterator[List[Dict]]: ...
      def get_total_records_estimate(self) -> Optional[int]: ...
  
  class BaseWriter(ABC):
      def __init__(self, asset_definition, target_config, output_base): ...
      @abstractmethod
      def write_batch(self, records, file_counter) -> List[Dict]: ...
      def commit_files(self, file_metadata) -> Dict[str, Any]: ...
  ```

**Data Format Standardization**
- Records always as `List[Dict[str, Any]]` (like Singer)
- Schema validation via ODCS v3.0.2 (JSON Schema-compatible)
- Metadata returned as dicts with standard keys (`path`, `size_bytes`, `record_count`)

**Rust FFI Bridge**
- Clean C FFI boundary with JSON serialization:
  ```rust
  #[no_mangle]
  pub extern "C" fn create_reader(config_json: *const c_char) -> *mut Reader
  #[no_mangle]
  pub extern "C" fn extract_batch(reader: *mut Reader) -> *const c_char  // JSON
  #[no_mangle]
  pub extern "C" fn free_reader(reader: *mut Reader)
  #[no_mangle]
  pub extern "C" fn free_string(s: *const c_char)
  ```

### ⚠️ Gaps and Risks

**No Standardized Message Protocol**
- Custom JSON dict format, not Singer RECORD/SCHEMA/STATE messages
- Cannot directly consume external Singer taps without translation
- Missing: `discover` method (schema introspection)

**Limited Lifecycle Hooks**
- No `setup()` / `teardown()` hooks for resource management
- No `validate_config()` for pre-flight checks
- No `catalog` / `discover` for schema introspection

**CLI/RPC Adapter Missing**
- External connectors (Airbyte) wrapped via Docker subprocess
- No RPC-style adapter for long-running connector processes
- Singer taps invoked via subprocess but output not fully parsed

**Metadata Exchange Incomplete**
- No `extract_metadata()` contract in `BaseReader` (exists in some subclasses)
- Plugin capabilities not machine-readable (e.g., "supports incremental", "supports backfill")

### 💡 Recommendations

1. **Adopt Singer Protocol (Subset)**
   ```python
   class BaseReader(ABC):
       def discover(self) -> Dict[str, Any]:
           """Return Singer SCHEMA message."""
           return {
               "type": "SCHEMA",
               "stream": self.source_config.objects[0],
               "schema": {"properties": {...}}
           }
       
       def extract(self, state_manager) -> Iterator[Dict[str, Any]]:
           """Yield Singer RECORD messages."""
           for batch in self._extract_batch():
               for record in batch:
                   yield {
                       "type": "RECORD",
                       "stream": "...",
                       "record": record
                   }
   ```

2. **Add Lifecycle Hooks**
   ```python
   class BaseReader(ABC):
       def setup(self) -> None:
           """Initialize connections, validate config."""
           pass
       
       def teardown(self) -> None:
           """Close connections, cleanup resources."""
           pass
       
       def validate_config(self) -> List[str]:
           """Return list of validation errors."""
           return []
   ```

3. **Create RPC Adapter**
   ```python
   class RPCConnectorAdapter:
       """Wrap external connectors as long-running processes."""
       def start(self, connector_image: str):
           self.process = subprocess.Popen(...)
       
       def send_request(self, method: str, params: Dict) -> Dict:
           # JSON-RPC over stdin/stdout
           ...
   ```

4. **Standardize Metadata Contract**
   ```python
   class ConnectorCapabilities(BaseModel):
       supports_incremental: bool
       supports_backfill: bool
       supports_discovery: bool
       max_concurrency: int
   
   class BaseReader(ABC):
       def get_capabilities(self) -> ConnectorCapabilities:
           return ConnectorCapabilities(...)
   ```

---

## 4. Extensibility & SDK Patterns

### ✔️ What's Working Well

**Declarative Plugin Registration**
- Plugins registered in job config via path:
  ```yaml
  source:
    custom_reader: "/app/plugins/my_reader.py:MyReader"
  ```
- Dynamic loading via `PluginLoader` with validation

**Language SDK (Implicit)**
- Python: `BaseReader`/`BaseWriter` abstract classes
- Rust: FFI interface pattern with JSON marshaling
- Both follow same conceptual model (config → init → extract/write → cleanup)

**Excellent Examples**
- `examples/plugins/` contains working Python plugins
- `examples/plugins/rust/` contains Rust plugins with Makefiles
- `docs/CUSTOM_PLUGINS.md` comprehensive guide

**Connector Recipe Format**
- YAML-based, easily versionable
- Supports multiple engines in single recipe
- Environment variable substitution: `"${STRIPE_API_KEY}"`

### ⚠️ Gaps and Risks

**No SDK Package**
- No pip-installable `dativo-plugin-sdk` package
- Plugin developers must import from main package: `from dativo_ingest.plugins import BaseReader`
- Risk: Breaking changes in main package affect plugins

**Plugin Versioning Missing**
- No version field in plugin manifest
- No compatibility check between plugin and platform versions
- Breaking changes not documented in plugin API

**Not Independently Deployable**
- Plugins deployed alongside platform code
- Cannot deploy/update plugins without redeploying platform
- No plugin marketplace or remote loading

**Discovery Mechanism Weak**
- Plugins located via hardcoded paths in job configs
- No `list_plugins()` or `discover_plugins(dir)` API
- Cannot introspect available plugins programmatically

### 💡 Recommendations

1. **Create SDK Package**
   ```
   # New package: dativo-plugin-sdk
   src/
     dativo_plugin_sdk/
       __init__.py
       reader.py       # BaseReader
       writer.py       # BaseWriter
       types.py        # Common types
       testing.py      # Test utilities
   
   # Install separately:
   pip install dativo-plugin-sdk
   ```

2. **Version Plugin API**
   ```python
   # dativo_plugin_sdk/__init__.py
   __version__ = "1.0.0"
   __api_version__ = "1.0"
   
   class BaseReader(ABC):
       @classmethod
       def min_sdk_version(cls) -> str:
           return "1.0.0"
   
   # Plugin manifest:
   class MyReader(BaseReader):
       __plugin_version__ = "2.1.0"
       __sdk_version__ = "1.0.0"
   ```

3. **Add Plugin Manifest**
   ```yaml
   # plugins/my_reader/manifest.yaml
   name: my_custom_reader
   version: "1.0.0"
   sdk_version: "1.0.0"
   type: reader
   entry_point: "my_reader.py:MyReader"
   capabilities:
     - incremental
     - parallel
   dependencies:
     - requests>=2.28.0
   ```

4. **Implement Plugin Discovery**
   ```python
   class PluginRegistry:
       def discover(self, plugin_dir: Path) -> List[PluginManifest]:
           """Scan directory for plugin manifests."""
           ...
       
       def load_plugin(self, name: str) -> Type[BaseReader]:
           """Load plugin by name from registry."""
           ...
       
       def validate_plugin(self, plugin_class: Type) -> List[str]:
           """Validate plugin implements required interface."""
           ...
   ```

5. **Plugin Packaging (Future)**
   ```bash
   # Package plugins as wheels
   cd plugins/my_reader
   poetry build
   pip install dist/my_reader-1.0.0-py3-none-any.whl
   
   # Reference by package name instead of path
   source:
     custom_reader: "my_reader:MyReader"  # Resolved from installed packages
   ```

---

## 5. Security & Isolation

### ✔️ What's Working Well

**Container Isolation (Airbyte)**
- Airbyte connectors run in Docker containers
- Resource limits configurable
- Network isolation via Docker networking

**Secret Management**
- Multiple backends: env vars, filesystem, Vault, AWS Secrets Manager, GCP Secret Manager
- Secrets loaded at runtime, not stored in job configs
- Environment variable substitution: `"${STRIPE_API_KEY}"`
- Filesystem secrets organized by tenant: `secrets/{tenant_id}/stripe.json`

**Credential Scoping**
- Secrets scoped to tenant_id
- Job configs don't contain sensitive data
- Connector recipes use environment variable references

**Audit Logging**
- Structured logging with event types (`job_started`, `extractor_initialized`)
- Tenant ID included in all log events
- Can filter by event type for audit trail

### ⚠️ Gaps and Risks

**No Plugin Sandboxing (Native)**
- Python plugins run in same process as platform
- No resource limits (CPU, memory, disk I/O)
- Malicious plugin can access entire filesystem
- Risk: Tenant A's plugin can read Tenant B's data

**Secret Injection Not Abstracted**
- Secrets loaded globally at job start
- All secrets visible to plugin via environment variables
- No fine-grained access control (plugin can only see its own secrets)

**Limited Audit Trail**
- No tracking of which plugins accessed which secrets
- No data lineage tracking (which records touched by which plugin)
- No access control logs

**Docker Security**
- Airbyte containers run as root (no user namespaces)
- Containers can access host Docker socket if mounted
- No image scanning for vulnerabilities

**No Input Validation**
- Plugin configs not validated against schema before execution
- Risk: Malicious config could exploit plugin vulnerabilities

### 💡 Recommendations

1. **Sandbox Python Plugins**
   ```python
   # Use subprocess + IPC instead of dynamic import
   class SandboxedPluginLoader:
       def load_plugin(self, plugin_path: str, config: Dict) -> PluginRunner:
           # Run plugin in separate process with resource limits
           proc = subprocess.Popen(
               ["python", "-m", "dativo_plugin_runner", plugin_path],
               stdin=subprocess.PIPE,
               stdout=subprocess.PIPE,
               # Resource limits
               preexec_fn=lambda: resource.setrlimit(
                   resource.RLIMIT_AS, (1 * 1024**3, 1 * 1024**3)  # 1GB RAM
               )
           )
           return PluginRunner(proc)
   ```

2. **Fine-Grained Secret Injection**
   ```python
   class SecretManager:
       def inject_secrets(
           self, 
           tenant_id: str, 
           plugin_id: str,
           required_secrets: List[str]
       ) -> Dict[str, str]:
           """Only provide secrets explicitly requested by plugin."""
           # Audit log: plugin X requested secret Y
           ...
   ```

3. **Audit Pipeline Access**
   ```python
   class AuditLogger:
       def log_data_access(
           self,
           tenant_id: str,
           plugin_id: str,
           resource: str,  # table, file, API endpoint
           action: str,    # read, write
           record_count: int
       ):
           # Write to audit log backend (database, SIEM)
           ...
   ```

4. **Validate Plugin Configs**
   ```python
   class PluginConfigValidator:
       def validate(
           self, 
           plugin_class: Type[BaseReader],
           config: Dict[str, Any]
       ) -> List[ValidationError]:
           """Validate config against plugin's schema."""
           schema = plugin_class.get_config_schema()
           return jsonschema.validate(config, schema)
   ```

5. **Docker Security Hardening**
   ```yaml
   # docker-compose.yml
   services:
     connector:
       security_opt:
         - no-new-privileges:true
       user: "1000:1000"  # Non-root user
       read_only: true
       tmpfs:
         - /tmp
       cap_drop:
         - ALL
   ```

---

## 6. Performance & Scaling

### ✔️ What's Working Well

**Incremental Sync Support**
- File-based: `file_modified_time` strategy with state tracking
- API-based: `updated_at`, `created` cursor strategies
- State persistence via `IncrementalStateManager`

**Batch Processing**
- Records processed in configurable batches (default 1000-50000)
- Parquet files sized to target (128-200 MB)
- Streaming extraction (generators) - constant memory

**Parallelism (Rust)**
- Rust plugins provide 10-100x speedup for data-intensive ops
- Example: CSV reader 15x faster, 12x less memory
- Parquet writer 3.5x faster, 27% better compression

**Observability**
- Structured logging with performance metrics
- Event types for filtering (`batch_written`, `commit_success`)
- Record counts and file sizes tracked

**Memory Efficiency**
- Streaming architecture (iterators, not lists)
- Parquet written incrementally via PyArrow
- CSV read in chunks via pandas

### ⚠️ Gaps and Risks

**No Parallelism (Python)**
- Files processed sequentially
- No concurrent API requests
- Single-threaded validation
- Risk: Slow for large job queues

**Batch Size Not Tunable Per Connector**
- Hardcoded batch sizes in extractors
- Should be configurable via engine options

**No Backpressure Handling**
- Fast extractor + slow writer = memory bloat
- No queue size limits between stages

**CDC Not Supported**
- No Change Data Capture for databases
- Full table scan or cursor-based only
- Risk: Cannot efficiently sync large tables

**Rate Limiting Basic**
- Simple sleep-based rate limiting in connectors
- No token bucket or adaptive backoff
- No shared rate limiter across concurrent jobs

**State Synchronization Issues**
- State written only after full job success
- Partial failure = re-process all data
- No checkpoint/resume within job

### 💡 Recommendations

1. **Add Parallelism**
   ```python
   from concurrent.futures import ThreadPoolExecutor
   
   class ParallelExtractor:
       def extract_parallel(
           self, 
           files: List[str],
           max_workers: int = 4
       ) -> Iterator[List[Dict]]:
           with ThreadPoolExecutor(max_workers=max_workers) as executor:
               futures = [executor.submit(self._extract_file, f) for f in files]
               for future in futures:
                   yield future.result()
   ```

2. **Implement Backpressure**
   ```python
   from queue import Queue
   
   class BufferedPipeline:
       def __init__(self, max_queue_size: int = 10):
           self.queue = Queue(maxsize=max_queue_size)
       
       def run(self):
           # Producer (extractor) blocks when queue full
           # Consumer (writer) processes from queue
           ...
   ```

3. **Add CDC Support**
   ```python
   class PostgresCDCExtractor(BaseReader):
       def extract(self, state_manager):
           # Use logical replication slot
           with psycopg2.connect(dsn, replication=True) as conn:
               for change in conn.cursor().consume_stream():
                   if change.operation == 'INSERT':
                       yield [{"op": "insert", "record": change.new}]
   ```

4. **Tunable Batch Sizes**
   ```yaml
   source:
     engine:
       options:
         batch_size: 10000        # Records per batch
         parallel_workers: 4       # Concurrent extractors
         max_queue_size: 20        # Backpressure limit
   ```

5. **Advanced Rate Limiting**
   ```python
   import aiolimiter
   
   class AdaptiveRateLimiter:
       def __init__(self, rps: int):
           self.limiter = aiolimiter.AsyncLimiter(rps, 1.0)
       
       async def acquire(self):
           async with self.limiter:
               # Adaptive: Increase rate on success, decrease on 429
               ...
   ```

6. **Checkpoint State**
   ```python
   class CheckpointedExtractor:
       def extract(self, state_manager):
           for batch_idx, batch in enumerate(self._extract_batches()):
               yield batch
               # Checkpoint every N batches
               if batch_idx % 10 == 0:
                   state_manager.write_state({
                       "last_checkpoint_batch": batch_idx,
                       "cursor": batch[-1]["updated_at"]
                   })
   ```

---

## 7. Migration & Compatibility

### ✔️ What's Working Well

**Forward Migration Path**
- Documentation explains transitioning from custom plugins to connectors
- Hybrid model allows gradual migration (use connector + custom plugin together)

**Backward Compatibility**
- Supports both old (`sources`/`targets`) and new (`connectors`) registry formats
- Old nested asset format migrated automatically:
  ```python
  @classmethod
  def _migrate_old_format(cls, data: Dict[str, Any]) -> Dict[str, Any]:
      if "asset" in data:
          # Migrate to ODCS flat format
          ...
  ```

**Version-Aware Asset Schemas**
- Assets versioned in directory structure: `assets/stripe/v1.0/customers.yaml`
- Asset definitions include `apiVersion: v3.0.2`
- Schema reference: `$schema: schemas/odcs/dativo-odcs-3.0.2-extended.schema.json`

**Deprecation Warnings**
- Old config fields marked deprecated with fallbacks:
  ```python
  retry_delay_seconds: Optional[int] = 5  # Deprecated: use initial_delay_seconds
  ```

### ⚠️ Gaps and Risks

**Plugin API Not Versioned**
- No `@since` or `@deprecated` annotations on plugin methods
- Breaking changes not documented
- Plugins have no way to declare minimum platform version

**No Interface Versioning**
- `BaseReader`/`BaseWriter` can change without notice
- No contract testing between platform and plugins

**Migration Tooling Missing**
- No automated migration scripts for config formats
- Manual edits required when upgrading

**Changelog Incomplete**
- `CHANGELOG.md` exists but doesn't track API changes
- No migration guide per version

**No Compatibility Matrix**
- Cannot determine which plugin versions work with which platform versions
- No automated compatibility testing

### 💡 Recommendations

1. **Version Plugin API**
   ```python
   # dativo_plugin_sdk/__init__.py
   __api_version__ = "1.0"
   
   class BaseReader(ABC):
       """Reader interface.
       
       @since: v1.0.0
       @stable: True
       """
       
       @abstractmethod
       def extract(self, state_manager) -> Iterator[List[Dict]]:
           """Extract data.
           
           @since: v1.0.0
           @deprecated: v2.0.0 (use extract_stream instead)
           """
           pass
   ```

2. **Add Contract Tests**
   ```python
   # tests/plugin_contract_test.py
   def test_reader_interface(plugin_class: Type[BaseReader]):
       """Verify plugin implements required interface."""
       assert hasattr(plugin_class, 'extract')
       assert hasattr(plugin_class, '__init__')
       # Check method signatures match expected
       ...
   ```

3. **Create Migration CLI**
   ```bash
   # Migrate configs to new format
   dativo migrate --from v1.0 --to v2.0 --config-dir jobs/
   
   # Check compatibility
   dativo check-compatibility --plugin my_reader.py --platform-version 2.0
   ```

4. **Document Breaking Changes**
   ```markdown
   # CHANGELOG.md
   ## [2.0.0] - 2025-02-01
   ### Breaking Changes
   - BaseReader.extract() signature changed: removed state_manager parameter
   - Migration: Update plugins to use get_state() method instead
   ```

5. **Compatibility Matrix**
   ```yaml
   # compatibility.yaml
   platform_version: "2.0.0"
   compatible_plugins:
     - name: csv_reader
       min_version: "1.5.0"
       max_version: "2.x"
     - name: stripe_reader
       min_version: "2.0.0"
   ```

---

## 8. Learnings from Airbyte, Meltano, Singer

### ✔️ Patterns Mirrored Successfully

**Airbyte**
- ✅ Docker-based connector isolation (`AirbyteExtractor`)
- ✅ Connector registry with capabilities
- ✅ Config-driven connector recipes (YAML)
- ✅ Source/target separation

**Meltano**
- ✅ Plugin manifests (connector YAML recipes)
- ✅ CLI-first execution model (`dativo run`)
- ✅ Orchestration layer (Dagster) separate from execution

**Singer**
- ✅ JSON-based data format (`List[Dict[str, Any]]`)
- ✅ Decoupled tap/target architecture (source/target split)
- ✅ Schema validation (ODCS instead of JSON Schema)

### ⚠️ Gaps vs Industry Standards

**vs Airbyte**
- ❌ No centralized connector hub/marketplace
- ❌ No connector versioning in registry
- ❌ No connector health checks or smoke tests
- ❌ Missing: SPEC (config schema), CHECK (connection test), DISCOVER (schema introspection)

**vs Meltano**
- ❌ No `discover` command for connector introspection
- ❌ No plugin lockfile (like `meltano.yml`)
- ❌ No dbt integration (transformation layer)
- ❌ Missing: Singer taps/targets registry integration

**vs Singer**
- ❌ Not using RECORD/SCHEMA/STATE message protocol
- ❌ No `--catalog` flag for stream selection
- ❌ No `--properties` flag for field selection
- ❌ Missing: SCHEMA messages for schema evolution

### 💡 Recommendations

1. **Adopt Singer Message Protocol**
   ```python
   # Align with Singer spec
   class SingerCompatibleExtractor(BaseReader):
       def extract(self, state_manager) -> Iterator[Dict[str, Any]]:
           # Emit SCHEMA message first
           yield {
               "type": "SCHEMA",
               "stream": "customers",
               "schema": {"type": "object", "properties": {...}},
               "key_properties": ["id"]
           }
           
           # Emit RECORD messages
           for batch in self._extract_batches():
               for record in batch:
                   yield {
                       "type": "RECORD",
                       "stream": "customers",
                       "record": record,
                       "time_extracted": "2025-11-27T12:00:00Z"
                   }
           
           # Emit STATE message for incremental
           yield {
               "type": "STATE",
               "value": {"bookmarks": {"customers": {"updated_at": "2025-11-27"}}}
           }
   ```

2. **Implement Airbyte Methods**
   ```python
   class BaseReader(ABC):
       @abstractmethod
       def spec(self) -> Dict[str, Any]:
           """Return connector config spec (JSON Schema)."""
           pass
       
       @abstractmethod
       def check(self) -> Dict[str, Any]:
           """Test connection. Return {"status": "succeeded"} or error."""
           pass
       
       @abstractmethod
       def discover(self) -> Dict[str, Any]:
           """Return available streams and schemas."""
           pass
       
       # Existing method
       def extract(...) -> Iterator: ...
   ```

3. **Create Connector Hub**
   ```yaml
   # hub/connectors.yaml (published online)
   connectors:
     - name: stripe
       version: "2.1.5"
       docker_image: "ghcr.io/dativo/connectors/stripe:2.1.5"
       source_code: "https://github.com/dativo/connectors-stripe"
       documentation: "https://docs.dativo.io/connectors/stripe"
       capabilities:
         - incremental
         - cdc
       supported_streams: [customers, charges, invoices]
   
   # Usage:
   dativo connector install stripe --version 2.1.5
   ```

4. **Add Singer Tap Registry**
   ```python
   # Support Singer taps via Meltano registry
   class SingerTapAdapter:
       def __init__(self, tap_name: str):
           # Load tap from Meltano Hub
           self.tap = meltano.Hub.get_tap(tap_name)
       
       def extract(self, config: Dict) -> Iterator[Dict]:
           # Run tap as subprocess
           proc = subprocess.Popen([self.tap.executable, "--config", ...])
           for line in proc.stdout:
               msg = json.loads(line)
               yield msg  # Singer message
   ```

5. **Implement Stream Selection**
   ```yaml
   # Job config with catalog
   source:
     objects: [customers, invoices]  # Stream selection
     fields:  # Field selection (Singer --properties)
       customers: [id, email, name]
       invoices: [id, amount, customer_id]
   ```

---

## Recommendations Summary

### Priority 1: Critical (Impact: High, Effort: Low-Medium)

1. **Complete Singer Protocol Support**
   - Adopt RECORD/SCHEMA/STATE message format
   - Enable direct Singer tap consumption
   - **Impact**: Instantly compatible with 200+ Singer taps

2. **Version Plugin API**
   - Add `__api_version__` to plugin SDK
   - Document breaking changes
   - **Impact**: Prevents plugin breakage on platform upgrades

3. **Sandbox Native Plugins**
   - Run Python plugins in separate processes
   - Add resource limits (CPU, memory)
   - **Impact**: Critical security gap closed

4. **Add Connector Hub**
   - Centralized registry of available connectors
   - Version management, health checks
   - **Impact**: Easier onboarding, ecosystem growth

### Priority 2: Important (Impact: Medium, Effort: Medium)

5. **Implement Airbyte Methods**
   - Add `spec()`, `check()`, `discover()` to BaseReader
   - **Impact**: Better developer experience, pre-flight validation

6. **Extract Cross-Cutting Middleware**
   - Secrets injection, retry logic, observability
   - **Impact**: Reusable, testable, maintainable

7. **Add Parallelism**
   - Concurrent file extraction, parallel validation
   - **Impact**: 3-5x throughput improvement

8. **Plugin SDK Package**
   - Separate `dativo-plugin-sdk` pip package
   - **Impact**: Decoupled plugin development

### Priority 3: Nice-to-Have (Impact: Low-Medium, Effort: High)

9. **State Backend Abstraction**
   - Pluggable state storage (DB, S3)
   - **Impact**: Scalability for high-frequency syncs

10. **CDC Support**
    - Change Data Capture for databases
    - **Impact**: Efficient large table syncs

11. **dbt Integration**
    - Transformation layer via dbt
    - **Impact**: Completes ELT pipeline (following Meltano model)

---

## Conclusion

**Dativo's architecture is fundamentally sound**, with excellent separation between connectors, plugins, and orchestration. The hybrid model (config + code) is pragmatic and powerful.

**Key strengths:**
- Clean plugin interface (Python + Rust)
- Flexible engine support (native, Airbyte, future Meltano/Singer)
- Strong schema validation (ODCS v3.0.2)
- Multi-tenant design with good tenant isolation

**Primary gaps:**
- Singer protocol not fully adopted (limits ecosystem compatibility)
- Plugin sandboxing missing (security risk)
- No centralized connector hub (discoverability)
- Plugin API versioning absent (stability risk)

**Implementing Priority 1 recommendations** would align Dativo with industry best practices (Airbyte + Singer + Meltano patterns) while preserving its unique hybrid architecture and high-performance Rust plugin capabilities.

---

**Assessment**: ✅ **Solid foundation, ready for ecosystem expansion**

The platform successfully implements a microkernel architecture with extensible plugins. With targeted improvements in protocol standardization, security isolation, and ecosystem tooling, Dativo can scale from internal tool to industry-standard data integration platform.
