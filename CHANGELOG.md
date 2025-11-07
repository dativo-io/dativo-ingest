# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- OSS connector wrappers (Stripe, HubSpot, Google Drive, Google Sheets, Postgres, MySQL)
- Enhanced state tracking with cursor-based incremental syncs
- Dagster schedule integration with retry policies
- Per-connector error handling and rate limiting

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

[Unreleased]: https://github.com/dativo/ingestion-platform/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/dativo/ingestion-platform/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/dativo/ingestion-platform/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/dativo/ingestion-platform/releases/tag/v0.1.0
