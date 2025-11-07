# Roadmap

This document outlines the development roadmap for the Dativo Ingestion Platform, organized by version milestones.

## Version History

| Version | Status | Completion Date | Description |
|---------|--------|----------------|-------------|
| v1.0.0 | ✅ Complete | 2024-11-01 | Core Framework & Configuration |
| v1.1.0 | ✅ Complete | 2024-11-07 | ETL Pipeline & Data Processing |
| v1.2.0 | 🚧 In Progress | TBD | OSS Connector Wrappers |
| v1.3.0 | 📋 Planned | TBD | Enhanced Orchestration |
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
- [ ] **PostgreSQL Connector** (self-hosted only)
  - Full table and incremental sync
  - Query-based extraction
  - Connection pooling
  - Configurable batch sizes
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

## 📋 v1.3.0 - Enhanced Orchestration (PLANNED)

**Target**: Q1 2025

### Goals
Enhance Dagster orchestration with schedule management, retry policies, and improved observability.

### Planned Features

#### Dagster Integration
- [ ] Map job configurations to Dagster schedules
- [ ] Cron and interval-based scheduling
- [ ] Exit code mapping to retry policies
- [ ] Tenant-level schedule isolation
- [ ] Configurable retry attempts and backoff
- [ ] Retryable error classification

#### Schedule Management
- [ ] Dynamic schedule registration from `runner.yaml`
- [ ] Schedule enable/disable without deployment
- [ ] Schedule history and audit logs
- [ ] Tenant-specific scheduling constraints
- [ ] Timezone-aware scheduling

#### Retry & Recovery
- [ ] Intelligent retry with exponential backoff
- [ ] Partial success handling (exit code 1)
- [ ] Failed record tracking and reprocessing
- [ ] Manual retry triggers via Dagster UI
- [ ] Retry budget management per tenant

#### Observability Enhancements
- [ ] Metrics collection (extraction rate, file sizes, API calls)
- [ ] Distributed tracing with OpenTelemetry
- [ ] Job duration tracking
- [ ] Cost tracking (API calls, storage, compute)
- [ ] Dagster UI integration for job monitoring

#### Metadata & Lineage
- [ ] Enhanced metadata emission (CPU time, API calls, tags)
- [ ] Data lineage tracking (source → target)
- [ ] Schema evolution tracking
- [ ] Governance metadata propagation
- [ ] Business metadata support

### Success Criteria
- Dagster schedules working for all connectors
- Retry policies functioning correctly
- Metrics and tracing operational
- Tenant isolation maintained
- Cost tracking accurate

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

## Contributing

We welcome contributions! If you'd like to contribute to any of the planned features:

1. Check the issue tracker for the version milestone
2. Comment on the issue to express interest
3. Review the handoff documentation for context
4. Submit a PR with tests and documentation

## Feedback

Have suggestions for the roadmap? Please open an issue with:
- **Feature description**: What problem does it solve?
- **Use case**: How would you use it?
- **Priority**: Why is it important?
- **Target version**: Which version should include it?

---

**Last Updated**: 2024-11-07
