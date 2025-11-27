# Dativo ETL Platform - Architecture Review

## Executive Summary

Dativo is a config-driven data ingestion platform supporting a hybrid plugin model combining YAML-configured connectors (Airbyte/Singer/Meltano-style) with custom Python/Rust code plugins. The system demonstrates solid architectural foundations with clear separation of concerns, but has several gaps in interface standardization, security isolation, and extensibility patterns that should be addressed to align with industry best practices.

---

## Architecture & Modularity

### ✔️ What's Working Well

1. **Clear Separation of Concerns**
   - Connector recipes (YAML) are tenant-agnostic and reusable
   - Job configs merge recipes with tenant-specific overrides
   - Asset definitions (ODCS v3.0.2) separate schema from execution
   - Orchestration (Dagster) is optional and decoupled

2. **Plugin Architecture Foundation**
   - Base classes (`BaseReader`, `BaseWriter`) provide clear contracts
   - Plugin loader supports both Python and Rust via dynamic loading
   - Custom plugins can bypass connector system entirely when needed

3. **Engine Abstraction**
   - `BaseEngineExtractor` abstracts Airbyte/Meltano/Singer execution
   - Connector recipes declare supported engines (`engines_supported`)
   - Native extractors coexist with engine-based ones

4. **Registry-Based Validation**
   - `ConnectorValidator` validates against `registry/connectors.yaml`
   - Registry tracks capabilities (incremental, roles, cloud mode)
   - Mode restrictions (self_hosted vs cloud) enforced

### ⚠️ Gaps & Risks

1. **Inconsistent Extractor Interfaces**
   - Native extractors (`CSVExtractor`, `PostgresExtractor`) don't inherit from `BaseEngineExtractor`
   - Some extractors (Stripe, HubSpot) wrap `AirbyteExtractor` but add custom metadata
   - No unified interface for all extractors (native, engine-based, custom)
   - **Impact**: Hard to add cross-cutting concerns (metrics, retries, state) uniformly

2. **Tight Coupling in CLI**
   - `cli.py` has hardcoded `if/elif` chains for connector routing (lines 463-548)
   - New connectors require code changes in CLI, not just config
   - **Impact**: Violates Open/Closed Principle; limits extensibility

3. **Missing Microkernel Pattern**
   - No plugin registry/discovery mechanism
   - Connectors registered in YAML but not dynamically discoverable
   - No plugin lifecycle management (install, update, uninstall)

4. **Orchestration Dependency**
   - Dagster integration exists but orchestration is optional
   - No clear abstraction for different orchestrators
   - **Impact**: Hard to swap orchestrators or support multiple simultaneously

### 💡 Recommendations

1. **Unified Extractor Interface**
   ```python
   class Extractor(ABC):
       @abstractmethod
       def extract(self, state_manager: Optional[IncrementalStateManager]) -> Iterator[List[Dict]]:
           pass
       
       @abstractmethod
       def discover_schema(self) -> Dict[str, Any]:
           """Return schema/catalog (like Singer/Airbyte discover)"""
           pass
       
       @abstractmethod
       def check_connection(self) -> bool:
           """Validate connection (like Singer/Airbyte check)"""
           pass
   ```
   - Make all extractors (native, engine-based, custom) implement this
   - Move routing logic to factory pattern based on connector registry

2. **Plugin Registry System**
   ```yaml
   # plugins/registry.yaml
   plugins:
     csv_reader_rust:
       type: rust
       path: "plugins/rust/target/release/libcsv_reader.so"
       entry_point: "create_reader"
       version: "1.0.0"
       capabilities: [read, incremental]
   ```
   - Auto-discover plugins from registry
   - Support plugin versioning and dependencies

3. **Factory-Based Routing**
   ```python
   class ExtractorFactory:
       def create(self, source_config, connector_recipe, tenant_id):
           # Check custom_reader first
           if source_config.custom_reader:
               return PluginLoader.load_reader(...)
           
           # Check registry for engine type
           engine_type = connector_recipe.default_engine.get("type")
           
           # Route to engine framework or native extractor
           return self._create_by_engine(engine_type, ...)
   ```
   - Remove hardcoded if/elif chains from CLI
   - Enable new connectors via config only

