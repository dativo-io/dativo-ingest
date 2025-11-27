# Dativo Ingestion Platform - Architecture Review

## Executive Summary

Dativo is a config-driven data integration platform supporting hybrid connectors (YAML-configured standard connectors via Airbyte/Singer/Meltano) and custom code plugins (Python/Rust). The system demonstrates solid architectural foundations with clear separation of concerns, but has gaps in plugin lifecycle standardization, connector versioning, and security isolation.

---

## Architecture & Modularity

### ✔️ What's Working Well

1. **Clear Separation of Concerns**
   - Connector recipes (tenant-agnostic) separated from job configs (tenant-specific)
   - Asset schemas (ODCS v3.0.2) decoupled from connector implementations
   - Orchestration (Dagster) isolated from extraction logic

2. **Plugin/Microkernel Pattern**
   - Core engine (`cli.py`, `config.py`) is agnostic to connector implementations
   - Connectors loaded dynamically via `PluginLoader` or engine framework
   - Standard connectors (Airbyte/Meltano/Singer) use adapter pattern via `engine_framework.py`

3. **Composable Connector Architecture**
   - Connector recipes define capabilities (roles, engines, incremental strategies)
   - Registry (`registry/connectors.yaml`) validates connector types and capabilities
   - Connectors can be source-only, target-only, or bidirectional

4. **Unified Connector Recipe Model**
   - `ConnectorRecipe` supports both source and target roles (replaces legacy `SourceConnectorRecipe`/`TargetConnectorRecipe`)
   - Backward compatibility maintained for legacy formats

### ⚠️ Gaps or Risks

1. **Orchestration Engine Coupling**
   - Dagster integration in `orchestrated.py` calls CLI via subprocess (lines 75-88)
   - Creates tight coupling: orchestration depends on CLI interface rather than programmatic API
   - **Risk**: Hard to test, limits flexibility for alternative orchestrators

