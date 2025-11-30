# Documentation Index

Welcome to the Dativo Ingestion Platform documentation. This index will help you find the right documentation for your needs.

## Getting Started

### For New Users

Start here if you're new to Dativo:

1. **[QUICKSTART.md](../QUICKSTART.md)** - Get up and running in 5 minutes
   - One-command setup
   - Run your first job
   - Understand the basics

2. **[SETUP_AND_TESTING.md](SETUP_AND_TESTING.md)** - Comprehensive setup guide
   - Prerequisites and dependencies
   - Local development environment
   - Docker deployment
   - Running tests

3. **[Main README](../README.md)** - Project overview, architecture, and quick reference

### Who Should Read What?

| I want to...                          | Read this                                |
|---------------------------------------|------------------------------------------|
| Get started quickly                   | [QUICKSTART.md](../QUICKSTART.md)       |
| Understand the architecture           | [Main README](../README.md#architecture) |
| Set up a production deployment        | [SETUP_AND_TESTING.md](SETUP_AND_TESTING.md) |
| Configure jobs and connectors         | [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) |
| Build custom plugins                  | [CUSTOM_PLUGINS.md](CUSTOM_PLUGINS.md)   |
| Manage secrets securely               | [SECRET_MANAGEMENT.md](SECRET_MANAGEMENT.md) |
| Integrate with a data catalog         | [CATALOG_INTEGRATION.md](CATALOG_INTEGRATION.md) |
| Understand Markdown-KV storage        | [MARKDOWN_KV_STORAGE.md](MARKDOWN_KV_STORAGE.md) |

## Configuration

### Core Configuration

- **[CONFIG_REFERENCE.md](CONFIG_REFERENCE.md)** - Complete configuration reference
  - Job configuration structure
  - Connector definitions
  - Asset schemas (ODCS v3.0.2)
  - Path conventions (local vs Docker)
  - Environment variable expansion

- **[MINIMAL_ASSET_EXAMPLE.md](MINIMAL_ASSET_EXAMPLE.md)** - Minimal asset definition example
  - Simplest possible asset
  - Required vs optional fields

### Secret Management

- **[SECRET_MANAGEMENT.md](SECRET_MANAGEMENT.md)** - Secret backend configuration
  - Environment variables
  - Filesystem (Docker volumes)
  - HashiCorp Vault
  - AWS Secrets Manager
  - GCP Secret Manager
  - Examples for each backend

## Development

### Custom Plugins

- **[CUSTOM_PLUGINS.md](CUSTOM_PLUGINS.md)** - Comprehensive plugin development guide
  - Python plugins (easy to develop)
  - Rust plugins (maximum performance)
  - Plugin API reference
  - Testing plugins
  - Performance benchmarks

- **[PLUGIN_DECISION_TREE.md](PLUGIN_DECISION_TREE.md)** - When to use connectors vs plugins
  - Decision framework
  - Use case examples
  - Performance considerations

- **[PLUGIN_SANDBOXING.md](PLUGIN_SANDBOXING.md)** - Plugin security guide
  - Docker-based sandboxing
  - Resource limits
  - Network isolation
  - Seccomp profiles
  - Cloud mode vs self-hosted mode

### Connector Development

- **[CONNECTOR_DEVELOPMENT.md](CONNECTOR_DEVELOPMENT.md)** - Building new connectors *(Planned)*
  - Connector architecture
  - Directory layout
  - Registry integration
  - Testing connectors

## Data Processing

### Execution Flow

- **[INGESTION_EXECUTION.md](INGESTION_EXECUTION.md)** - Detailed execution flow
  - Extract → Validate → Write → Commit → State
  - Error handling
  - Retry logic
  - State management

### Schema Validation

- **[SCHEMA_VALIDATION.md](SCHEMA_VALIDATION.md)** - Schema validation guide
  - ODCS v3.0.2 compliance
  - Strict vs warn modes
  - Type validation and coercion
  - Required field enforcement
  - Error reporting

### Data Formats

- **[MARKDOWN_KV_STORAGE.md](MARKDOWN_KV_STORAGE.md)** - Markdown-KV storage patterns
  - STRING storage (single column)
  - Raw file storage (direct S3/MinIO)
  - Structured storage (row-per-KV, document-level, hybrid)
  - Use cases for LLM/RAG pipelines

## Integration

### Data Catalogs

- **[CATALOG_INTEGRATION.md](CATALOG_INTEGRATION.md)** - Data catalog integration
  - OpenMetadata
  - AWS Glue
  - Databricks Unity Catalog
  - Nessie
  - Lineage tracking
  - Metadata management

- **[CATALOG_LIMITATIONS.md](CATALOG_LIMITATIONS.md)** - PyIceberg/Nessie compatibility notes
  - Known issues
  - Workarounds
  - When to use catalog vs direct S3 writes

### Orchestration

- **[RUNNER_AND_ORCHESTRATION.md](RUNNER_AND_ORCHESTRATION.md)** - Runner and orchestration
  - CLI runner (`dativo run`)
  - Dagster orchestration (`dativo start orchestrated`)
  - Scheduling (cron, interval)
  - Retry policies
  - Observability (tags, metadata)

## Deployment

### Docker

- **[Main README - Docker Deployment](../README.md#docker-deployment)** - Docker setup
  - Building images
  - Volume mounts
  - Environment variables
  - Oneshot vs orchestrated mode

### Mount Points

- **[MOUNT_POINTS_SUMMARY.md](../MOUNT_POINTS_SUMMARY.md)** - Docker mount points reference
  - Required vs optional mounts
  - Read-only vs read-write
  - Path conventions

## Testing

- **[tests/README.md](../tests/README.md)** - Complete testing guide
  - Unit tests
  - Integration tests
  - Smoke tests
  - Running specific test suites
  - Writing new tests

## Implementation Details

- **[IMPLEMENTATION_SUMMARY.md](../IMPLEMENTATION_SUMMARY.md)** - Technical implementation summary
  - Component architecture
  - Design decisions
  - Technical stack

## Examples

### Example Jobs

Located in `examples/jobs/`:
- **[csv_to_iceberg_with_catalog.yaml](../examples/jobs/csv_to_iceberg_with_catalog.yaml)** - CSV ingestion with catalog
- **[custom_plugin_example.yaml](../examples/jobs/custom_plugin_example.yaml)** - Python plugin example
- **[rust_plugin_example_full.yaml](../examples/jobs/rust_plugin_example_full.yaml)** - Full Rust plugin pipeline
- **[rust_plugin_example_mixed.yaml](../examples/jobs/rust_plugin_example_mixed.yaml)** - Mixed Python/Rust pipeline

### Example Plugins

Located in `examples/plugins/`:
- **[Python Plugins](../examples/plugins/)** - JSON API reader, JSON file writer
- **[Rust Plugins](../examples/plugins/rust/)** - High-performance CSV reader, Parquet writer
- **[Plugin READMEs](../examples/plugins/README.md)** - Usage examples and benchmarks

## Contributing

- **[.github/CONTRIBUTING.md](../.github/CONTRIBUTING.md)** - Contribution guide
  - Development setup
  - Code style and tools
  - Testing requirements
  - Pull request process
  - Code of conduct

## Changelog and Roadmap

- **[CHANGELOG.md](../CHANGELOG.md)** - Version history and release notes
- **[ROADMAP.md](../ROADMAP.md)** - Upcoming features and connectors *(if exists)*

## Support

### Getting Help

1. **Check the documentation** - Most common questions are answered here
2. **Search existing issues** - Someone may have asked the same question
3. **Review examples** - See working examples in `examples/` directory
4. **Ask in discussions** - GitHub Discussions for general questions
5. **Open an issue** - For bug reports or feature requests

### Common Issues

| Issue                                  | Documentation                           |
|----------------------------------------|-----------------------------------------|
| Job fails with "connection refused"    | [SETUP_AND_TESTING.md](SETUP_AND_TESTING.md) - Check infrastructure |
| Schema validation errors               | [SCHEMA_VALIDATION.md](SCHEMA_VALIDATION.md) |
| Secret not found errors                | [SECRET_MANAGEMENT.md](SECRET_MANAGEMENT.md) |
| Plugin loading failures                | [CUSTOM_PLUGINS.md](CUSTOM_PLUGINS.md) |
| Iceberg catalog issues                 | [CATALOG_LIMITATIONS.md](CATALOG_LIMITATIONS.md) |
| Docker volume mount issues             | [MOUNT_POINTS_SUMMARY.md](../MOUNT_POINTS_SUMMARY.md) |

## Quick Reference

### Command Cheat Sheet

```bash
# Run a single job
dativo run --config jobs/tenant/job.yaml --mode self_hosted

# Run all jobs in a directory
dativo run --job-dir jobs/tenant --secret-manager filesystem --secrets-dir secrets

# Check connection without running
dativo check --config jobs/tenant/job.yaml --verbose

# Discover available streams
dativo discover --config jobs/tenant/job.yaml --verbose

# Start Dagster orchestrator
dativo start orchestrated --runner-config configs/runner.yaml

# Show version
dativo --version

# Show help
dativo --help
```

### File Structure Quick Reference

```
/workspace/
├── connectors/          # Connector definitions (tenant-agnostic)
├── assets/              # Asset schemas (ODCS v3.0.2)
│   └── {source}/v{version}/
├── jobs/                # Job configs (tenant-specific)
│   └── {tenant_id}/
├── configs/             # Runner configs
├── registry/            # Connector registry
├── secrets/             # Filesystem secrets (optional)
│   └── {tenant_id}/
├── state/               # Incremental sync state
│   └── {tenant_id}/
├── examples/            # Example jobs and plugins
├── docs/                # Documentation (you are here)
├── tests/               # Test suite
└── src/dativo_ingest/   # Source code
```

---

**Can't find what you're looking for?** Open an issue or check [CONTRIBUTING.md](../.github/CONTRIBUTING.md#getting-help).