---

## Connector vs Plugin Decision Framework

### ✔️ What's Working Well

1. **Clear Documentation**
   - `docs/CUSTOM_PLUGINS.md` explains when to use connectors vs plugins
   - Connectors for standard sources (Stripe, HubSpot, PostgreSQL)
   - Custom plugins for proprietary APIs or performance-critical paths

2. **Hybrid Support**
   - Custom readers can reference connectors for metadata only
   - Example: `source_connector_path: connectors/csv.yaml` with `custom_reader`

3. **Registry Tracks Capabilities**
   - `connectors.yaml` declares `engines_supported`, `supports_incremental`, `roles`
   - Validator enforces mode restrictions (cloud vs self_hosted)

### ⚠️ Gaps & Risks

1. **No Explicit Decision Framework in Code**
   - Documentation exists but no programmatic guidance
   - No validation that custom plugin is necessary when connector exists
   - **Impact**: Users may create custom plugins unnecessarily

2. **Limited Hybrid Plugin Support**
   - Can't extend/override standard connectors with custom logic
   - No "wrapper" pattern to add custom logic around Airbyte connectors
   - **Impact**: Forces full custom implementation even for small customizations

3. **No Plugin Composition**
   - Can't chain plugins (e.g., custom reader → standard writer)
   - No middleware/interceptor pattern for cross-cutting concerns
   - **Impact**: Code duplication for common patterns (retries, rate limiting)

### 💡 Recommendations

1. **Decision Framework as Code**
   ```python
   class PluginDecisionFramework:
       def should_use_custom_plugin(self, source_type, requirements):
           """Returns recommendation with rationale"""
           if source_type in STANDARD_CONNECTORS:
               if requirements.get("performance") > 10x:
                   return "custom_rust_plugin"
               if requirements.get("custom_auth"):
                   return "custom_python_plugin"
               return "standard_connector"
   ```

2. **Connector Extension Pattern**
   ```python
   class ExtendedAirbyteExtractor(AirbyteExtractor):
       """Extends Airbyte with custom pre/post processing"""
       def extract(self, state_manager):
           # Custom pre-processing
           records = super().extract(state_manager)
           # Custom post-processing
           yield from self._transform(records)
   ```
   - Support connector inheritance/composition
   - Allow plugins to wrap standard connectors

3. **Plugin Middleware**
   ```python
   class RetryMiddleware(BaseReader):
       def __init__(self, reader: BaseReader, retry_config):
           self.reader = reader
           self.retry_config = retry_config
       
       def extract(self, state_manager):
           # Add retry logic around reader
   ```
   - Enable cross-cutting concerns without modifying plugins

---

## Interface Design

### ✔️ What's Working Well

1. **Base Plugin Interfaces**
   - `BaseReader.extract()` returns `Iterator[List[Dict]]` (batch-oriented)
   - `BaseWriter.write_batch()` accepts batches
   - Consistent data format (list of dictionaries)

2. **State Management Interface**
   - `IncrementalStateManager` provides state persistence
   - State path configurable per job/tenant
   - Airbyte state messages integrated

3. **Config-Driven Approach**
   - `SourceConfig` and `TargetConfig` are Pydantic models
   - Type validation and schema enforcement
   - Environment variable resolution

### ⚠️ Gaps & Risks

1. **Incomplete Lifecycle Methods**
   - No `discover()` method (like Singer/Airbyte discover)
   - No `check()` method (like Singer/Airbyte check)
   - No `spec()` method (like Singer/Airbyte spec)
   - **Impact**: Can't validate connections or discover schemas programmatically

2. **No Standardized Message Protocol**
   - Airbyte uses JSONL with `{"type": "RECORD", "record": {...}}`
   - Singer uses JSONL with `{"type": "RECORD", "stream": "...", "record": {...}}`
   - Native extractors return raw Python dicts
   - **Impact**: Hard to build generic tooling (monitoring, debugging, testing)

3. **Limited Schema Evolution Support**
   - Asset schemas are static (ODCS v3.0.2)
   - No schema versioning or migration paths
   - **Impact**: Breaking schema changes require manual migration

