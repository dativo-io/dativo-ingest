# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.1] - 2025-12-02

### Changed
- **Major CLI Refactoring**: Extracted CLI functionality into focused modules for better maintainability
  - `cli.py` reduced from 2,472 lines to 561 lines (77% reduction)
  - Created `job_executor.py` - JobExecutor class encapsulating complete ETL pipeline
  - Created `cli_commands.py` - ConnectionChecker & DiscoveryService classes
  - Created `startup.py` - Startup sequence for batch job execution
  - Created `connectors/factory.py` - ExtractorFactory following existing factory pattern
  - Created `utils.py` - Environment variable expansion utilities
  - Extended existing modules: `secrets/__init__.py`, `plugins.py`, `validator.py`
  - Improved testability and separation of concerns
  - All functionality preserved with backward compatibility maintained

### Fixed
- Fixed temp file resource leaks in Airbyte container execution
- Fixed S3 connection check to support AWS default credential chain
- Fixed incremental.enabled field not being read from job config
- Fixed inconsistent Stripe discover fallback streams
- Fixed missing flush/fsync in check_connection method

## [0.3.0] - 2025-12-01

### Added
- **Unified Incremental Strategy Framework**: Comprehensive incremental sync support
  - Cursor-based incremental sync for databases and APIs
  - File-based incremental sync for CSV and Google Sheets
  - Timestamp-based incremental sync
  - State persistence and recovery
- **Stripe Incremental Strategies**: Full incremental sync support for Stripe API
  - Automatic cursor tracking
  - Support for all Stripe object types
  - Airbyte data type mapping
- **ODCS v3.0.2 Compliance**: Converted all asset examples to flat ODCS v3.0.2 format
- **S3 Flat Structure Support**: Support for flat bucket structure configuration
  - Fallback to flat structure when domain not specified
  - Improved S3 path construction with tenant_id support
- **Environment Variable Expansion**: Enhanced `${VAR:-default}` syntax support
  - Embedded variable expansion
  - Default value fallbacks

### Fixed
- Fixed infinite reprocessing loop for empty files/spreadsheets with file-based incremental strategies
- Fixed S3 bucket expansion and removed unused prefix field
- Fixed CSV incremental sync documentation and added configuration safeguards
- Fixed asset fixture format to support flat ODCS structure

## [0.2.0] - 2025-11-30

### Added
- **Plugin Sandboxing**: Docker-based sandboxing for custom Python and Rust plugins
  - Resource limits (CPU, memory)
  - Network isolation
  - Seccomp profiles for security
  - Automatic sandboxing in cloud mode
  - Configurable sandbox settings via `plugins.sandbox` in job configuration
  - Rust plugin runner container for sandboxed Rust plugin execution
  - Comprehensive unit, integration, and performance tests
- **Connection Testing**: `check_connection()` method in BaseReader/BaseWriter
  - CLI command: `dativo check --config job.yaml [--json] [--verbose]`
  - Validates credentials before job execution
  - Supports both custom plugins and built-in connectors
  - Typed return objects: `ConnectionTestResult` with success, message, error_code, and details
  - JSON and verbose output options for better integration
- **Discovery Interface**: `discover()` method for available tables/streams
  - CLI command: `dativo discover --config job.yaml [--json] [--verbose]`
  - Typed return objects: `DiscoveryResult` with objects list and metadata
  - Returns list of available data sources with schema information
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

### Changed
- Updated `SourceConfig` to include optional `custom_reader` field
- Updated `TargetConfig` to include optional `custom_writer` field
- Enhanced CLI to dynamically load and instantiate Python and Rust plugins
- Updated `PluginLoader` to detect plugin type from file extension
- Enhanced README with Python and Rust plugin examples
- Added performance comparison data for Rust plugins
- Disabled incremental state by default with improved logging

### Fixed
- Fixed Rust sandboxed wrapper to actually execute plugin methods
- Fixed C string pointer type in Rust plugin runner
- Fixed abstract class detection in sandbox plugin selection
- Fixed sandbox to skip abstract base classes when finding plugin class
- Fixed Colima seccomp issues and improved sandbox error handling
- Fixed Docker image tag and added --pull flag for CI robustness
- Fixed incremental state default behavior

## [0.1.0] - 2025-11-26

### Added
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
  - Comprehensive documentation in `docs/CUSTOM_PUGINS.md`
  - Integration with existing ETL pipeline (custom plugins work alongside built-in extractors)
- **OSS Connector Wrappers**: Airbyte, Meltano, and Singer support
  - Docker-based connector execution
  - Catalog generation and transformation
  - Support for all Airbyte connector types
- **Dagster Orchestration**: Enhanced orchestration support
  - Tenant-level serialization
  - Schedule management
  - Asset-based job definitions
- **Catalog Integration**: Data catalog support for lineage and metadata
  - OpenMetadata integration
  - Tag propagation to Iceberg table properties
  - ODCS v3.0.2 compliance for tag propagation
- **Secret Management**: Pluggable secret managers
  - Environment variable secret manager (default)
  - Filesystem secret manager (legacy)
  - HashiCorp Vault integration
  - AWS Secrets Manager integration
  - GCP Secret Manager integration
  - Tenant-isolated secret loading
- **Enhanced Documentation**:
  - `docs/PLUGIN_SANDBOXING.md` - Security guide for plugin sandboxing
  - `docs/CONNECTOR_VS_PLUGIN_DECISION_TREE.md` - Decision tree for choosing connectors vs plugins
  - Example plugins: `examples/plugins/json_api_reader.py` and `examples/plugins/json_file_writer.py`
  - Comprehensive testing guides and playbooks
- **Module Exports**: 
  - Exported plugin classes (`BaseReader`, `BaseWriter`, `ConnectionTestResult`, `DiscoveryResult`) from main module
  - Exported error classes and utility functions for clean imports
  - Added `__all__` for explicit API surface

### Changed
- Enhanced CLI to support multiple secret manager backends
- Updated configuration schema to support plugin sandbox settings
- Improved error messages and logging throughout

## [0.0.1] - 2024-11-01

### Added
- **Core Framework**: Initial release
  - Config-driven architecture (connectors, assets, jobs)
  - ODCS v3.0.2 compliant asset definitions
  - Registry-based connector validation
  - Structured logging with secret redaction
  - Secrets management with tenant isolation
  - Infrastructure validation (Nessie, S3, databases)
  - Incremental state management
  - Markdown-KV storage support (3 patterns: string, structured, raw_file)
  - CLI with oneshot and orchestrated modes
  - Testing infrastructure (unit + smoke tests)
- **Built-in Connectors**:
  - Stripe API connector
  - HubSpot API connector
  - PostgreSQL database connector
  - MySQL database connector
  - CSV file connector
  - Google Sheets connector
  - Google Drive CSV connector
- **Data Processing**:
  - Parquet writer with partitioning
  - Schema validation (strict/warn modes)
  - Iceberg table format support
  - Markdown-KV transformation for LLM-optimized data
- **CLI Commands**:
  - `dativo run` - Execute single job or batch jobs
  - `dativo start orchestrated` - Start Dagster orchestrator
  - `dativo check` - Test connections
  - `dativo discover` - Discover available streams

---

## Version History Notes

- **0.0.1**: Initial core framework release
- **0.1.0**: Custom plugin system and OSS connector wrappers
- **0.2.0**: Plugin sandboxing and enhanced security
- **0.3.0**: Unified incremental sync framework
- **Unreleased**: Major CLI refactoring for maintainability
