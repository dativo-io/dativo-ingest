# Roadmap

This document outlines the development roadmap for the Dativo Ingestion Platform, organized by version milestones.

## Version History

| Version | Status | Completion Date | Description |
|---------|--------|----------------|-------------|
| v1.0.0 | ✅ Complete | 2024-11-01 | Core Framework & Configuration |
| v1.1.0 | ✅ Complete | 2024-11-07 | ETL Pipeline & Data Processing |
| v1.2.0 | 🚧 In Progress | TBD | OSS Connector Wrappers |
| v1.3.0 | ✅ Complete | 2025-11-07 | Enhanced Orchestration |
| v2.0.0 | 📋 Planned | TBD | Production Features & Scale |

---

## ✅ v1.0.0 - Core Framework (COMPLETE)

**Status**: Released 2024-11-01

### Goals
Establish the foundational framework for the ingestion platform with configuration management, validation, observability, and state management.

### Key Features
- ✅ Decoupled configuration architecture (connectors, assets, jobs)
- ✅ ODCS v3.0.2 compliant asset definitions
- ✅ Registry-based connector validation
- ✅ Structured logging with secret redaction
- ✅ Secrets management with tenant isolation
- ✅ Infrastructure validation (Nessie, S3, databases)
- ✅ Incremental state management
- ✅ Markdown-KV storage support (3 patterns)
- ✅ CLI with oneshot and orchestrated modes
- ✅ Testing infrastructure (unit + smoke tests)

### Architecture Decisions
- Config-driven architecture (no hardcoded logic)
- Tenant-first isolation (state, secrets, logging)
- Flat source/target configuration structure
- CLI-first smoke testing approach
- Industry-standard test structure with pytest

### Documentation
- [MILESTONE_1_1_COMPLETE.md](docs/MILESTONE_1_1_COMPLETE.md)

---

## ✅ v1.1.0 - ETL Pipeline & Data Processing (COMPLETE)

**Status**: Released 2024-11-07

### Goals
Implement the complete Extract-Transform-Load pipeline with Parquet writing, schema validation, and Iceberg integration.

### Key Features
- ✅ Schema validator with strict/warn modes
- ✅ CSV data extractor with chunking and incremental sync
- ✅ Parquet writer with target file sizing (128-200 MB)
- ✅ Industry-standard storage paths with Hive-style partitioning
- ✅ Iceberg/Nessie integration (optional catalog)
- ✅ Complete ETL orchestration with exit codes
- ✅ Graceful degradation (S3 writes work without catalog)
- ✅ Comprehensive metadata propagation (governance, lineage, metrics)
- ✅ Local development setup (Docker Compose with MinIO + Nessie)
- ✅ GitHub Actions workflow for automated testing

### Technical Highlights
- Native Python CSV extraction (pandas-based)
- PyArrow Parquet writing with snappy compression
- PyIceberg catalog integration (with known Nessie limitations)
- S3 metadata tagging for governance and compliance
- Configurable validation modes and file sizing

### Documentation
- [MILESTONE_1_2_COMPLETE.md](docs/MILESTONE_1_2_COMPLETE.md)
- [INGESTION_EXECUTION.md](docs/INGESTION_EXECUTION.md)
- [CATALOG_LIMITATIONS.md](docs/CATALOG_LIMITATIONS.md)
- [SETUP_AND_TESTING.md](docs/SETUP_AND_TESTING.md)

---

## 🚧 v1.2.0 - OSS Connector Wrappers (IN PROGRESS)

**Status**: In Development

**Target**: Q4 2024

### Goals
Expand source connector support beyond CSV to include major SaaS APIs and databases using open-source connector wrappers.

### Planned Features

#### Source Connectors
- [ ] **Stripe Connector**
  - Customers, charges, invoices, subscriptions
  - Timestamp-based incremental sync
  - Rate limiting and retry handling
  - Native Python implementation using Stripe SDK
- [ ] **HubSpot Connector**
  - Contacts, deals, companies, tickets
  - Cursor-based incremental sync
  - Pagination and rate limiting
  - Native Python implementation using HubSpot API client
- [ ] **Google Drive CSV Connector**
  - File discovery and listing
  - Modified time tracking
  - OAuth2 authentication
  - Incremental sync by file modification
- [ ] **Google Sheets Connector**
  - Spreadsheet data extraction
  - Range-based reading
  - OAuth2 authentication
  - Change detection
