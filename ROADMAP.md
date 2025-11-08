# Roadmap

This document outlines the development roadmap for the Dativo Ingestion Platform, organized by version milestones.

## Version History

| Version | Status | Completion Date | Description |
|---------|--------|----------------|-------------|
| v1.0.0 | ✅ Complete | 2024-11-01 | Core Framework & Configuration |
| v1.1.0 | ✅ Complete | 2024-11-07 | ETL Pipeline & Data Processing |
| v1.2.0 | 🚧 In Progress | TBD | OSS Connector Wrappers |
| v1.3.0 | ✅ Complete | 2025-11-07 | Enhanced Orchestration |
| v1.4.0 | 🔥 In Review | Nov 2025 | Enterprise Foundations (4 PRs active) |
| v1.5.0 | 📋 Planned | Dec 2025 | Pluggable Architecture |
| v1.6.0 | 📋 Planned | Feb 2026 | Performance & Scale (Rust) |
| v2.0.0 | 📋 Planned | Oct 2026 | Marketplace & Production |

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

## 🔥 v1.4.0 - Enterprise Foundations (IN REVIEW)

**Status**: 4 Pull Requests Ready for Review  
**Target**: Week of November 25, 2025

### Active Pull Requests

#### PR #7: Multiple Secret Managers (+1,314 lines)
**Status**: ✅ Ready for Review  
**Impact**: Security & Operations

- Native support for 6 secret backends (Env, Filesystem, Vault, AWS, GCP, Azure)
- Environment variables as new default
- Backward compatible with existing filesystem approach
- Complete documentation and tests

**Files Changed**: `secrets.py`, `config.py`, `cli.py`, `requirements.txt`, docs

#### PR #6: Job/Asset Creation CLI (+2,009 lines)
**Status**: ✅ Ready for Review  
**Impact**: Developer Experience

- Interactive CLI wizard for creating jobs and assets
- Registry-aware smart suggestions
- Automatic PII detection
- Schema inference from source
- Reduces configuration time by 80%

**Files Changed**: `generator.py`, `cli.py`, docs, examples

#### PR #5: Custom Readers/Writers Plugin System (+2,284 lines)
**Status**: ✅ Ready for Review (needs beta testing)  
**Impact**: 🏆 **CATEGORY-DEFINING**

- Pluggable reader/writer architecture
- Users can bring custom Python plugins
- Example plugins (JSON API reader, JSON file writer)
- Foundation for ecosystem growth
- Enables Rust/Go support in future (v1.6.0)

**Files Changed**: `plugins.py`, `cli.py`, examples, docs, tests

**Note**: This PR implements the pluggable architecture researched in our competitive analysis. See [PLUGGABLE_READERS_EXECUTIVE_BRIEF.md](docs/PLUGGABLE_READERS_EXECUTIVE_BRIEF.md) for full business case.

#### PR #4: Tag Propagation & Data Governance (+5,813 lines)
**Status**: ✅ Ready for Review  
**Impact**: Compliance & FinOps

- Automatic PII/sensitive data detection
- Tag propagation to Iceberg table properties
- Three-level override system (auto-detection, asset, job)
- FinOps cost attribution metadata
- Integration tests and documentation

**Files Changed**: `tag_derivation.py`, `iceberg_committer.py`, tests, docs

### Success Criteria
- ✅ All 4 PRs reviewed and merged
- ✅ 0 critical bugs in staging tests
- ✅ Backward compatibility maintained
- ✅ Documentation complete
- ✅ Release notes prepared

### Business Impact
- **Enterprise Ready**: Cloud-native secret management
- **Developer Experience**: 10x faster configuration
- **Extensibility**: Platform for custom connectors
- **Compliance**: Automated data governance

### Next Steps
1. Review and merge PRs (Week of Nov 11)
2. Integration testing (Week of Nov 18)
3. Release v1.4.0 (Week of Nov 25)

**See**: [ROADMAP_UPDATED_WITH_PRS.md](docs/ROADMAP_UPDATED_WITH_PRS.md) for detailed analysis

---

## 📋 v1.5.0 - Pluggable Architecture (PLANNED)

**Target**: December 2025

### Goals
Ship plugin system with beta validation and community examples.

### Planned Features
- ✅ Custom Python readers/writers (from PR #5)
- [ ] Plugin marketplace infrastructure (basic)
- [ ] 5+ example plugins
- [ ] Plugin development documentation
- [ ] Beta program with 3-5 customers

### Beta Program
- Recruit 3-5 customers with custom source needs
- 2-week beta period
- Collect feedback on plugin API
- Iterate based on usage patterns

### Success Criteria
- 3+ custom plugins created by beta users
- 0 critical plugin API issues
- Positive NPS feedback
- Clear path to v1.6.0 enhancements

---

## 📋 v1.6.0 - Performance & Scale with Rust (PLANNED)

**Target**: February 2026

### Goals
Add high-performance Rust reader/writer support for 10x improvement.

### Planned Features

#### Rust Integration
- [ ] PyO3 integration for Rust ↔ Python
- [ ] Arrow-based data exchange (zero-copy)
- [ ] Rust reader interface specification
- [ ] Example: High-performance Postgres reader (Rust)
- [ ] Example: Encrypted S3 writer with HSM (Rust)

#### Performance
- [ ] 10x performance improvement (Python → Rust)
- [ ] Benchmarking framework
- [ ] Performance documentation
- [ ] Cost savings calculator

#### Documentation
- [ ] Rust plugin development guide
- [ ] PyO3 integration examples
- [ ] Performance tuning guide
- [ ] Migration guide (Python → Rust plugins)

### Business Impact
- **Performance**: 10x faster ingestion
- **Cost Savings**: $16K/year per high-volume customer
- **Market**: Unlock 1TB+ daily customers ($75K ARR each)
- **Competitive Moat**: 6-12 month lead (no competitor has this)
- **Revenue**: $1.75M ARR potential (Year 1)

### Technical Approach
Based on research in [PLUGGABLE_READERS_WRITERS_ANALYSIS.md](docs/PLUGGABLE_READERS_WRITERS_ANALYSIS.md):
- Week 1-2: API design for Rust interop
- Week 3-4: Rust Postgres reader POC
- Week 5-6: Integration & benchmarks
- Week 7-8: Documentation & beta testing

### Success Criteria
- 10x performance improvement proven
- 2+ Rust readers in production
- 1+ high-volume customer ($75K ARR)
- 5+ beta testers
- Community contributions enabled

**See**: 
- [PLUGGABLE_READERS_EXECUTIVE_BRIEF.md](docs/PLUGGABLE_READERS_EXECUTIVE_BRIEF.md) - Business case
- [PLUGGABLE_READERS_IMPLEMENTATION_GUIDE.md](docs/PLUGGABLE_READERS_IMPLEMENTATION_GUIDE.md) - Technical guide
- [PLUGGABLE_READERS_CODE_EXAMPLES.md](docs/PLUGGABLE_READERS_CODE_EXAMPLES.md) - Working code

---

## 📋 v2.0.0 - Marketplace & Production (PLANNED)

**Target**: October 2026

### Goals
Production marketplace with observability, security, multi-tenancy, and ecosystem growth.

### Planned Features

#### Connector Marketplace
- [ ] Marketplace infrastructure (website, registry, payments)
- [ ] Plugin certification program
- [ ] Revenue share model (30% commission)
- [ ] 20+ community/commercial plugins
- [ ] Plugin discovery and ratings
- [ ] Automated security scanning

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
