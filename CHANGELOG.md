# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Plugin Sandboxing**: Docker-based sandboxing for custom Python plugins
  - Resource limits (CPU, memory)
  - Network isolation
  - Seccomp profiles for security
  - Automatic sandboxing in cloud mode
  - Comprehensive documentation in `docs/PLUGIN_SANDBOXING.md`
- **Connection Testing**: `check_connection()` method in BaseReader/BaseWriter
  - CLI command: `dativo check --config job.yaml [--json] [--verbose]`
  - Validates credentials before job execution
  - Supports both custom plugins and built-in connectors
  - Typed return objects: `ConnectionTestResult` with success, message, error_code, and details
  - JSON and verbose output options for better integration
- **Standardized Error Handling**: Comprehensive error hierarchy
  - Full error hierarchy in `exceptions.py`: `ConnectionError`, `AuthenticationError`, `ValidationError`
  - `TransientError`, `RateLimitError`, `PluginError`, `SandboxError`
  - Error codes and retryable flags for orchestrator integration
  - Utility functions: `is_retryable_error()`, `get_error_code()`, `wrap_exception()`
  - Proper error exports in `__init__.py` for clean imports
- **Plugin Versioning**: Version compatibility checks
  - `__version__` attribute in BaseReader/BaseWriter
  - SDK version tracking (PLUGIN_SDK_VERSION)
  - Version validation on plugin load
- **Discovery Interface**: `discover()` method for available tables/streams
  - CLI command: `dativo discover --config job.yaml [--json] [--verbose]`
  - Typed return objects: `DiscoveryResult` with objects list and metadata
  - Returns list of available data sources with schema information
  - JSON and verbose output options for better integration
- **Enhanced Documentation**:
  - `docs/PLUGIN_SANDBOXING.md` - Security guide for plugin sandboxing
  - `docs/CONNECTOR_VS_PLUGIN_DECISION_TREE.md` - Decision tree for choosing connectors vs plugins
  - Example plugins: `examples/plugins/json_api_reader.py` and `examples/plugins/json_file_writer.py`
- **Module Exports**: 
  - Exported plugin classes (`BaseReader`, `BaseWriter`, `ConnectionTestResult`, `DiscoveryResult`) from main module
  - Exported error classes and utility functions for clean imports
  - Added `__all__` for explicit API surface
- **Custom Plugin System**: Support for Python and Rust plugins
  - **Python Plugins:**
    - New `BaseReader` and `BaseWriter` base classes for plugin development
    - `PluginLoader` utility for dynamic plugin loading from file paths
    - Example plugins: JSON API reader and JSON file writer
  - **Rust Plugins:**
    - Support for high-performance Rust plugins via FFI
    - Automatic detection based on file extension (.py vs .so/.dylib/.dll)
    - `RustReaderWrapper` and `RustWriterWrapper` bridge classes
    - Example plugins: CSV reader (15x faster) and Parquet writer (3.5x faster)
    - Comprehensive build system with Cargo workspace
    - Performance benchmarks and optimization guide
  - `custom_reader` and `custom_writer` configuration options in job configs
  - Plugins receive connection details and can implement format-aware, high-performance processing
  - Comprehensive documentation in `docs/CUSTOM_PLUGINS.md`
  - Integration with existing ETL pipeline (custom plugins work alongside built-in extractors)
  - Cloud plugin storage via `s3://` and `gs://` URIs with local caching (`DATIVO_PLUGIN_CACHE_DIR`)
  
### Changed
- Updated `SourceConfig` to include optional `custom_reader` field
- Updated `TargetConfig` to include optional `custom_writer` field
- Enhanced CLI to dynamically load and instantiate Python and Rust plugins
- Updated `PluginLoader` to detect plugin type from file extension
- Enhanced README with Python and Rust plugin examples
- Added performance comparison data for Rust plugins

### Testing
- **Comprehensive Test Suite**: 76 total tests covering all plugin functionality
  - 47 unit tests in `test_plugins.py`
  - 19 integration tests in `test_plugin_integration.sh`
  - 10 Rust plugin tests in `test_rust_plugins.sh`
  - Master test runner: `run_all_plugin_tests.sh`
- **100% Feature Coverage**: All plugin types (default, Python, Rust) fully tested
- **Test Documentation**: Complete testing guide in `tests/README.md`
- **GitHub Actions CI/CD**: Automated workflows for all tests
  - `ci.yml` - Complete CI pipeline (lint, core tests, plugin tests, Rust)
  - `plugin-tests.yml` - Dedicated plugin system tests (Python + Rust)
  - Matrix testing across Python 3.10, 3.11 and Ubuntu, macOS
  - Automatic test coverage reporting with Codecov

### Planned
- OSS connector wrappers (Stripe, HubSpot, Google Drive, Google Sheets, MySQL)
- Per-connector error handling and rate limiting

## [1.3.0] - 2025-11-07

### Added - Enhanced Orchestration & Connectors

#### Enhanced Orchestration
- **Dagster Schedule Integration** with retry policies
  - Cron and interval-based scheduling support
  - Schedule enable/disable configuration
  - Timezone-aware scheduling
  - Max concurrent runs control
  - Custom schedule tags