- [x] **PostgreSQL Connector** (self-hosted only) ✅ **COMPLETE in v1.3.0**
  - Full table and incremental sync
  - Query-based extraction
  - Connection pooling
  - Configurable batch sizes
  - Cursor-based incremental sync with state management
- [ ] **MySQL Connector** (self-hosted only)
  - Full table and incremental sync
  - Query-based extraction
  - Connection pooling
  - Configurable batch sizes

#### State Management Enhancements
- [ ] Cursor-based incremental sync (timestamp, ID)
- [ ] Per-object state tracking with cursor fields
- [ ] Error state tracking for retry logic
- [ ] State migration utilities

#### Error Handling
- [ ] Per-connector error classification
- [ ] Transient vs permanent error handling
- [ ] Rate limiting with exponential backoff
- [ ] API quota management
- [ ] Connection timeout handling

#### Testing
- [ ] Unit tests for each connector
- [ ] Mock API responses for testing
- [ ] Integration tests with test accounts
- [ ] Smoke tests for end-to-end validation

### Implementation Approach
1. **Native Python** (preferred): Direct API calls using official SDKs
2. **Airbyte Wrappers** (fallback): Docker containers for complex sources
3. **Singer Taps** (legacy): For existing Singer ecosystem compatibility

### Success Criteria
- All 6 connectors functional with incremental sync
- State persistence working across runs
- Rate limiting handled gracefully
- Unit and integration tests passing
- Documentation for each connector

### Documentation
- [MILESTONE_1_3_HANDOFF.md](docs/MILESTONE_1_3_HANDOFF.md)

---

## ✅ v1.3.0 - Enhanced Orchestration (COMPLETE)

**Status**: Released 2025-11-07

### Goals
Enhance Dagster orchestration with schedule management, retry policies, and improved observability.

### Key Features

#### Dagster Integration
- ✅ Map job configurations to Dagster schedules
- ✅ Cron and interval-based scheduling
- ✅ Exit code mapping to retry policies
- ✅ Tenant-level schedule isolation
- ✅ Configurable retry attempts and backoff
- ✅ Retryable error classification

#### Schedule Management
- ✅ Dynamic schedule registration from `runner.yaml`
- ✅ Schedule enable/disable without deployment
- ✅ Tenant-specific scheduling constraints
- ✅ Timezone-aware scheduling
- ✅ Max concurrent runs control
- ✅ Custom schedule tags

#### Retry & Recovery
- ✅ Intelligent retry with exponential backoff
- ✅ Partial success handling (exit code 1)
- ✅ Custom retry logic with Dagster integration
- ✅ Retry state tracking and recovery
- ✅ Retryable exit codes and error pattern matching

#### Observability Enhancements
- ✅ Metrics collection framework
- ✅ Distributed tracing with OpenTelemetry
- ✅ Job duration tracking
- ✅ Enhanced asset tags for Dagster UI (tenant_id, connector_type, job_name)
- ✅ Job execution metadata propagation

#### Unified Connector Architecture
- ✅ Bidirectional connector support
- ✅ Unified `ConnectorRecipe` model
- ✅ Connector roles metadata (`[source]`, `[target]`, `[source, target]`)
- ✅ Registry schema v3 with roles support
- ✅ All connectors migrated to unified structure

#### Postgres Connector
- ✅ Native Postgres extractor implementation
- ✅ Full table and incremental sync support
- ✅ Cursor-based incremental sync
- ✅ Environment variable expansion for connection parameters
- ✅ Batch processing with state management

#### Markdown-KV Transformations
- ✅ Postgres to Markdown-KV transformation pipeline
- ✅ String mode (entire document as single column)
- ✅ Structured mode (parsed into key-value rows)
- ✅ Integration with Parquet writer for Iceberg tables

#### Testing & CI/CD
- ✅ Comprehensive GitHub Actions workflows (unit tests, smoke tests, schema validation)
- ✅ Postgres, MinIO, and Nessie service integration
- ✅ AdventureWorks test data loading
- ✅ Expanded smoke test suite

### Success Criteria
- ✅ Dagster schedules working for all connectors
- ✅ Retry policies functioning correctly
- ✅ Metrics and tracing framework operational
- ✅ Tenant isolation maintained
- ✅ Postgres connector fully functional
- ✅ Markdown-KV transformations working
- ✅ CI/CD pipelines operational

---

## 📋 v2.0.0 - Production Features & Scale (PLANNED)

**Target**: Q2 2025

### Goals
Production-ready features including observability, security, multi-tenancy, and performance optimizations.

### Planned Features