2. **Missing Abstract Connector Interface**
   - No formal `IConnector` interface that all connectors must implement
   - Connectors have inconsistent method signatures (some have `extract_metadata()`, others don't)
   - **Impact**: Hard to ensure all connectors support required lifecycle methods

3. **Engine Framework Incomplete**
   - `MeltanoExtractor` and `SingerExtractor` are stubs (raise `NotImplementedError`)
   - Only `AirbyteExtractor` is fully implemented
   - **Risk**: Users may configure Meltano/Singer connectors that fail at runtime

4. **Connector Discovery**
   - No programmatic connector discovery API
   - Connectors must be manually registered in `registry/connectors.yaml`
   - **Impact**: Hard to build connector marketplace or dynamic connector loading

---

## Connector vs Plugin Decision Framework

### ✔️ What's Working Well

1. **Clear Configuration Path**
   - Standard connectors: use `source_connector_path` pointing to YAML recipe
   - Custom plugins: use `custom_reader`/`custom_writer` pointing to Python/Rust code
   - Decision is explicit in job configuration

2. **Hybrid Support**
   - Can use standard connector recipes with custom readers/writers
   - Example: Airbyte connector can be extended with custom metadata extraction

3. **Plugin Type Detection**
   - `PluginLoader._detect_plugin_type()` automatically detects Python vs Rust from file extension
   - Supports `.py` (Python), `.so`/`.dylib`/`.dll` (Rust)

### ⚠️ Gaps or Risks

1. **No Decision Framework Documentation**
   - No clear guidance on when to use config-driven vs code-driven
   - Missing decision tree or best practices
   - **Recommendation**: Add decision framework to docs:
     - Use standard connectors for: well-supported sources (Stripe, HubSpot), standard protocols (Singer/Airbyte)
     - Use custom plugins for: proprietary APIs, performance-critical paths, special formats

2. **Hybrid Plugin Override Mechanism Unclear**
   - Can plugins extend standard connectors? (e.g., override `extract()` but use connector's `discover()`)
   - No documented pattern for partial overrides
   - **Risk**: Users may duplicate connector logic instead of extending

3. **No Plugin Registry**
   - Custom plugins are file paths, not registered entities
   - Can't version, discover, or validate plugins independently
   - **Impact**: Hard to share plugins across teams or enforce plugin standards

---

## Interface Design

### ✔️ What's Working Well

1. **Standardized Plugin Interfaces**
   - `BaseReader` and `BaseWriter` provide clear contracts
   - Both support initialization with config objects
   - `BaseReader.extract()` yields batches (memory-efficient streaming)

2. **Incremental State Management**
   - `IncrementalStateManager` provides consistent state handling
   - State stored as JSON files (can be extended to S3/database)
   - State path auto-generated from tenant/connector/object

3. **Data Format Standardization**
   - Records as `List[Dict[str, Any]]` (Python dicts)
   - Schema validation via ODCS v3.0.2 asset definitions
   - Parquet output with standardized partitioning (Hive-style)

4. **Rust Plugin Bridge**
   - `RustReaderWrapper` and `RustWriterWrapper` provide Python-compatible interfaces
   - JSON serialization for config/records (language-agnostic)
   - Proper memory management (Rust allocator for strings)

### ⚠️ Gaps or Risks

1. **Incomplete Lifecycle Methods**
   - Missing standard methods: `discover()` (schema discovery), `check()` (connection validation), `spec()` (capabilities)
   - Only `extract()` and `write_batch()` are standardized
   - **Impact**: Can't validate connections before extraction, can't discover schemas dynamically

2. **No Standardized Error Handling**
   - Connectors raise exceptions inconsistently
   - No error code taxonomy (retryable vs fatal)
   - **Risk**: Orchestration can't make intelligent retry decisions

3. **State Management Not Standardized**
   - Some connectors use `IncrementalStateManager`, others manage state internally
   - Airbyte connectors handle state in `_update_state()` but not all connectors follow pattern
   - **Recommendation**: Make state management part of `BaseReader` interface

4. **Missing RPC/CLI Adapter Standard**
   - Airbyte uses Docker subprocess (not true RPC)
   - No standard protocol for external connectors (like Singer's JSONL over stdout)
   - **Impact**: Hard to integrate arbitrary external connectors

---

## Extensibility & SDK Patterns

### ✔️ What's Working Well

1. **Plugin SDK (Base Classes)**
   - `BaseReader` and `BaseWriter` serve as SDK foundation
   - Clear examples in `examples/plugins/` (JSON API reader, CSV reader)
   - Documentation in README with code examples

2. **Dynamic Plugin Loading**
   - `PluginLoader` supports both Python and Rust plugins
   - Path-based loading: `"path/to/module.py:ClassName"` or `"path/to/lib.so:function_name"`
   - Runtime validation (checks inheritance from base classes)

3. **Rust Plugin Support**
   - High-performance option (10-100x faster for large datasets)
   - C-compatible FFI interface via ctypes
   - Examples in `examples/plugins/rust/` (CSV reader, Parquet writer)

4. **Connector Registry**
   - Declarative connector capabilities in `registry/connectors.yaml`
   - Versioned registry (version: 3)
   - Validates: roles, engines, incremental support, mode restrictions

### ⚠️ Gaps or Risks

1. **No Formal SDK Package**
   - No `dativo-sdk` package for plugin developers
   - Base classes are in main package (`dativo_ingest.plugins`)
   - **Impact**: Plugin developers must install full platform to build plugins

2. **Plugin Versioning Missing**
   - Plugins are file paths, not versioned entities
   - Can't specify plugin version in job config
   - **Risk**: Plugin updates may break existing jobs

3. **No Plugin Discovery**
   - Can't list available plugins programmatically
   - No plugin marketplace or catalog
   - **Impact**: Hard to share plugins across organizations

4. **Limited Plugin Validation**
   - Only checks inheritance, not interface compliance
   - No validation of required methods or signatures
   - **Recommendation**: Add plugin validation tool (e.g., `dativo validate-plugin`)

5. **No Plugin Testing Framework**
   - No test utilities for plugin developers
   - No mock `SourceConfig`/`TargetConfig` for unit testing
   - **Impact**: Plugin development requires full platform setup

---

## Security & Isolation

### ✔️ What's Working Well

1. **Multi-Backend Secret Management**
   - Pluggable secret managers: `env`, `filesystem`, `vault`, `aws`, `gcp`
   - Tenant-scoped secrets (secrets loaded per tenant)
   - Secret path templates with `{tenant}` placeholder

2. **Secret Redaction in Logging**
   - `setup_logging(redact_secrets=True)` prevents secret leakage
   - Configurable per job via `logging.redaction`

3. **Tenant Isolation**
   - Jobs scoped by `tenant_id`
   - State files isolated per tenant
   - Branch defaults to `tenant_id` for Iceberg catalog

### ⚠️ Gaps or Risks

1. **No Plugin Sandboxing**
   - Python plugins run in same process as orchestrator
   - Rust plugins loaded via ctypes (no isolation)
   - **Risk**: Malicious or buggy plugins can crash orchestrator or access secrets

2. **Docker Isolation Only for Airbyte**
   - Airbyte connectors run in Docker containers (good isolation)
   - Native connectors (CSV, Postgres, MySQL) run in orchestrator process
   - **Risk**: Database connectors can access orchestrator's network/filesystem

3. **No Secrets Audit Trail**
   - No logging of which secrets were accessed by which connector
   - No audit log for secret manager operations
   - **Impact**: Hard to track secret usage for compliance

4. **Secret Injection Not Validated**
   - Secrets injected via environment variables or config
   - No validation that secrets match expected format (e.g., JWT token format)
   - **Risk**: Misconfigured secrets may cause runtime failures

5. **No Plugin Permission Model**
   - Plugins can access all secrets loaded for tenant
   - No fine-grained permissions (e.g., "read-only" secrets)
   - **Recommendation**: Add plugin capability model (e.g., `required_secrets: ["read_only"]`)

---

## Performance & Scaling

### ✔️ What's Working Well

1. **Streaming/Batch Processing**
   - `extract()` yields batches (memory-efficient)
   - Parquet writer supports target file size (128-200 MB default)
   - Partitioning support (Hive-style: `column=value/`)

2. **Incremental Sync Support**
   - Multiple strategies: `updated_at`, `created`, `file_modified_time`, `spreadsheet_modified_time`
   - State persistence via `IncrementalStateManager`
   - Lookback window support (`lookback_days`)

3. **Rust Plugin Performance**
   - 10-100x performance gains for large datasets
   - Zero-copy operations where possible
   - Constant memory usage with streaming

4. **Configurable Batching**
   - Engine options support `batch_size` tuning
   - Rust plugins support larger batches (50k+ records)

### ⚠️ Gaps or Risks

1. **No CDC Support**
   - No Change Data Capture (CDC) for databases
   - Incremental sync uses cursor fields, not log-based replication
   - **Impact**: Can't capture deletes or updates in real-time

2. **Limited Parallelism**
   - Jobs run sequentially in orchestrated mode
   - No parallel extraction from multiple objects
   - **Recommendation**: Add `max_workers` config for parallel object extraction

3. **Memory Management Not Tunable**
   - Batch sizes hardcoded or in engine options
   - No memory limits per job
   - **Risk**: Large datasets may cause OOM

4. **No Observability Metrics**
   - Logging exists but no metrics (Prometheus/StatsD)
   - No performance metrics (records/sec, bytes/sec)
   - **Impact**: Hard to monitor pipeline health or performance

5. **Retry Policy Basic**
   - Retry config exists but no exponential backoff implementation
   - No circuit breaker pattern
   - **Risk**: Transient failures may cause excessive retries

---

## Migration & Compatibility

### ✔️ What's Working Well

1. **Backward Compatibility**
   - Legacy `SourceConnectorRecipe`/`TargetConnectorRecipe` still supported
   - Old asset format (nested `asset` key) auto-migrated to ODCS flat format
   - Environment variable expansion in paths

2. **Schema Evolution Support**
   - Iceberg supports schema evolution (`supports_schema_evolution: true`)
   - Validation mode: `strict` vs `warn` (allows schema drift)

3. **Versioned Asset Schemas**
   - Assets versioned in path: `assets/stripe/v1.0/customers.yaml`
   - ODCS v3.0.2 compliance

### ⚠️ Gaps or Risks

1. **No Plugin Interface Versioning**
   - `BaseReader`/`BaseWriter` interfaces not versioned
   - Breaking changes would break all plugins
   - **Recommendation**: Add interface version (e.g., `BaseReaderV1`, `BaseReaderV2`)

2. **No Migration Path for Plugins**
   - Can't migrate from custom plugin to standard connector
   - No tooling to convert plugin code to connector recipe
   - **Impact**: Users locked into custom plugins

3. **Connector Versioning Missing**
   - Connector recipes not versioned (only registry is versioned)
   - Can't specify connector version in job config
   - **Risk**: Connector updates may break existing jobs

4. **No Breaking Change Documentation**
   - No CHANGELOG for connector/plugin interface changes
   - No deprecation warnings
   - **Impact**: Users may be surprised by breaking changes

---

## Learnings from Airbyte, Meltano, Singer

### ✔️ Implemented Patterns

1. **Airbyte Patterns**
   - ✅ Docker-based connector isolation (Airbyte extractor)
   - ✅ Standard connector interface (spec, check, discover, read)
   - ⚠️ Partial: Only `read` command implemented, others missing

2. **Meltano Patterns**
   - ⚠️ Stub implementation (not yet implemented)
   - ❌ No plugin manifest system
   - ❌ No CLI-first modularity

3. **Singer Patterns**
   - ⚠️ Stub implementation (not yet implemented)
   - ❌ No JSON message protocol (RECORD, STATE, SCHEMA)
   - ❌ No decoupled tap/target architecture

### ⚠️ Missing Patterns

1. **Airbyte: Full Lifecycle**
   - Missing: `spec` (connector capabilities), `check` (connection validation), `discover` (schema discovery)
   - Only `read` command implemented
   - **Recommendation**: Implement full Airbyte protocol

2. **Meltano: Plugin Manifest**
   - No `meltano.yml` equivalent for plugin discovery
   - No plugin installation system (`meltano add`)
   - **Recommendation**: Add plugin manifest YAML

3. **Singer: Message Protocol**
   - No standardized JSONL message format
   - No SCHEMA/RECORD/STATE message types
   - **Recommendation**: Add Singer-compatible message parser

4. **Common: Centralized Versioning**
   - No connector marketplace or version registry
   - Connectors are file paths, not versioned packages
   - **Recommendation**: Add connector registry API (similar to Airbyte's connector registry)

---

## Recommendations Summary

### High Priority

1. **Complete Engine Framework**
   - Implement `MeltanoExtractor` and `SingerExtractor`
   - Add full Airbyte lifecycle (spec, check, discover)

2. **Plugin Interface Standardization**
   - Add missing lifecycle methods: `discover()`, `check()`, `spec()`
   - Standardize error handling (error codes, retryable vs fatal)
   - Make state management part of `BaseReader` interface

3. **Security Isolation**
   - Add Docker-based sandboxing for native connectors (not just Airbyte)
   - Implement plugin permission model
   - Add secrets audit logging

4. **Observability**
   - Add metrics (Prometheus/StatsD)
   - Add performance metrics (records/sec, bytes/sec)
   - Add distributed tracing support

### Medium Priority

5. **Plugin SDK & Tooling**
   - Create `dativo-sdk` package for plugin developers
   - Add plugin validation tool (`dativo validate-plugin`)
   - Add plugin testing framework

6. **Versioning & Migration**
   - Version plugin interfaces (`BaseReaderV1`, `BaseReaderV2`)
   - Add connector versioning to recipes
   - Create migration tooling (plugin → connector)

7. **Documentation**
   - Add decision framework (config-driven vs code-driven)
   - Document plugin extension patterns
   - Add breaking change policy

### Low Priority

8. **Advanced Features**
   - Add CDC support for databases
   - Add parallel extraction (multiple objects)
   - Add circuit breaker pattern for retries

9. **Ecosystem Integration**
   - Implement Singer message protocol
   - Add Meltano plugin manifest
   - Create connector marketplace/registry API

---

## Conclusion

Dativo demonstrates a solid architectural foundation with clear separation of concerns, flexible plugin system, and good support for both config-driven and code-driven connectors. The main gaps are in plugin lifecycle standardization, security isolation, and observability. The system is well-positioned to adopt patterns from Airbyte, Meltano, and Singer, but needs to complete the engine framework implementations and add missing lifecycle methods.

**Overall Assessment**: **B+** - Strong foundation, needs completion of core features and security hardening.