- **Retry Policies** with exponential backoff
  - Configurable initial delay, max delay, and backoff multiplier
  - Retryable exit codes and error pattern matching
  - Custom retry logic with Dagster integration
  - Retry state tracking and recovery
- **Enhanced Observability**
  - Metrics collection framework
  - Distributed tracing with OpenTelemetry
  - Job execution metadata (tenant_id, connector_type, job_name)
  - Enhanced asset tags for Dagster UI

#### Unified Connector Architecture
- **Bidirectional Connectors** support
  - Unified `ConnectorRecipe` model replacing separate source/target recipes
  - Connector roles metadata (`[source]`, `[target]`, `[source, target]`)
  - Registry schema updated to support roles
  - All connectors migrated to unified structure
- **Connector Registry v3** with roles-based capabilities

#### Postgres Extractor
- **Native Postgres Connector** implementation
  - Full table and incremental sync support
  - Cursor-based incremental sync with `cursor_field`
  - Connection parameter handling with environment variable expansion
  - Bash-style default value syntax (`${VAR:-default}`)
  - Batch processing with configurable batch sizes
  - Date/datetime to ISO format conversion
  - State management integration

#### Markdown-KV Transformations
- **Postgres to Markdown-KV** transformation pipeline
  - String mode: Entire Markdown-KV document as single column
  - Structured mode: Parsed Markdown-KV into key-value rows
  - Support for `row_per_kv` and `document_level` patterns
  - Automatic doc_id extraction from common ID fields
  - Integration with Parquet writer for Iceberg tables

#### Testing & CI/CD
- **Comprehensive GitHub Actions Workflows**
  - Unit tests workflow with pytest
  - Smoke tests workflow with Postgres, MinIO, and Nessie services
  - Schema validation workflow with ajv-cli and yq
  - Test data loading for AdventureWorks Postgres dataset
  - Artifact uploads for debugging
- **Expanded Smoke Tests**
  - Postgres to Iceberg Parquet (Markdown-KV) test suite
  - Multiple table coverage (person, product, customer, sales_order_header, employee, address, product_category)
  - Both string and structured Markdown-KV modes
  - MinIO bucket verification

#### Documentation & Examples
- Job examples moved to `docs/examples/jobs/`
- AdventureWorks Postgres setup scripts
- Minimal data loading for faster test execution

### Changed
- **Unified Connector Structure**: Migrated from `connectors/sources/` and `connectors/targets/` to unified `connectors/` directory
- **Deprecated Models**: `SourceConnectorRecipe` and `TargetConnectorRecipe` marked as deprecated (use `ConnectorRecipe` instead)
- **Retry Configuration**: Enhanced `RetryConfig` with exponential backoff parameters (deprecated `retry_delay_seconds`)
- **Schedule Configuration**: New `ScheduleConfig` model with cron/interval support, timezone, and concurrency control
- **Dagster Compatibility**: Added fallback for older Dagster versions (IntervalSchedule → cron conversion)

### Fixed
- Missing dependencies in `pyproject.toml` (`jsonschema`, `requests`)
- Postgres extractor environment variable expansion for connection parameters
- Dagster `IntervalSchedule` import compatibility issues
- GitHub Actions workflow dependencies (ajv-cli, yq installation)
- Postgres incremental sync cursor field validation

### Technical Details
- **Dagster Version Compatibility**: Supports Dagster 1.5.0+ with fallback for interval scheduling
- **Postgres Support**: Uses `psycopg2-binary` for database connectivity
- **State Management**: Incremental state updates after successful extraction
- **Error Handling**: Enhanced error classification for retry logic

## [1.1.0] - 2024-11-07

### Added - M1.2: ETL Pipeline & Data Processing

#### Schema Validation
- **Schema Validator** with configurable strict/warn modes
- Required field enforcement with `required: true`
- Type validation and coercion (string, integer, float, boolean, date)
- Comprehensive error reporting with field-level details
- PyArrow schema generation from asset definitions

#### Data Extraction
- **CSV Extractor** with native Python implementation
- Chunking support for large files
- Incremental sync with file modified time tracking
- Lookback days support for backfilling
- File-based incremental state management

#### Parquet Writing
- **Parquet Writer** with target file size management (128-200 MB default)
- Industry-standard path structure: `s3://bucket/domain/data_product/table/partition/file.parquet`
- Hive-style partitioning with normalized column names and values
- PyArrow integration with snappy compression
- Local temporary file handling with S3 upload

#### Iceberg/Nessie Integration
- **Iceberg Committer** with optional catalog support
- S3/MinIO file upload with comprehensive metadata tagging
- PyIceberg integration for table creation and management
- Branch management (defaults to tenant_id)
- File appending to Iceberg tables

#### ETL Pipeline
- Complete Extract-Transform-Load pipeline orchestration
- Exit codes: 0 (success), 1 (partial success), 2 (failure)
- Graceful degradation when catalog operations fail
- State updates after successful extraction