4. **No RPC/CLI Adapter Standard**
   - Airbyte connectors run as Docker containers (subprocess)
   - Meltano/Singer not fully implemented
   - No standard CLI interface for external connectors
   - **Impact**: Can't easily integrate third-party connectors

### 💡 Recommendations

1. **Complete Lifecycle Interface**
   ```python
   class BaseReader(ABC):
       @abstractmethod
       def extract(self, state_manager) -> Iterator[List[Dict]]:
           pass
       
       def discover(self) -> Dict[str, Any]:
           """Return catalog/schema (Singer/Airbyte discover)"""
           return {}
       
       def check(self) -> bool:
           """Validate connection"""
           return True
       
       def spec(self) -> Dict[str, Any]:
           """Return connector specification"""
           return {}
   ```

2. **Standardized Message Protocol**
   ```python
   class Message:
       type: Literal["RECORD", "STATE", "SCHEMA", "LOG"]
       stream: Optional[str] = None
       record: Optional[Dict] = None
       state: Optional[Dict] = None
       schema: Optional[Dict] = None
   ```
   - Use Singer-style messages for all extractors
   - Enable generic tooling (monitors, validators, transformers)

3. **Schema Versioning**
   ```yaml
   # assets/stripe/v1.0/customers.yaml
   version: "1.0"
   schema: [...]
   
   # assets/stripe/v1.1/customers.yaml
   version: "1.1"
   migrations:
     - from: "1.0"
       steps: [...]
   ```
   - Support schema migrations
   - Track schema history

4. **CLI Adapter for External Connectors**
   ```python
   class CLIAdapter(BaseReader):
       """Runs external connector as CLI process"""
       def __init__(self, command: str, config: Dict):
           self.command = command
           self.config = config
       
       def extract(self, state_manager):
           # Run CLI, parse JSONL output
           process = subprocess.Popen([self.command, "read", "--config", "-"], ...)
           # Parse Singer/Airbyte messages
   ```
   - Enable integration with any CLI-based connector

---

## Extensibility & SDK Patterns

### ✔️ What's Working Well

1. **Plugin Loader**
   - Dynamic loading of Python classes via `importlib`
   - Rust plugin support via `ctypes` FFI
   - Path-based registration: `"path/to/module.py:ClassName"`

2. **Rust Plugin Bridge**
   - `RustReaderWrapper` and `RustWriterWrapper` provide Python-compatible interfaces
   - JSON serialization for config/records
   - Memory management (free_string, free_reader)

3. **Examples Provided**
   - `examples/plugins/json_api_reader.py` (Python)
   - `examples/plugins/rust/csv_reader/` (Rust)
   - Documentation in `docs/CUSTOM_PLUGINS.md`

### ⚠️ Gaps & Risks

1. **No Connector SDK**
   - No equivalent to Airbyte CDK or Meltano Singer SDK
   - Developers must implement full `BaseReader`/`BaseWriter`
   - **Impact**: High barrier to entry for custom plugins

2. **No Declarative Plugin Registration**
   - Plugins registered via path strings in job configs
   - No plugin manifest or metadata file
   - **Impact**: Hard to discover, version, or validate plugins

3. **Limited Plugin Versioning**
   - No version tracking for plugins
   - No dependency management
   - **Impact**: Breaking changes in plugins affect all jobs

4. **No Plugin Marketplace/Registry**
   - Plugins are file-based only
   - No centralized discovery or distribution
   - **Impact**: Hard to share plugins across teams/tenants

### 💡 Recommendations

1. **Connector SDK**
   ```python
   # dativo_ingest.sdk
   from dativo_ingest.sdk import ConnectorSDK
   
   class MyConnector(ConnectorSDK):
       def discover(self):
           # Auto-generates schema discovery
           return self._discover_from_api()
       
       def extract(self, state_manager):
           # Provides pagination, rate limiting, retries
           return self._paginated_extract()
   ```
   - Provide base classes with common patterns (pagination, retries, rate limiting)
   - Auto-generate schema discovery from API responses

2. **Plugin Manifest**
   ```yaml
   # my_plugin/plugin.yaml
   name: my_custom_reader
   version: 1.0.0
   type: python
   entry_point: my_plugin.reader:MyReader
   dependencies:
     - requests>=2.28.0
   capabilities:
     - incremental
     - schema_discovery
   ```
   - Declarative plugin metadata
   - Enable validation and dependency resolution