#### Observability & Monitoring
- [ ] Prometheus metrics export
- [ ] Grafana dashboard templates
- [ ] Alert definitions for common failures
- [ ] SLA monitoring and reporting
- [ ] Cost attribution by tenant

#### Security & Compliance
- [ ] Secret rotation support
- [ ] Encryption at rest for state files
- [ ] Audit logging for all operations
- [ ] Role-based access control (RBAC)
- [ ] Compliance reporting (GDPR, CCPA)

#### Multi-Tenancy
- [ ] Tenant resource quotas
- [ ] Tenant-level rate limiting
- [ ] Tenant isolation guarantees
- [ ] Tenant billing and cost allocation
- [ ] Tenant-specific configurations

#### Performance & Scale
- [ ] Parallel job execution within tenants
- [ ] Optimized Parquet writing (columnar compression)
- [ ] Connection pooling for databases
- [ ] Caching for frequently accessed data
- [ ] Horizontal scaling support

#### Data Quality
- [ ] Data quality rules engine
- [ ] Anomaly detection
- [ ] Schema drift detection
- [ ] Data profiling and statistics
- [ ] Quality score tracking

#### Developer Experience
- [ ] CLI improvements (better error messages, progress bars)
- [ ] Job templates and generators
- [ ] Configuration validation in IDE
- [ ] Local testing utilities
- [ ] Debugging tools

### Success Criteria
- Sub-minute job startup time
- 99.9% uptime for orchestrator
- Complete observability stack
- Security audit passing
- Multi-tenant isolation verified

---

## 📋 Future Considerations (v2.1+)

### Additional Connectors
- Salesforce
- Zendesk
- MongoDB
- Snowflake
- BigQuery
- Azure Blob Storage
- Kafka/Event Streams

### Advanced Features
- Schema evolution handling
- Data masking and anonymization
- Change Data Capture (CDC)
- Real-time streaming ingestion
- Custom transformation logic
- Webhook triggers
- Event-driven orchestration

### Cloud Integrations
- AWS Glue Data Catalog integration
- Azure Data Factory integration
- GCP Dataflow integration
- Managed Airflow/Dagster support

### AI/ML Features
- Intelligent schema inference
- Anomaly detection using ML
- Predictive resource allocation
- Auto-tuning of batch sizes and parallelism

---

## 📋 Detailed Technical Roadmap

For a comprehensive 12-month technical roadmap with sprint-level details, see:
- **[Roadmap Executive Summary](docs/ROADMAP_EXECUTIVE_SUMMARY.md)** - Strategic vision, business model, go-to-market strategy
- **[Visual Roadmap](docs/ROADMAP_VISUAL.md)** - Visual timeline, milestones, and metrics
- **[12-Month Technical Roadmap](docs/TECHNICAL_ROADMAP_12M.md)** - Detailed sprint planning, technical specifications, and architecture evolution
- **[MVP Execution Plan](docs/MVP_EXECUTION_PLAN.md)** - Week-by-week breakdown for next 12 weeks
- **[Sprint Planning Template](docs/SPRINT_PLANNING_TEMPLATE.md)** - Template for sprint execution

### Key Highlights from Technical Roadmap

**Q1 (Months 1-3): MVP Completion**
- Sprint 1-2: Stripe & HubSpot connectors
- Sprint 3-4: Error handling framework & MySQL connector
- Sprint 5-6: Google Drive/Sheets connectors & observability

**Q2 (Months 4-6): Production Hardening**
- Security & compliance (SOC2 ready)
- Additional connectors (Salesforce, Snowflake, MongoDB)
- Performance optimization (parallel processing)
- v2.0.0 release

**Q3 (Months 7-9): Scale & Performance**
- Data quality framework
- CDC support
- SSO/RBAC
- Multi-region support

**Q4 (Months 10-12): Enterprise Features**
- Feature store integration
- Event-driven orchestration
- Cost optimization
- v2.5.0 release

---

## Contributing

We welcome contributions! If you'd like to contribute to any of the planned features:

1. Check the issue tracker for the version milestone
2. Comment on the issue to express interest
3. Review the handoff documentation for context
4. Review the [Technical Roadmap](docs/TECHNICAL_ROADMAP_12M.md) for implementation details
5. Submit a PR with tests and documentation

## Feedback

Have suggestions for the roadmap? Please open an issue with:
- **Feature description**: What problem does it solve?
- **Use case**: How would you use it?
- **Priority**: Why is it important?
- **Target version**: Which version should include it?

---

**Last Updated**: 2025-11-07