#### Configuration Enhancements
- `schema_validation_mode`: strict or warn mode
- `parquet_target_size_mb`: configurable Parquet file sizing
- `retry_config`: retry configuration framework
- Optional catalog configuration for S3-only writes

#### Infrastructure & Testing
- Local development setup with Docker Compose (MinIO + Nessie)
- Automated setup script (`scripts/setup-dev.sh`)
- Unit tests for all ETL components
- Smoke tests with GitHub Actions workflow
- End-to-end CSV → Parquet → S3 flow validation

#### Documentation
- `INGESTION_EXECUTION.md`: Detailed execution flow documentation
- `CATALOG_LIMITATIONS.md`: PyIceberg/Nessie compatibility notes
- `SETUP_AND_TESTING.md`: Comprehensive setup guide
- `QUICKSTART.md`: Quick reference guide
- Updated README with execution flow details

### Changed
- Made Nessie catalog optional (can write Parquet directly to S3)
- Infrastructure validation now treats catalog as optional
- Target configuration supports branch defaulting to tenant_id
- Enhanced metadata propagation to S3 objects (governance, lineage, file metrics)

### Fixed
- PyIceberg REST catalog compatibility issues with Nessie documented
- State directory initialization for new tenants
- Error handling for missing optional fields in records

## [1.0.0] - 2024-11-01

### Added - M1.1: Core Framework

#### Configuration Architecture
- **Decoupled configuration model** with connectors, assets, and jobs
- `SourceConnectorRecipe`: Reusable source connector definitions
- `TargetConnectorRecipe`: Reusable target connector definitions
- `AssetDefinition`: ODCS v3.0.2 compliant schema definitions
- `JobConfig`: Tenant-specific job configurations with flat source/target structure
- Configuration loading from YAML files
- Environment variable expansion in configurations

#### Validation System
- **ConnectorValidator** for registry-based validation
- Mode restrictions (cloud vs self-hosted)
- Incremental strategy validation
- Connector type validation
- **Schema validation** against ODCS v3.0.2 standard
- Asset definition presence validation
- Environment variable validation

#### Observability Foundation
- **Structured JSON logging** with secret redaction
- Tenant tagging for multi-tenant isolation
- Event-based logging with `event_type` field
- Configurable log levels and output formats

#### Secrets Management
- **Secrets loading** from filesystem storage
- Support for JSON, .env, and plain text formats
- Tenant-based directory structure
- Environment variable expansion in secrets
- Graceful handling of missing secrets

#### Infrastructure Validation
- **Connectivity checks** for Nessie catalog
- S3/MinIO endpoint validation
- Database port validation
- Graceful failure handling with warnings

#### State Management
- **IncrementalStateManager** for tracking sync state
- File-based state storage (JSON)
- File modified time tracking
- Lookback days support
- State directory initialization

#### Markdown-KV Storage Support
- **Three storage patterns**:
  - STRING storage (Markdown-KV as STRING column)
  - Raw file storage (direct S3/MinIO storage)
  - Structured storage (row-per-KV, document-level, hybrid)
- Parser and transformer implementation
- Asset definitions for structured patterns
- Source connector for Markdown-KV files

#### CLI & Orchestration
- **CLI commands**: `run` (oneshot) and `start` (orchestrated)
- Complete startup sequence orchestration
- Job execution framework
- Mode selection (cloud vs self-hosted)
- Secrets directory configuration

#### Testing Infrastructure
- **Unit tests** for config, validator, and state management
- **Smoke tests** with direct CLI execution
- Test fixtures for jobs, assets, seeds, and secrets
- Industry-standard test structure with pytest

#### Documentation
- `CONFIG_REFERENCE.md`: Configuration reference guide
- `MARKDOWN_KV_STORAGE.md`: Markdown-KV storage patterns
- `RUNNER_AND_ORCHESTRATION.md`: Runner and orchestration docs
- `SCHEMA_VALIDATION.md`: Schema validation documentation
- Comprehensive README with architecture overview

#### Project Structure
- Docker build with multi-stage optimization
- Makefile for common tasks
- Registry for connector capabilities
- JSON schemas for validation (connectors, ODCS)
- Organized directory structure (connectors, assets, jobs)

### Changed
- Adopted flat `source`/`target` structure (removed `source_overrides`/`target_overrides`)
- Made metrics collection and distributed tracing optional (deferred)

### Architecture Decisions
- **Config-driven architecture**: Everything defined in YAML
- **ODCS v3.0.2 compliance**: Industry-standard schema definitions
- **Tenant isolation**: All operations tenant-scoped
- **Incremental sync support**: First-class support for state tracking
- **CLI-first testing**: Direct CLI invocation for smoke tests

## [0.1.0] - 2024-10-15

### Added
- Initial project scaffolding
- Basic Docker setup
- Repository structure
- Initial documentation

[Unreleased]: https://github.com/dativo/ingestion-platform/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/dativo/ingestion-platform/compare/v1.1.0...v1.3.0
[1.1.0]: https://github.com/dativo/ingestion-platform/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/dativo/ingestion-platform/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/dativo/ingestion-platform/releases/tag/v0.1.0