3. **Plugin Registry Service**
   ```python
   class PluginRegistry:
       def register(self, plugin_path: Path):
           """Register plugin from manifest"""
       
       def discover(self, capability: str) -> List[Plugin]:
           """Find plugins by capability"""
       
       def install(self, plugin_name: str, version: str):
           """Install plugin with dependencies"""
   ```
   - Centralized plugin management
   - Support plugin distribution (GitHub, S3, private registry)

4. **Plugin Versioning**
   ```python
   class VersionedPlugin:
       version: str
       min_platform_version: str
       dependencies: Dict[str, str]
   ```
   - Track plugin versions
   - Enforce compatibility

---

## Security & Isolation

### ✔️ What's Working Well

1. **Secret Management Abstraction**
   - `SecretManager` base class with multiple backends
   - Support for env, filesystem, Vault, AWS Secrets Manager, GCP Secret Manager
   - Tenant-scoped secrets

2. **Secret Redaction in Logs**
   - `setup_logging(redact_secrets=True)` option
   - Prevents credential leakage in logs

3. **Environment Variable Validation**
   - `validate_environment_variables()` checks required vars
   - Fails fast if secrets missing

### ⚠️ Gaps & Risks

1. **No Plugin Sandboxing**
   - Python plugins run in same process as orchestrator
   - Rust plugins loaded via `ctypes` (no isolation)
   - **Impact**: Malicious or buggy plugins can crash entire system

2. **Limited Secret Injection**
   - Secrets passed via config dicts (in-memory)
   - No secret rotation support
   - **Impact**: Secrets may be logged or leaked in error messages

3. **No Audit Logging**
   - No tracking of which plugins accessed which secrets
   - No pipeline run audit trail
   - **Impact**: Can't detect unauthorized access or compliance violations

4. **Docker Isolation Only for Airbyte**
   - Airbyte connectors run in Docker (good isolation)
   - Native and custom plugins run in host process
   - **Impact**: Inconsistent security posture

### 💡 Recommendations

1. **Plugin Sandboxing**
   ```python
   # Option 1: Process isolation
   class IsolatedPluginRunner:
       def run_plugin(self, plugin_path, config):
           # Run plugin in subprocess with restricted permissions
           subprocess.run([sys.executable, plugin_path], ...)
   
   # Option 2: Container isolation
   class ContainerizedPlugin:
       def run(self, plugin_path, config):
           # Run plugin in lightweight container (gVisor, Firecracker)
           docker.run(image="dativo-plugin-runtime", ...)
   ```
   - Isolate plugins from orchestrator
   - Use containers or restricted subprocesses

2. **Secret Rotation**
   ```python
   class RotatingSecretManager(SecretManager):
       def get_secret(self, name: str, version: Optional[str] = None):
           # Support versioned secrets
           # Auto-rotate on expiration
   ```
   - Support secret versioning
   - Auto-rotate expired secrets

3. **Audit Logging**
   ```python
   class AuditLogger:
       def log_secret_access(self, plugin_name, secret_name, tenant_id):
           # Log all secret accesses
       
       def log_pipeline_run(self, job_config, status, records_processed):
           # Log pipeline execution
   ```
   - Track all secret accesses
   - Log pipeline runs for compliance

4. **Consistent Isolation**
   - Run all plugins (native, custom, engine-based) in containers
   - Use lightweight runtimes (gVisor, Firecracker) for performance
   - Provide option for trusted plugins to run in-process

---

## Performance & Scaling

### ✔️ What's Working Well

1. **Batch-Oriented Processing**
   - Extractors yield batches (`Iterator[List[Dict]]`)
   - Writers accept batches
   - Reduces memory pressure

2. **Rust Plugin Support**
   - 10-100x performance improvements demonstrated
   - Lower memory usage
   - Better compression

3. **Incremental Sync Support**
   - `IncrementalStateManager` tracks state
   - Multiple strategies (created, updated_after, file_modified_time)
   - State persisted to files (configurable path)

4. **Metrics Collection**
   - `MetricsCollector` tracks records, files, API calls, errors
   - Execution time and throughput metrics
   - Structured logging for observability

### ⚠️ Gaps & Risks

1. **No CDC Support**
   - Incremental sync only (polling-based)
   - No Change Data Capture (CDC) for databases
   - **Impact**: Can't capture real-time changes

2. **Limited Parallelism Control**
   - No explicit parallelism configuration
   - Batch sizes hardcoded or engine-specific
   - **Impact**: Can't optimize for different workloads

3. **Memory Management Not Tunable**
   - Batch sizes fixed or engine-specific
   - No memory limits per job/plugin
   - **Impact**: Large datasets may cause OOM

4. **No Distributed Execution**
   - Jobs run on single machine
   - No support for distributed processing (Spark, Dask)
   - **Impact**: Can't scale horizontally

### 💡 Recommendations

1. **CDC Support**
   ```python
   class CDCExtractor(BaseReader):
       def extract(self, state_manager):
           # Use Debezium, Kafka Connect, or native CDC
           # Stream change events
   ```
   - Integrate Debezium for database CDC
   - Support Kafka as change log source

2. **Parallelism Configuration**
   ```yaml
   source:
     parallelism:
       workers: 4
       batch_size: 10000
       max_memory_mb: 2048
   ```
   - Allow per-job parallelism tuning
   - Support worker pools for I/O-bound operations

3. **Memory Management**
   ```python
   class MemoryAwareExtractor(BaseReader):
       def extract(self, state_manager):
           # Monitor memory usage
           # Adjust batch size dynamically
           # Spill to disk if needed
   ```
   - Add memory limits per job
   - Support disk spilling for large datasets

4. **Distributed Execution**
   ```python
   class DistributedExecutor:
       def run(self, job_config):
           # Submit to Spark/Dask cluster
           # Partition data across workers
   ```
   - Support Spark/Dask for large-scale processing
   - Enable horizontal scaling

---

## Migration & Compatibility

### ✔️ What's Working Well

1. **Backward Compatibility**
   - Supports legacy `SourceConnectorRecipe` and `TargetConnectorRecipe`
   - Unified `ConnectorRecipe` with role-based support
   - Migration helpers in `AssetDefinition._migrate_old_format()`

2. **Versioned Asset Schemas**
   - Assets stored in versioned paths: `assets/stripe/v1.0/customers.yaml`
   - ODCS v3.0.2 compliance

### ⚠️ Gaps & Risks

1. **No Plugin Interface Versioning**
   - `BaseReader`/`BaseWriter` interfaces not versioned
   - Breaking changes would affect all plugins
   - **Impact**: Can't evolve interfaces safely

2. **No Migration Path for Plugins**
   - No tooling to migrate plugins between versions
   - No compatibility checks
   - **Impact**: Manual migration required

3. **Limited Documentation on Breaking Changes**
   - No CHANGELOG for plugin interfaces
   - No deprecation warnings
   - **Impact**: Surprise breaking changes

### 💡 Recommendations

1. **Interface Versioning**
   ```python
   class BaseReader(ABC):
       interface_version: str = "1.0"
       
       @abstractmethod
       def extract(self, state_manager) -> Iterator[List[Dict]]:
           pass
   ```
   - Version plugin interfaces
   - Support multiple interface versions simultaneously

2. **Migration Tooling**
   ```python
   class PluginMigrator:
       def migrate(self, plugin_path: str, from_version: str, to_version: str):
           # Auto-migrate plugin code
           # Update imports, method signatures
   ```
   - Provide migration scripts
   - Auto-update plugin code

3. **Deprecation Warnings**
   ```python
   import warnings
   
   class BaseReader:
       def extract(self, state_manager):
           warnings.warn(
               "extract() will change in v2.0. Use extract_v2()",
               DeprecationWarning
           )
   ```
   - Warn before breaking changes
   - Provide migration guides

---

## Learnings from Airbyte, Meltano, Singer

### ✔️ What's Working Well

1. **Airbyte Patterns**
   - Docker-based isolation for Airbyte connectors ✅
   - JSONL message protocol (partially) ✅
   - Connector registry with capabilities ✅

2. **Meltano Patterns**
   - Plugin manifests (partially via connector recipes) ✅
   - CLI-first approach ✅

3. **Singer Patterns**
   - JSON message protocol (partially) ✅
   - Decoupled tap/target architecture (readers/writers) ✅

### ⚠️ Gaps & Risks

1. **Missing Airbyte Patterns**
   - No `discover()` method (Airbyte discover command)
   - No `check()` method (Airbyte check command)
   - No `spec()` method (Airbyte spec command)
   - **Impact**: Can't validate connectors or discover schemas

2. **Missing Meltano Patterns**
   - No plugin installation system (`meltano install`)
   - No plugin discovery (`meltano discover`)
   - No environment management
   - **Impact**: Hard to manage plugin lifecycle

3. **Missing Singer Patterns**
   - No standardized message types (RECORD, STATE, SCHEMA, LOG)
   - No catalog format
   - **Impact**: Can't use Singer tooling ecosystem

### 💡 Recommendations

1. **Adopt Full Airbyte Protocol**
   ```python
   class AirbyteCompatibleExtractor(BaseReader):
       def spec(self) -> Dict:
           """Return connector specification"""
       
       def check(self, config: Dict) -> Dict:
           """Validate connection"""
       
       def discover(self, config: Dict) -> Dict:
           """Discover schema/catalog"""
   ```
   - Implement full Airbyte protocol
   - Enable Airbyte tooling compatibility

2. **Adopt Meltano Plugin Management**
   ```python
   class PluginManager:
       def install(self, plugin_name: str):
           """Install plugin (like meltano install)"""
       
       def discover(self) -> List[Plugin]:
           """Discover available plugins"""
   ```
   - Add plugin installation system
   - Support plugin discovery

3. **Adopt Singer Message Protocol**
   ```python
   class SingerMessage:
       type: Literal["RECORD", "STATE", "SCHEMA", "LOG"]
       stream: Optional[str]
       record: Optional[Dict]
       state: Optional[Dict]
       schema: Optional[Dict]
   ```
   - Use Singer message format for all extractors
   - Enable Singer tooling ecosystem

---

## Recommendations Summary

### High Priority

1. **Unified Extractor Interface**
   - Make all extractors implement common interface
   - Add lifecycle methods (discover, check, spec)
   - Remove hardcoded routing from CLI

2. **Plugin Sandboxing**
   - Isolate plugins from orchestrator (containers or subprocesses)
   - Consistent security posture across all plugins

3. **Complete Lifecycle Methods**
   - Implement discover, check, spec for all extractors
   - Enable connection validation and schema discovery

4. **Standardized Message Protocol**
   - Adopt Singer-style messages for all extractors
   - Enable generic tooling ecosystem

### Medium Priority

5. **Connector SDK**
   - Provide base classes with common patterns
   - Reduce barrier to entry for custom plugins

6. **Plugin Registry System**
   - Declarative plugin manifests
   - Plugin versioning and discovery

7. **CDC Support**
   - Add Change Data Capture for databases
   - Support real-time change streaming

8. **Parallelism & Memory Management**
   - Tunable parallelism per job
   - Memory limits and disk spilling

### Low Priority

9. **Distributed Execution**
   - Support Spark/Dask for large-scale processing
   - Horizontal scaling

10. **Interface Versioning**
    - Version plugin interfaces
    - Migration tooling

---

## Conclusion

Dativo demonstrates a solid architectural foundation with clear separation of concerns, config-driven design, and support for hybrid plugin models. The system successfully combines YAML-configured connectors with custom Python/Rust plugins, providing flexibility for both standard and custom use cases.

**Key Strengths:**
- Clear separation: connectors (YAML) vs plugins (code)
- Registry-based validation and capabilities tracking
- Support for multiple engines (Airbyte, Meltano, Singer)
- Rust plugin support for performance-critical paths
- Comprehensive secret management

**Key Gaps:**
- Inconsistent extractor interfaces (native vs engine-based)
- No plugin sandboxing (security risk)
- Missing lifecycle methods (discover, check, spec)
- No standardized message protocol
- Limited extensibility patterns (hardcoded routing)

**Overall Assessment:**
The platform is production-ready for current use cases but would benefit from the recommended improvements to align with industry standards (Airbyte, Meltano, Singer) and improve security, extensibility, and maintainability.
